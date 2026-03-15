"""Cloudflare Browser Rendering backend -- REST API.

Requires: account_id + api_token in config.
Free tier: 10 min/day, 3 concurrent (simultaneous) browsers.

Endpoints used:
  POST /browser-rendering/markdown   -> markdown string
  POST /browser-rendering/screenshot -> PNG bytes
"""
from __future__ import annotations

from maestro_fetch.core.errors import FetchError

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:  # pragma: no cover
    _HTTPX_AVAILABLE = False

_TIMEOUT = 30  # seconds


class CloudflareBackend:
    """Cloudflare Browser Rendering via REST API."""

    name: str = "cloudflare"

    def __init__(self, account_id: str, api_token: str) -> None:
        self._account_id = account_id
        self._api_token = api_token
        self._base_url = (
            f"https://api.cloudflare.com/client/v4/accounts"
            f"/{account_id}/browser-rendering"
        )

    # -- helpers --------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, payload: dict) -> "httpx.Response":
        """POST to a Browser Rendering endpoint and return the response."""
        if not _HTTPX_AVAILABLE:
            raise FetchError("httpx is required for the Cloudflare backend")
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{self._base_url}/{path}",
                headers=self._headers(),
                json=payload,
            )
        if resp.status_code >= 400:
            raise FetchError(
                f"Cloudflare API error {resp.status_code}: {resp.text}"
            )
        return resp

    # -- protocol methods -----------------------------------------------

    async def is_available(self) -> bool:
        """Available when account_id and api_token are non-empty."""
        return bool(self._account_id and self._api_token and _HTTPX_AVAILABLE)

    async def fetch_content(self, url: str) -> str:
        """POST to /browser-rendering/markdown, return markdown text."""
        resp = await self._post("markdown", {"url": url})
        data = resp.json()
        # The API may return {"result": "..."} or plain text.
        if isinstance(data, dict):
            return data.get("result", data.get("content", resp.text))
        return resp.text

    async def fetch_screenshot(self, url: str) -> bytes:
        """POST to /browser-rendering/screenshot, return PNG bytes."""
        resp = await self._post("screenshot", {"url": url})
        return resp.content

    async def eval_js(self, js: str) -> None:
        """Not supported by Cloudflare Browser Rendering."""
        _ = js
        raise NotImplementedError(
            "Cloudflare backend does not support eval_js"
        )

    async def site_adapter(self, adapter_name: str, *args: str) -> dict:
        """Not supported by Cloudflare Browser Rendering."""
        _ = adapter_name, args
        raise NotImplementedError(
            "Cloudflare backend does not support site adapters"
        )
