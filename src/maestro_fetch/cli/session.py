"""Interactive browser sessions — `mfetch session start|click|fill|snapshot|screenshot|eval|end`.

Launches a persistent Chromium process with CDP. Subsequent commands
connect via CDP, perform the action, and disconnect — the browser stays alive.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

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


# ---- Commands ----


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
            import json

            try:
                typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
            except (TypeError, ValueError):
                typer.echo(str(result))
    except Exception as e:
        typer.echo(f"Error evaluating JS: {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        if pw and browser:
            _run(disconnect(pw, browser))


@app.command()
def quote(
    tweet_url: str = typer.Argument(..., help="URL of the tweet to quote"),
    text: str = typer.Argument(..., help="Your quote text"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Navigate and fill but don't post"),
) -> None:
    """Quote retweet a tweet on Twitter/X."""
    state = _require_session()
    pw = browser = page = None
    try:
        pw, browser, page = _run(connect_page(state))
        _run(_do_quote(page, tweet_url, text, dry_run))
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error quoting tweet: {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        if pw and browser:
            _run(disconnect(pw, browser))


async def _do_quote(page, tweet_url: str, text: str, dry_run: bool) -> None:
    """Execute the quote retweet flow on Twitter/X."""
    # Step 1: Navigate to the tweet
    typer.echo(f"Navigating to {tweet_url}")
    await page.goto(tweet_url, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_selector("[data-testid='tweet']", timeout=10_000, state="attached")
    await page.wait_for_timeout(1000)

    # Step 2: Click the retweet button (first one = the tweet itself, not replies)
    rt_btn = page.locator("[data-testid='retweet']").first
    await rt_btn.click(timeout=5_000)
    await page.wait_for_timeout(500)

    # Step 3: Click "Quote" in the dropdown menu
    quote_item = page.locator("[role='menuitem']").filter(has_text="Quote")
    await quote_item.click(timeout=5_000)
    await page.wait_for_timeout(1500)

    # Step 4: Type the quote text (DraftEditor doesn't support fill, use keyboard)
    editor = page.locator("[data-testid='tweetTextarea_0']").first
    await editor.click(timeout=5_000)
    await page.keyboard.type(text, delay=30)
    await page.wait_for_timeout(500)

    if dry_run:
        typer.echo(f"[dry-run] Quote composed. Text: {text}")
        typer.echo("Review in browser, then post manually or run without --dry-run")
        return

    # Step 5: Click Post
    post_btn = page.locator("[data-testid='tweetButton']")
    await post_btn.click(timeout=5_000)
    await page.wait_for_timeout(2000)

    typer.echo(f"Quote posted: {text[:80]}...")


@app.command()
def like(tweet_url: str = typer.Argument(..., help="URL of the tweet to like")) -> None:
    """Like a tweet on Twitter/X."""
    state = _require_session()
    pw = browser = page = None
    try:
        pw, browser, page = _run(connect_page(state))
        _run(_do_tweet_action(page, tweet_url, "like"))
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        if pw and browser:
            _run(disconnect(pw, browser))


@app.command()
def bookmark(tweet_url: str = typer.Argument(..., help="URL of the tweet to bookmark")) -> None:
    """Bookmark a tweet on Twitter/X."""
    state = _require_session()
    pw = browser = page = None
    try:
        pw, browser, page = _run(connect_page(state))
        _run(_do_tweet_action(page, tweet_url, "bookmark"))
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        if pw and browser:
            _run(disconnect(pw, browser))


@app.command()
def repost(tweet_url: str = typer.Argument(..., help="URL of the tweet to repost")) -> None:
    """Repost (retweet) a tweet on Twitter/X."""
    state = _require_session()
    pw = browser = page = None
    try:
        pw, browser, page = _run(connect_page(state))
        _run(_do_tweet_action(page, tweet_url, "repost"))
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        if pw and browser:
            _run(disconnect(pw, browser))


async def _do_tweet_action(page, tweet_url: str, action: str) -> None:
    """Navigate to tweet and perform like/bookmark/repost."""
    await page.goto(tweet_url, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_selector("[data-testid='tweet']", timeout=10_000, state="attached")
    await page.wait_for_timeout(800)

    if action == "like":
        btn = page.locator("[data-testid='like']").first
        await btn.click(timeout=5_000)
        typer.echo(f"Liked: {tweet_url}")
    elif action == "bookmark":
        btn = page.locator("[data-testid='bookmark']").first
        await btn.click(timeout=5_000)
        typer.echo(f"Bookmarked: {tweet_url}")
    elif action == "repost":
        btn = page.locator("[data-testid='retweet']").first
        await btn.click(timeout=5_000)
        await page.wait_for_timeout(300)
        confirm = page.locator("[data-testid='retweetConfirm']")
        await confirm.click(timeout=5_000)
        typer.echo(f"Reposted: {tweet_url}")


@app.command()
def end() -> None:
    """End the active browser session."""
    if end_session():
        typer.echo("Session ended.")
    else:
        typer.echo("No active session.", err=True)
        raise typer.Exit(code=1)
