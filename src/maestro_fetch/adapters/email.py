"""EmailAdapter -- parses .eml and .msg email files.

Extracts subject, sender, recipients, date, body (text or HTML→markdown),
and saves attachments to cache. Uses stdlib `email` module — zero extra deps.
"""

from __future__ import annotations

import email
import email.policy
import re
from pathlib import Path

import httpx

from maestro_fetch.adapters.base import BaseAdapter
from maestro_fetch.core.config import FetchConfig
from maestro_fetch.core.errors import DownloadError, ParseError
from maestro_fetch.core.result import FetchResult

_EMAIL_PATTERNS = [
    r"\.eml(\?|$)",
    r"\.msg(\?|$)",
]


class EmailAdapter(BaseAdapter):
    """Parses .eml email files into structured markdown."""

    def supports(self, url: str) -> bool:
        return any(re.search(p, url, re.IGNORECASE) for p in _EMAIL_PATTERNS)

    async def fetch(self, url: str, config: FetchConfig) -> FetchResult:
        raw_bytes = await self._download(url, config)
        return self._parse(url, raw_bytes, config)

    async def _download(self, url: str, config: FetchConfig) -> bytes:
        if url.startswith("file://") or Path(url).is_file():
            path = Path(url.removeprefix("file://"))
            return path.read_bytes()

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=config.timeout or 60
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.content
        except Exception as exc:
            raise DownloadError(f"Failed to download email from {url}: {exc}") from exc

    def _parse(self, url: str, raw: bytes, config: FetchConfig) -> FetchResult:
        try:
            msg = email.message_from_bytes(raw, policy=email.policy.default)
        except Exception as exc:
            raise ParseError(f"Failed to parse email: {exc}") from exc

        subject = msg.get("subject", "(no subject)")
        sender = msg.get("from", "")
        to = msg.get("to", "")
        cc = msg.get("cc", "")
        date = msg.get("date", "")

        # Extract body
        body_text = ""
        body_html = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain" and not body_text:
                    body_text = part.get_content()
                elif ct == "text/html" and not body_html:
                    body_html = part.get_content()
        else:
            ct = msg.get_content_type()
            if ct == "text/plain":
                body_text = msg.get_content()
            elif ct == "text/html":
                body_html = msg.get_content()

        # Prefer plain text; fall back to HTML→markdown
        if body_text:
            body = body_text
        elif body_html:
            try:
                import html2text
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = True
                body = h.handle(body_html)
            except ImportError:
                body = re.sub(r"<[^>]+>", " ", body_html)
        else:
            body = "(empty body)"

        # Extract attachments
        attachments = []
        attach_dir = config.cache_dir / "email_attachments"
        attach_dir.mkdir(parents=True, exist_ok=True)
        if msg.is_multipart():
            for part in msg.iter_attachments():
                filename = part.get_filename()
                if filename:
                    path = attach_dir / filename
                    path.write_bytes(part.get_content())
                    attachments.append({"filename": filename, "path": str(path), "size": path.stat().st_size})

        # Build markdown output
        lines = [
            f"## {subject}",
            "",
            f"**From:** {sender}",
            f"**To:** {to}",
        ]
        if cc:
            lines.append(f"**CC:** {cc}")
        lines.extend([
            f"**Date:** {date}",
            "",
            "---",
            "",
            body.strip(),
        ])
        if attachments:
            lines.extend(["", "---", "", "### Attachments", ""])
            for att in attachments:
                size_kb = att["size"] / 1024
                lines.append(f"- **{att['filename']}** ({size_kb:.1f} KB) → `{att['path']}`")

        content = "\n".join(lines)
        return FetchResult(
            url=url,
            source_type="email",
            content=content,
            tables=[],
            metadata={
                "subject": subject,
                "from": sender,
                "to": to,
                "date": date,
                "attachments": [a["filename"] for a in attachments],
            },
        )
