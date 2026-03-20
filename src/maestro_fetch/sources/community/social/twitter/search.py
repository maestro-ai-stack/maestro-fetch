"""
@meta
name: twitter/search
description: Search tweets on Twitter/X via twikit API
category: social
args:
  query: {required: true, description: "Search query", example: "climate change"}
  limit: {required: false, description: "Number of results", default: 20}
requires: [twikit]
output: markdown
"""
from social.twitter._utils import get_client


async def run(ctx, query, limit=20):
    client = await get_client()
    result = await client.search_tweet(query, product="Latest", count=limit)

    lines = []
    for i, tweet in enumerate(result, 1):
        user = tweet.user.name if tweet.user else "Unknown"
        handle = tweet.user.screen_name if tweet.user else ""
        text = tweet.text or ""
        likes = getattr(tweet, "favorite_count", 0)
        url = f"https://x.com/{handle}/status/{tweet.id}"
        lines.append(
            f"{i}. **@{handle}** ({user})\n"
            f"   {text[:200]}\n"
            f"   {likes} likes — {url}\n"
        )

    return {
        "content": f"## Twitter Search: {query}\n\n" + "\n".join(lines),
        "metadata": {"source": "Twitter/twikit", "query": query, "count": len(lines)},
    }
