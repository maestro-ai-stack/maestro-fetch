"""MCP Server -- exposes maestro-fetch capabilities as MCP tools via FastMCP.

Responsibility: bridge between MCP protocol and maestro-fetch SDK.
Inputs: MCP tool calls with URL(s) and config parameters.
Outputs: structured dicts suitable for MCP responses.
Invariants: each tool returns a plain dict (JSON-serializable).
"""
from __future__ import annotations

try:
    from fastmcp import FastMCP
except ImportError as e:
    raise ImportError("pip install maestro-fetch[mcp]") from e

from maestro_fetch.interfaces.sdk import fetch, batch_fetch
from maestro_fetch.core.result import FetchResult

mcp = FastMCP("maestro-fetch")


@mcp.tool()
async def fetch_url(
    url: str,
    output_format: str = "markdown",
    provider: str = "anthropic",
) -> dict:
    """Fetch data from any URL. Auto-detects source type (web/PDF/cloud/video/image)."""
    result = await fetch(url, provider=provider, output_format=output_format)
    return {
        "url": result.url,
        "source_type": result.source_type,
        "content": result.content,
        "table_count": len(result.tables),
        "metadata": result.metadata,
    }


@mcp.tool()
async def batch_fetch_urls(
    urls: list[str],
    output_format: str = "markdown",
    concurrency: int = 5,
) -> list[dict]:
    """Fetch multiple URLs concurrently."""
    results = await batch_fetch(urls, concurrency=concurrency, output_format=output_format)
    return [
        {
            "url": r.url,
            "source_type": r.source_type,
            "content": r.content,
            "table_count": len(r.tables),
        }
        for r in results
    ]


@mcp.tool()
async def detect_url_type(url: str) -> dict:
    """Detect the source type of a URL without downloading."""
    from maestro_fetch.core.router import detect_type
    return {"url": url, "source_type": detect_type(url)}


def run():
    mcp.run()
