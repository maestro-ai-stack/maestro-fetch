"""browser-use backend -- LLM-driven universal browser automation.

Requires: pip install browser-use>=0.2
Uses an LLM (default: claude-sonnet) to drive a real browser via
natural language task descriptions. The ultimate fallback layer.
"""
from __future__ import annotations

import asyncio
from typing import Any

from maestro_fetch.core.errors import FetchError

_TIMEOUT = 120  # seconds (LLM-driven tasks can be slow)


def _is_importable() -> bool:
    """Check if browser-use is installed."""
    try:
        import browser_use  # noqa: F401

        return True
    except ImportError:
        return False


class BrowserUseBackend:
    """LLM-driven browser automation via browser-use."""

    name: str = "browser-use"

    def __init__(self, model: str = "claude-sonnet-4-20250514", timeout: int = _TIMEOUT) -> None:
        self._model = model
        self._timeout = timeout

    async def is_available(self) -> bool:
        """Return True if browser-use is importable."""
        return _is_importable()

    async def execute_task(self, task: str, url: str | None = None) -> dict:
        """Execute a natural language task via browser-use.

        Parameters
        ----------
        task : str
            Natural language description of what to do.
        url : str | None
            Optional starting URL. If provided, the agent navigates here first.
        """
        try:
            from browser_use import Agent
        except ImportError as exc:
            raise FetchError(
                "browser-use requires: pip install 'browser-use>=0.2'"
            ) from exc

        import os

        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        openrouter_key = os.environ.get("OPENROUTER_API_KEY")

        if anthropic_key:
            from browser_use.llm.anthropic.chat import ChatAnthropic

            llm = ChatAnthropic(model=self._model, api_key=anthropic_key)
        elif openrouter_key:
            from browser_use.llm.openrouter.chat import ChatOpenRouter

            # Map exact model IDs to OpenRouter format
            or_model = self._model
            if not or_model.startswith("anthropic/"):
                or_model = f"anthropic/{or_model}"
            # OpenRouter uses simplified names (e.g. claude-sonnet-4 not claude-sonnet-4-20250514)
            or_model = or_model.split("-2025")[0].split("-2024")[0].split("-2026")[0]
            llm = ChatOpenRouter(
                model=or_model,
                api_key=openrouter_key,
            )
        else:
            raise FetchError(
                "browser-use needs ANTHROPIC_API_KEY or OPENROUTER_API_KEY in env"
            )

        full_task = task
        if url:
            full_task = f"Go to {url} and then: {task}"

        agent = Agent(task=full_task, llm=llm)

        try:
            result = await asyncio.wait_for(
                agent.run(), timeout=self._timeout
            )
        except asyncio.TimeoutError:
            raise FetchError(
                f"browser-use timed out after {self._timeout}s: {task[:80]}"
            )

        # browser-use returns an AgentHistory; extract final result
        if hasattr(result, "final_result"):
            return {
                "success": True,
                "result": result.final_result(),
                "task": task,
            }
        # Fallback for different browser-use versions
        return {
            "success": True,
            "result": str(result),
            "task": task,
        }

    # -- BrowserBackend protocol stubs ----------------------------------

    async def fetch_content(self, url: str) -> str:
        """Fetch page content by asking the LLM agent to extract it."""
        result = await self.execute_task(
            "Extract the main content of this page as markdown text.", url=url
        )
        return result.get("result", "")

    async def fetch_screenshot(self, url: str) -> bytes:
        raise FetchError("browser-use does not support direct screenshots")

    async def eval_js(self, js: str) -> Any:
        raise FetchError("browser-use does not support direct JS evaluation")

    async def site_adapter(self, adapter_name: str, *args: str) -> dict:
        """Execute a site adapter task via natural language."""
        task = f"Run the '{adapter_name}' operation"
        if args:
            task += f" with arguments: {', '.join(args)}"
        return await self.execute_task(task)
