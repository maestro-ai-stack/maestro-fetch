"""opencli backend -- wraps the opencli CLI for 19+ site YAML pipelines.

Requires: npm install -g @jackwener/opencli
All commands delegate to ``opencli <site> <command> ...`` via
asyncio.create_subprocess_exec.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from typing import Any

from maestro_fetch.core.errors import FetchError

_TIMEOUT = 60  # seconds (pipelines can be slow)


class OpencliBackend:
    """Wraps the ``opencli`` CLI as a browser pipeline backend."""

    name: str = "opencli"

    # -- helpers --------------------------------------------------------

    @staticmethod
    async def _run(*cmd: str, timeout: int = _TIMEOUT) -> dict:
        """Run an opencli command and return parsed JSON output."""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise FetchError(
                f"opencli timed out after {timeout}s: {' '.join(cmd)}"
            )

        if proc.returncode != 0:
            err_msg = stderr.decode(errors="replace").strip()
            raise FetchError(
                f"opencli exited {proc.returncode}: {err_msg}"
            )

        raw = stdout.decode(errors="replace").strip()
        if not raw:
            return {"output": ""}

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # opencli may return plain text for some commands
            return {"output": raw}

    # -- protocol methods -----------------------------------------------

    async def is_available(self) -> bool:
        """Return True if ``opencli`` is on PATH."""
        return shutil.which("opencli") is not None

    async def run_pipeline(self, site: str, command: str, **kwargs: Any) -> dict:
        """Run ``opencli <site> <command> [args]``.

        Extra kwargs are passed as ``--key value`` flags.
        """
        cmd = ["opencli", site, command]
        for key, value in kwargs.items():
            cmd.extend([f"--{key}", str(value)])
        return await self._run(*cmd)

    async def explore(self, url: str) -> dict:
        """Run ``opencli explore <url>`` to discover site APIs."""
        return await self._run("opencli", "explore", url)

    async def synthesize(self, url: str, task: str) -> dict:
        """Run ``opencli synthesize <url> <task>`` to generate a pipeline."""
        return await self._run("opencli", "synthesize", url, task)

    # -- BrowserBackend protocol stubs ----------------------------------
    # opencli is not a general browser, so these are minimal.

    async def fetch_content(self, url: str) -> str:
        """Fetch content via opencli explore."""
        result = await self.explore(url)
        return result.get("output", "")

    async def fetch_screenshot(self, url: str) -> bytes:
        raise FetchError("opencli does not support screenshots")

    async def eval_js(self, js: str) -> Any:
        raise FetchError("opencli does not support JS evaluation")

    async def site_adapter(self, adapter_name: str, *args: str) -> dict:
        """Map site adapter calls to opencli pipelines."""
        parts = adapter_name.split("/", 1)
        site = parts[0]
        command = parts[1] if len(parts) > 1 else "default"
        return await self.run_pipeline(site, command)
