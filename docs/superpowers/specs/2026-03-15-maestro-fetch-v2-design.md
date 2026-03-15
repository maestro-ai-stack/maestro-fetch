# maestro-fetch v2: Agent Perception Layer

**Date**: 2026-03-15
**Status**: Approved
**Repo**: maestro-ai-stack/maestro-fetch

## 1. Vision

maestro-fetch is the universal data acquisition layer for AI agents. It fetches anything — web pages, PDFs, cloud files, videos, authenticated pages, financial data, government statistics — and returns agent-friendly markdown or structured data. No single backend covers all scenarios; maestro-fetch orchestrates multiple backends (bb-browser, Cloudflare Browser Rendering, Playwright, crawl4ai) behind a unified CLI and SDK.

**Identity**: "Fetch everything, for agents" — the perception layer.

## 2. Distribution Model

- **Core**: `pip install maestro-fetch` (PyPI)
- **CLI entry points**: `maestro-fetch` (full) + `mfetch` (short alias)
- **Skill integration**: SKILL.md bundled in `skills/fetch/` — discoverable by `npx skills-npm`
- **Claude Code Plugin**: thin wrapper (SKILL.md + hook pointing to CLI)
- **Community adapters**: separate repo `maestro-ai-stack/maestro-fetch-sources`
- **No MCP server** — CLI + SDK only

## 3. Project Structure

```
maestro-fetch/
├── pyproject.toml
├── LICENSE (MIT)
├── README.md
├── llms.txt
├── src/maestro_fetch/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli/
│   │   ├── __init__.py          # typer app, register subcommands
│   │   ├── fetch.py             # mfetch <url> (default command)
│   │   ├── source.py            # mfetch source update/list/info/run
│   │   ├── session.py           # mfetch session start/click/fill/snapshot/end
│   │   ├── cache.py             # mfetch cache list/clear
│   │   └── config.py            # mfetch config init/show
│   ├── core/
│   │   ├── router.py            # URL → adapter dispatch
│   │   ├── fetcher.py           # orchestrate adapter execution
│   │   ├── config.py            # TOML config loader
│   │   ├── cache.py             # SQLite cache index (NEW)
│   │   ├── result.py            # FetchResult dataclass
│   │   └── errors.py            # error hierarchy
│   ├── adapters/
│   │   ├── base.py              # BaseAdapter protocol
│   │   ├── web.py               # crawl4ai → httpx → cloudflare → bb-browser → playwright-stealth
│   │   ├── doc.py               # PDF, Excel, CSV
│   │   ├── binary.py            # archives, geospatial, data science formats
│   │   ├── cloud.py             # Dropbox, Google Drive/Docs/Sheets
│   │   ├── media.py             # YouTube, Vimeo (yt-dlp + Whisper)
│   │   ├── baidu_pan.py         # Baidu Pan OAuth + PCS API
│   │   ├── browser.py           # BrowserBackend dispatch (NEW)
│   │   └── session.py           # interactive Playwright sessions (NEW)
│   ├── backends/                # pluggable browser backends (NEW)
│   │   ├── __init__.py
│   │   ├── base.py              # BrowserBackend Protocol
│   │   ├── bb_browser.py        # wraps bb-browser CLI
│   │   ├── cloudflare.py        # Cloudflare Browser Rendering REST API
│   │   └── playwright.py        # Playwright headless (fallback)
│   ├── sources/                 # external adapter loader (NEW)
│   │   ├── __init__.py
│   │   └── loader.py            # scan @meta, register into router
│   └── providers/               # LLM extraction (optional)
│       ├── base.py
│       ├── anthropic.py
│       └── openai.py
├── skills/
│   └── fetch/
│       └── SKILL.md
├── examples/
├── tests/
└── docs/
```

## 4. CLI Interface

### 4.1 Default Command: fetch

```bash
mfetch <url>                              # smart route → markdown output
mfetch <url> --output json|csv|raw        # output format
mfetch <url> --dir ./out/                 # save to directory
mfetch <url> --no-cache                   # skip cache
mfetch <url> --timeout 120               # custom timeout
mfetch <url> --backend cloudflare         # force specific backend
mfetch batch urls.txt --dir ./data/ --concurrency 10
```

### 4.2 Source Adapters

```bash
mfetch source update                      # git pull maestro-fetch-sources
mfetch source list                        # list all available adapters
mfetch source list --category economics   # filter by category
mfetch source info twitter/search         # show args and examples
mfetch source run worldbank/gdp CN        # execute adapter
mfetch source run twitter/search "AI"     # requires bb-browser
```

### 4.3 Browser Sessions (escape hatch)

```bash
mfetch session start <url>                # open Playwright session
mfetch session click <selector>
mfetch session fill <selector> <text>
mfetch session snapshot                   # current page → markdown
mfetch session screenshot
mfetch session eval <js>
mfetch session end
```

### 4.4 Cache & Config

```bash
mfetch cache list
mfetch cache clear --older-than 7d
mfetch config init                        # generate ~/.maestro-fetch/config.toml
mfetch config show
```

## 5. Smart Router Decision Chain

```
URL enters
 │
 ├─ Match source adapter (@meta pattern)?
 │   └─ requires bb-browser?
 │       ├─ available → bb-browser executes
 │       └─ unavailable → httpx/SDK fallback or error
 │
 ├─ Match built-in adapter?
 │   ├─ pan.baidu.com → BaiduPanAdapter
 │   ├─ dropbox/gdrive/gdocs → CloudAdapter
 │   ├─ youtube/vimeo → MediaAdapter
 │   ├─ *.pdf/xlsx/csv → DocAdapter
 │   └─ *.zip/tif/nc/parquet → BinaryAdapter
 │
 └─ Web content (fallback chain):
     Pass 1: crawl4ai (headless JS render)
     Pass 2: httpx (static pages)
     Pass 3: Cloudflare Browser Rendering (/markdown)
     Pass 4: bb-browser fetch (authenticated)
     Pass 5: playwright-stealth (WAF bypass)
```

## 6. Pluggable Browser Backends

### 6.1 Protocol

```python
class BrowserBackend(Protocol):
    name: str
    async def is_available(self) -> bool
    async def fetch_content(self, url: str) -> str           # → markdown
    async def fetch_screenshot(self, url: str) -> bytes      # → PNG
    async def eval_js(self, js: str) -> Any                  # execute JS
    async def site_adapter(self, name: str, *args) -> dict   # site command
```

### 6.2 Implementations

| Backend | Requires | Strengths |
|---------|----------|-----------|
| bb-browser | npm + Chrome extension | Login state, 100+ site adapters, eval |
| Cloudflare | API key (free tier: 10min/day) | Anti-bot advantage, /crawl endpoint, zero install |
| Playwright | pip install playwright | Interactive sessions, screenshots, PDF |

### 6.3 Config

```toml
[backends]
priority = ["bb-browser", "cloudflare", "playwright"]

[backends.bb-browser]
enabled = true   # auto-detect CLI

[backends.cloudflare]
enabled = false
account_id = ""
api_token = ""

[backends.playwright]
enabled = true
headless = true
```

## 7. Storage Architecture

### 7.1 Directory Layout

```
~/.maestro-fetch/
├── config.toml           # user config
├── cache/                # content-addressed files
├── cache.db              # SQLite cache index
├── sources/              # git clone maestro-fetch-sources
├── custom/               # user private adapters (override community)
└── sessions/             # temp session state JSON
```

### 7.2 SQLite Schema (cache.db)

```sql
CREATE TABLE cache (
    url         TEXT PRIMARY KEY,
    hash        TEXT NOT NULL,
    raw_path    TEXT NOT NULL,
    source_type TEXT NOT NULL,
    size_bytes  INTEGER,
    mime_type   TEXT,
    fetched_at  TEXT NOT NULL,
    ttl_seconds INTEGER DEFAULT 86400,
    etag        TEXT,
    metadata    TEXT  -- JSON blob
);
CREATE INDEX idx_cache_hash ON cache(hash);
CREATE INDEX idx_cache_fetched ON cache(fetched_at);
```

### 7.3 Cache Policy

- Default TTL: 1 day (web), 30 days (binary/doc)
- `--no-cache` bypasses
- `mfetch cache clear --older-than 7d` manual eviction
- `max_size` in config triggers LRU eviction

## 8. Source Adapter Format

### 8.1 File Format

```python
# maestro-fetch-sources/economics/worldbank/gdp.py
"""
@meta
name: worldbank/gdp
description: World Bank GDP data by country code
category: economics
args:
  country: {required: true, description: "ISO 3166 country code", example: "CN"}
  years: {required: false, description: "Number of years", default: 20}
requires: []
output: markdown
"""

async def run(ctx, country, years=20):
    url = f"https://api.worldbank.org/v2/country/{country}/indicator/NY.GDP.MKTP.CD?format=json&per_page={years}"
    resp = await ctx.fetch(url)
    data = resp.json()
    # parse into markdown table
    return {"content": table_md, "metadata": {"source": "World Bank"}}
```

### 8.2 Context Object

```python
class SourceContext:
    async def fetch(self, url, **kwargs) -> Response     # httpx
    async def browser_fetch(self, url) -> str            # bb-browser
    async def browser_eval(self, js) -> Any              # bb-browser eval
    async def browser_site(self, adapter, *args) -> dict # bb-browser site
    cache: CacheManager
    config: dict
```

### 8.3 Categories

economics, finance, politics, climate, social, academic, government, industrial, internet

### 8.4 Discovery

1. `mfetch source update` → git pull ~/.maestro-fetch/sources/
2. Loader scans .py files, parses @meta comments
3. Registers into router (URL pattern match or `mfetch source run <name>`)
4. ~/.maestro-fetch/custom/ overrides community adapters of same name

## 9. Relationship with bb-browser

Complementary, not competing:
- bb-browser: real browser + login state + site adapters + CDP eval
- maestro-fetch: file parsing + data sources + multi-backend orchestration + agent-friendly output

maestro-fetch wraps bb-browser as one of its pluggable backends. Users who install bb-browser automatically unlock 100+ site adapters. Users without bb-browser still get full functionality via Cloudflare, Playwright, and built-in adapters.

## 10. Migration from Current Codebase

### Phase 1: Restructure (no new features)
- Move `maestro_fetch/` → `src/maestro_fetch/`
- Split `interfaces/cli.py` → `cli/` directory
- Remove `interfaces/mcp_server.py`
- Merge examples from both copies (projects/ and maestro-skills/)
- Move SKILL.md into `skills/fetch/`
- Update pyproject.toml (src layout, mfetch alias, remove mcp dep)
- Update git remote to maestro-ai-stack
- Add LICENSE, update README

### Phase 2: New capabilities
- Add `core/cache.py` (SQLite)
- Add `backends/` (BrowserBackend protocol + bb_browser + cloudflare + playwright)
- Add `adapters/browser.py` (dispatch to backends)
- Add `adapters/session.py` (interactive Playwright sessions)
- Add `sources/loader.py` (scan @meta, register)
- Add `cli/source.py`, `cli/session.py`, `cli/cache.py`, `cli/config.py`
- Add config.toml support

### Phase 3: Open-source release
- Create maestro-ai-stack/maestro-fetch-sources with initial adapters
- Publish to PyPI: `pip install maestro-fetch`
- Add GitHub Actions CI (lint, test, publish)
- Write llms.txt, README with badges
- Submit to Claude Code plugin marketplace (optional)

## 11. pyproject.toml (target state)

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "maestro-fetch"
version = "0.2.0"
description = "Fetch everything, for agents. Universal data acquisition with smart routing."
readme = "README.md"
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [{name = "Maestro AI", email = "hello@maestro.onl"}]
keywords = ["agent", "fetch", "scraping", "data-acquisition", "llm", "cli"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Internet :: WWW/HTTP",
    "Topic :: Scientific/Engineering",
]
dependencies = [
    "crawl4ai>=0.4.0",
    "httpx>=0.27",
    "html2text>=2024.2",
    "typer>=0.12",
    "pandas>=2.2",
    "aiofiles>=23.0",
    "aiosqlite>=0.20",
    "tomli>=2.0; python_version<'3.11'",
]

[project.scripts]
maestro-fetch = "maestro_fetch.cli:app"
mfetch = "maestro_fetch.cli:app"

[project.optional-dependencies]
pdf = ["docling>=2.0", "openpyxl>=3.1"]
media = ["yt-dlp>=2024.1", "openai-whisper>=20231117"]
browser = ["playwright>=1.40"]
anthropic = ["anthropic>=0.34"]
openai = ["openai>=1.40"]
all = [
    "maestro-fetch[pdf]",
    "maestro-fetch[media]",
    "maestro-fetch[browser]",
    "maestro-fetch[anthropic]",
    "maestro-fetch[openai]",
]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "pytest-mock>=3.14", "ruff>=0.4"]

[tool.hatch.build.targets.wheel]
packages = ["src/maestro_fetch"]

[tool.ruff]
line-length = 120
target-version = "py311"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```
