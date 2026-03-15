"""Playwright backend -- headless browser fallback.

Requires: pip install maestro-fetch[browser]
Used for interactive sessions and as final fallback when bb-browser
and Cloudflare are unavailable.
"""
from __future__ import annotations

from typing import Any

from maestro_fetch.core.errors import FetchError

try:
    import html2text as _html2text

    _H2T_AVAILABLE = True
except ImportError:  # pragma: no cover
    _html2text = None  # type: ignore[assignment]
    _H2T_AVAILABLE = False


def _playwright_importable() -> bool:
    """Return True if playwright can be imported."""
    try:
        import playwright as _pw  # noqa: F401
        _ = _pw
        return True
    except ImportError:
        return False


class PlaywrightBackend:
    """Headless Chromium via Playwright."""

    name: str = "playwright"

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless

    # -- protocol methods -----------------------------------------------

    async def is_available(self) -> bool:
        """True when playwright is importable."""
        return _playwright_importable()

    async def fetch_content(self, url: str) -> str:
        """Launch browser, navigate to *url*, return markdown via html2text."""
        if not _playwright_importable():
            raise FetchError("playwright is not installed")

        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self._headless)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30_000)
                html = await page.content()
            finally:
                await browser.close()

        if not _H2T_AVAILABLE or _html2text is None:
            return html
        converter = _html2text.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = False
        return converter.handle(html)

    async def fetch_screenshot(self, url: str) -> bytes:
        """Navigate to *url* and capture a full-page PNG screenshot."""
        if not _playwright_importable():
            raise FetchError("playwright is not installed")

        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self._headless)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30_000)
                screenshot = await page.screenshot(full_page=True)
            finally:
                await browser.close()
        return screenshot

    async def eval_js(self, js: str) -> Any:
        """Evaluate *js* in a blank page context.

        Note: for real usage the caller should manage the page lifecycle
        via browser sessions (adapters/session.py).
        """
        if not _playwright_importable():
            raise FetchError("playwright is not installed")

        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self._headless)
            try:
                page = await browser.new_page()
                result = await page.evaluate(js)
            finally:
                await browser.close()
        return result

    async def site_adapter(self, adapter_name: str, *args: str) -> dict:
        """Not supported by the Playwright backend."""
        _ = adapter_name, args
        raise NotImplementedError(
            "Playwright backend does not support site adapters"
        )
