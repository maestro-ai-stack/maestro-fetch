"""BaiduPanAdapter -- downloads files from Baidu Pan (百度网盘) share links.

Responsibility: handle pan.baidu.com/s/ share URLs end-to-end.

Flow (no BDUSS required, uses official PCS OAuth):
  1. Check bypy access_token in ~/.bypy/bypy.json
     If missing: print auth URL and prompt for code (one-time setup)
  2. GET share page -> extract bdstoken
  3. POST share/verify with pwd -> get randsk (sekey)
  4. GET share/list -> get file list + shareid + uk (owner uid)
  5. POST PCS transfer API -> save file(s) to own pan at /maestro_fetch_cache/
  6. GET PCS filemetas -> resolve dlink for each transferred file
  7. GET dlink with access_token -> download bytes
  8. Parse (CSV/Excel) -> FetchResult

Pitfalls discovered in practice (2026-02-28):
  - bypy CLI root is /apps/bypy/, not /. Use PCS API directly for own-pan paths.
  - dlink requires ?access_token= suffix AND User-Agent: pan.baidu.com header.
  - Transfer destination must not already exist (use ondup=newcopy).
  - randsk from share/verify IS the sekey used in transfer API.
  - share/list returns share_id + uk needed for transfer; parse from JSON response.
  - Authorization code is one-time use, 10-min expiry; stored token auto-refreshes.

One-time setup:
  .venv/bin/python -c "from maestro_fetch.adapters.baidu_pan import ensure_authorized; ensure_authorized()"
  -- or --
  maestro-fetch "pan.baidu.com/s/..." will trigger auth automatically on first run.

Token stored at: ~/.bypy/bypy.json  (bypy-compatible format)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from maestro_fetch.adapters.base import BaseAdapter
from maestro_fetch.adapters.cloud import _parse_content
from maestro_fetch.core.config import FetchConfig
from maestro_fetch.core.errors import DownloadError
from maestro_fetch.core.result import FetchResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SHARE_PATTERN = r"pan\.baidu\.com/s/"
_TOKEN_PATH = Path.home() / ".bypy" / "bypy.json"
_APP_ID = "250528"         # Baidu web client app_id (public)
_BYPY_CLIENT_ID = "q8WE4EpCsau1oS0MplgMKNBn"   # bypy's registered app
_BYPY_CLIENT_SECRET = "jXiFMOPVPCWlO2M5CwR6zYpMoYztIAXf"

_UA_BROWSER = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_UA_PAN = "pan.baidu.com"   # required by dlink download endpoint

# Destination folder in user's own pan for transferred files.
_TRANSFER_DIR = "/maestro_fetch_cache"

_AUTH_URL = (
    f"https://openapi.baidu.com/oauth/2.0/authorize"
    f"?client_id={_BYPY_CLIENT_ID}&response_type=code"
    f"&redirect_uri=oob&scope=basic+netdisk"
)

# ---------------------------------------------------------------------------
# Token management (bypy-compatible ~/.bypy/bypy.json)
# ---------------------------------------------------------------------------

def _load_token() -> dict | None:
    """Return token dict or None if not authorized."""
    if not _TOKEN_PATH.exists():
        return None
    try:
        return json.loads(_TOKEN_PATH.read_text())
    except Exception:
        return None


def _save_token(token: dict) -> None:
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_PATH.write_text(json.dumps(token, indent=2))


def _refresh_token(token: dict) -> dict:
    """Refresh access_token using refresh_token. Returns updated token dict."""
    r = httpx.post(
        "https://openapi.baidu.com/oauth/2.0/token",
        params={
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
            "client_id": _BYPY_CLIENT_ID,
            "client_secret": _BYPY_CLIENT_SECRET,
        },
        timeout=30,
    )
    data = r.json()
    if "access_token" not in data:
        raise DownloadError(f"Token refresh failed: {data}")
    token.update(data)
    _save_token(token)
    return token


def _exchange_code(code: str) -> dict:
    """Exchange authorization code for access_token + refresh_token."""
    r = httpx.post(
        "https://openapi.baidu.com/oauth/2.0/token",
        params={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": _BYPY_CLIENT_ID,
            "client_secret": _BYPY_CLIENT_SECRET,
            "redirect_uri": "oob",
        },
        timeout=30,
    )
    data = r.json()
    if "access_token" not in data:
        raise DownloadError(f"Authorization failed: {data}")
    _save_token(data)
    return data


def ensure_authorized() -> str:
    """Return a valid access_token, triggering interactive auth if needed.

    Safe to call from async context (does not use asyncio).
    Raises DownloadError if auth fails.
    """
    token = _load_token()
    if token and token.get("access_token"):
        # Try to validate; refresh if needed
        try:
            r = httpx.get(
                "https://pan.baidu.com/rest/2.0/xpan/nas",
                params={"method": "uinfo", "access_token": token["access_token"]},
                timeout=10,
            )
            if r.json().get("errno") == 111:   # token expired
                token = _refresh_token(token)
            return token["access_token"]
        except Exception:
            if token.get("refresh_token"):
                token = _refresh_token(token)
                return token["access_token"]

    # Interactive one-time setup
    print(f"\n[BaiduPan] First-time setup required.")
    print(f"  1. Open this URL in your browser (log in to Baidu first):")
    print(f"     {_AUTH_URL}")
    print(f"  2. Copy the authorization code shown on the page.")
    code = input("  3. Paste authorization code here: ").strip()
    token = _exchange_code(code)
    print(f"[BaiduPan] Authorized. Token saved to {_TOKEN_PATH}")
    return token["access_token"]


# ---------------------------------------------------------------------------
# Share link resolution
# ---------------------------------------------------------------------------

def _parse_share_url(url: str) -> tuple[str, str]:
    """Return (surl, pwd). pwd is empty string if absent."""
    parsed = urlparse(url)
    import re
    m = re.search(r"/s/([^/?#]+)", parsed.path)
    surl = m.group(1) if m else ""
    pwd = parse_qs(parsed.query).get("pwd", [""])[0]
    return surl, pwd


# ---------------------------------------------------------------------------
# PCS own-pan operations
# ---------------------------------------------------------------------------


_PREFERRED_EXTENSIONS = [".xlsx", ".xls", ".csv", ".json", ".pdf"]


async def _dlink_for_fsid(
    client: httpx.AsyncClient, access_token: str, fs_id: int
) -> str:
    """Return dlink for a single fs_id via filemetas API."""
    resp = await client.get(
        "https://pan.baidu.com/rest/2.0/xpan/multimedia",
        params={
            "method": "filemetas",
            "access_token": access_token,
            "fsids": f"[{fs_id}]",
            "dlink": 1,
            "web": 1,
        },
    )
    meta = resp.json()
    return meta["list"][0]["dlink"]


async def _resolve_dlink(
    client: httpx.AsyncClient, access_token: str, saved_name: str
) -> tuple[str, str]:
    """Locate saved_name in pan root and return (dlink, filename) for primary data file.

    Invariants:
      - saved_name is the name of an item (file or directory) at pan root /
      - If it is a directory, the primary data file is the first match in
        _PREFERRED_EXTENSIONS order (xlsx > xls > csv > json > pdf).
      - If it is a file, it is the target directly.
    """
    resp = await client.get(
        "https://pan.baidu.com/rest/2.0/xpan/file",
        params={"method": "list", "access_token": access_token, "dir": "/", "web": 1},
    )
    root_files = resp.json().get("list", [])
    entry = next(
        (f for f in root_files if f["server_filename"] == saved_name), None
    )
    if not entry:
        raise DownloadError(
            f"Saved item not found in pan root: {saved_name!r}. "
            "The save may have failed or placed the file elsewhere."
        )

    if entry["isdir"] == 0:
        dlink = await _dlink_for_fsid(client, access_token, entry["fs_id"])
        return dlink, entry["server_filename"]

    # Directory: list and pick primary data file
    resp2 = await client.get(
        "https://pan.baidu.com/rest/2.0/xpan/file",
        params={
            "method": "list",
            "access_token": access_token,
            "dir": f"/{saved_name}",
            "web": 1,
        },
    )
    dir_files = [f for f in resp2.json().get("list", []) if f["isdir"] == 0]
    if not dir_files:
        raise DownloadError(f"No files found inside saved directory: /{saved_name}")

    target = None
    for ext in _PREFERRED_EXTENSIONS:
        target = next(
            (f for f in dir_files if f["server_filename"].lower().endswith(ext)),
            None,
        )
        if target:
            break
    if target is None:
        target = dir_files[0]

    dlink = await _dlink_for_fsid(client, access_token, target["fs_id"])
    return dlink, target["server_filename"]


async def _download_dlink(
    client: httpx.AsyncClient, dlink: str, access_token: str
) -> bytes:
    """Download file bytes from a dlink. Requires access_token suffix + UA."""
    resp = await client.get(
        f"{dlink}&access_token={access_token}",
        headers={"User-Agent": _UA_PAN},
        follow_redirects=True,
    )
    if resp.status_code != 200:
        raise DownloadError(
            f"dlink download failed HTTP {resp.status_code}. "
            "Token may have expired; delete ~/.bypy/bypy.json and re-authorize."
        )
    return resp.content


# ---------------------------------------------------------------------------
# Playwright-based share save (handles bdstoken + JS rendering)
# ---------------------------------------------------------------------------

async def _save_share_via_playwright(url: str, access_token: str) -> str:
    """Open share link in a playwright browser, click '保存到网盘', return saved_name.

    Uses playwright with a persistent profile so Baidu login session is reused.
    Falls back to interactive login if the session is missing.

    Returns: the server_filename of the top-level saved item (file or directory).
    Baidu Pan saves to the pan root by default.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise DownloadError(
            "playwright is required for Baidu Pan share saving: pip install playwright"
        ) from exc

    # Use a persistent profile so Baidu login session is reused across calls.
    user_data_dir = str(Path.home() / ".maestro_fetch" / "playwright_profile")

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,              # show browser so user can log in if needed
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # Register share/list interceptor BEFORE navigation so we don't miss early responses.
        share_list_data: list[dict] = []

        async def handle_response(resp):
            if "share/list" in resp.url or "shareinfo" in resp.url:
                try:
                    data = await resp.json()
                    share_list_data.extend(data.get("list", []))
                except Exception:
                    pass

        page.on("response", handle_response)
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        # Check if we need to enter the pwd (extract code input visible)
        pwd_input = page.locator("input[placeholder*='提取码'], input[placeholder*='密码']")
        if await pwd_input.count() > 0:
            import re as _re
            pwd = _re.search(r"[?&]pwd=([^&]+)", url)
            if pwd:
                await pwd_input.first.fill(pwd.group(1))
                await page.locator(
                    "button:has-text('提取文件'), button:has-text('确定')"
                ).first.click()

        # Check if we're not logged in (login prompt)
        login_btn = page.locator("text=登录, text=去登录")
        if await login_btn.count() > 0:
            print("[BaiduPan] Please log in to Baidu in the browser window that opened.")
            print("           After logging in, press Enter here to continue.")
            sys.stdin.readline()
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        # Wait for share/list XHR (Baidu SPA fires it after domcontentloaded).
        # 5s is generous; typical load is <2s on a good connection.
        await page.wait_for_timeout(5000)
        page.remove_listener("response", handle_response)

        # Click 保存到网盘 (may not exist if already saved -- that's OK)
        save_btn = page.locator("button:has-text('保存到网盘'), a:has-text('保存到网盘')")
        if await save_btn.count() > 0:
            await save_btn.first.click()
            await page.wait_for_timeout(3000)

        await ctx.close()

    # Determine saved_name: from intercepted share/list (most reliable),
    # or fallback to newest item in pan root by modification time.
    if share_list_data:
        # The top-level item in the share -- could be file or directory.
        first = share_list_data[0]
        return first.get("server_filename", "download")

    # Fallback: list pan root sorted by time desc and return newest entry.
    # This assumes the just-saved item is the most recently modified.
    async with httpx.AsyncClient(timeout=30) as _client:
        r = await _client.get(
            "https://pan.baidu.com/rest/2.0/xpan/file",
            params={
                "method": "list",
                "access_token": access_token,
                "dir": "/",
                "order": "time",
                "desc": 1,
                "web": 1,
            },
        )
        files = r.json().get("list", [])
        if not files:
            raise DownloadError(
                "No files found in pan root after save. "
                "Make sure you are logged in and the save succeeded."
            )
        return files[0]["server_filename"]


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class BaiduPanAdapter(BaseAdapter):
    """Downloads files from Baidu Pan share links via PCS OAuth (bypy token).

    One-time setup: run maestro-fetch on any pan.baidu.com/s/ URL.
    Token stored at ~/.bypy/bypy.json (compatible with bypy CLI).

    For each download:
      share URL -> verify -> list -> transfer to own pan -> dlink -> bytes
    """

    def supports(self, url: str) -> bool:
        import re
        return bool(re.search(_SHARE_PATTERN, url, re.IGNORECASE))

    async def fetch(self, url: str, config: FetchConfig) -> FetchResult:
        # ensure_authorized is synchronous; run before async client opens
        access_token = ensure_authorized()

        surl, pwd = _parse_share_url(url)
        if not surl:
            raise DownloadError(f"Cannot parse surl from: {url}")

        timeout = config.timeout or 120

        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            # Step 1: save share to own pan via playwright (handles bdstoken/JS).
            # Baidu Pan saves to pan root by default; saved_name is the top-level item.
            saved_name = await _save_share_via_playwright(url, access_token)

            # Step 2: locate the primary data file (may be inside a directory).
            dlink, filename = await _resolve_dlink(client, access_token, saved_name)
            content_bytes = await _download_dlink(client, dlink, access_token)

        text, tables = _parse_content(content_bytes, filename)

        config.cache_dir.mkdir(parents=True, exist_ok=True)
        raw_path = config.cache_dir / filename
        raw_path.write_bytes(content_bytes)

        return FetchResult(
            url=url,
            source_type="cloud",
            content=text,
            tables=tables,
            metadata={
                "adapter": "baidu_pan",
                "filename": filename,
            },
            raw_path=raw_path,
        )
