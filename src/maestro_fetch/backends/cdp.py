"""CDP backend -- connect to an already-running Chrome via DevTools Protocol.

使用场景：Chrome 已登录飞书/内网，通过 CDP 复用登录态抓取需要认证的页面。

启动 Chrome 时加参数：
    /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
        --remote-debugging-port=9222

然后 mfetch 自动通过 CDP 连接，复用所有 cookies/localStorage/session。

抓取策略（三层 fallback）：
1. 拦截 XHR/fetch API 响应，取最大 JSON body（SPA 数据源）
2. innerText（JS 渲染后的 DOM 文本）
3. page.content() + html2text（传统 HTML）
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from maestro_fetch.core.errors import FetchError

log = logging.getLogger(__name__)

_DEFAULT_CDP_ENDPOINT = "http://127.0.0.1:9222"

# API 响应最小长度（太短的不是正文数据）
_MIN_API_BODY_LEN = 500


def _get_cdp_endpoint() -> str:
    """读取 CDP endpoint，支持环境变量覆盖。"""
    return os.environ.get("MAESTRO_CDP_ENDPOINT", _DEFAULT_CDP_ENDPOINT)


async def _probe_cdp(endpoint: str) -> bool:
    """检测 CDP endpoint 是否可用（GET /json/version）。"""
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


def _extract_text_from_json(body: str) -> str | None:
    """从 API JSON 响应中提取文章正文。

    常见模式：
    - {"data": {"content": "..."}}
    - {"data": {"article": {"body": "..."}}}
    - 递归搜索最长字符串值
    """
    try:
        obj = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return None

    # 递归找最长字符串字段
    best = ""

    def _walk(node: Any, depth: int = 0) -> None:
        nonlocal best
        if depth > 10:
            return
        if isinstance(node, str) and len(node) > len(best):
            best = node
        elif isinstance(node, dict):
            for v in node.values():
                _walk(v, depth + 1)
        elif isinstance(node, list):
            for item in node[:50]:  # 防止超大数组
                _walk(item, depth + 1)

    _walk(obj)
    return best if len(best) >= _MIN_API_BODY_LEN else None


# -----------------------------------------------------------------------
# CDPBackend
# -----------------------------------------------------------------------


class CDPBackend:
    """通过 Chrome DevTools Protocol 连接已运行的浏览器。"""

    name: str = "cdp"

    def __init__(self, endpoint: str | None = None) -> None:
        self._endpoint = endpoint or _get_cdp_endpoint()

    # -- protocol methods ---------------------------------------------------

    async def is_available(self) -> bool:
        """CDP 可用 = playwright 已装 + endpoint 有响应。"""
        if not _playwright_importable():
            return False
        return await _probe_cdp(self._endpoint)

    async def fetch_content(self, url: str, timeout: int = 30) -> str:
        """通过 CDP 抓取页面内容。

        三层策略：
        1. 拦截网络 API 响应（SPA 数据源）
        2. document.body.innerText（JS 渲染后文本）
        3. page.content() + html2text（传统 HTML fallback）
        """
        if not _playwright_importable():
            raise FetchError("playwright is not installed")

        from playwright.async_api import async_playwright

        try:
            import html2text as _html2text
            _h2t = True
        except ImportError:
            _html2text = None  # type: ignore[assignment]
            _h2t = False

        timeout_ms = timeout * 1000
        # (url, body) 元组，保留 API URL 用于智能排序
        api_responses: list[tuple[str, str]] = []
        from urllib.parse import urlparse
        target_host = urlparse(url).hostname or ""

        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(self._endpoint)
            try:
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = await context.new_page()

                # 拦截所有网络响应，收集 API JSON body
                async def _on_response(response: Any) -> None:
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" not in ct:
                            return
                        if response.status != 200:
                            return
                        body = await response.text()
                        if len(body) >= _MIN_API_BODY_LEN:
                            api_responses.append((response.url, body))
                    except Exception:
                        pass  # 部分响应无法读取 body（opaque/redirect）

                page.on("response", _on_response)

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    # 等待 SPA 渲染 + API 请求完成
                    try:
                        await page.wait_for_load_state("networkidle", timeout=15_000)
                    except Exception:
                        await page.wait_for_timeout(5000)

                    # --- 策略 1：从 API 响应中提取正文 ---
                    # 优先同域 API（如 bytetech 的 article/detail），按长度排序
                    same_host = [(u, b) for u, b in api_responses
                                 if target_host and target_host in u]
                    other = [(u, b) for u, b in api_responses
                             if not (target_host and target_host in u)]
                    # 同域优先，同域内按 body 大小降序
                    ranked = sorted(same_host, key=lambda x: len(x[1]), reverse=True) + \
                             sorted(other, key=lambda x: len(x[1]), reverse=True)

                    for api_url, body in ranked[:15]:
                        text = _extract_text_from_json(body)
                        if text:
                            short = api_url.split("?")[0][-60:]
                            log.info("CDP: extracted %d chars from %s", len(text), short)
                            return text

                    # --- 策略 2：innerText ---
                    inner = await page.evaluate("document.body.innerText")
                    if inner and len(inner) > _MIN_API_BODY_LEN:
                        log.info("CDP: using innerText (%d chars)", len(inner))
                        return inner

                    # --- 策略 3：page.content() + html2text ---
                    html = await page.content()
                    log.info("CDP: falling back to page.content() (%d chars)", len(html))
                    if _h2t and _html2text is not None:
                        converter = _html2text.HTML2Text()
                        converter.ignore_links = False
                        converter.ignore_images = False
                        return converter.handle(html)
                    return html

                finally:
                    await page.close()
            finally:
                await browser.close()

    async def fetch_screenshot(self, url: str) -> bytes:
        """通过 CDP 截图。"""
        if not _playwright_importable():
            raise FetchError("playwright is not installed")

        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(self._endpoint)
            try:
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = await context.new_page()
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
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
