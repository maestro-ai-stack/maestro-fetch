"""Load source adapters from maestro-fetch-sources directory.

Scans Python files for @meta YAML blocks in their module docstrings,
registers them as SourceAdapter instances that the CLI and router can
invoke (call) on demand.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine

try:
    import yaml as _yaml

    _YAML_AVAILABLE = True
except ImportError:
    _yaml = None  # type: ignore[assignment]
    _YAML_AVAILABLE = False

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class SourceMeta:
    """Metadata parsed from the @meta block of a source adapter file."""

    name: str
    description: str = ""
    category: str = "uncategorized"
    args: dict[str, dict[str, Any]] = field(default_factory=dict)
    requires: list[str] = field(default_factory=list)
    output: str = "markdown"


@dataclass
class SourceAdapter:
    """A loaded source adapter ready for execution."""

    meta: SourceMeta
    file_path: Path
    _module: Any = field(default=None, repr=False)

    @property
    def module(self) -> Any:
        """Lazy-import the adapter module on first access."""
        if self._module is None:
            self._module = _import_module(self.file_path)
        return self._module


class SourceContext:
    """Context object passed to every source adapter ``run()`` function.

    Provides HTTP fetching, browser helpers, cache, and config.
    """

    def __init__(
        self,
        *,
        browser_fetch: Callable[..., Coroutine] | None = None,
        browser_eval: Callable[..., Coroutine] | None = None,
        browser_site: Callable[..., Coroutine] | None = None,
        cache: Any = None,
        config: dict | None = None,
    ) -> None:
        self._browser_fetch = browser_fetch
        self._browser_eval = browser_eval
        self._browser_site = browser_site
        self.cache = cache
        self.config = config or {}

    async def fetch(self, url: str, **kwargs: Any) -> Any:
        """HTTP GET via httpx (thin wrapper)."""
        if httpx is None:
            raise RuntimeError("httpx is required for source adapter fetch()")
        async with httpx.AsyncClient(timeout=30) as client:
            return await client.get(url, **kwargs)

    async def browser_fetch(self, url: str) -> str:
        """Fetch URL through the browser backend (bb-browser preferred)."""
        if self._browser_fetch is None:
            raise RuntimeError("No browser backend available for browser_fetch")
        return await self._browser_fetch(url)

    async def browser_eval(self, js: str) -> Any:
        """Evaluate JS through the browser backend."""
        if self._browser_eval is None:
            raise RuntimeError("No browser backend available for browser_eval")
        return await self._browser_eval(js)

    async def browser_site(self, adapter: str, *args: str) -> dict:
        """Run a site adapter through the browser backend."""
        if self._browser_site is None:
            raise RuntimeError("No browser backend available for browser_site")
        return await self._browser_site(adapter, *args)


# ---------------------------------------------------------------------------
# @meta parsing
# ---------------------------------------------------------------------------

_META_BLOCK_RE = re.compile(
    r"@meta\s*\n(.*?)(?:\n\s*\"\"\"|\Z)", re.DOTALL
)


def _parse_yaml_simple(text: str) -> dict:
    """Minimal YAML-subset parser for when PyYAML is not installed.

    Handles flat key: value pairs and one level of nested dicts.
    Enough for @meta blocks but not a general YAML parser.
    """
    result: dict[str, Any] = {}
    current_key: str | None = None
    current_dict: dict[str, Any] | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        # Top-level key
        if indent == 0 and ":" in stripped:
            if current_key and current_dict:
                result[current_key] = current_dict
                current_dict = None
                current_key = None

            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()

            if not val:
                # Might be a nested block
                current_key = key
                current_dict = {}
            elif val.startswith("[") and val.endswith("]"):
                items = [
                    s.strip().strip("'\"")
                    for s in val[1:-1].split(",")
                    if s.strip()
                ]
                result[key] = items
            else:
                result[key] = val.strip("'\"")
        elif indent > 0 and current_dict is not None and ":" in stripped:
            # Nested key: value (or {k: v, ...} inline dict)
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if val.startswith("{") and val.endswith("}"):
                inner: dict[str, Any] = {}
                for pair in val[1:-1].split(","):
                    if ":" in pair:
                        ik, _, iv = pair.partition(":")
                        iv_clean = iv.strip().strip("'\"")
                        # Coerce booleans and ints
                        if iv_clean == "true":
                            inner[ik.strip()] = True
                        elif iv_clean == "false":
                            inner[ik.strip()] = False
                        elif iv_clean.isdigit():
                            inner[ik.strip()] = int(iv_clean)
                        else:
                            inner[ik.strip()] = iv_clean
                current_dict[key] = inner
            else:
                current_dict[key] = val.strip("'\"")

    if current_key and current_dict:
        result[current_key] = current_dict

    return result


def _parse_yaml(text: str) -> dict:
    if _YAML_AVAILABLE and _yaml is not None:
        result: dict = _yaml.safe_load(text)  # type: ignore[union-attr]
        return result or {}
    return _parse_yaml_simple(text)


def parse_meta(file_path: Path) -> SourceMeta | None:
    """Extract and parse the @meta YAML block from a Python source file.

    Returns None if no @meta block is found.
    """
    source = file_path.read_text(encoding="utf-8")
    match = _META_BLOCK_RE.search(source)
    if not match:
        return None

    raw = match.group(1)
    data = _parse_yaml(raw)
    if not data.get("name"):
        return None

    return SourceMeta(
        name=data["name"],
        description=data.get("description", ""),
        category=data.get("category", "uncategorized"),
        args=data.get("args", {}),
        requires=data.get("requires", []),
        output=data.get("output", "markdown"),
    )


# ---------------------------------------------------------------------------
# Module importing
# ---------------------------------------------------------------------------


def _import_module(file_path: Path) -> Any:
    """Dynamically import a Python file as a module."""
    module_name = f"maestro_fetch_source_{file_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def load_sources(sources_dir: Path) -> list[SourceAdapter]:
    """Scan *sources_dir* recursively for .py files with @meta blocks.

    Returns a list of SourceAdapter instances sorted by name.
    """
    adapters: list[SourceAdapter] = []
    if not sources_dir.is_dir():
        return adapters

    for py_file in sorted(sources_dir.rglob("*.py")):
        if py_file.name.startswith("_"):
            continue
        meta = parse_meta(py_file)
        if meta is not None:
            adapters.append(SourceAdapter(meta=meta, file_path=py_file))

    adapters.sort(key=lambda a: a.meta.name)
    return adapters


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


async def run_adapter(
    adapter: SourceAdapter,
    ctx: SourceContext,
    **kwargs: Any,
) -> dict:
    """Import and execute the adapter's ``run()`` function.

    The adapter module must define::

        async def run(ctx, **kwargs) -> dict

    Returns the dict produced by ``run()``.
    """
    mod = adapter.module
    run_fn = getattr(mod, "run", None)
    if run_fn is None:
        raise RuntimeError(
            f"Source adapter {adapter.meta.name} has no run() function"
        )
    return await run_fn(ctx, **kwargs)
