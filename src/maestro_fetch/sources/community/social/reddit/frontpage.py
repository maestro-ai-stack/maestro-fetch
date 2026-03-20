"""
@meta
name: reddit/frontpage
description: Reddit front page posts via praw API
category: social
args:
  limit: {required: false, description: "Number of posts", default: 25}
requires: [praw]
output: markdown
"""


async def run(ctx, limit=25):
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

    lines = []
    for i, post in enumerate(reddit.front.hot(limit=limit), 1):
        lines.append(
            f"{i}. **{post.title}** ({post.score} pts, {post.num_comments} comments)\n"
            f"   r/{post.subreddit} — https://reddit.com{post.permalink}\n"
        )

    return {
        "content": "## Reddit Front Page\n\n" + "\n".join(lines),
        "metadata": {"source": "Reddit/praw", "count": len(lines)},
    }
