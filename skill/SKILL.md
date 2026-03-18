---
name: maestro-fetch
description: |
  Download any file or data from a URL to local disk via mfetch CLI.
  Triggers: mfetch, maestro-fetch CLI, download URL, 下载.
  Do NOT use for: browser automation → browser.
---

# maestro-fetch — Universal File Acquisition

## Role in the Pipeline

maestro-fetch does ONE thing: **get the file to disk**.

```
URL  →  maestro-fetch  →  ~/.maestro/cache/<filename>
                                     ↓
                          maestro-data-analyst
                          maestro-data-qa
                          maestro-data-ocr
                          (any downstream skill)
```

It does NOT clean, transform, or analyze. Once `raw_path` exists, hand off.

## Recommended Usage Pattern

### Step 1 — Acquire (maestro-fetch)

```python
from maestro_fetch import fetch
import asyncio

result = asyncio.run(fetch("https://any-url.com/data.xlsx"))
print(result.raw_path)   # ~/.maestro/cache/data.xlsx  ← hand this off
```

Or via CLI:
```bash
maestro-fetch "https://example.com/data.xlsx"
# raw file saved to ~/.maestro/cache/data.xlsx
# prints markdown preview to stdout
```

### Step 2 — Process (downstream skill)

```python
import pandas as pd

# Downstream script receives raw_path and works from there
df = pd.read_excel(result.raw_path)   # or pd.read_csv(...)
# ... cleaning, analysis, QA
```

**The handoff contract:** `result.raw_path` is the only thing maestro-fetch guarantees downstream. `result.tables` and `result.content` are convenience previews, not the authoritative output.

---

## URL Auto-Detection

| URL Pattern | Adapter | What Gets Downloaded |
|-------------|---------|----------------------|
| `pan.baidu.com/s/*` | BaiduPan | xlsx/csv from share (playwright + PCS OAuth) |
| `dropbox.com/*` | Cloud | resolved file |
| `drive.google.com/*` | Cloud | resolved file |
| `docs.google.com/document/d/*` | Cloud | exported as .txt |
| `docs.google.com/spreadsheets/d/*` | Cloud | exported as .csv |
| `docs.google.com/presentation/d/*` | Cloud | exported as .pdf |
| `youtube.com/watch*` | Media | audio transcript |
| `*.zip` `*.gz` `*.tar` `*.bz2` `*.7z` | Binary | streamed to disk, progress bar, cache-hit skip |
| `*.shp` `*.nc` `*.geotiff` `*.tif` | Binary | geospatial binary — streamed |
| `*.parquet` `*.feather` `*.h5` `*.nc` | Binary | data science binary — streamed |
| `*.dta` `*.sas7bdat` `*.rds` | Binary | stats software binary — streamed |
| `*.pdf` | Doc | PDF file |
| `*.xlsx`, `*.csv` | Doc | spreadsheet file |
| Everything else | Web | HTML → markdown (crawl4ai; httpx fallback) |

Adapter priority: **BaiduPan** > Cloud > **Binary** > Doc > Web

**Binary adapter features:**
- HEAD request → Content-Length → **cache hit detection** (skip re-download if size matches)
- **Streaming** (1 MB chunks) → safe for files >500 MB (no OOM)
- **Range-resume with auto-retry** (up to 5×): sends `Range: bytes=N-` on reconnect; appends if server returns 206, restarts if 200 (no Range support)
- ASCII progress bar with size/percentage
- 1-hour read timeout for slow servers
- Covers: `.zip .gz .tar .bz2 .7z .rar .shp .nc .tiff .parquet .feather .h5 .dta .sas7bdat .rds .npy` and more

---

## CLI Reference

```bash
# Download any URL — raw file to ~/.maestro/cache/
maestro-fetch "https://example.com/data.xlsx"

# Save parsed CSV to a specific directory
maestro-fetch "https://example.com/data.xlsx" --output csv --output-dir ./out/

# Batch (one URL per line)
maestro-fetch dummy --batch urls.txt --output-dir ./data/

# Custom cache location
maestro-fetch "https://..." --cache-dir /tmp/myproject/
```

Default cache: `~/.maestro/cache/` (global, shared across projects)

---

## Python SDK Reference

```python
from maestro_fetch import fetch, batch_fetch

# Single URL
result = await fetch("https://any-url.com/data")
result.raw_path      # Path — the downloaded file (authoritative output)
result.tables        # list[pd.DataFrame] — convenience parse (may be empty)
result.content       # str — markdown preview
result.source_type   # "web" | "doc" | "cloud" | "media" | "baidu_pan"
result.metadata      # dict — adapter-specific info

# Batch with concurrency
results = await batch_fetch(urls, concurrency=10)

# Custom timeout / headers
result = await fetch(url, timeout=120, headers={"User-Agent": "my-app"})
```

---

## Baidu Pan (百度网盘) Share Links

**One-time setup** — triggers automatically on first use:
```bash
maestro-fetch "https://pan.baidu.com/s/1xxxxx?pwd=abcd"
# Browser opens → log in → OAuth token saved to ~/.bypy/bypy.json
```

**Usage:**
```bash
maestro-fetch "https://pan.baidu.com/s/1xxxxx?pwd=abcd"
# Downloads primary data file (xlsx > xls > csv > json > pdf) from share
# Saved to ~/.maestro/cache/<filename>
```

**How it works:**
1. Opens share URL in playwright persistent browser (`~/.maestro_fetch/playwright_profile`)
2. Intercepts `share/list` XHR (before goto) to get filename
3. Clicks 保存到网盘 (silently skips if already saved)
4. PCS API + OAuth token → dlink → download bytes
5. Share is a directory → recurse, pick primary data file

**Pitfalls (hard-won):**
- `wait_until="networkidle"` times out — Baidu SPA polls continuously, use `domcontentloaded`
- bdstoken not in static HTML (SPA) — playwright handles CSRF automatically, never try to extract bdstoken via httpx
- dlink download requires `?access_token=` suffix AND `User-Agent: pan.baidu.com`
- Share always saves to pan root `/` (not configurable); `_resolve_dlink` searches root then recurses dirs

---

## Installation

Not on PyPI. Installed from local source:

```bash
# CLI
/Users/ding/maestro/projects/maestro-fetch/.venv/bin/maestro-fetch

# Python SDK (no install needed)
import sys
sys.path.insert(0, '/Users/ding/maestro/maestro-skills/fetch/scripts')
from maestro_fetch import fetch
```

### MCP Server (Claude Code)

Configured in `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "maestro-fetch": {
      "command": "/Users/ding/maestro/projects/maestro-fetch/.venv/bin/python",
      "args": ["-c", "import sys; sys.path.insert(0, '/Users/ding/maestro/maestro-skills/fetch/scripts'); from maestro_fetch.interfaces.mcp_server import mcp; mcp.run()"]
    }
  }
}
```

MCP tools: `fetch_url`, `batch_fetch_urls`, `detect_url_type`

**IMPORTANT**: curl and wget are DENIED. Always use maestro-fetch for any URL download task.

---

## Key Rules

1. maestro-fetch acquires; downstream skills process — do not mix
2. `raw_path` is the handoff contract; `tables`/`content` are previews only
3. No API key needed for core fetch; LLM key only for `schema=` extraction (rarely needed)
4. Default cache `~/.maestro/cache/` is global — do not use per-project relative paths
5. For Open-Meteo long date ranges: chunk into ≤365-day segments

---

## Built-in Public Sources — Additional Notes

### data.gov.sg (Singapore Open Data Portal)
- Base URL: `https://data.gov.sg/api/action/`
- Search datasets: `package_search?q=<keyword>`
- Download: `datastore_search?resource_id=<id>&limit=50000&offset=<N>`
- Rate limiting: Aggressive 429 errors — use 5s delays, exponential backoff
- Pagination: Use offset param; repeat until `records` < `limit`
- GeoJSON boundaries: Direct URL download (no pagination needed)
- Auth: None required
- License: Singapore Open Data Licence v1.0 (free for any use with attribution)

### Zenodo / Figshare Large File Downloads
- **Zenodo CDN does NOT support HTTP Range requests** — responds HTTP 200 (full file) instead of 206 (partial). Never attempt resume/append: always overwrite from scratch or you get a corrupted file (double-size, binary garbage appended).
- DocAdapter streams all binary files from scratch (no Range header), so this does not affect maestro-fetch internal behavior.
- Zenodo API for file list: `curl https://zenodo.org/api/records/{id}` → `files[].links.self` for content URLs
- Figshare API: `curl https://api.figshare.com/v2/articles/{id}` → `files[].download_url`
- Both services redirect to CDN URLs; Content-Disposition header on redirect contains the real filename.

### NASA Earthdata (SEDAC, LP DAAC, etc.)
- Auth via `~/.netrc`: `machine urs.earthdata.nasa.gov login <user> password <pass>`
- curl usage: `curl -L --netrc-file ~/.netrc -c /tmp/ed_cookies.txt -b /tmp/ed_cookies.txt -o out.zip <URL>`
- Token API: `curl -u user:pass https://urs.earthdata.nasa.gov/api/users/tokens` → `[{"access_token": "..."}]`
- **SEDAC China datasets: PERMANENTLY UNAVAILABLE (2026).** CIESIN contract ended 2025-04-30; S3 buckets empty; all 3 China datasets (population census, agricultural stats, county socioeconomic) return HTTP 404. Do NOT attempt download — use USDA FAS PSD or SciDB as alternatives.
- Other SEDAC datasets (non-China) may still work via Earthdata Cloud; check `search.earthdata.nasa.gov` first.
- Download status page: `https://search.earthdata.nasa.gov/downloads/{order_id}` — get order via Earthdata Search UI.

### SciDB (scidb.cn / sciencedb.cn) — Chinese National Science Data
- **Vue.js SPA**: file list uses v-lazy lazy loading — files NOT visible in initial HTML, only rendered after scroll/click.
- **Download mechanism** (from JS bundle reverse engineering):
  - `fileDown(item)` → `genDownloadUrl(item.id)` → `window.open(url)`
  - Download URL = `https://china.scidb.cn/download?fileId=<item.id>` (note: `china.scidb.cn`, NOT `www.scidb.cn`)
  - `window.open()` opens a NEW TAB — `page.on("response")` does NOT capture this; use `context.on("page")` to intercept the popup
  - OR extract `item.id` directly from Vue component tree via `__vue__.$children` walk (no click needed)
- **API endpoints that work**:
  - File listing: `POST https://www.scidb.cn/api/gin-sdb-filetree/public/file/childrenFileListByPath` body `{dataSetId, version, path, lastIndex, pageSize}` — returns empty if version unknown
  - Dataset info: `GET /api/sdb-dataset-service/dataset/details/<id>` requires auth (PERMISSION NO ACCESS without login)
- **API endpoints broken**: `/api/dataset/v2/en/detail` returns 404; `/api/sdb-dataset-service/public/dataset/details/<id>` returns 404.
- **Required approach**: Use playwright + DOM manipulation:
  1. Navigate to `https://www.scidb.cn/en/detail?dataSetId=<id>` with `waitUntil="domcontentloaded"` (NOT networkidle — Nuxt.js polls)
  2. Expand file tree: click `.v-treeview-node__toggle`; wait 2s
  3. Read file list from `.fileTree innerText` (filename on one line, `MD5:<hash> (<size> KB)` on next)
  4. For each file: walk `__vue__.$children` to find node with matching `item.label`, get `item.id`; construct download URL
  5. Download via `GET https://china.scidb.cn/download?fileId=<id>` with httpx (redirects to CDN)
- **Reusable script template**: `scripts/download_scidb.py` in RAD-20260211-0001 project — copy-adapt for new SciDB datasets. Supports `--doi`, `--dataset-id`, `--pattern`, `--list` flags.
- **Auth**: CC BY 4.0 public datasets download without login.
- **Dataset ID format**: `DS_<hex32>` or via DOI redirect: `doi.org/10.57760/sciencedb.<id>` → final URL contains `dataSetId=` query param.
- **File naming**: datasets contain 数据实体.xlsx, 数据文档.docx, 数据样例.xlsx, 缩略图.jpg; download only 数据实体.xlsx.

### FAOSTAT (FAO Agricultural Statistics)
- **WARNING**: FAOSTAT backend is frequently down (HTTP 521 "Web server is down")
- Direct bulk download URL returns 403 (hotlink blocked): `fenixservices.fao.org/faostat/static/bulkdownloads/*.zip`
- **Fallback 1 (best)**: USDA FAS PSD — same data, always available:
  - Grains only: `https://apps.fas.usda.gov/psdonline/downloads/psd_grains_pulses_csv.zip` (2.8MB)
  - All commodities: `https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip` (10MB)
  - Columns: `Commodity_Description, Country_Name, Market_Year, Attribute_Description, Value, Unit_Description`
  - Yield unit: MT/HA (multiply ×1000 for kg/ha)
  - Filter: `Attribute_Description == 'Yield'` + country + crop
- **Fallback 2**: World Bank API (national cereal yield only):
  - `https://api.worldbank.org/v2/country/CN/indicator/AG.YLD.CREL.KG?format=json&per_page=100&mrv=40`
- **Limitation**: both fallbacks are national-level only. Province-level yield requires NBS yearbooks (Chinese, manual extraction).

---

## Gotchas (Hard-Won)

### File extension cannot be trusted
Downloaded files may have wrong extensions. SciDB `.xls` files have been observed to contain OOXML `.docx` content (Word document with metadata/logos, not spreadsheet data). Always verify:
```python
import magic  # python-magic
mime = magic.from_file(str(raw_path), mime=True)
# Expected: 'application/vnd.ms-excel' or 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
# Got: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' → wrong!
```
Fallback without python-magic: try `pd.read_excel()` and catch exceptions; or check first 4 bytes (`PK\x03\x04` = zip-based Office, then inspect `[Content_Types].xml` inside).

### Downloaded archive may contain applications, not data
Example: `nongzuowu.zip` (105MB) from a Chinese agricultural statistics site contained a complete Java Spring Boot web application (RuoYi framework) with embedded CSV files, not a standalone dataset. The CSV files inside were national+provincial only (no county-level data), making the entire download useless for the intended purpose.
**Rule**: After downloading any archive, immediately inspect its contents (`zipfile.namelist()` or `tar tf`) before assuming it contains the expected data format. Check file sizes, directory structure, and sample content.

### Zenodo CDN ignores Range headers (reminder)
Zenodo responds HTTP 200 (full file) to Range requests instead of 206 (partial). Never attempt resume/append — you get a corrupted double-size file. Always download from scratch or verify file size matches expected before use.
