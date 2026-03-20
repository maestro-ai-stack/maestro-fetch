"""
@meta
name: twitter/trending
description: Twitter/X trending topics via twikit API
category: social
args:
  limit: {required: false, description: "Number of trends", default: 20}
requires: [twikit]
output: markdown
"""
from social.twitter._utils import get_client


async def run(ctx, limit=20):
    client = await get_client()
    trends = await client.get_trends("trending")

    lines = []
    for i, trend in enumerate(trends[:limit], 1):
        name = getattr(trend, "name", str(trend))
        tweet_count = getattr(trend, "tweet_count", "")
        count_str = f" ({tweet_count} tweets)" if tweet_count else ""
        lines.append(f"{i}. **{name}**{count_str}")

    return {
        "content": "## Twitter Trending\n\n" + "\n".join(lines),
        "metadata": {"source": "Twitter/twikit", "count": len(lines)},
    }
