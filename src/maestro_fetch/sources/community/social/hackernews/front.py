"""
@meta
name: hackernews/front
description: Hacker News front page stories via official Firebase API
category: social
args:
  limit: {required: false, description: "Number of stories (max 30)", default: 30}
requires: []
output: markdown
"""


async def run(ctx, limit=30):
    limit = min(int(limit), 30)

    # HN official API: top story IDs
    resp = await ctx.fetch(
        "https://hacker-news.firebaseio.com/v0/topstories.json",
        headers={"User-Agent": "maestro-fetch/0.2"},
    )
    story_ids = resp.json()[:limit]

    lines = []
    for i, sid in enumerate(story_ids, 1):
        item_resp = await ctx.fetch(
            f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
            headers={"User-Agent": "maestro-fetch/0.2"},
        )
        item = item_resp.json()
        title = item.get("title", "")
        url = item.get("url", f"https://news.ycombinator.com/item?id={sid}")
        score = item.get("score", 0)
        comments = item.get("descendants", 0)
        author = item.get("by", "")
        hn_link = f"https://news.ycombinator.com/item?id={sid}"

        lines.append(
            f"{i}. **{title}** ({score} pts, {comments} comments) by {author}\n"
            f"   {url}\n"
            f"   HN: {hn_link}\n"
        )

    return {
        "content": "## Hacker News — Front Page\n\n" + "\n".join(lines),
        "metadata": {
            "source": "Hacker News",
            "count": len(lines),
        },
    }
