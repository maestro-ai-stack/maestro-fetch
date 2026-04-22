"""``mfetch do "natural language task"`` — extension-first browser automation.

Uses the Chrome extension backend (real browser, real cookies) for interaction,
with LLM planning the actions.

Architecture:
    LLM (via API) plans actions based on page content/screenshots
        ↓
    Extension backend executes: navigate, eval_js, screenshot
        ↓
    Real Chrome with user's sessions and cookies
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import textwrap
from typing import Any

import typer

from maestro_fetch.core.errors import FetchError

app = typer.Typer(help="Execute natural language browser tasks.")


def _run(coro):
    return asyncio.run(coro)


SYSTEM_PROMPT = textwrap.dedent("""\
You are a browser automation agent. You interact with web pages by outputting JSON commands.
You will receive the page content (as markdown text) and must decide what action to take.

Available actions (respond with a JSON object):

1. Navigate to URL:
   {"action": "navigate", "url": "https://..."}

2. Execute JavaScript for arbitrary DOM logic:
   {"action": "exec", "code": "document.querySelector('#email').value = 'user@example.com'"}

3. Type into the currently focused element using real keyboard events:
   {"action": "type", "text": "user@example.com"}

4. Click at screen coordinates using native mouse events:
   {"action": "click_at", "x": 640, "y": 420}

5. Capture a screenshot and inspect it on the next turn:
   {"action": "screenshot"}

6. Wait for page changes:
   {"action": "wait", "seconds": 2}

7. Read current page content:
   {"action": "read"}

8. Task complete:
   {"action": "done", "result": "description of what was accomplished", "success": true}

9. Task failed:
   {"action": "done", "result": "description of what went wrong", "success": false}

Rules:
- Output ONLY the JSON command, no other text
- Use CSS selectors to find elements. Prefer: id > name > type > class > text content
- Use "type" for frameworks that need real keyboard events; focus the target first with exec/click
- Use "click_at" when selectors are unstable but the target position is visually obvious
- Use "screenshot" when text content is insufficient to understand the current state
- For Japanese forms, look for labels near inputs to identify fields
- After clicking submit, wait 2s then read the page to verify
- If a page has multiple forms or sections, read it first to understand the structure
- Limit yourself to 15 steps maximum
""")


def _now() -> float:
    return asyncio.get_running_loop().time()


def _remaining_timeout(deadline: float) -> float:
    return max(0.0, deadline - _now())


async def _await_with_deadline(
    awaitable,
    *,
    deadline: float,
    label: str,
    max_slice: float | None = None,
):
    remaining = _remaining_timeout(deadline)
    if remaining <= 0:
        raise FetchError(f"Automation timed out while {label}")

    budget = min(remaining, max_slice) if max_slice is not None else remaining
    try:
        async with asyncio.timeout(budget):
            return await awaitable
    except TimeoutError as exc:
        raise FetchError(f"Automation timed out while {label}") from exc


def _user_text_message(text: str) -> dict[str, Any]:
    return {"role": "user", "content": text}


def _user_image_message(text: str, png_bytes: bytes) -> dict[str, Any]:
    data_uri = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": data_uri}},
        ],
    }


async def _extension_agent_loop(task: str, url: str | None, model: str, timeout: float):
    """Run LLM agent loop using extension backend."""
    from maestro_fetch.backends.extension import ExtensionBackend

    ext = ExtensionBackend()
    deadline = _now() + max(0.001, float(timeout))

    if not await _await_with_deadline(ext.is_available(), deadline=deadline, label="checking extension availability"):
        raise FetchError(
            "Extension backend is not available. "
            "Open Chrome with the maestro-fetch extension enabled."
        )

    typer.echo("Using Chrome extension backend (real browser)")

    # Navigate to starting URL if provided
    if url:
        typer.echo(f"Navigating to: {url}")
        await _await_with_deadline(ext.navigate(url), deadline=deadline, label=f"navigating to {url}")
        await _await_with_deadline(asyncio.sleep(2.0), deadline=deadline, label="waiting for initial page load")

    # Get initial page content
    page_content = await _get_page_content(ext, deadline=deadline)

    # Set up LLM client
    llm_call = _get_llm_caller(model)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Task: {task}\n\nCurrent page content:\n{page_content[:8000]}"},
    ]

    max_steps = 15
    for step in range(max_steps):
        typer.echo(f"\n--- Step {step + 1}/{max_steps} ---")

        # Call LLM
        response = await _await_with_deadline(
            llm_call(messages),
            deadline=deadline,
            label="waiting for LLM response",
            max_slice=60.0,
        )
        typer.echo(f"LLM: {response[:200]}")

        # Parse action — LLM may wrap JSON in text or code blocks
        try:
            action = _parse_json_action(response)
        except (json.JSONDecodeError, ValueError):
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": "Please respond with ONLY a JSON command, no other text."})
            continue

        messages.append({"role": "assistant", "content": json.dumps(action)})

        act = action.get("action", "")

        if act == "done":
            return {
                "success": action.get("success", True),
                "result": action.get("result", ""),
                "task": task,
            }

        elif act == "navigate":
            nav_url = action.get("url", "")
            typer.echo(f"  → Navigating to {nav_url}")
            await _await_with_deadline(ext.navigate(nav_url), deadline=deadline, label=f"navigating to {nav_url}")
            await _await_with_deadline(asyncio.sleep(2.0), deadline=deadline, label="waiting for navigation")
            page_content = await _get_page_content(ext, deadline=deadline)
            messages.append(_user_text_message(f"Navigated. Current page:\n{page_content[:8000]}"))

        elif act == "exec":
            code = action.get("code", "")
            typer.echo(f"  → Executing JS: {code[:100]}")
            try:
                result = await _await_with_deadline(
                    ext.eval_js(code),
                    deadline=deadline,
                    label="executing JavaScript",
                )
                result_str = str(result) if result else "(no return value)"
                typer.echo(f"  → Result: {result_str[:200]}")
                messages.append(_user_text_message(f"JS executed. Result: {result_str[:2000]}"))
            except Exception as e:
                typer.echo(f"  → JS Error: {e}")
                messages.append(_user_text_message(f"JS execution error: {e}"))

        elif act == "type":
            text = str(action.get("text", ""))
            typer.echo(f"  → Typing: {text[:100]}")
            result = await _await_with_deadline(
                ext.type_text(text),
                deadline=deadline,
                label="typing into the page",
            )
            messages.append(_user_text_message(f"Typed text. Result: {result}"))

        elif act == "click_at":
            x = int(action.get("x", 0))
            y = int(action.get("y", 0))
            typer.echo(f"  → Clicking at ({x}, {y})")
            result = await _await_with_deadline(
                ext.click_at(x, y),
                deadline=deadline,
                label="clicking at coordinates",
            )
            messages.append(_user_text_message(f"Clicked at ({x}, {y}). Result: {result}"))

        elif act == "screenshot":
            typer.echo("  → Capturing screenshot")
            png_bytes = await _await_with_deadline(
                ext.screenshot_current(),
                deadline=deadline,
                label="capturing screenshot",
            )
            messages.append(
                _user_image_message(
                    "Current page screenshot. Use this visual state to decide the next action.",
                    png_bytes,
                )
            )

        elif act == "wait":
            secs = min(action.get("seconds", 2), 10)
            typer.echo(f"  → Waiting {secs}s")
            await _await_with_deadline(asyncio.sleep(secs), deadline=deadline, label=f"waiting {secs}s")
            messages.append(_user_text_message("Wait complete."))

        elif act == "read":
            page_content = await _get_page_content(ext, deadline=deadline)
            messages.append(_user_text_message(f"Current page:\n{page_content[:8000]}"))

        else:
            messages.append(
                _user_text_message(
                    f"Unknown action '{act}'. Use navigate/exec/type/click_at/screenshot/wait/read/done."
                )
            )

    return {
        "success": False,
        "result": "Reached maximum steps without completing task",
        "task": task,
    }


async def _get_page_content(ext, deadline: float) -> str:
    """Get current page as markdown text."""
    try:
        code = "document.title + '\\n\\n' + document.body.innerText"
        result = await _await_with_deadline(
            ext.eval_js(code),
            deadline=deadline,
            label="reading page content",
        )
        return str(result) if result else "(empty page)"
    except Exception as e:
        return f"(error reading page: {e})"


def _get_llm_caller(model: str):
    """Return an async function that calls the LLM API."""
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    if openrouter_key:
        or_model = model
        if not or_model.startswith("anthropic/"):
            or_model = f"anthropic/{or_model}"
        or_model = or_model.split("-2025")[0].split("-2024")[0].split("-2026")[0]

        def _openrouter_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
            payload = []
            for message in messages:
                content = message["content"]
                if isinstance(content, str):
                    payload.append(message)
                    continue
                blocks = []
                for block in content:
                    if block["type"] == "text":
                        blocks.append({"type": "text", "text": block["text"]})
                    elif block["type"] == "image_url":
                        blocks.append({"type": "image_url", "image_url": block["image_url"]})
                payload.append({"role": message["role"], "content": blocks})
            return payload

        async def call_openrouter(messages):
            import httpx
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {openrouter_key}"},
                    json={"model": or_model, "messages": _openrouter_messages(messages), "max_tokens": 1024},
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        return call_openrouter

    elif anthropic_key:
        def _anthropic_message_content(content: str | list[dict[str, Any]]) -> str | list[dict[str, Any]]:
            if isinstance(content, str):
                return content

            blocks = []
            for block in content:
                if block["type"] == "text":
                    blocks.append({"type": "text", "text": block["text"]})
                    continue
                image_url = block.get("image_url", {}).get("url", "")
                prefix = "data:image/png;base64,"
                if not image_url.startswith(prefix):
                    continue
                blocks.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_url[len(prefix):],
                        },
                    }
                )
            return blocks

        async def call_anthropic(messages):
            import httpx
            system = ""
            api_messages = []
            for m in messages:
                if m["role"] == "system":
                    system = str(m["content"])
                else:
                    api_messages.append(
                        {
                            "role": m["role"],
                            "content": _anthropic_message_content(m["content"]),
                        }
                    )
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": anthropic_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "system": system,
                        "messages": api_messages,
                        "max_tokens": 1024,
                    },
                )
                resp.raise_for_status()
                return resp.json()["content"][0]["text"]
        return call_anthropic

    else:
        raise FetchError("Need ANTHROPIC_API_KEY or OPENROUTER_API_KEY for mfetch do")

def _parse_json_action(response: str) -> dict:
    """Extract a JSON object from LLM response, handling text wrapping."""
    import re

    text = response.strip()

    # Strip markdown code blocks
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the outermost {...} block using brace counting
    start = text.find('{')
    if start == -1:
        raise ValueError("No JSON object found in response")

    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])

    raise ValueError("No complete JSON object found in response")


@app.callback(invoke_without_command=True, context_settings={"allow_interspersed_args": True})
def do(
    task: str = typer.Argument(..., help="Natural language task description"),
    url: str = typer.Option(None, "--url", "-u", help="Starting URL"),
) -> None:
    """Execute a natural language task via Chrome extension (real browser).

    Uses your real Chrome browser with all cookies and sessions.
    """
    from maestro_fetch.core.config import load_config

    config = load_config()
    automation_cfg = config.get("automation", {})
    model = automation_cfg.get("model", "claude-sonnet-4-20250514")
    timeout = automation_cfg.get("timeout", 120)

    typer.echo(f"Executing: {task}")

    try:
        result = _run(_extension_agent_loop(task, url, model, timeout))
        content = result.get("result", "")
        if content:
            typer.echo(content)
        else:
            typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
