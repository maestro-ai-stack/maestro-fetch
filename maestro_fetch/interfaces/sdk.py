"""SDK entry point -- public async API for maestro-fetch.

Responsibility: provide a simple async interface (fetch, batch_fetch)
that constructs FetchConfig from keyword arguments and delegates to Fetcher.

Inputs: URL(s) + optional config kwargs
Outputs: FetchResult or list[FetchResult]
"""
from __future__ import annotations

from pathlib import Path

from maestro_fetch.core.config import FetchConfig
from maestro_fetch.core.fetcher import Fetcher
from maestro_fetch.core.result import FetchResult

_fetcher = Fetcher()


async def fetch(
    url: str,
    *,
    provider: str = "anthropic",
    model: str | None = None,
    schema: dict | None = None,
    output_format: str = "markdown",
    cache_dir: str = ".maestro_cache",
    timeout: int = 60,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
) -> FetchResult:
    """Fetch data from any URL. Auto-detects source type."""
    config = FetchConfig(
        provider=provider,
        model=model,
        schema=schema,
        output_format=output_format,
        cache_dir=Path(cache_dir),
        timeout=timeout,
        headers=headers,
        cookies=cookies,
    )
    return await _fetcher.fetch(url, config)


async def batch_fetch(
    urls: list[str],
    concurrency: int = 5,
    **kwargs: object,
) -> list[FetchResult]:
    """Fetch multiple URLs concurrently."""
    config_kwargs = {
        k: v for k, v in kwargs.items() if k in FetchConfig.__dataclass_fields__
    }
    config = FetchConfig(**config_kwargs)  # type: ignore[arg-type]
    return await _fetcher.batch_fetch(urls, config, concurrency=concurrency)
