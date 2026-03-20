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
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise FetchError(
                "browser-use requires: pip install 'browser-use>=0.2' 'langchain-anthropic'"
            ) from exc

        llm = ChatAnthropic(model_name=self._model)

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
