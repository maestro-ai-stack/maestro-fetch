# Changelog

All notable changes to maestro-fetch are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## 0.3.1 (2026-05-12)

### Added
- Site alias CLI: `mfetch twitter reply` routes to `mfetch source run twitter/reply`
- 16 tab-exec site adapters: Twitter/X (9 commands), Xiaohongshu (5), WeChat (2)
- All site operations run inside background Chrome tabs — zero focus stealing

### Removed
- twikit-based Twitter adapters (replaced by tab-exec adapters)
- twikit dependency from the `social` extras group

### Fixed
- Version reporting: `importlib.metadata` instead of hardcoded string
- `asyncio.get_event_loop()` deprecation → `get_running_loop()`
- Modernized type annotations in CLI (`Optional[X]` → `X | None`)
- Removed dead `interfaces/cli.py`

---

## 0.3.0 (2026-04-22)

### Added
- `mfetch tab` subcommand: attach to existing Chrome tabs via CDP
- CDP-level `type` and `click-at` commands for precise tab automation
- `mfetch do` browser automation loop — extension-first with LLM agent
- Extension tab targeting hardened with selector-missing failure mode
- Legacy opencli daemon header handling

### Changed
- Extension-only browser architecture: session, CDP standalone, and Playwright
  backends removed — one backend, one runtime
- Browser runtime internalized (no external bb-browser dependency)
- Open-source release hardening: internal files and docs sanitized

### Fixed
- CLI `--output-dir` now correctly saves markdown and JSON output to file
- `browser-use` integration uses native LLM classes with OpenRouter fallback

---

## 0.2.1 (2026-03-27)

### Added
- httpx-first fallback chain: httpx → Chrome extension → on-demand browser
- `mfetch do` LLM-guided automation (early preview)
- Email parsing, CSV encoding detection, Excel multi-sheet, dataset preview adapters
- Media adapter: subtitle extraction first, Whisper fallback
- BaiduPan adapter with PCS OAuth + Playwright save flow
- Global `~/.maestro/cache` default cache directory

### Changed
- Replaced bb-browser / Cloudflare / opencli backends with Chrome extension backend
- Dead CDP and Playwright fallback tiers removed from web adapter

### Fixed
- MediaAdapter registration for YouTube / Vimeo / Bilibili / TikTok
- Local file adapter: GBK encoding, pyarrow for dataset preview
- Playwright networkidle timeout in CLI

---

## 0.2.0 (2026-02-22)

### Added
- `src/` layout with CLI subcommand architecture
- Pluggable browser backends and source adapter loader
- SQLite cache manager and TOML config loader
- Screen recording via Playwright + ffmpeg (session mode)
- CDP action layer with SPA-aware navigation
- Integration test suite (web, CSV, Excel, media)
- `llms.txt` for LLM-readable documentation

### Changed
- Full v2 rewrite: modular adapters, typed backends, clean CLI surface

---

## 0.1.x (2026-02-21 and earlier)

Initial release. Single-file fetcher with basic web, image, and Wikimedia support.
