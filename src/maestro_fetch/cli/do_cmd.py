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

import typer

app = typer.Typer(help="Execute natural language browser tasks.")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


SYSTEM_PROMPT = textwrap.dedent("""\
You are a browser automation agent. You interact with web pages by outputting JSON commands.
You will receive the page content (as markdown text) and must decide what action to take.

Available actions (respond with a JSON object):

1. Navigate to URL:
   {"action": "navigate", "url": "https://..."}

2. Execute JavaScript (click, fill, read):
   {"action": "exec", "code": "document.querySelector('#email').value = 'user@example.com'"}

3. Click an element:
   {"action": "exec", "code": "document.querySelector('button[type=submit]').click()"}

4. Fill a form field:
   {"action": "exec", "code": "var el = document.querySelector('input[name=email]'); el.value = 'user@example.com'; el.dispatchEvent(new Event('input', {bubbles: true}))"}

5. Wait for page changes:
   {"action": "wait", "seconds": 2}

6. Read current page content:
   {"action": "read"}

7. Task complete:
   {"action": "done", "result": "description of what was accomplished", "success": true}

8. Task failed:
   {"action": "done", "result": "description of what went wrong", "success": false}

Rules:
- Output ONLY the JSON command, no other text
- Use CSS selectors to find elements. Prefer: id > name > type > class > text content
- For Japanese forms, look for labels near inputs to identify fields
- After clicking submit, wait 2s then read the page to verify
- If a page has multiple forms or sections, read it first to understand the structure
- Limit yourself to 15 steps maximum
""")


async def _extension_agent_loop(task: str, url: str | None, model: str, timeout: int):
    """Run LLM agent loop using extension backend."""
    from maestro_fetch.backends.extension import ExtensionBackend

    ext = ExtensionBackend()

    if not await ext.is_available():
        raise FetchError(
            "Extension backend is not available. "
            "Open Chrome with the maestro-fetch extension enabled."
        )

    typer.echo("Using Chrome extension backend (real browser)")

    # Navigate to starting URL if provided
    if url:
        typer.echo(f"Navigating to: {url}")
        await ext.navigate(url)
        await asyncio.sleep(2.0)

    # Get initial page content
    page_content = await _get_page_content(ext)

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
        response = await llm_call(messages)
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
            await ext.navigate(nav_url)
            await asyncio.sleep(2.0)
            page_content = await _get_page_content(ext)
            messages.append({"role": "user", "content": f"Navigated. Current page:\n{page_content[:8000]}"})

        elif act == "exec":
            code = action.get("code", "")
            typer.echo(f"  → Executing JS: {code[:100]}")
            try:
                result = await ext.eval_js(code)
                result_str = str(result) if result else "(no return value)"
                typer.echo(f"  → Result: {result_str[:200]}")
                messages.append({"role": "user", "content": f"JS executed. Result: {result_str[:2000]}"})
            except Exception as e:
                typer.echo(f"  → JS Error: {e}")
                messages.append({"role": "user", "content": f"JS execution error: {e}"})

        elif act == "wait":
            secs = min(action.get("seconds", 2), 10)
            typer.echo(f"  → Waiting {secs}s")
            await asyncio.sleep(secs)
            messages.append({"role": "user", "content": "Wait complete."})

        elif act == "read":
            page_content = await _get_page_content(ext)
            messages.append({"role": "user", "content": f"Current page:\n{page_content[:8000]}"})

        else:
            messages.append({"role": "user", "content": f"Unknown action '{act}'. Use navigate/exec/wait/read/done."})

    return {
        "success": False,
        "result": "Reached maximum steps without completing task",
        "task": task,
    }


async def _get_page_content(ext) -> str:
    """Get current page as markdown text."""
    try:
        code = "document.title + '\\n\\n' + document.body.innerText"
        result = await ext.eval_js(code)
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

        async def call_openrouter(messages):
            import httpx
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {openrouter_key}"},
                    json={"model": or_model, "messages": messages, "max_tokens": 1024},
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        return call_openrouter

    elif anthropic_key:
        async def call_anthropic(messages):
            import httpx
            system = ""
            api_messages = []
            for m in messages:
                if m["role"] == "system":
                    system = m["content"]
                else:
                    api_messages.append(m)
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


from maestro_fetch.core.errors import FetchError


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
