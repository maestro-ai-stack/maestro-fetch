"""Tests for browser backend registry behavior."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from maestro_fetch.backends import get_available_backends, get_best_backend
from maestro_fetch.backends.extension import ExtensionBackend


@pytest.mark.asyncio
async def test_get_available_backends_returns_extension_when_available() -> None:
    config = {"backends": {"priority": ["extension"]}}

    with patch.object(
        ExtensionBackend,
        "is_available",
        new_callable=AsyncMock,
        return_value=True,
    ):
        backends = await get_available_backends(config)

    assert [backend.name for backend in backends] == ["extension"]


@pytest.mark.asyncio
async def test_get_available_backends_skips_disabled_backend() -> None:
    config = {
        "backends": {
            "priority": ["extension"],
            "extension": {"enabled": False},
        }
    }

    backends = await get_available_backends(config)
    assert backends == []


@pytest.mark.asyncio
async def test_get_best_backend_returns_none_when_unavailable() -> None:
    config = {"backends": {"priority": ["extension"]}}

    with patch.object(
        ExtensionBackend,
        "is_available",
        new_callable=AsyncMock,
        return_value=False,
    ):
        best = await get_best_backend(config)

    assert best is None
