"""Interactive browser sessions — `mfetch session start|click|fill|snapshot|screenshot|eval|action|end`.

Launches a persistent Chromium process with CDP. Subsequent commands
connect via CDP, perform the action, and disconnect — the browser stays alive.

Platform actions (like, post, repost, etc.) are routed through the
three-layer ActionRouter instead of being hardcoded.
"""
from __future__ import annotations

import asyncio
import json as _json
from pathlib import Path
from typing import Optional

import typer

from maestro_fetch.core.session import (
    connect_page,
    disconnect,
    end_session,
    get_active_session,
    start_session,
)

app = typer.Typer(help="Interactive browser sessions.")


def _run(coro):
    """Run an async coroutine from sync CLI context."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _require_session():
    """Get active session or exit with error."""
    state = get_active_session()
    if state is None:
        typer.echo("No active session. Run 'mfetch session start <url>' first.", err=True)
        raise typer.Exit(code=1)
    return state


# ---- Generic Commands ----


@app.command()
def start(
    url: str = typer.Argument(..., help="URL to open"),
    cdp: bool = typer.Option(False, "--cdp", help="Connect to existing Chrome (reuse login state)"),
    cdp_port: int = typer.Option(9222, "--cdp-port", help="CDP port for --cdp mode"),
) -> None:
    """Start a new browser session."""
    try:
        state = _run(start_session(url, cdp=cdp, cdp_port=cdp_port))
    except RuntimeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    mode = "CDP (external Chrome)" if cdp else f"PID {state.pid}"
    typer.echo(f"Session {state.session_id} started ({mode}, CDP :{state.cdp_port})")
    typer.echo(f"Navigated to {state.url}")


@app.command()
def click(selector: str = typer.Argument(..., help="CSS selector to click")) -> None:
    """Click an element in the active session."""
    state = _require_session()
    pw = browser = page = None
    try:
        pw, browser, page = _run(connect_page(state))
        _run(page.click(selector, timeout=10_000))
        _run(page.wait_for_timeout(1000))
        typer.echo(f"Clicked: {selector}")
        typer.echo(f"URL: {page.url}")
    except Exception as e:
        typer.echo(f"Error clicking '{selector}': {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        if pw and browser:
            _run(disconnect(pw, browser))


@app.command()
def fill(
    selector: str = typer.Argument(..., help="CSS selector of input"),
    text: str = typer.Argument(..., help="Text to type"),
) -> None:
    """Fill a form field in the active session."""
    state = _require_session()
    pw = browser = page = None
    try:
        pw, browser, page = _run(connect_page(state))
        _run(page.fill(selector, text, timeout=10_000))
        typer.echo(f"Filled '{selector}' with: {text}")
    except Exception as e:
        typer.echo(f"Error filling '{selector}': {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        if pw and browser:
            _run(disconnect(pw, browser))


@app.command()
def snapshot(
    selector: str = typer.Option(None, "--selector", "-s", help="Scope to CSS selector"),
    scroll: int = typer.Option(0, "--scroll", help="Scroll N times before capture"),
) -> None:
    """Capture current page as markdown."""
    state = _require_session()
    pw = browser = page = None
    try:
        pw, browser, page = _run(connect_page(state))

        # Optional scroll
        for _ in range(scroll):
            _run(page.evaluate("window.scrollBy(0, window.innerHeight)"))
            _run(page.wait_for_timeout(1000))

        # Extract HTML
        if selector:
            el = _run(page.query_selector(selector))
            if el is None:
                typer.echo(f"Selector '{selector}' not found", err=True)
                raise typer.Exit(code=1)
            html = _run(el.inner_html())
        else:
            html = _run(page.content())

        # Convert to markdown
        try:
            import html2text

            converter = html2text.HTML2Text()
            converter.ignore_links = False
            converter.ignore_images = True
            converter.body_width = 0
            md = converter.handle(html)
        except ImportError:
            import re

            md = re.sub(r"<[^>]+>", " ", html)
            md = re.sub(r"\s+", " ", md).strip()

        typer.echo(md)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error taking snapshot: {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        if pw and browser:
            _run(disconnect(pw, browser))


@app.command()
def screenshot(
    output: str = typer.Option("screenshot.png", "--output", "-o", help="Output file path"),
    full_page: bool = typer.Option(True, "--full-page/--viewport", help="Full page or viewport only"),
) -> None:
    """Take a screenshot of the active session."""
    state = _require_session()
    pw = browser = page = None
    try:
        pw, browser, page = _run(connect_page(state))
        data = _run(page.screenshot(full_page=full_page))
        out_path = Path(output)
        out_path.write_bytes(data)
        typer.echo(f"Screenshot saved: {out_path.resolve()} ({len(data)} bytes)")
    except Exception as e:
        typer.echo(f"Error taking screenshot: {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        if pw and browser:
            _run(disconnect(pw, browser))


@app.command("eval")
def eval_js(js: str = typer.Argument(..., help="JavaScript to evaluate")) -> None:
    """Evaluate JavaScript in the active session."""
    state = _require_session()
    pw = browser = page = None
    try:
        pw, browser, page = _run(connect_page(state))
        result = _run(page.evaluate(js))
        if result is not None:
            try:
                typer.echo(_json.dumps(result, indent=2, ensure_ascii=False))
            except (TypeError, ValueError):
                typer.echo(str(result))
    except Exception as e:
        typer.echo(f"Error evaluating JS: {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        if pw and browser:
            _run(disconnect(pw, browser))


# ---- Platform Action Command (three-layer routing) ----


@app.command()
def action(
    platform: str = typer.Argument(..., help="Platform name (twitter, reddit, linkedin, ...)"),
    action_name: str = typer.Argument(..., help="Action to perform (like, post, search, ...)"),
    args: Optional[list[str]] = typer.Argument(None, help="Additional arguments"),
) -> None:
    """Execute a platform action via three-layer routing (API → opencli → browser-use)."""
    from maestro_fetch.core.action_router import ActionRouter

    router = ActionRouter()
    action_args = args or []

    # Parse key=value pairs from args into kwargs
    positional: list[str] = []
    kwargs: dict[str, str] = {}
    for arg in action_args:
        if "=" in arg:
            k, _, v = arg.partition("=")
            kwargs[k] = v
        else:
            positional.append(arg)

    try:
        result = _run(router.execute(platform, action_name, *positional, **kwargs))
        layer = result.get("layer", "unknown")
        typer.echo(f"[{layer}] {platform}/{action_name} — success")

        # Print result content
        content = result.get("content") or result.get("result") or result.get("output")
        if content:
            typer.echo(content)
        else:
            typer.echo(_json.dumps(result, indent=2, ensure_ascii=False, default=str))
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


# ---- Backward-compatible aliases (hidden) ----


@app.command(hidden=True)
def like(tweet_url: str = typer.Argument(..., help="URL of the tweet to like")) -> None:
    """Like a tweet on Twitter/X (backward compat → action twitter like)."""
    action("twitter", "like", [f"url={tweet_url}"])


@app.command(hidden=True)
def bookmark(tweet_url: str = typer.Argument(..., help="URL of the tweet to bookmark")) -> None:
    """Bookmark a tweet on Twitter/X (backward compat → action twitter bookmark)."""
    action("twitter", "bookmark", [f"url={tweet_url}"])


@app.command(hidden=True)
def repost(tweet_url: str = typer.Argument(..., help="URL of the tweet to repost")) -> None:
    """Repost a tweet on Twitter/X (backward compat → action twitter repost)."""
    action("twitter", "repost", [f"url={tweet_url}"])


@app.command(hidden=True)
def quote(
    tweet_url: str = typer.Argument(..., help="URL of the tweet to quote"),
    text: str = typer.Argument(..., help="Your quote text"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Navigate and fill but don't post"),
) -> None:
    """Quote retweet on Twitter/X (backward compat → action twitter quote)."""
    action("twitter", "quote", [f"url={tweet_url}", f"text={text}", f"dry_run={dry_run}"])


@app.command(hidden=True)
def post(
    text: str = typer.Argument(..., help="Tweet text"),
    image: str = typer.Option(None, "--image", "-i", help="Path to image file"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Compose but don't post"),
) -> None:
    """Post a tweet on Twitter/X (backward compat → action twitter post)."""
    args = [f"text={text}"]
    if image:
        args.append(f"image={image}")
    if dry_run:
        args.append("dry_run=true")
    action("twitter", "post", args)


@app.command()
def end() -> None:
    """End the active browser session."""
    if end_session():
        typer.echo("Session ended.")
    else:
        typer.echo("No active session.", err=True)
        raise typer.Exit(code=1)
