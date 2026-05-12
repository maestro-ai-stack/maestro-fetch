# Contributing to maestro-fetch

## Setup

```bash
git clone https://github.com/maestro-ai-stack/maestro-fetch
cd maestro-fetch
uv sync --all-extras
```

Run tests:

```bash
uv run pytest tests/
```

Lint + type-check:

```bash
uv run ruff check src/
uv run pyright src/
```

## Adding a Source Adapter

Source adapters live in `src/maestro_fetch/sources/community/`.
Each adapter is a YAML file or a Python module — see existing adapters for examples.

Checklist:
- [ ] Adapter slug is lowercase, hyphen-separated
- [ ] Works without side effects (no focus stealing, no global state)
- [ ] Returns a `FetchResult` with `content`, `content_type`, and `source_url`
- [ ] Has at least one test in `tests/`

For tab-exec adapters (site operations running in Chrome tabs):
- Put the adapter under `sources/community/<site>/`
- Use the `TabExecAdapter` base class
- All actions must run in a background tab — never `window.focus()`

## Coding Standards

- Python 3.11+, `X | None` not `Optional[X]`
- No files over 800 lines
- Type annotations on all public functions
- `asyncio.get_running_loop()` not `get_event_loop()`
- No hardcoded version strings — use `importlib.metadata`

## PR Process

1. Branch from `main`, name it `feat/...` or `fix/...`
2. Keep PRs focused — one feature or fix per PR
3. Update `CHANGELOG.md` under an `## Unreleased` section
4. All tests must pass
5. Fill in the PR template

## Questions

Open a GitHub Discussion or email hello@maestro.onl.
