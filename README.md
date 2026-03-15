# maestro-fetch

**One interface. Any source. Agent-ready output.**

[![PyPI version](https://img.shields.io/pypi/v/maestro-fetch.svg)](https://pypi.org/project/maestro-fetch/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A Python CLI and SDK that fetches data from any URL -- web pages, PDFs, spreadsheets, cloud storage, video, binary datasets -- and returns agent-friendly markdown or structured data. Smart routing picks the right adapter automatically; pluggable browser backends handle anti-bot and authentication.

```bash
pip install maestro-fetch
mfetch "https://example.com/report.pdf"
```

---

## Why maestro-fetch?

| | maestro-fetch | Firecrawl | Jina Reader | crawl4ai |
|---|---|---|---|---|
| Source types | 7 built-in adapters + community sources | Web pages only | Web pages only | Web pages only |
| PDF / Excel / CSV | Native parsing (Docling) | Requires separate tool | No | No |
| Video transcription | yt-dlp + Whisper | No | No | No |
| Cloud storage | Google Drive, Dropbox, Baidu Pan | No | No | No |
| Binary datasets | GeoTIFF, NetCDF, Parquet, HDF5, ... | No | No | No |
| Browser backends | 3 pluggable (bb-browser, Cloudflare, Playwright) | Hosted only | Hosted only | Playwright only |
| Hosting | Self-hosted, no API key required | SaaS | SaaS | Self-hosted |
| Community adapters | Extensible (economics, finance, climate, ...) | No | No | No |
| Cache | SQLite with TTL and LRU eviction | No | No | No |

maestro-fetch treats "fetch" as a universal problem -- not just web scraping. Give it any URL and it figures out the rest: route to the right adapter, pick a browser backend if needed, parse the content, return markdown or structured data.

---

## Supported Sources

| Adapter | Source types | Examples |
|---|---|---|
| `web` | HTML pages, APIs, SPAs | Any URL; falls back through crawl4ai, httpx, Cloudflare, bb-browser, Playwright |
| `doc` | Documents and spreadsheets | `.pdf`, `.xlsx`, `.xls`, `.ods`, `.csv` |
| `binary` | Archives, geospatial, data science | `.zip`, `.parquet`, `.tif`, `.nc`, `.hdf5`, `.shp`, `.feather` |
| `cloud` | Cloud storage | Google Drive, Google Docs/Sheets, Dropbox |
| `media` | Video and audio | YouTube, Vimeo (transcription via yt-dlp + Whisper) |
| `baidu_pan` | Baidu Pan | `pan.baidu.com` links via OAuth + PCS API |
| `browser` | Authenticated / JS-heavy pages | Playwright interactive sessions |
| `source` | Community adapters | World Bank, FRED, NOAA, academic datasets, ... |

---

## CLI Usage

### Fetch any URL

```bash
mfetch "https://example.com"                       # auto-detect, markdown output
mfetch "https://example.com/report.pdf"            # PDF -> markdown
mfetch "https://example.com" --output json         # JSON output
mfetch "https://example.com" --timeout 120         # custom timeout
mfetch "https://example.com" --batch urls.txt      # batch from file
```

### Community source adapters

```bash
mfetch source update                               # pull latest adapters
mfetch source list                                 # show all adapters
mfetch source list --category economics            # filter by category
mfetch source info worldbank/gdp                   # show args and examples
mfetch source run worldbank/gdp CN                 # fetch World Bank GDP for China
```

### Interactive browser sessions

```bash
mfetch session start "https://login-required.com"
mfetch session fill "#email" "user@example.com"
mfetch session click "#submit"
mfetch session snapshot                            # current page as markdown
mfetch session screenshot                          # save screenshot
mfetch session end
```

### Cache management

```bash
mfetch cache list                                  # show cached entries
mfetch cache clear                                 # clear all
mfetch cache clear --older-than 7d                 # evict old entries
```

### Configuration

```bash
mfetch config init                                 # generate ~/.maestro-fetch/config.toml
mfetch config show                                 # display current config
```

---

## Python SDK

```python
from maestro_fetch import fetch, batch_fetch

# Auto-detect and fetch
result = await fetch("https://example.com/data")
result.content       # markdown text
result.source_type   # "web" | "doc" | "cloud" | "media" | "binary"
result.tables        # list[pd.DataFrame] (if tabular data found)
result.metadata      # provenance dict
result.raw_path      # Path to cached raw file

# Batch with concurrency
results = await batch_fetch(urls, concurrency=10)

# LLM structured extraction (requires ANTHROPIC_API_KEY or OPENAI_API_KEY)
result = await fetch(
    "https://worldbank.org/report.pdf",
    schema={"country": str, "gdp": float},
    provider="anthropic",
)
```

---

## Installation

```bash
# Core -- web, cloud, doc adapters. No API key needed.
pip install maestro-fetch

# Optional extras
pip install maestro-fetch[pdf]       # PDF and Excel parsing (Docling, openpyxl)
pip install maestro-fetch[media]     # YouTube/audio transcription (yt-dlp, Whisper)
pip install maestro-fetch[browser]   # Interactive sessions (Playwright)
pip install maestro-fetch[anthropic] # Claude LLM extraction
pip install maestro-fetch[openai]    # GPT LLM extraction
pip install maestro-fetch[all]       # Everything
```

### Development setup

```bash
git clone https://github.com/maestro-ai-stack/maestro-fetch.git
cd maestro-fetch
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
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
           +----------+----------+----------+----------+
           |          |          |          |          |
      +----v---+ +---v----+ +--v-----+ +--v-----+ +-v--------+
      |  web   | |  doc   | | cloud  | | media  | | source   |
      |adapter | |adapter | |adapter | |adapter | | adapters |
      +----+---+ +--------+ +--------+ +--------+ +----------+
           |
  +--------+--------+--------+
  |        |        |        |
+-v------+ v------+ v--------+
|crawl4ai| Cloud- | Playwright|
|/ httpx | flare  | (fallback)|
+--------+ +------+ +---------+
```

**Router decision chain:**

1. Match community source adapter (`@meta` pattern) -- dispatch to source
2. Match built-in adapter (baidu pan, cloud, media, doc, binary) -- dispatch directly
3. Web content fallback chain: crawl4ai -> httpx -> Cloudflare -> bb-browser -> playwright-stealth

---

## Configuration

Config lives at `~/.maestro-fetch/config.toml`. Generate with `mfetch config init`.

```toml
[cache]
max_size = "2GB"
default_ttl = 86400              # 1 day for web content

[backends]
priority = ["bb-browser", "cloudflare", "playwright"]

[backends.bb-browser]
enabled = true                    # auto-detected from PATH

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

**New source adapters** -- contribute to [maestro-ai-stack/maestro-fetch-sources](https://github.com/maestro-ai-stack/maestro-fetch-sources). Each adapter is a single Python file with an `@meta` header and an `async def run(ctx, ...)` function.

---

## License

MIT

---

Built by [Maestro](https://maestro.onl) -- Singapore AI product studio.
