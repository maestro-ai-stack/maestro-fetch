---
name: maestro-data-fetch
description: >
  Universal data acquisition. Use when: scraping web pages, downloading files,
  fetching Dropbox or Google Drive public links, extracting PDF tables,
  reading Excel files, transcribing YouTube videos, extracting image tables.
  Wraps maestro-fetch CLI and Python SDK.
triggers:
  - scrape
  - crawl
  - download
  - fetch data
  - dropbox
  - google drive
  - pdf extract
  - excel download
  - video transcribe
  - image table
  - data acquisition
  - get data from url
---

## When to use maestro-fetch

Use this tool for any data acquisition task involving external URLs.
It auto-detects the source type and handles the right parser.

## CLI usage

```bash
# Web page -> Markdown
maestro-fetch "https://example.com/data"

# PDF -> tables
maestro-fetch "https://example.com/report.pdf" --output csv

# Dropbox public link -> download + parse
maestro-fetch "https://www.dropbox.com/sh/xxx/file.xlsx?dl=0" --output csv

# YouTube -> transcript
maestro-fetch "https://youtube.com/watch?v=xxx"

# Schema-based LLM extraction
maestro-fetch "https://example.com/page" --schema schema.json --provider anthropic

# Batch
maestro-fetch dummy --batch urls.txt --output-dir ./data/
```

## Python SDK usage

```python
from maestro_fetch import fetch, batch_fetch

# Single URL
result = await fetch("https://dropbox.com/sh/xxx/data.csv?dl=0")
df = result.tables[0]  # pandas DataFrame

# Schema extraction
result = await fetch(
    "https://worldbank.org/report.pdf",
    schema={"country": str, "gdp": float},
    provider="anthropic"  # or "openai", "gemini", "ollama"
)

# Batch
results = await batch_fetch(["url1", "url2"], concurrency=5)
```

## Output: FetchResult

```python
result.url          # original URL
result.source_type  # "web" | "doc" | "cloud" | "media"
result.content      # Markdown text
result.tables       # list[pd.DataFrame] - extracted tables
result.metadata     # dict - provenance info
result.raw_path     # Path to cached raw file
```

## Install

```bash
pip install maestro-fetch            # web + cloud
pip install maestro-fetch[pdf]       # + PDF/Excel
pip install maestro-fetch[media]     # + YouTube/audio
pip install maestro-fetch[all]       # everything
```
