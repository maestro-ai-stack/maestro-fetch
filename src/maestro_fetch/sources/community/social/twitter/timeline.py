"""
@meta
name: twitter/timeline
description: Twitter/X home timeline via twikit API
category: social
args:
  limit: {required: false, description: "Number of tweets", default: 20}
requires: [twikit]
output: markdown
"""
from social.twitter._utils import get_client


async def run(ctx, limit=20):
    client = await get_client()
    tweets = await client.get_timeline(count=limit)

    lines = []
    for i, tweet in enumerate(tweets, 1):
        user = tweet.user.name if tweet.user else "Unknown"
        handle = tweet.user.screen_name if tweet.user else ""
        text = tweet.text or ""
        likes = getattr(tweet, "favorite_count", 0)
        rts = getattr(tweet, "retweet_count", 0)
        url = f"https://x.com/{handle}/status/{tweet.id}"
        lines.append(
            f"{i}. **@{handle}** ({user})\n"
            f"   {text[:200]}\n"
            f"   {likes} likes, {rts} RTs — {url}\n"
        )

    return {
        "content": "## Twitter Timeline\n\n" + "\n".join(lines),
        "metadata": {"source": "Twitter/twikit", "count": len(tweets)},
    }
