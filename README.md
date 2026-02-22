# maestro-fetch

> Universal data acquisition toolkit -- fetch from any URL: web, PDF, cloud, video, images.

**[maestro.onl](https://maestro.onl)** | [Documentation](https://maestro.onl/docs) | [Dataset Catalog](https://ra.maestro.onl/data/datasets) | [GitHub](https://github.com/maesto-ai-tech/maestro-fetch)

## Why maestro-fetch?

| Source          | wget | Crawl4AI | Firecrawl | maestro-fetch |
|-----------------|:----:|:--------:|:---------:|:-------------:|
| Static HTML     | yes  | yes      | yes       | yes           |
| JS-rendered     | no   | yes      | yes       | yes           |
| PDF tables      | no   | no       | no        | yes           |
| Excel / CSV     | no   | no       | no        | yes           |
| Dropbox / GDrive| no   | no       | no        | yes           |
| YouTube -> text | no   | no       | no        | yes           |
| Image tables    | no   | no       | no        | yes           |
| Swap LLM model  | n/a  | partial  | no        | yes           |
| Cost            | free | free     | paid      | free          |

## Install

```bash
pip install maestro-fetch            # core: web + cloud + PDF/CSV (no API key needed)
pip install maestro-fetch[pdf]       # + advanced PDF/Excel parsing (Docling)
pip install maestro-fetch[media]     # + YouTube/audio transcription (yt-dlp + Whisper)
pip install maestro-fetch[anthropic] # + Claude LLM extraction (requires ANTHROPIC_API_KEY)
pip install maestro-fetch[openai]    # + GPT-4o LLM extraction (requires OPENAI_API_KEY)
pip install maestro-fetch[mcp]       # + MCP server for Claude Code
pip install maestro-fetch[all]       # everything
```

> **Note:** Core fetching (`fetch`, `batch_fetch`) works without any API key. LLM API keys are only needed when using `schema` or `provider` parameters for structured extraction.

## Quick Start

### CLI

```bash
# Web page -> Markdown
maestro-fetch "https://example.com/data"

# PDF -> CSV tables
maestro-fetch "https://example.com/report.pdf" --output csv

# Dropbox public link -> download + parse
maestro-fetch "https://www.dropbox.com/sh/xxx/file.xlsx?dl=0" --output csv

# YouTube -> transcript
maestro-fetch "https://youtube.com/watch?v=xxx"

# Schema-based LLM extraction
maestro-fetch "https://example.com/page" --schema schema.json --provider anthropic

# Batch fetch
maestro-fetch dummy --batch urls.txt --output-dir ./data/
```

### Python SDK

```python
from maestro_fetch import fetch, batch_fetch

# Single URL
result = await fetch("https://dropbox.com/sh/xxx/data.csv?dl=0")
df = result.tables[0]  # pandas DataFrame

# Schema extraction
result = await fetch(
    "https://worldbank.org/report.pdf",
    schema={"country": str, "gdp": float},
    provider="anthropic",  # or "openai", "gemini", "ollama"
)

# Batch
results = await batch_fetch(["url1", "url2"], concurrency=5)
```

### MCP Server

Add to your Claude Code config:

```json
{
  "mcpServers": {
    "maestro-fetch": {
      "command": "maestro-fetch-mcp"
    }
  }
}
```

Tools: `fetch_url`, `batch_fetch_urls`, `detect_url_type`

## Data Sources

maestro-fetch works with 23+ public data sources out of the box across 6 domains:

| Domain | Sources | Examples |
|--------|---------|----------|
| Weather | 7 | Open-Meteo, NOAA, DWD, CMA, NASA POWER |
| Economics | 4 | FRED, World Bank, OECD, Eurostat |
| Labor | 3 | BLS, ILO, Japan e-Stat |
| Politics | 3 | V-Dem, WGI, Freedom House |
| Environment | 3 | WAQI, EPA AQS, Copernicus |
| Urban | 3 | US Census, OpenStreetMap, GTFS |

Browse the full catalog with API endpoints, auth requirements, and example queries at **[ra.maestro.onl/data/datasets](https://ra.maestro.onl/data/datasets)**.

See working examples in the [`examples/`](./examples/) directory:
- [`global_weather.py`](./examples/global_weather.py) -- 30 cities, 4 data strategies
- [`china_weather_historical.py`](./examples/china_weather_historical.py) -- decades of daily records

## FetchResult

```python
result.url          # original URL
result.source_type  # "web" | "doc" | "cloud" | "media"
result.content      # Markdown text
result.tables       # list[pd.DataFrame]
result.metadata     # dict with provenance info
result.raw_path     # Path to cached raw file
```

## Architecture

```
URL -> Router (detect_type) -> Adapter (fetch) -> FetchResult
                                  |
                            LLM Provider (optional extraction)
```

Adapters: `CloudAdapter`, `DocAdapter`, `WebAdapter`, `MediaAdapter`
Providers: `AnthropicProvider`, `OpenAIProvider` (pluggable via registry)

## Professional Data Services

Need custom data pipelines, panel data construction, or large-scale data engineering for academic research? **[RA Data](https://ra.maestro.onl/data)** provides professional data services powered by maestro-fetch.

## License

MIT

---

Built by **[Maestro](https://maestro.onl)** -- Singapore AI product studio.
