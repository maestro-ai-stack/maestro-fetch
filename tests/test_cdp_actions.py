"""Regression tests for CDP session layer in ActionRouter."""
from __future__ import annotations

import pytest

from maestro_fetch.core.platform_registry import Layer, get_action, list_actions


class TestLayerOrdering:
    """Verify SESSION is first for write ops, absent for read ops."""

    def test_write_ops_have_session_first(self):
        write_actions = [a for a in list_actions() if a.is_write]
        assert len(write_actions) > 0, "No write actions registered"
        for a in write_actions:
            assert a.layers[0] == Layer.SESSION, (
                f"{a.platform}/{a.action}: first layer is {a.layers[0]}, expected SESSION"
            )

    def test_read_ops_no_session_layer(self):
        read_actions = [a for a in list_actions() if not a.is_write]
        assert len(read_actions) > 0, "No read actions registered"
        for a in read_actions:
            assert Layer.SESSION not in a.layers, (
                f"{a.platform}/{a.action}: read op should not have SESSION layer"
            )

    def test_write_ops_preserve_pipeline_llm_fallback(self):
        write_actions = [a for a in list_actions() if a.is_write]
        for a in write_actions:
            assert Layer.PIPELINE in a.layers, (
                f"{a.platform}/{a.action}: missing PIPELINE fallback"
            )
            assert Layer.LLM in a.layers, (
                f"{a.platform}/{a.action}: missing LLM fallback"
            )

    def test_session_layer_enum_exists(self):
        assert Layer.SESSION.value == "session"


class TestReadOpsUnchanged:
    """Verify read ops still have their original layer stacks."""

    def test_twitter_timeline_layers(self):
        pa = get_action("twitter", "timeline")
        assert pa is not None
        assert pa.layers == (Layer.API, Layer.PIPELINE, Layer.LLM)

    def test_twitter_search_layers(self):
        pa = get_action("twitter", "search")
        assert pa is not None
        assert pa.layers == (Layer.API, Layer.PIPELINE, Layer.LLM)

    def test_hackernews_front_layers(self):
        pa = get_action("hackernews", "front")
        assert pa is not None
        assert pa.layers == (Layer.API, Layer.PIPELINE, Layer.LLM)

    def test_bilibili_hot_layers(self):
        pa = get_action("bilibili", "hot")
        assert pa is not None
        # No source adapter → no API layer
        assert pa.layers == (Layer.PIPELINE, Layer.LLM)


class TestWriteOpsLayers:
    """Verify specific write ops have correct layer stacks."""

    @pytest.mark.parametrize("platform,action", [
        ("twitter", "like"),
        ("twitter", "post"),
        ("twitter", "repost"),
        ("twitter", "quote"),
        ("twitter", "bookmark"),
        ("reddit", "upvote"),
        ("reddit", "comment"),
        ("linkedin", "post"),
        ("hackernews", "comment"),
    ])
    def test_write_action_layers(self, platform, action):
        pa = get_action(platform, action)
        assert pa is not None, f"{platform}/{action} not registered"
        assert pa.layers == (Layer.SESSION, Layer.PIPELINE, Layer.LLM)


class TestActionDispatch:
    """Verify execute_cdp_action routes to correct handler."""

    def test_known_handlers_registered(self):
        from maestro_fetch.backends.cdp_actions import _HANDLERS

        expected = [
            ("twitter", "post"),
            ("twitter", "like"),
            ("twitter", "bookmark"),
            ("twitter", "unbookmark"),
            ("twitter", "repost"),
            ("twitter", "quote"),
            ("twitter", "reply"),
            ("twitter", "follow"),
            ("twitter", "unfollow"),
            ("twitter", "delete"),
            ("twitter", "timeline"),
            ("twitter", "search"),
            ("twitter", "profile"),
            ("twitter", "bookmarks_read"),
            ("twitter", "thread"),
            ("twitter", "trending"),
        ]
        for platform, action in expected:
            assert (platform, action) in _HANDLERS, (
                f"Missing CDP handler: {platform}/{action}"
            )

    def test_unknown_action_raises(self):
        from maestro_fetch.backends.cdp_actions import execute_cdp_action

        with pytest.raises(NotImplementedError, match="No CDP handler"):
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                execute_cdp_action(None, "unknown_platform", "unknown_action")
            )


class TestSessionFallback:
    """Verify ActionRouter falls through when no session is active."""

    @pytest.mark.asyncio
    async def test_no_session_falls_through(self):
        """When no CDP session is active, SESSION layer fails and router
        continues to PIPELINE/LLM layers."""
        from unittest.mock import AsyncMock, patch

        from maestro_fetch.core.action_router import ActionRouter

        router = ActionRouter()

        # Mock: no active session → _execute_session raises
        # Mock: pipeline also fails → should collect both errors
        with patch.object(router, "_execute_session", side_effect=Exception("No active CDP session")), \
             patch.object(router, "_execute_pipeline", side_effect=Exception("opencli not installed")), \
             patch.object(router, "_execute_llm", side_effect=Exception("browser-use not installed")):
            with pytest.raises(Exception, match="All layers failed"):
                await router.execute("twitter", "like", url="https://x.com/test/status/123")

    @pytest.mark.asyncio
    async def test_session_success_skips_pipeline(self):
        """When SESSION layer succeeds, PIPELINE and LLM are not called."""
        from unittest.mock import AsyncMock, patch

        from maestro_fetch.core.action_router import ActionRouter

        router = ActionRouter()
        session_result = {"success": True, "action": "like", "layer": "session"}

        with patch.object(router, "_execute_session", return_value=session_result) as mock_session, \
             patch.object(router, "_execute_pipeline") as mock_pipeline, \
             patch.object(router, "_execute_llm") as mock_llm:
            result = await router.execute("twitter", "like", url="https://x.com/test/status/123")
            assert result["success"] is True
            assert result["layer"] == "session"
            mock_session.assert_called_once()
            mock_pipeline.assert_not_called()
            mock_llm.assert_not_called()
