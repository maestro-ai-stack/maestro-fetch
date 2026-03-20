"""
@meta
name: reddit/subreddit
description: Posts from a specific subreddit via praw API
category: social
args:
  subreddit: {required: true, description: "Subreddit name without r/", example: "python"}
  sort: {required: false, description: "Sort: hot, new, top, rising", default: "hot"}
  limit: {required: false, description: "Number of posts", default: 25}
requires: [praw]
output: markdown
"""


async def run(ctx, subreddit, sort="hot", limit=25):
    try:
        import praw
    except ImportError:
        raise RuntimeError("praw is required: pip install 'maestro-fetch[social]'")

    config = ctx.config or {}
    auth = config.get("auth", {}).get("reddit", {})

    reddit = praw.Reddit(
        client_id=auth.get("client_id", ""),
        client_secret=auth.get("client_secret", ""),
        user_agent=auth.get("user_agent", "maestro-fetch/0.2"),
    )

    sub = reddit.subreddit(subreddit)
    fetcher = getattr(sub, sort, sub.hot)
    results = fetcher(limit=limit)

    lines = []
    for i, post in enumerate(results, 1):
        lines.append(
            f"{i}. **{post.title}** ({post.score} pts, {post.num_comments} comments)\n"
            f"   https://reddit.com{post.permalink}\n"
        )

    return {
        "content": f"## r/{subreddit} — {sort}\n\n" + "\n".join(lines),
        "metadata": {"source": "Reddit/praw", "subreddit": subreddit, "count": len(lines)},
    }
