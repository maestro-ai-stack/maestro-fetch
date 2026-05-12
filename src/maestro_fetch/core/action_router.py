"""Action router for social platform operations.

Routing strategy:
  Layer 1 (API)      — source adapters (praw, etc.), READ only, fast, no browser
  Layer 2 (Tab exec) — extension backend tab targeting, READ+WRITE, no focus steal

Write operations skip Layer 1, try tab exec first.
"""
from __future__ import annotations

import logging
from typing import Any

from maestro_fetch.core.config import load_config
from maestro_fetch.core.errors import FetchError
from maestro_fetch.core.platform_registry import (
    Layer,
    PlatformAction,
    get_action,
)

logger = logging.getLogger(__name__)


class ActionRouter:
    """Routes platform actions through the layer fallback chain."""

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or load_config()

    async def execute(
        self, platform: str, action: str, *args: str, **kwargs: Any
    ) -> dict:
        """Execute a platform action with automatic layer fallback.

        Returns a dict with at least ``success`` and ``result`` keys.
        """
        pa = get_action(platform, action)

        if pa is None:
            raise FetchError(f"Unregistered action: {platform}/{action}")

        errors: list[str] = []
        for layer in pa.layers:
            try:
                if layer == Layer.API:
                    return await self._execute_api(pa, *args, **kwargs)
                if layer == Layer.PIPELINE:
                    return await self._execute_pipeline(pa, *args, **kwargs)
            except Exception as exc:
                msg = f"Layer {layer.value} failed: {exc}"
                logger.warning(msg)
                errors.append(msg)
                continue

        raise FetchError(
            f"All layers failed for {platform}/{action}: "
            + "; ".join(errors)
        )

    # -- Layer 1: API (source adapters) ---------------------------------

    async def _execute_api(
        self, pa: PlatformAction, *args: str, **kwargs: Any
    ) -> dict:
        """Execute via source adapter (praw, tab-exec, etc.)."""
        if not pa.source_adapter:
            raise FetchError(f"No source adapter for {pa.platform}/{pa.action}")

        from maestro_fetch.sources.loader import (
            SourceContext,
            load_sources,
            run_adapter,
        )

        # Load sources from both community and custom dirs
        sources_dir = self._config.get("sources", {}).get(
            "custom_dir", ""
        )
        from maestro_fetch.core.config import BASE_DIR

        community_dir = BASE_DIR / "sources"
        all_adapters = load_sources(community_dir)

        # Also load custom sources
        if sources_dir:
            from pathlib import Path

            custom = Path(sources_dir)
            if custom.is_dir():
                all_adapters.extend(load_sources(custom))

        # Find the matching adapter
        adapter = None
        for a in all_adapters:
            if a.meta.name == pa.source_adapter:
                adapter = a
                break

        if adapter is None:
            raise FetchError(
                f"Source adapter '{pa.source_adapter}' not found"
            )

        ctx = SourceContext(config=self._config)
        result = await run_adapter(adapter, ctx, **kwargs)
        return {"success": True, "layer": "api", **result}

    # -- Layer 2: Pipeline (extension) ------------------------------------

    async def _execute_pipeline(
        self, pa: PlatformAction, *args: str, **kwargs: Any
    ) -> dict:
        """Execute via Chrome extension backend."""
        from maestro_fetch.backends.extension import ExtensionBackend

        backend = ExtensionBackend()
        if not await backend.is_available():
            raise FetchError("Extension backend is not available")

        # Navigate to URL if provided
        url = kwargs.get("url")
        if url:
            await backend.navigate(url)

        # Execute site-specific JS via extension
        site = pa.platform
        action_name = pa.action
        adapter_key = f"{site}/{action_name}"
        result = await backend.site_adapter(adapter_key, *(args or ()))
        return {"success": True, "layer": "extension", **result}
