"""WebAdapter: fetches web pages via browser backends or httpx, outputs Markdown.

Responsibility: handle generic web URLs (HTML pages, JS-rendered SPAs).
Non-goals: PDF, spreadsheets, cloud storage, media -- handled by dedicated adapters.

Strategy (2-tier, fast-first):
    1. httpx plain GET -- fastest, try first for static pages
    2. Extension backend (real Chrome via daemon + extension) -- auth, JS, cookies
"""
from __future__ import annotations

import re

from maestro_fetch.adapters.base import BaseAdapter
from maestro_fetch.core.config import FetchConfig
from maestro_fetch.core.errors import DownloadError
from maestro_fetch.core.result import FetchResult

_NON_WEB_PATTERNS = [
    r"dropbox\.com/",
    r"drive\.google\.com/",
    r"docs\.google\.com/",
    r"youtube\.com/watch",
    r"youtu\.be/",
    r"\.pdf(\?|$)",
    r"\.(xlsx|xls|ods|csv)(\?|$)",
]

_FALLBACK_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_WAF_BLOCK_MARKERS = (
    "Incapsula incident ID",
    "Request unsuccessful",
    "_Incapsula_Resource",
    "visitorId",
    "cf-browser-verification",
    "Enable JavaScript and cookies",
    "Just a moment",
    "Access Denied",
)

_LOGIN_WALL_MARKERS = (
    "Feishu, first choice",
    "飞书，先进企业协作与管理平台",
    "suite/passport/static/login",
    "accounts.google.com/signin",
    "login.microsoftonline.com",
)

# Sites that require JS rendering -- skip httpx, go straight to browser backends.
_BROWSER_REQUIRED_PATTERNS = (
    r"x\.com/",
    r"twitter\.com/",
    r"reddit\.com/",
    r"producthunt\.com/",
    r"feishu\.cn/",
    r"larksuite\.com/",
    r"notion\.so/",
    r"figma\.com/",
    r"linkedin\.com/",
    r"instagram\.com/",
    r"facebook\.com/",
    r"threads\.net/",
    r"mail\.google\.com/",
)


def _is_waf_blocked(content: str) -> bool:
    return any(marker in content for marker in _WAF_BLOCK_MARKERS)


def _is_login_wall(content: str) -> bool:
    return any(marker in content for marker in _LOGIN_WALL_MARKERS)


async def _extension_fetch(url: str, config: FetchConfig) -> str | None:  # noqa: ARG001
    """Try fetching via the Chrome extension backend.

    Strategy: first try attaching to an existing tab matching the URL
    (preserves auth/cookies). If no matching tab, navigate in automation window.
    """
    try:
        from maestro_fetch.backends.extension import ExtensionBackend

        backend = ExtensionBackend()
        if not await backend.is_available():
            return None

        # Try attaching to existing tab first (preserves login state)
        tab = await backend.find_tab(url)
        if tab:
            content = await backend.snapshot_tab(tab["tabId"])
            if content and len(content) > 200 and not _is_login_wall(content):
                return content

        # Fallback: navigate in automation window
        content = await backend.fetch_content(url)
        if content and len(content) > 200 and not _is_login_wall(content):
            return content
        return None
    except Exception:
        return None



async def _httpx_fetch(url: str, config: FetchConfig) -> str:
    """Fetch with httpx and convert HTML to Markdown."""
    try:
        import httpx
    except ImportError as exc:
        raise ImportError(
            "httpx is required for WebAdapter: pip install httpx"
        ) from exc

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
    except Exception as exc:
        raise DownloadError(f"httpx fetch failed for {url}: {exc}") from exc

    try:
        import html2text

        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        return h.handle(html)
    except ImportError:
        return re.sub(r"<[^>]+>", " ", html)


class WebAdapter(BaseAdapter):
    """Fetches web pages with a fast-first native stack.

    Strategy:
        1. httpx plain GET -- fastest, try first
        2. Extension (real Chrome via daemon) -- auth, JS, cookies
    """

    def supports(self, url: str) -> bool:
        return not any(re.search(p, url, re.IGNORECASE) for p in _NON_WEB_PATTERNS)

    async def fetch(self, url: str, config: FetchConfig) -> FetchResult:
        errors: dict[str, str] = {}
        needs_browser = any(re.search(p, url, re.IGNORECASE) for p in _BROWSER_REQUIRED_PATTERNS)

        # --- Tier 1: httpx plain GET (fastest, skip for JS-heavy sites) ---
        if not needs_browser:
            try:
                content = await _httpx_fetch(url, config)
                if not _is_waf_blocked(content) and not _is_login_wall(content):
                    return FetchResult(
                        url=url,
                        source_type="web",
                        content=content,
                        tables=[],
                        metadata={"adapter": "httpx"},
                    )
                errors["httpx"] = "WAF block or login wall detected"
            except (DownloadError, ImportError) as exc:
                errors["httpx"] = str(exc)

        # --- Tier 2: Extension (real Chrome, auth + JS) ---
        ext_content = await _extension_fetch(url, config)
        if ext_content:
            return FetchResult(
                url=url,
                source_type="web",
                content=ext_content,
                tables=[],
                metadata={"adapter": "extension", "errors": errors},
            )

        raise DownloadError(
            f"All fetch strategies failed for {url}: {errors}"
        )
