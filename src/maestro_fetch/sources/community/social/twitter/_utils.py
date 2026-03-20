"""Shared twikit client initialization for Twitter source adapters.

Cookie management: ~/.maestro-fetch/auth/twitter_cookies.json
"""
from __future__ import annotations

import json
from pathlib import Path

_COOKIES_PATH = Path.home() / ".maestro-fetch" / "auth" / "twitter_cookies.json"
_client = None


async def get_client():
    """Return a shared twikit Client instance, initialized with saved cookies."""
    global _client
    if _client is not None:
        return _client

    try:
        from twikit import Client
    except ImportError:
        raise RuntimeError(
            "twikit is required for Twitter adapters: pip install 'maestro-fetch[social]'"
        )

    client = Client("en-US")

    if _COOKIES_PATH.exists():
        cookies = json.loads(_COOKIES_PATH.read_text())
        client.set_cookies(cookies)
    else:
        raise RuntimeError(
            f"Twitter cookies not found at {_COOKIES_PATH}. "
            "Log in via browser and export cookies to this file."
        )

    _client = client
    return _client
