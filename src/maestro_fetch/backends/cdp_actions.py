"""CDP-based action implementations for social platforms.

Uses an active CDP session (Playwright Page) to perform UI actions
via verified selectors. Falls back gracefully — if no session is active,
ActionRouter skips to the next layer.

Architecture:
  - @with_page decorator handles connect/disconnect lifecycle
  - _navigate() always bounces via /home to force SPA re-render
  - _insert_text() uses execCommand with keyboard.type() fallback
  - execute_cdp_batch() shares one connection across multiple actions
"""
from __future__ import annotations

import asyncio
import json
import logging
from functools import wraps
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_HANDLERS: dict[tuple[str, str], Any] = {}


def _handler(platform: str, action: str):
    """Decorator to register a CDP action handler."""
    def decorator(fn):
        _HANDLERS[(platform, action)] = fn
        return fn
    return decorator


async def execute_cdp_action(
    state: Any, platform: str, action: str, *,
    _connection: tuple | None = None, **kwargs: Any,
) -> dict:
    """Route to the correct CDP handler for platform+action.

    Args:
        _connection: Optional (pw, browser, page) tuple to reuse.
                     If provided, the handler will NOT disconnect after use.
    """
    key = (platform.lower(), action.lower())
    handler = _HANDLERS.get(key)
    if handler is None:
        raise NotImplementedError(
            f"No CDP handler for {platform}/{action}"
        )
    return await handler(state, _connection=_connection, **kwargs)


async def execute_cdp_batch(
    state: Any, actions: list[tuple[str, str, dict]],
) -> list[dict]:
    """Execute multiple CDP actions sharing a single Playwright connection.

    Args:
        actions: List of (platform, action, kwargs) tuples.

    Returns:
        List of result dicts, one per action.
    """
    from maestro_fetch.core.session import connect_page, disconnect

    pw, browser, page = await connect_page(state)
    conn = (pw, browser, page)
    results: list[dict] = []
    try:
        for platform, action, kwargs in actions:
            try:
                r = await execute_cdp_action(
                    state, platform, action, _connection=conn, **kwargs,
                )
                results.append(r)
            except Exception as exc:
                results.append({"success": False, "action": action, "error": str(exc)})
    finally:
        await disconnect(pw, browser)
    return results


# ---------------------------------------------------------------------------
# Connection decorator
# ---------------------------------------------------------------------------

def with_page(fn):
    """Decorator that provides (page,) to the handler and manages lifecycle.

    If _connection is passed, reuse it (caller owns lifecycle).
    Otherwise, create a new connection and disconnect when done.
    """
    @wraps(fn)
    async def wrapper(state: Any, *, _connection: tuple | None = None, **kwargs):
        if _connection:
            _, _, page = _connection
            return await fn(page, **kwargs)

        from maestro_fetch.core.session import connect_page, disconnect
        pw, browser, page = await connect_page(state)
        try:
            return await fn(page, **kwargs)
        finally:
            await disconnect(pw, browser)
    return wrapper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _poll_selector(page: Any, selector: str, *, attempts: int = 20, interval_ms: int = 500):
    """Poll for a selector to appear. Returns the element or None."""
    for _ in range(attempts):
        el = await page.query_selector(selector)
        if el:
            return el
        await asyncio.sleep(interval_ms / 1000)
    return None


async def _navigate(page: Any, url: str, wait_selector: str = '[data-testid="tweet"]') -> None:
    """Navigate to a URL and wait for SPA content to render.

    Always bounces through /home first. Twitter's React SPA often fails to
    re-render content on direct goto — only the app shell loads. Bouncing
    forces a clean state transition.
    """
    await page.goto("https://x.com/home", wait_until="domcontentloaded")
    await asyncio.sleep(1)

    await page.goto(url, wait_until="domcontentloaded")
    try:
        await page.wait_for_selector(wait_selector, timeout=10_000)
    except Exception:
        await asyncio.sleep(3)


async def _insert_text(page: Any, selector: str, text: str) -> None:
    """Insert text into a React-controlled contenteditable element.

    Strategy:
      1. Click to focus the element
      2. Try execCommand('insertText') — works in most React contexts
      3. Check if the nearby Post button became enabled
      4. If still disabled, clear and retry with keyboard.type() which
         fires proper input events that React's synthetic system detects
    """
    await page.click(selector)
    await asyncio.sleep(0.2)

    # Try execCommand first (fast, works for replies/quotes)
    await page.evaluate(
        """(text) => document.execCommand('insertText', false, text)""",
        text,
    )
    await asyncio.sleep(0.5)

    # Check if any Post button became enabled
    btn_enabled = await page.evaluate("""() => {
        const btns = document.querySelectorAll(
            '[data-testid="tweetButton"], [data-testid="tweetButtonInline"]'
        );
        return [...btns].some(b => !b.disabled);
    }""")

    if btn_enabled:
        return  # execCommand worked

    log.info("execCommand didn't enable Post button, falling back to keyboard.type()")

    # Clear the text that execCommand inserted (it's in DOM but React doesn't know)
    await page.click(selector)
    await page.keyboard.press("Meta+a")
    await page.keyboard.press("Backspace")
    await asyncio.sleep(0.3)

    # Re-click and use keyboard.type() which fires proper input events
    await page.click(selector)
    await asyncio.sleep(0.2)
    await page.keyboard.type(text, delay=10)


async def _get_cookies_dict(page: Any) -> dict[str, str]:
    """Extract cookies from the page context as a dict."""
    cookies = await page.context.cookies()
    return {c["name"]: c["value"] for c in cookies}


def _graphql_headers(ct0: str) -> dict[str, str]:
    """Build auth headers for Twitter GraphQL requests."""
    return {
        "Authorization": (
            "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
            "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
        ),
        "X-Csrf-Token": ct0,
        "X-Twitter-Auth-Type": "OAuth2Session",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Twitter WRITE actions
# ---------------------------------------------------------------------------

@_handler("twitter", "post")
@with_page
async def twitter_post(page: Any, *, text: str = "", dry_run: bool = False, **kw: Any) -> dict:
    """Compose and post a tweet."""
    await _navigate(page, "https://x.com/compose/tweet",
                    wait_selector='[data-testid="tweetTextarea_0"]')
    textarea = await page.query_selector('[data-testid="tweetTextarea_0"]')
    if not textarea:
        raise RuntimeError("Tweet compose textarea not found")

    await _insert_text(page, '[data-testid="tweetTextarea_0"]', text)
    await asyncio.sleep(0.3)

    if dry_run:
        return {"success": True, "action": "post", "dry_run": True, "text": text}

    btn = (
        await page.query_selector('[data-testid="tweetButton"]:not([disabled])')
        or await page.query_selector('[data-testid="tweetButtonInline"]:not([disabled])')
    )
    if not btn:
        raise RuntimeError("Tweet button not found or disabled")
    await btn.click()
    await asyncio.sleep(2)
    return {"success": True, "action": "post", "text": text}


@_handler("twitter", "like")
@with_page
async def twitter_like(page: Any, *, url: str = "", **kw: Any) -> dict:
    """Like a tweet by navigating to its URL."""
    await _navigate(page, url)
    btn = await page.query_selector('[data-testid="like"]')
    if not btn:
        if await page.query_selector('[data-testid="unlike"]'):
            return {"success": True, "action": "like", "already_liked": True}
        raise RuntimeError("Like button not found")

    await btn.click()
    await asyncio.sleep(0.5)

    unlike = await _poll_selector(page, '[data-testid="unlike"]', attempts=5)
    return {"success": bool(unlike), "action": "like", "url": url}


@_handler("twitter", "bookmark")
@with_page
async def twitter_bookmark(page: Any, *, url: str = "", **kw: Any) -> dict:
    """Bookmark a tweet."""
    await _navigate(page, url)
    btn = await page.query_selector('[data-testid="bookmark"]')
    if not btn:
        if await page.query_selector('[data-testid="removeBookmark"]'):
            return {"success": True, "action": "bookmark", "already_bookmarked": True}
        raise RuntimeError("Bookmark button not found")

    await btn.click()
    await asyncio.sleep(0.5)

    verify = await _poll_selector(page, '[data-testid="removeBookmark"]', attempts=5)
    return {"success": bool(verify), "action": "bookmark", "url": url}


@_handler("twitter", "unbookmark")
@with_page
async def twitter_unbookmark(page: Any, *, url: str = "", **kw: Any) -> dict:
    """Remove a bookmark from a tweet."""
    await _navigate(page, url)
    btn = await page.query_selector('[data-testid="removeBookmark"]')
    if not btn:
        if await page.query_selector('[data-testid="bookmark"]'):
            return {"success": True, "action": "unbookmark", "not_bookmarked": True}
        raise RuntimeError("removeBookmark button not found")

    await btn.click()
    await asyncio.sleep(0.5)

    verify = await _poll_selector(page, '[data-testid="bookmark"]', attempts=5)
    return {"success": bool(verify), "action": "unbookmark", "url": url}


@_handler("twitter", "repost")
@with_page
async def twitter_repost(page: Any, *, url: str = "", **kw: Any) -> dict:
    """Retweet a tweet."""
    await _navigate(page, url)
    btn = await page.query_selector('[data-testid="retweet"]')
    if not btn:
        raise RuntimeError("Retweet button not found")

    await btn.click()
    await asyncio.sleep(0.5)

    confirm = await _poll_selector(page, '[data-testid="retweetConfirm"]')
    if confirm:
        await confirm.click()
    else:
        menu_items = await page.query_selector_all('[role="menuitem"]')
        if menu_items:
            await menu_items[0].click()
        else:
            raise RuntimeError("Repost confirm menu not found")

    await asyncio.sleep(1.0)
    return {"success": True, "action": "repost", "url": url}


@_handler("twitter", "quote")
@with_page
async def twitter_quote(page: Any, *, url: str = "", text: str = "",
                        dry_run: bool = False, **kw: Any) -> dict:
    """Quote-tweet: click retweet → Quote → fill text → post."""
    await _navigate(page, url)
    btn = await page.query_selector('[data-testid="retweet"]')
    if not btn:
        raise RuntimeError("Retweet button not found")

    await btn.click()
    await asyncio.sleep(0.5)

    menu_items = await page.query_selector_all('[role="menuitem"]')
    quote_item = None
    for item in menu_items:
        item_text = await item.inner_text()
        if "quote" in item_text.lower():
            quote_item = item
            break
    if not quote_item:
        if len(menu_items) >= 2:
            quote_item = menu_items[1]
        else:
            raise RuntimeError("Quote option not found in menu")

    await quote_item.click()
    await asyncio.sleep(1.0)

    textarea = await _poll_selector(page, '[data-testid="tweetTextarea_0"]')
    if not textarea:
        raise RuntimeError("Quote textarea not found")

    await _insert_text(page, '[data-testid="tweetTextarea_0"]', text)
    await asyncio.sleep(0.3)

    if dry_run:
        return {"success": True, "action": "quote", "dry_run": True, "text": text, "url": url}

    post_btn = (
        await page.query_selector('[data-testid="tweetButton"]:not([disabled])')
        or await page.query_selector('[data-testid="tweetButtonInline"]:not([disabled])')
    )
    if not post_btn:
        raise RuntimeError("Tweet button not found or disabled")
    await post_btn.click()
    await asyncio.sleep(1.5)
    return {"success": True, "action": "quote", "text": text, "url": url}


@_handler("twitter", "reply")
@with_page
async def twitter_reply(page: Any, *, url: str = "", text: str = "",
                        dry_run: bool = False, **kw: Any) -> dict:
    """Reply to a tweet."""
    await _navigate(page, url)
    textarea = await page.query_selector('[data-testid="tweetTextarea_0"]')
    if not textarea:
        raise RuntimeError("Reply textarea not found")

    await _insert_text(page, '[data-testid="tweetTextarea_0"]', text)
    await asyncio.sleep(0.3)

    if dry_run:
        return {"success": True, "action": "reply", "dry_run": True, "text": text, "url": url}

    btn = (
        await page.query_selector('[data-testid="tweetButtonInline"]:not([disabled])')
        or await page.query_selector('[data-testid="tweetButton"]:not([disabled])')
    )
    if not btn:
        raise RuntimeError("Reply button not found or disabled")
    await btn.click()
    await asyncio.sleep(1.5)
    return {"success": True, "action": "reply", "text": text, "url": url}


@_handler("twitter", "follow")
@with_page
async def twitter_follow(page: Any, *, url: str = "", **kw: Any) -> dict:
    """Follow a user by navigating to their profile."""
    await _navigate(page, url, wait_selector='[data-testid$="-follow"], [data-testid$="-unfollow"]')
    btn = await page.query_selector('[data-testid$="-follow"]')
    if not btn:
        if await page.query_selector('[data-testid$="-unfollow"]'):
            return {"success": True, "action": "follow", "already_following": True}
        raise RuntimeError("Follow button not found")

    await btn.click()
    await asyncio.sleep(1.0)

    verify = await _poll_selector(page, '[data-testid$="-unfollow"]', attempts=5)
    return {"success": bool(verify), "action": "follow", "url": url}


@_handler("twitter", "unfollow")
@with_page
async def twitter_unfollow(page: Any, *, url: str = "", **kw: Any) -> dict:
    """Unfollow a user."""
    await _navigate(page, url, wait_selector='[data-testid$="-follow"], [data-testid$="-unfollow"]')
    btn = await page.query_selector('[data-testid$="-unfollow"]')
    if not btn:
        if await page.query_selector('[data-testid$="-follow"]'):
            return {"success": True, "action": "unfollow", "not_following": True}
        raise RuntimeError("Unfollow button not found")

    await btn.click()
    await asyncio.sleep(0.5)

    confirm = await _poll_selector(page, '[data-testid="confirmationSheetConfirm"]')
    if confirm:
        await confirm.click()
        await asyncio.sleep(1.0)

    return {"success": True, "action": "unfollow", "url": url}


@_handler("twitter", "delete")
@with_page
async def twitter_delete(page: Any, *, url: str = "", **kw: Any) -> dict:
    """Delete a tweet."""
    await _navigate(page, url)
    more_btn = await page.query_selector('[aria-label="More"]')
    if not more_btn:
        raise RuntimeError("More button not found")
    await more_btn.click()
    await asyncio.sleep(0.5)

    menu_items = await page.query_selector_all('[role="menuitem"]')
    delete_item = None
    for item in menu_items:
        item_text = await item.inner_text()
        if "delete" in item_text.lower():
            delete_item = item
            break
    if not delete_item:
        raise RuntimeError("Delete menu item not found")

    await delete_item.click()
    await asyncio.sleep(0.5)

    confirm = await _poll_selector(page, '[data-testid="confirmationSheetConfirm"]')
    if confirm:
        await confirm.click()
        await asyncio.sleep(1.0)

    return {"success": True, "action": "delete", "url": url}


# ---------------------------------------------------------------------------
# Twitter READ actions (GraphQL via page.evaluate)
# ---------------------------------------------------------------------------

_GRAPHQL_QUERIES = {
    "timeline": ("c-CzHF1LboFilMpsx4ZCrQ", "HomeTimeline"),
    "search": (None, "SearchTimeline"),  # dynamic query ID
    "profile": ("qRednkZG-rn1P6b48NINmQ", "UserByScreenName"),
    "bookmarks": ("Fy0QMy4q_aZCpkO0PnyLYw", "Bookmarks"),
    "thread": ("nBS-WpgA6ZG0CyNHD517JQ", "TweetDetail"),
}


async def _graphql_fetch(page: Any, query_id: str, operation: str, variables: dict) -> dict:
    """Execute a Twitter GraphQL query via page.evaluate(fetch(...))."""
    cookies = await _get_cookies_dict(page)
    ct0 = cookies.get("ct0", "")
    headers = _graphql_headers(ct0)

    encoded_vars = json.dumps(variables)
    features = json.dumps({
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
        "rweb_video_timestamps_enabled": True,
        "longform_notetweets_rich_text_read_enabled": True,
        "longform_notetweets_inline_media_enabled": True,
        "responsive_web_enhance_cards_enabled": False,
    })

    url = f"https://x.com/i/api/graphql/{query_id}/{operation}?variables={encoded_vars}&features={features}"

    js = """
    async ([url, headers]) => {
        const resp = await fetch(url, { headers, credentials: 'include' });
        return await resp.json();
    }
    """
    result = await page.evaluate(js, [url, headers])
    return result


@_handler("twitter", "timeline")
@with_page
async def twitter_timeline(page: Any, *, count: int = 20, **kw: Any) -> dict:
    """Fetch home timeline via GraphQL."""
    query_id, operation = _GRAPHQL_QUERIES["timeline"]
    variables = {"count": count, "includePromotedContent": False}
    data = await _graphql_fetch(page, query_id, operation, variables)
    return {"success": True, "action": "timeline", "layer": "session", "data": data}


@_handler("twitter", "search")
@with_page
async def twitter_search(page: Any, *, query: str = "", count: int = 20, **kw: Any) -> dict:
    """Search tweets — intercept SearchTimeline response."""
    collected: list[dict] = []

    async def capture_response(response):
        if "SearchTimeline" in response.url:
            try:
                body = await response.json()
                collected.append(body)
            except Exception:
                pass

    page.on("response", capture_response)
    search_url = f"https://x.com/search?q={query}&src=typed_query"
    await page.goto(search_url, wait_until="domcontentloaded")
    await asyncio.sleep(3)
    page.remove_listener("response", capture_response)

    return {
        "success": True,
        "action": "search",
        "layer": "session",
        "query": query,
        "data": collected[0] if collected else {},
    }


@_handler("twitter", "profile")
@with_page
async def twitter_profile(page: Any, *, screen_name: str = "", **kw: Any) -> dict:
    """Fetch user profile via GraphQL."""
    query_id, operation = _GRAPHQL_QUERIES["profile"]
    variables = {"screen_name": screen_name, "withSafetyModeUserFields": True}
    data = await _graphql_fetch(page, query_id, operation, variables)
    return {"success": True, "action": "profile", "layer": "session", "data": data}


@_handler("twitter", "bookmarks_read")
@with_page
async def twitter_bookmarks_read(page: Any, *, count: int = 20, **kw: Any) -> dict:
    """Fetch bookmarks via GraphQL."""
    query_id, operation = _GRAPHQL_QUERIES["bookmarks"]
    variables = {"count": count, "includePromotedContent": False}
    data = await _graphql_fetch(page, query_id, operation, variables)
    return {"success": True, "action": "bookmarks_read", "layer": "session", "data": data}


@_handler("twitter", "thread")
@with_page
async def twitter_thread(page: Any, *, tweet_id: str = "", **kw: Any) -> dict:
    """Fetch tweet thread via GraphQL."""
    query_id, operation = _GRAPHQL_QUERIES["thread"]
    variables = {
        "focalTweetId": tweet_id,
        "with_rux_injections": False,
        "includePromotedContent": False,
        "withCommunity": True,
        "withQuickPromoteEligibilityTweetFields": True,
        "withBirdwatchNotes": True,
        "withVoice": True,
        "withV2Timeline": True,
    }
    data = await _graphql_fetch(page, query_id, operation, variables)
    return {"success": True, "action": "thread", "layer": "session", "data": data}


@_handler("twitter", "trending")
@with_page
async def twitter_trending(page: Any, **kw: Any) -> dict:
    """Fetch trending topics via REST API."""
    cookies = await _get_cookies_dict(page)
    ct0 = cookies.get("ct0", "")
    headers = _graphql_headers(ct0)

    url = "https://x.com/i/api/2/guide.json"
    js = """
    async ([url, headers]) => {
        const resp = await fetch(url, { headers, credentials: 'include' });
        return await resp.json();
    }
    """
    data = await page.evaluate(js, [url, headers])
    return {"success": True, "action": "trending", "layer": "session", "data": data}
