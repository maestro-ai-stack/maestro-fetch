"""WebAdapter: fetches JS-rendered web pages via Crawl4AI, outputs Markdown.

Responsibility: handle generic web URLs (HTML pages, JS-rendered SPAs).
Non-goals: PDF, spreadsheets, cloud storage, media -- those are excluded
via _NON_WEB_PATTERNS and handled by dedicated adapters.

Invariants:
- supports() returns False for URLs matching known non-web patterns
- fetch() always returns FetchResult with source_type="web"
- fetch() raises DownloadError only when crawl4ai, httpx, AND playwright-stealth all fail
- crawl4ai is tried first (handles JS-rendered SPAs); on timeout/nav error,
  falls back to httpx plain GET + html2text (handles static/government sites
  that block headless browsers); if httpx returns a WAF block page (Incapsula etc.),
  falls back to playwright-stealth (handles anti-bot protected pages)
"""
from __future__ import annotations
import re
from maestro_fetch.adapters.base import BaseAdapter
from maestro_fetch.core.config import FetchConfig
from maestro_fetch.core.result import FetchResult
from maestro_fetch.core.errors import DownloadError

_NON_WEB_PATTERNS = [
    r"dropbox\.com/",
    r"drive\.google\.com/",
    r"docs\.google\.com/",
    r"youtube\.com/watch",
    r"youtu\.be/",
    r"\.pdf(\?|$)",
    r"\.(xlsx|xls|ods|csv)(\?|$)",
]

# User-agent used for httpx fallback (static GET).
# Mimics a real browser to avoid bot-detection on government sites.
_FALLBACK_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# crawl4ai raises these exception types on navigation timeout / browser errors.
# Checked by substring on the exception class name to avoid hard import of
# playwright internals.
_CRAWL4AI_TRANSIENT_PATTERNS = (
    "timeout",
    "TimeoutError",
    "NavigationError",
    "Page.goto",
)

# Markers in response body that indicate WAF/anti-bot blocking (not real content).
_WAF_BLOCK_MARKERS = (
    "Incapsula incident ID",
    "Request unsuccessful",
    "_Incapsula_Resource",
    "visitorId",          # Cloudflare challenge
    "cf-browser-verification",
    "Enable JavaScript and cookies",
    "Just a moment",       # Cloudflare 5-second page
    "Access Denied",
)

# 登录墙标记：内容命中这些说明需要认证（CDP 可解决）
_LOGIN_WALL_MARKERS = (
    "Feishu, first choice",          # 飞书登录页（英文）
    "飞书，先进企业协作与管理平台",       # 飞书登录页（中文）
    "suite/passport/static/login",   # 飞书 passport 资源路径
    "accounts.google.com/signin",    # Google 登录
    "login.microsoftonline.com",     # Microsoft 登录
    "sso.bytedance.com",             # 字节 SSO
)


def _is_crawl4ai_transient(exc: Exception) -> bool:
    """Return True when the exception looks like a crawl4ai navigation failure."""
    msg = f"{type(exc).__name__}: {exc}".lower()
    return any(p.lower() in msg for p in _CRAWL4AI_TRANSIENT_PATTERNS)


def _is_waf_blocked(content: str) -> bool:
    """Return True when the response body looks like a WAF block page."""
    return any(marker in content for marker in _WAF_BLOCK_MARKERS)


def _is_login_wall(content: str) -> bool:
    """Return True when the content looks like a login/SSO redirect page."""
    return any(marker in content for marker in _LOGIN_WALL_MARKERS)


async def _cdp_fetch(url: str, config: FetchConfig) -> str | None:
    """尝试通过 CDP 连接已运行的 Chrome 抓取页面。

    成功返回 markdown 内容，CDP 不可用或失败返回 None。
    """
    try:
        from maestro_fetch.backends.cdp import CDPBackend
        backend = CDPBackend()
        if not await backend.is_available():
            return None
        content = await backend.fetch_content(url)
        if content and len(content) > 200 and not _is_login_wall(content):
            return content
        return None
    except Exception:
        return None


async def _playwright_stealth_fetch(url: str, config: FetchConfig) -> str:
    """Fetch url using playwright-stealth to bypass anti-bot WAFs (Incapsula, Cloudflare).

    Invariants:
    - Returns str (Markdown via html2text, or raw text fallback)
    - Raises DownloadError on browser failure or empty body
    """
    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import stealth_async
    except ImportError as exc:
        raise ImportError(
            "playwright and playwright-stealth are required: "
            "pip install playwright playwright-stealth && playwright install chromium"
        ) from exc

    try:
        import html2text as _html2text
        _h2t_available = True
    except ImportError:
        _h2t_available = False

    timeout_ms = int((config.timeout or 60) * 1000)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=_FALLBACK_UA,
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()
        await stealth_async(page)

        try:
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            # Give JS a moment to render dynamic content
            await page.wait_for_timeout(2000)
            html = await page.content()
        except Exception as exc:
            await browser.close()
            raise DownloadError(f"playwright-stealth navigation failed for {url}: {exc}") from exc

        await browser.close()

    if not html or len(html) < 200:
        raise DownloadError(f"playwright-stealth returned empty body for {url}")

    if _h2t_available:
        h = _html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        return h.handle(html)
    return re.sub(r"<[^>]+>", " ", html)


async def _httpx_fetch(url: str, config: FetchConfig) -> str:
    """Fetch url with httpx and convert HTML to Markdown via html2text.

    Invariants:
    - Always returns a str (empty on empty body)
    - Raises DownloadError on HTTP error or network failure
    """
    try:
        import httpx
    except ImportError as exc:
        raise ImportError("httpx is required for WebAdapter fallback: pip install httpx") from exc

    headers = {"User-Agent": _FALLBACK_UA}
    if config.headers:
        headers.update(config.headers)

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=config.timeout or 60,
        ) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPStatusError as exc:
        raise DownloadError(f"HTTP {exc.response.status_code} for {url}") from exc
    except Exception as exc:
        raise DownloadError(f"httpx fetch failed for {url}: {exc}") from exc

    # Convert HTML -> Markdown; fall back to raw text if html2text not installed.
    try:
        import html2text
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        return h.handle(html)
    except ImportError:
        # Strip tags manually as a last resort.
        return re.sub(r"<[^>]+>", " ", html)


class WebAdapter(BaseAdapter):
    """Fetches web pages via Crawl4AI with CDP/httpx/stealth fallback.

    Strategy:
      1. Try crawl4ai (headless browser) -- best for JS-rendered SPAs
      1.5. On login wall/WAF, try CDP (已登录 Chrome) -- best for内网/飞书
      2. Fall back to httpx plain GET (static/government sites)
      3. Fall back to playwright-stealth (anti-bot WAF bypass)
    """

    def supports(self, url: str) -> bool:
        return not any(re.search(p, url, re.IGNORECASE) for p in _NON_WEB_PATTERNS)

    async def fetch(self, url: str, config: FetchConfig) -> FetchResult:
        crawl4ai_error: Exception | None = None

        # --- Pass 1: crawl4ai (JS rendering) ---
        try:
            from crawl4ai import AsyncWebCrawler

            async with AsyncWebCrawler() as crawler:
                crawl_kwargs: dict = dict(url=url)
                if config.headers:
                    crawl_kwargs["headers"] = config.headers
                crawl_result = await crawler.arun(**crawl_kwargs)
                if crawl_result.success:
                    md = crawl_result.markdown or ""
                    if not _is_waf_blocked(md) and not _is_login_wall(md):
                        return FetchResult(
                            url=url,
                            source_type="web",
                            content=md,
                            tables=[],
                            metadata={"adapter": "crawl4ai"},
                        )
                    # WAF 或登录墙 -- 尝试 CDP 再 fallback
                    crawl4ai_error = DownloadError(
                        f"WAF/login wall detected (crawl4ai) for {url}"
                    )
                else:
                    # crawl4ai returned success=False -- treat as transient
                    crawl4ai_error = DownloadError(f"Crawl4AI failed for {url}")
        except ImportError:
            # crawl4ai not installed; skip directly to httpx fallback.
            pass
        except Exception as exc:
            if not _is_crawl4ai_transient(exc):
                # Non-transient crawl4ai error (e.g. bad URL scheme) -- re-raise.
                raise DownloadError(f"Web fetch failed for {url}: {exc}") from exc
            crawl4ai_error = exc

        # --- Pass 1.5: CDP (复用已登录 Chrome) ---
        cdp_content = await _cdp_fetch(url, config)
        if cdp_content:
            return FetchResult(
                url=url,
                source_type="web",
                content=cdp_content,
                tables=[],
                metadata={"adapter": "cdp", "crawl4ai_error": str(crawl4ai_error)},
            )

        # --- Pass 2: httpx plain GET fallback ---
        httpx_error: Exception | None = None
        try:
            content = await _httpx_fetch(url, config)
            if not _is_waf_blocked(content):
                return FetchResult(
                    url=url,
                    source_type="web",
                    content=content,
                    tables=[],
                    metadata={"adapter": "httpx", "crawl4ai_error": str(crawl4ai_error)},
                )
            # WAF block page detected -- escalate to playwright-stealth
            httpx_error = DownloadError(f"WAF block detected for {url}")
        except DownloadError as exc:
            httpx_error = exc
        except Exception as exc:
            raise DownloadError(f"Web fetch failed for {url}: {exc}") from exc

        # --- Pass 3: playwright-stealth (WAF bypass) ---
        try:
            content = await _playwright_stealth_fetch(url, config)
            return FetchResult(
                url=url,
                source_type="web",
                content=content,
                tables=[],
                metadata={
                    "adapter": "playwright-stealth",
                    "crawl4ai_error": str(crawl4ai_error),
                    "httpx_error": str(httpx_error),
                },
            )
        except (DownloadError, ImportError) as exc:
            raise DownloadError(
                f"All fetch strategies failed for {url}: "
                f"crawl4ai={crawl4ai_error}, httpx={httpx_error}, playwright-stealth={exc}"
            ) from exc
