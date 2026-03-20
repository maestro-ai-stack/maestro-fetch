"""
@meta
name: github/trending
description: GitHub trending repositories (scrapes HTML, no API key needed)
category: social
args:
  language: {required: false, description: "Programming language filter", example: "python"}
  since: {required: false, description: "Time range: daily|weekly|monthly", default: "daily"}
  limit: {required: false, description: "Number of repos to return", default: 25}
requires: []
output: markdown
"""
import re


async def run(ctx, language="", since="daily", limit=25):
    limit = int(limit)

    url = "https://github.com/trending"
    if language:
        url += f"/{language}"
    url += f"?since={since}"

    resp = await ctx.fetch(url, headers={"User-Agent": "maestro-fetch/0.2"})
    html = resp.text

    # Parse trending repos from HTML
    # Each repo is in an <article> with class "Box-row"
    # The h2 contains <a href="/owner/repo">
    repo_blocks = re.findall(
        r'<article[^>]*class="[^"]*Box-row[^"]*"[^>]*>(.*?)</article>',
        html,
        re.DOTALL,
    )

    lines = []
    for block in repo_blocks[:limit]:
        # Extract repo path
        href_match = re.search(r'<h2[^>]*>.*?<a[^>]*href="(/[^"]+)"', block, re.DOTALL)
        if not href_match:
            continue
        repo_path = href_match.group(1).strip()
        name = repo_path.strip("/")

        # Extract description
        desc_match = re.search(r'<p[^>]*class="[^"]*col-9[^"]*"[^>]*>(.*?)</p>', block, re.DOTALL)
        desc = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip() if desc_match else ""

        # Extract language
        lang_match = re.search(r'itemprop="programmingLanguage"[^>]*>([^<]+)', block)
        lang = lang_match.group(1).strip() if lang_match else ""

        # Extract total stars (number comes after </svg> inside the stargazers link)
        stars_match = re.search(
            r'stargazers[^>]*>.*?</svg>\s*([\d,]+)',
            block,
            re.DOTALL,
        )
        stars = stars_match.group(1).strip() if stars_match else "?"

        # Extract today's stars
        today_match = re.search(r'(\d[\d,]*)\s+stars?\s+(?:today|this week|this month)', block)
        today = today_match.group(1).strip() if today_match else "?"

        lang_str = f" [{lang}]" if lang else ""
        i = len(lines) + 1
        lines.append(
            f"{i}. **{name}**{lang_str} — ⭐ {stars} (+{today} {since})\n"
            f"   {desc}\n"
            f"   https://github.com{repo_path}\n"
        )

    lang_label = f" ({language})" if language else ""
    return {
        "content": f"## GitHub Trending{lang_label} — {since}\n\n" + "\n".join(lines),
        "metadata": {
            "source": "GitHub Trending",
            "language": language,
            "since": since,
            "count": len(lines),
        },
    }
