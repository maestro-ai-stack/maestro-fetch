<p align="center">
  <img src=".github/maestro-logo.png" alt="Maestro" width="120" />
</p>

<h1 align="center">maestro-fetch</h1>

<p align="center">
  <strong>One interface. Any source. Agent-ready output.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/maestro-fetch/"><img src="https://img.shields.io/pypi/v/maestro-fetch.svg" alt="PyPI version" /></a>
  <a href="https://pepy.tech/project/maestro-fetch"><img src="https://static.pepy.tech/badge/maestro-fetch/month" alt="Downloads" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+" /></a>
  <a href="https://github.com/maestro-ai-stack/maestro-fetch/actions"><img src="https://img.shields.io/github/actions/workflow/status/maestro-ai-stack/maestro-fetch/ci.yml?label=CI" alt="CI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT" /></a>
  <a href="https://github.com/anthropics/skills"><img src="https://img.shields.io/badge/skills-ecosystem-blueviolet" alt="Skills Ecosystem" /></a>
</p>

Give it any URL -- web page, PDF, spreadsheet, cloud file, video, binary dataset -- and get back clean markdown or structured data. Smart routing picks the right adapter; the native browser stack handles authentication and JS-heavy pages. No API key is required for core fetching.

Today, "universal" means one CLI for the currently supported adapters and browser workflows: public web, authenticated Chrome-backed web sessions, documents, cloud share links, media, Baidu Pan, and common binary/data files. It does not yet mean every URI scheme in the roadmap.

---

## Quickstart

### For AI Agents

```bash
# Claude Code -- install as a skill (Vercel skills ecosystem)
npx skills add maestro-ai-stack/maestro-fetch -y -g

# Claude Code -- install as a plugin (marketplace)
/plugin marketplace add maestro-ai-stack/maestro-fetch
/plugin install maestro-fetch@maestro-fetch
```

Works with: **Claude Code** | **Cursor** | **Codex** | **Gemini CLI** | **OpenCode** | **Trae** and any agent that speaks MCP or CLI tools.

### For Developers

```bash
# Recommended (global command, no venv needed)
uv tool install maestro-fetch

# Or with all extras (PDF, media, browser, LLM, social)
uv tool install "maestro-fetch[all]"

# Classic pip
pip install maestro-fetch
```

```bash
mfetch "https://example.com"
# equivalent explicit form:
mfetch main "https://example.com"
```

Try it now:

```bash
$ mfetch "https://api.worldbank.org/v2/country/CN/indicator/NY.GDP.MKTP.CD?format=json&per_page=5"

## GDP (current US$) - China

| Year | GDP (USD)            |
|------|----------------------|
| 2024 | $17,794,782,410,032  |
| 2023 | $17,662,434,751,902  |
| 2022 | $17,963,170,547,847  |
| 2021 | $17,734,062,645,371  |
| 2020 | $14,687,674,437,370  |
```

```bash
$ mfetch "https://arxiv.org/pdf/2301.07041"

## Dissociating language and thought in large language models ...
(full paper text as clean markdown)
```

If you find this useful, consider giving it a star -- it helps others discover the project.

---

## Why maestro-fetch?

AI agents need data from the web. Most rely on built-in tools like `WebFetch` (Claude Code), `curl`, or `requests`. Here's why mfetch is better:

### mfetch vs built-in agent tools

| Dimension | **mfetch** | **WebFetch** (Claude Code built-in) |
|-----------|-----------|-------------------------------------|
| **Speed** | httpx direct — no LLM overhead | HTTP GET + small model processing (extra round-trip) |
| **Token cost** | Raw content → main model. **Single pass.** | Small model summarizes → main model reads summary. **Double pass.** |
| **Content quality** | Full raw markdown, tables as DataFrames, PDFs via Docling | Summarized by small model — large pages truncated, details lost |
| **Recall rate** | Native browser stack (httpx → Extension), login session reuse, authenticated Chrome execution when needed | Plain HTTP GET only — no JS rendering, no auth, WAF blocks fail |

### mfetch vs other fetch tools

| | mfetch | Firecrawl | Jina Reader | crawl4ai |
|---|---|---|---|---|
| Source types | 7 adapters + community sources | Web only | Web only | Web only |
| PDF / Excel / CSV | Native (Docling + openpyxl) | Separate tool | No | No |
| Video transcription | yt-dlp + Whisper | No | No | No |
| Cloud storage | Google Drive, Dropbox, Baidu Pan | No | No | No |
| Binary datasets | GeoTIFF, NetCDF, Parquet, HDF5, Stata, ... | No | No | No |
| Browser backends | Native stack (Extension + httpx) | Hosted only | Hosted only | Playwright only |
| Auth / login reuse | Extension reuses Chrome sessions and cookies | No | No | No |
| Hosting | Local, no API key required | SaaS ($) | SaaS ($) | Local |
| Community adapters | Extensible (economics, climate, social, ...) | No | No | No |
| Cache | SQLite + content-addressed + TTL + LRU | No | No | No |
| Batch operations | Concurrent with configurable parallelism | API-based | No | No |
| Interactive sessions | `mfetch tab` + `mfetch do` | No | No | No |

maestro-fetch treats "fetch" as a universal problem -- not just web scraping. Give it any URI and it figures out the rest: route to the right adapter, pick a browser backend if needed, parse the content, return markdown or structured data.

---

## Benchmarks

Tested on macOS (Apple Silicon), Python 3.11, uv 0.11.2. March 2026.

### Installation

| Method | Time | Notes |
|--------|------|-------|
| `uv tool install "maestro-fetch[all]"` | **~8s** (200 packages) | Global command, no venv management |
| `pip install "maestro-fetch[all]"` | ~45s | Requires manual venv setup |

### Fetch speed (single URL, public static page)

| Tool | Pipeline | Latency |
|------|----------|---------|
| **mfetch** (httpx) | HTTP GET → html2text → raw markdown | **~200ms** |
| **mfetch** (Extension) | Chrome tab → extract → markdown | ~500ms |
| **WebFetch** | HTTP GET → html2text → small LLM call → summary | ~2-5s |
| **curl + manual parse** | HTTP GET → raw HTML (no processing) | ~150ms |

### Token efficiency

| Tool | Flow | Effective token cost |
|------|------|---------------------|
| **mfetch** | Raw content → main model (Opus/Sonnet) processes it | **1x** |
| **WebFetch** | Small model processes content (hidden tokens) → summary → main model | **~2x** (double pass) |

### Content fidelity

| Scenario | mfetch | WebFetch |
|----------|--------|----------|
| 10 KB HTML page | 100% content preserved | ~90% (minor summarization) |
| 100 KB HTML page | 100% content preserved | ~60% (significant truncation) |
| PDF with tables | Tables as DataFrames, full text | Not supported |
| JS-rendered SPA | Full render via Extension | Fails (no JS engine) |
| Login-required page | Extension reuses Chrome session | Fails (no auth) |

---

## Supported Sources

| Adapter | Source types | Examples |
|---|---|---|
| `web` | HTML pages, APIs, SPAs | Any URL; uses httpx first, then the native extension backend when browser execution is required |
| `doc` | Documents and spreadsheets | `.pdf`, `.xlsx`, `.xls`, `.ods`, `.csv` |
| `binary` | Archives, geospatial, data science | `.zip`, `.parquet`, `.tif`, `.nc`, `.hdf5`, `.shp`, `.feather` |
| `cloud` | Cloud storage | Google Drive, Google Docs/Sheets, Dropbox |
| `media` | Video and audio | YouTube, Vimeo (transcription via yt-dlp + Whisper) |
| `baidu_pan` | Baidu Pan | `pan.baidu.com` links via OAuth + PCS API |
| `browser` | Authenticated / JS-heavy pages | Chrome extension-backed interactive sessions |
| `source` | Community adapters | World Bank GDP, Open-Meteo weather, arXiv search, GitHub trending, Hacker News, Reddit (4 adapters) |
| `.eml`, `.msg` files | Email | Message body + metadata extraction |

---

## Site Adapters

Interact with social platforms directly from the CLI. All operations run in a background Chrome tab — **zero focus stealing**.

```bash
# Twitter/X
mfetch twitter timeline             # Home feed (GraphQL)
mfetch twitter search "AI agents"   # Search tweets
mfetch twitter reply "text" "url"   # Reply to a tweet
mfetch twitter post "hello world"   # Post a new tweet
mfetch twitter thread "url"         # Read a full thread
mfetch twitter like "url"           # Like a tweet
mfetch twitter bookmark "url"       # Bookmark a tweet
mfetch twitter bookmarks            # List your bookmarks
mfetch twitter trending             # Trending topics

# Xiaohongshu (小红书)
mfetch xiaohongshu feed             # Home feed
mfetch xiaohongshu search "上海"    # Search notes
mfetch xiaohongshu publish "text"   # Publish a note
mfetch xiaohongshu creator-notes    # Creator dashboard
mfetch xiaohongshu creator-profile  # Creator stats

# WeChat (微信公众号)
mfetch weixin article "url"         # Read article → Markdown
mfetch weixin search "query"        # Search via Sogou
```

Requires: Chrome with the maestro-fetch extension. Log into each platform in Chrome first.

Custom adapters go in `~/.maestro-fetch/custom/<site>/<command>.py` — auto-discovered, no registration needed.

---

## CLI Usage

### Fetch any URL

```bash
mfetch "https://example.com"                       # auto-detect, markdown output
mfetch main "https://example.com"                  # explicit fetch subcommand form
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

### Interactive browser tasks

```bash
mfetch discover "https://login-required.com"
mfetch tab list                                    # List all Chrome tabs
mfetch tab find "x.com"                            # Find tab by URL/title
mfetch tab snapshot 123                            # Get page content as markdown
mfetch tab screenshot 123                          # Take a screenshot
mfetch tab exec 123 "document.title"               # Execute JS in tab
mfetch tab click 123 ".btn"                        # Click an element
mfetch tab fill 123 "#input" "val"                 # Fill a form field
mfetch tab type 123 "hello"                        # Type via keyboard events
mfetch do "log into this site and open the billing page" --url "https://login-required.com"
```

`mfetch tab` is the low-level browser control surface for existing Chrome tabs.
`mfetch do` is the higher-level browser operator that plans over the same native browser stack, including page reads, screenshots, real keyboard typing, coordinate clicks, waits, and JS execution.

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

### Recommended: uv (global command, no venv)

```bash
uv tool install maestro-fetch                # core only
uv tool install "maestro-fetch[all]"         # everything (PDF, media, LLM, social, native browser daemon)
```

### pip

```bash
pip install maestro-fetch                    # core
pip install maestro-fetch[pdf]               # PDF + Excel (Docling, openpyxl)
pip install maestro-fetch[media]             # YouTube/audio (yt-dlp, Whisper)
pip install maestro-fetch[anthropic]         # Claude LLM extraction
pip install maestro-fetch[openai]            # GPT LLM extraction
pip install maestro-fetch[social]            # Twitter/Reddit API adapters
pip install maestro-fetch[all]               # Everything
```

### Development setup

```bash
git clone https://github.com/maestro-ai-stack/maestro-fetch.git
cd maestro-fetch
uv sync --extra dev                          # or: python3.11 -m venv .venv && pip install -e ".[dev]"
pytest tests/ -v
```

### Test matrix

```bash
pytest -q                 # stable local/CI suite
pytest --run-network -q   # live network regression suite
```

---

## Works With

maestro-fetch integrates as a tool or skill in these AI agent environments:

- **Claude Code** -- via [skills ecosystem](https://github.com/anthropics/skills) or [plugin marketplace](https://github.com/anthropics/claude-code-plugins)
- **Cursor** -- as a CLI tool in agent mode
- **OpenAI Codex** -- as a shell tool
- **Gemini CLI** -- as an MCP tool
- **OpenCode / Trae** -- via CLI or MCP bridge

See the [maestro-fetch skill definition](https://github.com/maestro-ai-stack/maestro-fetch/tree/main/skill) for integration details.

---

## Architecture

```
CLI / SDK / MCP
       ↓
   Router (URL type detection via regex)
       ↓
   Adapter dispatch (priority: BaiduPan > Cloud > Binary > Doc > Web)
       ↓
   Web adapter native stack:
       httpx (plain async GET, fastest for static pages)
           ↓ login wall / JS requirement
       Extension (real Chrome + mfetch daemon, full auth)
       ↓
   Optional: LLM extraction (--schema)
       ↓
   Cache (SQLite + content-addressed files, TTL)
       ↓
   FetchResult → markdown | json | csv | parquet
```

**Router decision chain:** (1) match community source adapter (`@meta`) → dispatch to source; (2) match built-in adapter by URL pattern → dispatch directly; (3) native web stack for everything else.

Current product surface:

- Fetch and parse public or authenticated web pages
- Operate Chrome via `mfetch tab` and `mfetch do`
- Download and parse PDFs, spreadsheets, CSV/JSON docs
- Download cloud share files from Google Drive/Docs/Sheets/Dropbox
- Download from Baidu Pan via OAuth + browser-assisted save flow
- Download media transcripts from YouTube/Vimeo paths supported by `yt-dlp`
- Download binary/data artifacts like Parquet, GeoTIFF, NetCDF, HDF5, ZIP

---

## Configuration

Config lives at `~/.maestro-fetch/config.toml`. Generate with `mfetch config init`.

```toml
[cache]
max_size = "5GB"
default_ttl = 86400

[automation]
model = "claude-sonnet-4-20250514"
timeout = 120

[backends]
priority = ["extension"]

[backends.extension]
enabled = true
port = 19825

```

Storage: `~/.maestro-fetch/` contains `config.toml`, `cache.db`, `cache/`, `sources/`, `custom/`, `auth/`.

---

## Roadmap

### 0.3.x — Polish

- **Streaming output** — yield chunks as they arrive for long pages and large PDFs
- **MCP server** — expose mfetch as an MCP tool for any agent (FastMCP)
- **Retry with backoff** — configurable retry policy per adapter
- **`mfetch pipe`** — stdin/stdout piping for Unix composability

### 0.4.x — Power

- **Parallel batch with progress** — tqdm progress bar, per-URL status reporting
- **Diff mode** — `mfetch diff <url>` compares cached vs live content, shows delta
- **Schema library** — pre-built extraction schemas for common pages (arXiv, PubMed, SEC filings, ...)
- **Proxy rotation** — SOCKS5/HTTP proxy support for high-volume scraping

### 1.0 — Fetch Anything

Any URI scheme → `mfetch <uri>` → clean structured output.

- **Database** — `mfetch postgres://...` / `mfetch bigquery://...` → DataFrame
- **Cloud objects** — `mfetch s3://bucket/key` / `mfetch gs://...` / `mfetch az://...`
- **FTP/SFTP** — `mfetch sftp://host/path`
- **Email** — `mfetch imap://...` → extract attachments and body
- **Torrent** — `mfetch magnet:?xt=...`
- **IPFS** — `mfetch ipfs://Qm...`
- **Real-time feeds** — `mfetch ws://...` / `mfetch mqtt://...`
- **Plugin marketplace** — `mfetch plugin install <name>`
- **Watch mode** — `mfetch watch <url> --interval 5m` with change detection

---

## Contributing

**Core improvements** -- open issues and PRs on this repo.

**New source adapters** -- add a Python file to `src/maestro_fetch/sources/community/`. Each adapter is a single file with an `@meta` header and an `async def run(ctx, ...)` function.

---

## License

MIT

---

<p align="center">
  Built by <a href="https://maestro.onl">Maestro</a> — Singapore AI product studio.
</p>
