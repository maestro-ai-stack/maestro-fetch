#!/usr/bin/env python3
"""Benchmark: CDP backend vs other strategies on social/trending sites.

Tests x.com, reddit, producthunt, github trending.
Measures: latency, content length, content quality, strategy used.

Usage:
    python benchmarks/bench_cdp_social.py
    python benchmarks/bench_cdp_social.py --strategies cdp,httpx
    python benchmarks/bench_cdp_social.py --sites reddit,github
    python benchmarks/bench_cdp_social.py --rounds 3
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from textwrap import shorten

# ---------------------------------------------------------------------------
# Target sites
# ---------------------------------------------------------------------------
SITES = {
    "x.com": "https://x.com/home",
    "reddit": "https://www.reddit.com/r/popular/",
    "producthunt": "https://www.producthunt.com/",
    "github": "https://github.com/trending",
}

# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------

@dataclass
class BenchResult:
    site: str
    strategy: str
    latency_s: float
    content_len: int
    text_density: float  # ratio of alpha chars to total
    link_count: int
    error: str | None = None
    sample: str = ""  # first 200 chars
    api_intercepted: bool = False


@dataclass
class SiteReport:
    site: str
    results: list[BenchResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Content quality metrics
# ---------------------------------------------------------------------------

def text_density(content: str) -> float:
    """Ratio of alphabetic characters to total length."""
    if not content:
        return 0.0
    alpha = sum(1 for c in content if c.isalpha())
    return round(alpha / len(content), 3)


def count_links(content: str) -> int:
    """Count markdown links and raw URLs."""
    md_links = len(re.findall(r"\[.*?\]\(.*?\)", content))
    raw_urls = len(re.findall(r"https?://\S+", content))
    return md_links + raw_urls


def meaningful_lines(content: str) -> int:
    """Count non-empty, non-whitespace lines with >10 chars."""
    return sum(1 for line in content.splitlines() if len(line.strip()) > 10)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

async def bench_cdp(url: str, timeout: int = 45) -> tuple[str, dict]:
    """Fetch via CDP backend."""
    from maestro_fetch.backends.cdp import CDPBackend
    backend = CDPBackend()
    if not await backend.is_available():
        raise RuntimeError("CDP not available")
    content = await backend.fetch_content(url, timeout=timeout)
    return content, {"api_intercepted": bool(content and len(content) > 500)}


async def bench_crawl4ai(url: str, timeout: int = 45) -> tuple[str, dict]:
    """Fetch via crawl4ai."""
    from crawl4ai import AsyncWebCrawler
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        if result.success:
            return result.markdown or "", {}
        raise RuntimeError(f"crawl4ai failed: {result}")


async def bench_httpx(url: str, timeout: int = 30) -> tuple[str, dict]:
    """Fetch via httpx + html2text."""
    import httpx
    import html2text
    ua = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        resp = await client.get(url, headers={"User-Agent": ua})
        resp.raise_for_status()
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        return h.handle(resp.text), {}


async def bench_playwright_stealth(url: str, timeout: int = 45) -> tuple[str, dict]:
    """Fetch via playwright-stealth."""
    from playwright.async_api import async_playwright
    from playwright_stealth import stealth_async
    import html2text

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()
        await stealth_async(page)
        await page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        html = await page.content()
        await browser.close()

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    return h.handle(html), {}


STRATEGIES = {
    "cdp": bench_cdp,
    "crawl4ai": bench_crawl4ai,
    "httpx": bench_httpx,
    "playwright-stealth": bench_playwright_stealth,
}

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_single(site: str, url: str, strategy: str) -> BenchResult:
    """Run a single benchmark."""
    fn = STRATEGIES[strategy]
    t0 = time.perf_counter()
    try:
        content, meta = await fn(url)
        elapsed = time.perf_counter() - t0
        return BenchResult(
            site=site,
            strategy=strategy,
            latency_s=round(elapsed, 2),
            content_len=len(content),
            text_density=text_density(content),
            link_count=count_links(content),
            sample=shorten(content.strip(), 200, placeholder="..."),
            api_intercepted=meta.get("api_intercepted", False),
        )
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        return BenchResult(
            site=site,
            strategy=strategy,
            latency_s=round(elapsed, 2),
            content_len=0,
            text_density=0.0,
            link_count=0,
            error=f"{type(exc).__name__}: {exc}",
        )


async def run_benchmark(
    sites: dict[str, str],
    strategies: list[str],
    rounds: int = 1,
) -> list[BenchResult]:
    """Run all benchmarks sequentially (avoid resource conflicts)."""
    results = []
    for round_num in range(1, rounds + 1):
        if rounds > 1:
            print(f"\n{'='*60}")
            print(f"Round {round_num}/{rounds}")
            print(f"{'='*60}")
        for site, url in sites.items():
            for strategy in strategies:
                print(f"  [{strategy:20s}] {site:15s} ...", end=" ", flush=True)
                r = await run_single(site, url, strategy)
                if r.error:
                    print(f"ERROR ({r.latency_s}s): {r.error[:60]}")
                else:
                    print(
                        f"OK  {r.latency_s:5.1f}s  "
                        f"len={r.content_len:>7,}  "
                        f"density={r.text_density:.3f}  "
                        f"links={r.link_count:>3}"
                    )
                results.append(r)
    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(results: list[BenchResult]) -> None:
    """Print a summary table."""
    print("\n" + "=" * 90)
    print("BENCHMARK REPORT")
    print("=" * 90)
    print(
        f"{'Site':15s} {'Strategy':20s} {'Latency':>8s} {'Length':>9s} "
        f"{'Density':>8s} {'Links':>6s} {'Status':>8s}"
    )
    print("-" * 90)

    for r in results:
        status = "ERROR" if r.error else "OK"
        print(
            f"{r.site:15s} {r.strategy:20s} {r.latency_s:>7.1f}s "
            f"{r.content_len:>8,}  {r.text_density:>7.3f} "
            f"{r.link_count:>6d}  {status:>6s}"
        )

    # Summary: best strategy per site
    print("\n" + "-" * 90)
    print("BEST STRATEGY PER SITE (by content quality score = density * log(len) * (1 if no error else 0)):")
    print("-" * 90)

    import math
    sites_seen = set()
    for r in results:
        sites_seen.add(r.site)

    for site in sorted(sites_seen):
        site_results = [r for r in results if r.site == site and not r.error]
        if not site_results:
            print(f"  {site:15s}: ALL FAILED")
            continue
        # Score: density * log(content_len + 1) — rewards both quality and volume
        best = max(site_results, key=lambda r: r.text_density * math.log(r.content_len + 1))
        print(
            f"  {site:15s}: {best.strategy:20s} "
            f"(latency={best.latency_s}s, len={best.content_len:,}, "
            f"density={best.text_density})"
        )

    # Content samples
    print("\n" + "-" * 90)
    print("CONTENT SAMPLES (first 200 chars):")
    print("-" * 90)
    for r in results:
        if r.error:
            continue
        print(f"\n[{r.site} / {r.strategy}]")
        print(f"  {r.sample}")


def save_results(results: list[BenchResult], path: Path) -> None:
    """Save results as JSON."""
    data = [asdict(r) for r in results]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\nResults saved to {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark CDP on social sites")
    parser.add_argument(
        "--sites", default=",".join(SITES.keys()),
        help="Comma-separated site names (default: all)",
    )
    parser.add_argument(
        "--strategies", default=",".join(STRATEGIES.keys()),
        help="Comma-separated strategies (default: all)",
    )
    parser.add_argument("--rounds", type=int, default=1, help="Number of rounds")
    parser.add_argument(
        "--output", default="benchmarks/results/cdp_social.json",
        help="Output JSON path",
    )
    args = parser.parse_args()

    selected_sites = {k: SITES[k] for k in args.sites.split(",") if k in SITES}
    selected_strategies = [s for s in args.strategies.split(",") if s in STRATEGIES]

    print(f"Sites: {list(selected_sites.keys())}")
    print(f"Strategies: {selected_strategies}")
    print(f"Rounds: {args.rounds}")

    results = await run_benchmark(selected_sites, selected_strategies, args.rounds)
    print_report(results)
    save_results(results, Path(args.output))


if __name__ == "__main__":
    asyncio.run(main())
