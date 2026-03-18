"""CDP backend -- connect to an already-running Chrome via DevTools Protocol.

使用场景：Chrome 已登录飞书/内网/社交网站，通过 CDP 复用登录态抓取需要认证的页面。

启动 Chrome 时加参数：
    /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
        --remote-debugging-port=9222 \\
        --user-data-dir=$HOME/.chrome-cdp

然后 mfetch 自动通过 CDP 连接，复用所有 cookies/localStorage/session。

抓取策略（v2 — optimized for SPA/social feeds）：
1. 导航 + 智能等待（selector-based, not blind networkidle）
2. 对 infinite-feed 站点自动滚动加载更多内容
3. page.content() + html2text 输出结构化 Markdown（保留链接）
4. API 响应拦截作为补充数据源（过滤噪音 URL/image blob）
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

from maestro_fetch.core.errors import FetchError

log = logging.getLogger(__name__)

_DEFAULT_CDP_ENDPOINT = "http://127.0.0.1:9222"

# API 响应最小长度
_MIN_API_BODY_LEN = 1000

# URL patterns that indicate non-content API responses (avatars, tracking, etc.)
_NOISE_URL_PATTERNS = re.compile(
    r"(googleusercontent\.com|"
    r"pbs\.twimg\.com/profile|"
    r"\.png|\.jpg|\.gif|\.svg|\.ico|\.woff|"
    r"analytics|telemetry|tracking|beacon|pixel|"
    r"favicon|manifest\.json|service-worker|"
    r"fonts\.|gstatic\.com|"
    r"accounts\.google\.com|"
    r"sentry\.io|bugsnag|datadog)",
    re.IGNORECASE,
)

# Site-specific hints for smarter waiting and content extraction
_SITE_HINTS: dict[str, dict[str, Any]] = {
    "x.com": {
        "wait_selector": "[data-testid='tweet']",
        "scroll_count": 3,
        "scroll_delay_ms": 1500,
        "content_selector": "main[role='main']",
    },
    "twitter.com": {
        "wait_selector": "[data-testid='tweet']",
        "scroll_count": 3,
        "scroll_delay_ms": 1500,
        "content_selector": "main[role='main']",
    },
    "reddit.com": {
        "wait_selector": "shreddit-post, article, [data-testid='post-container']",
        "scroll_count": 3,
        "scroll_delay_ms": 1200,
        "content_selector": "main, #main-content, [data-testid='posts-list']",
    },
    "producthunt.com": {
        # Cloudflare challenge takes ~5-8s; use generic body wait
        "wait_selector": "a[href*='/products/'], [data-test='post-item']",
        "scroll_count": 1,
        "scroll_delay_ms": 800,
        "content_selector": "main, [class*='homepage']",
    },
    "github.com": {
        "wait_selector": ".Box-row, article.Box-row, [class*='trending']",
        "scroll_count": 1,
        "scroll_delay_ms": 500,
        "content_selector": "main, .application-main",
    },
}


def _get_cdp_endpoint() -> str:
    return os.environ.get("MAESTRO_CDP_ENDPOINT", _DEFAULT_CDP_ENDPOINT)


async def _probe_cdp(endpoint: str) -> bool:
    try:
        import httpx
    except ImportError:
        return False
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            resp = await client.get(f"{endpoint}/json/version")
            return resp.status_code == 200
    except Exception:
        return False


def _playwright_importable() -> bool:
    try:
        import playwright as _pw  # noqa: F401
        _ = _pw
        return True
    except ImportError:
        return False


def _get_site_hints(url: str) -> dict[str, Any]:
    """Match URL to site-specific hints."""
    hostname = urlparse(url).hostname or ""
    for domain, hints in _SITE_HINTS.items():
        if domain in hostname:
            return hints
    return {}


def _is_noise_url(api_url: str) -> bool:
    """Filter out non-content API URLs (avatars, tracking, static assets)."""
    return bool(_NOISE_URL_PATTERNS.search(api_url))


def _extract_text_from_json(body: str) -> str | None:
    """Extract article/feed text from API JSON response.

    Looks for content-like keys first, then falls back to longest string.
    Rejects strings that look like URLs or base64 data.
    """
    try:
        obj = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return None

    # Collect candidate strings with their key context
    candidates: list[tuple[str, str]] = []  # (key_path, value)

    # Content-like key names (high priority)
    _CONTENT_KEYS = {
        "content", "body", "text", "description", "summary",
        "markdown", "html", "article", "message", "comment",
        "title", "headline", "selftext", "full_text",
    }

    def _walk(node: Any, path: str = "", depth: int = 0) -> None:
        if depth > 12:
            return
        if isinstance(node, str) and len(node) >= 100:
            # Reject URL-like or base64-like strings
            if node.startswith(("http://", "https://", "data:")):
                return
            if len(node) > 200 and re.match(r"^[A-Za-z0-9+/=\s]+$", node[:200]):
                return
            candidates.append((path, node))
        elif isinstance(node, dict):
            for k, v in node.items():
                _walk(v, f"{path}.{k}", depth + 1)
        elif isinstance(node, list):
            for i, item in enumerate(node[:100]):
                _walk(item, f"{path}[{i}]", depth + 1)

    _walk(obj)

    if not candidates:
        return None

    # Prioritize content-like keys, then by length
    def _score(item: tuple[str, str]) -> tuple[int, int]:
        path, val = item
        key = path.rsplit(".", 1)[-1].lower().strip("[]0123456789")
        is_content_key = 1 if key in _CONTENT_KEYS else 0
        return (is_content_key, len(val))

    candidates.sort(key=_score, reverse=True)
    best_path, best_val = candidates[0]

    if len(best_val) < _MIN_API_BODY_LEN:
        return None

    log.debug("CDP API: selected %s (%d chars)", best_path, len(best_val))
    return best_val


# -----------------------------------------------------------------------
# CDPBackend
# -----------------------------------------------------------------------


class CDPBackend:
    """CDP backend with optimized SPA/social feed extraction."""

    name: str = "cdp"

    def __init__(self, endpoint: str | None = None) -> None:
        self._endpoint = endpoint or _get_cdp_endpoint()

    async def is_available(self) -> bool:
        if not _playwright_importable():
            return False
        return await _probe_cdp(self._endpoint)

    async def fetch_content(self, url: str, timeout: int = 30) -> str:
        """Fetch page content via CDP with smart waiting + scroll loading.

        Strategy (v2):
        1. Navigate + smart wait (selector-based for known sites)
        2. Scroll to load infinite feed content
        3. Extract via page.content() + html2text (preserves links + structure)
        4. Supplement with API response interception for SPA data
        """
        if not _playwright_importable():
            raise FetchError("playwright is not installed")

        from playwright.async_api import async_playwright

        try:
            import html2text as _html2text
        except ImportError:
            _html2text = None  # type: ignore[assignment]

        timeout_ms = timeout * 1000
        hints = _get_site_hints(url)
        api_responses: list[tuple[str, str]] = []
        target_host = urlparse(url).hostname or ""

        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(self._endpoint)
            try:
                ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = await ctx.new_page()

                # Intercept API responses (supplementary data source)
                async def _on_response(response: Any) -> None:
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" not in ct:
                            return
                        if response.status != 200:
                            return
                        if _is_noise_url(response.url):
                            return
                        body = await response.text()
                        if len(body) >= _MIN_API_BODY_LEN:
                            api_responses.append((response.url, body))
                    except Exception:
                        pass

                page.on("response", _on_response)

                try:
                    # --- Step 1: Navigate ---
                    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

                    # --- Step 2: Smart wait ---
                    wait_sel = hints.get("wait_selector")
                    if wait_sel:
                        try:
                            await page.wait_for_selector(
                                wait_sel, timeout=8000, state="attached"
                            )
                            log.info("CDP: selector '%s' found", wait_sel)
                        except Exception:
                            log.info("CDP: selector '%s' not found, falling back to delay", wait_sel)
                            await page.wait_for_timeout(3000)
                    else:
                        # Generic: wait for networkidle with short timeout
                        try:
                            await page.wait_for_load_state("networkidle", timeout=8000)
                        except Exception:
                            await page.wait_for_timeout(2000)

                    # --- Step 3: Scroll to load more content ---
                    scroll_count = hints.get("scroll_count", 0)
                    scroll_delay = hints.get("scroll_delay_ms", 1000)
                    if scroll_count > 0:
                        for i in range(scroll_count):
                            await page.evaluate("window.scrollBy(0, window.innerHeight)")
                            await page.wait_for_timeout(scroll_delay)
                            log.debug("CDP: scroll %d/%d", i + 1, scroll_count)
                        # Scroll back to top for full content capture
                        await page.evaluate("window.scrollTo(0, 0)")
                        await page.wait_for_timeout(500)

                    # --- Step 4: Extract content ---
                    # Strategy A: Scoped content extraction (if site hint has selector)
                    content_sel = hints.get("content_selector")
                    html = ""
                    if content_sel:
                        try:
                            el = await page.query_selector(content_sel)
                            if el:
                                html = await el.inner_html()
                                log.info(
                                    "CDP: extracted %d chars from '%s'",
                                    len(html), content_sel,
                                )
                        except Exception:
                            pass

                    # Fallback to full page content
                    if len(html) < 500:
                        html = await page.content()
                        log.info("CDP: using full page.content() (%d chars)", len(html))

                    # Convert HTML to Markdown
                    if _html2text is not None:
                        converter = _html2text.HTML2Text()
                        converter.ignore_links = False
                        converter.ignore_images = True
                        converter.body_width = 0  # no line wrapping
                        converter.skip_internal_links = True
                        markdown = converter.handle(html)
                    else:
                        # Strip tags as fallback
                        markdown = re.sub(r"<[^>]+>", " ", html)
                        markdown = re.sub(r"\s+", " ", markdown).strip()

                    # --- Step 5: Supplement with API data ---
                    # If markdown is thin, try API responses
                    if len(markdown) < 2000 and api_responses:
                        same_host = [
                            (u, b) for u, b in api_responses
                            if target_host and target_host in u
                        ]
                        other = [
                            (u, b) for u, b in api_responses
                            if not (target_host and target_host in u)
                        ]
                        ranked = (
                            sorted(same_host, key=lambda x: len(x[1]), reverse=True)
                            + sorted(other, key=lambda x: len(x[1]), reverse=True)
                        )
                        for api_url, body in ranked[:10]:
                            text = _extract_text_from_json(body)
                            if text and len(text) > len(markdown):
                                short = api_url.split("?")[0][-60:]
                                log.info(
                                    "CDP: API data (%d chars) > markdown (%d), using API from %s",
                                    len(text), len(markdown), short,
                                )
                                return text

                    return markdown

                finally:
                    await page.close()
            finally:
                await browser.close()

    async def fetch_screenshot(self, url: str) -> bytes:
        if not _playwright_importable():
            raise FetchError("playwright is not installed")

        from playwright.async_api import async_playwright

        hints = _get_site_hints(url)

        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(self._endpoint)
            try:
                ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = await ctx.new_page()
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    # Smart wait
                    wait_sel = hints.get("wait_selector")
                    if wait_sel:
                        try:
                            await page.wait_for_selector(wait_sel, timeout=8000)
                        except Exception:
                            await page.wait_for_timeout(2000)
                    else:
                        await page.wait_for_timeout(2000)
                    screenshot = await page.screenshot(full_page=True)
                finally:
                    await page.close()
            finally:
                await browser.close()
        return screenshot

    async def eval_js(self, js: str) -> Any:
        """Not supported -- use session commands instead."""
        raise NotImplementedError("CDP backend does not support standalone eval_js")

    async def site_adapter(self, adapter_name: str, *args: str) -> dict:
        """Not supported."""
        _ = adapter_name, args
        raise NotImplementedError("CDP backend does not support site adapters")
