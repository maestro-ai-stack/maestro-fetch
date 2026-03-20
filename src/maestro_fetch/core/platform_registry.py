"""Platform action registry — maps platform+action to routing layers.

Each PlatformAction describes which layers can handle it and in what order.
Write operations skip Layer 1 (API) by design to reduce ban risk.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Layer(str, Enum):
    """Execution layers, ordered by preference."""

    API = "api"  # twikit, praw — READ only, fast, no browser
    SESSION = "session"  # active CDP session — WRITE, uses Playwright selectors
    PIPELINE = "pipeline"  # opencli YAML pipelines — READ+WRITE
    LLM = "llm"  # browser-use — universal fallback


@dataclass(frozen=True)
class PlatformAction:
    """Describes a single platform action and its routing strategy."""

    platform: str
    action: str
    is_write: bool = False
    layers: tuple[Layer, ...] = (Layer.PIPELINE, Layer.LLM)
    opencli_command: str | None = None  # e.g. "twitter like"
    source_adapter: str | None = None  # e.g. "twitter/timeline"
    description: str = ""


def _read(platform: str, action: str, *, source: str | None = None,
          opencli_cmd: str | None = None, desc: str = "") -> PlatformAction:
    """Helper to create a READ action with all three layers."""
    layers = (Layer.API, Layer.PIPELINE, Layer.LLM)
    if not source:
        layers = (Layer.PIPELINE, Layer.LLM)
    return PlatformAction(
        platform=platform, action=action, is_write=False,
        layers=layers, opencli_command=opencli_cmd,
        source_adapter=source, description=desc,
    )


def _write(platform: str, action: str, *, opencli_cmd: str | None = None,
           desc: str = "") -> PlatformAction:
    """Helper to create a WRITE action (skips API layer, SESSION first)."""
    return PlatformAction(
        platform=platform, action=action, is_write=True,
        layers=(Layer.SESSION, Layer.PIPELINE, Layer.LLM),
        opencli_command=opencli_cmd, description=desc,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PLATFORM_ACTIONS: dict[tuple[str, str], PlatformAction] = {}


def _register(*actions: PlatformAction) -> None:
    for a in actions:
        PLATFORM_ACTIONS[(a.platform, a.action)] = a


# -- Twitter / X -----------------------------------------------------------
_register(
    _read("twitter", "timeline", source="twitter/timeline", desc="Home timeline"),
    _read("twitter", "search", source="twitter/search", desc="Search tweets"),
    _read("twitter", "trending", source="twitter/trending", desc="Trending topics"),
    _write("twitter", "like", opencli_cmd="twitter like", desc="Like a tweet"),
    _write("twitter", "post", opencli_cmd="twitter post", desc="Post a tweet"),
    _write("twitter", "repost", opencli_cmd="twitter repost", desc="Retweet"),
    _write("twitter", "quote", opencli_cmd="twitter quote", desc="Quote tweet"),
    _write("twitter", "bookmark", opencli_cmd="twitter bookmark", desc="Bookmark a tweet"),
)

# -- Reddit ----------------------------------------------------------------
_register(
    _read("reddit", "hot", source="reddit/hot", desc="Hot posts"),
    _read("reddit", "frontpage", source="reddit/frontpage", desc="Front page"),
    _read("reddit", "search", source="reddit/search", desc="Search posts"),
    _read("reddit", "subreddit", source="reddit/subreddit", desc="Subreddit posts"),
    _write("reddit", "upvote", desc="Upvote a post"),
    _write("reddit", "comment", desc="Comment on a post"),
)

# -- LinkedIn --------------------------------------------------------------
_register(
    _write("linkedin", "post", desc="Post on LinkedIn"),
)

# -- Bilibili --------------------------------------------------------------
_register(
    _read("bilibili", "hot", opencli_cmd="bilibili hot", desc="Bilibili hot videos"),
    _read("bilibili", "search", opencli_cmd="bilibili search", desc="Search Bilibili"),
    _read("bilibili", "feed", opencli_cmd="bilibili feed", desc="Bilibili feed"),
)

# -- 小红书 (Xiaohongshu / RED) ---------------------------------------------
_register(
    _read("xiaohongshu", "hot", opencli_cmd="xiaohongshu hot", desc="Xiaohongshu hot"),
    _read("xiaohongshu", "search", opencli_cmd="xiaohongshu search", desc="Search Xiaohongshu"),
)

# -- Hacker News -----------------------------------------------------------
_register(
    _read("hackernews", "front", source="hackernews/front", desc="HN front page"),
    _write("hackernews", "comment", desc="Comment on HN"),
)


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def get_action(platform: str, action: str) -> PlatformAction | None:
    """Look up a registered action, or None if unregistered."""
    return PLATFORM_ACTIONS.get((platform.lower(), action.lower()))


def list_actions(platform: str | None = None) -> list[PlatformAction]:
    """List all registered actions, optionally filtered by platform."""
    actions = list(PLATFORM_ACTIONS.values())
    if platform:
        actions = [a for a in actions if a.platform == platform.lower()]
    return sorted(actions, key=lambda a: (a.platform, a.action))
