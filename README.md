# maestro-fetch

**Fetch everything, for agents.**

[![PyPI version](https://img.shields.io/pypi/v/maestro-fetch)](https://pypi.org/project/maestro-fetch/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/maestro-ai-stack/maestro-fetch)](https://github.com/maestro-ai-stack/maestro-fetch)

Universal data acquisition for AI agents with smart routing across 15+ source types.

---

## Quick Start

```bash
pip install maestro-fetch
mfetch "https://any-url.com"
```

---

## Features

| Capability | Description |
|---|---|
| Smart routing | Auto-detects URL type and dispatches to the right adapter |
| 7 built-in adapters | `web`, `doc`, `binary`, `cloud`, `media`, `baidu_pan`, `browser` |
| Pluggable browser backends | bb-browser, Cloudflare Browser Rendering, Playwright |
| Community source adapters | economics, finance, climate, social, academic, government |
| SQLite cache with TTL | Content-addressed storage, configurable eviction (LRU) |
| Interactive browser sessions | Click, fill, screenshot, eval JS via Playwright |
| Agent-friendly output | Markdown by default, with JSON/CSV/raw alternatives |

---

## CLI Examples

### Fetch any URL

```bash
mfetch "https://example.com/report.pdf"           # auto-detect, markdown output
mfetch "https://example.com" --output json         # JSON output
mfetch "https://example.com" --backend cloudflare  # force backend
mfetch batch urls.txt --dir ./data/ --concurrency 10
```

### Source adapters

```bash
mfetch source update                      # pull community adapters
mfetch source list --category economics   # browse by category
mfetch source info worldbank/gdp          # show args and examples
mfetch source run worldbank/gdp CN        # fetch World Bank GDP for China
```

### Interactive browser sessions

```bash
mfetch session start "https://login-required-site.com"
mfetch session fill "#email" "user@example.com"
mfetch session click "#submit"
mfetch session snapshot                   # current page as markdown
mfetch session end
```

### Cache management

```bash
mfetch cache list
mfetch cache clear --older-than 7d
```

---

## Architecture

```
                          +------------------+
                          |   CLI / SDK      |
                          |  (mfetch / API)  |
                          +--------+---------+
                                   |
                          +--------v---------+
                          |     Router       |
                          | (URL detection)  |
                          +--------+---------+
                                   |
             +---------------------+---------------------+
             |          |          |         |            |
       +-----v--+ +----v---+ +---v----+ +--v-----+ +---v------+
       |  web   | |  doc   | | cloud  | | media  | | source   |
       |adapter | |adapter | |adapter | |adapter | | adapters |
       +-----+--+ +--------+ +--------+ +--------+ +----------+
             |
    +--------+--------+--------+
    |        |        |        |
+---v---+ +--v----+ +-v-------++
|crawl4ai| |Cloud- | |Playwright|
|/ httpx | |flare  | |(fallback)|
+--------+ +-------+ +---------+
    Browser Backends
```

**Router decision chain:**

1. Match community source adapter (`@meta` pattern) -- dispatch to source
2. Match built-in adapter (baidu pan, cloud, media, doc, binary) -- dispatch directly
3. Web content fallback chain: crawl4ai -> httpx -> Cloudflare -> bb-browser -> playwright-stealth

---

## Installation

```bash
# Core (web + cloud + doc adapters)
pip install maestro-fetch

# With optional dependencies
pip install maestro-fetch[pdf]       # PDF and Excel parsing (Docling, openpyxl)
pip install maestro-fetch[media]     # YouTube/audio transcription (yt-dlp, Whisper)
pip install maestro-fetch[browser]   # Interactive sessions (Playwright)
pip install maestro-fetch[anthropic] # Claude LLM extraction
pip install maestro-fetch[openai]    # GPT LLM extraction
pip install maestro-fetch[all]       # Everything
```

Core fetching works without any API key. LLM keys are only needed for schema-based structured extraction.

---

## Python SDK

```python
from maestro_fetch import fetch, batch_fetch

# Auto-detect and fetch
result = await fetch("https://example.com/data")
print(result.content)       # markdown
print(result.source_type)   # "web" | "doc" | "cloud" | "media" | ...

# Batch with concurrency
results = await batch_fetch(urls, concurrency=10)

# LLM extraction (requires ANTHROPIC_API_KEY)
result = await fetch(
    "https://worldbank.org/report.pdf",
    schema={"country": str, "gdp": float},
    provider="anthropic",
)
```

---

## Configuration

Config lives at `~/.maestro-fetch/config.toml`. Generate with `mfetch config init`.

```toml
[cache]
max_size = "2GB"
default_ttl = 86400         # 1 day for web content

[backends]
priority = ["bb-browser", "cloudflare", "playwright"]

[backends.bb-browser]
enabled = true               # auto-detected from PATH

[backends.cloudflare]
enabled = false
account_id = ""
api_token = ""

[backends.playwright]
enabled = true
headless = true
```

### Storage layout

```
~/.maestro-fetch/
  config.toml       # user configuration
  cache.db          # SQLite cache index
  cache/            # content-addressed file store
  sources/          # community adapters (git clone)
  custom/           # user private adapters (override community)
  sessions/         # temporary session state
```

---

## Contributing

**Core improvements** -- open issues and PRs on this repo.

**New source adapters** -- contribute to [maestro-ai-stack/maestro-fetch-sources](https://github.com/maestro-ai-stack/maestro-fetch-sources). Each adapter is a single Python file with `@meta` header and an `async def run(ctx, ...)` function. See the [source adapter format](docs/superpowers/specs/2026-03-15-maestro-fetch-v2-design.md#8-source-adapter-format) for details.

```bash
# Development setup
git clone https://github.com/maestro-ai-stack/maestro-fetch.git
cd maestro-fetch
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

---

## License

MIT

---

Built by [Maestro](https://maestro.onl) -- Singapore AI product studio.
