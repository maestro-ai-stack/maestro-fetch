"""
@meta
name: reddit/search
description: Search Reddit posts via praw API
category: social
args:
  query: {required: true, description: "Search query", example: "machine learning"}
  subreddit: {required: false, description: "Limit to subreddit", default: "all"}
  limit: {required: false, description: "Number of results", default: 25}
  sort: {required: false, description: "Sort order: relevance, hot, top, new", default: "relevance"}
requires: [praw]
output: markdown
"""


async def run(ctx, query, subreddit="all", limit=25, sort="relevance"):
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
    results = sub.search(query, sort=sort, limit=limit)

    lines = []
    for i, post in enumerate(results, 1):
        lines.append(
            f"{i}. **{post.title}** ({post.score} pts, {post.num_comments} comments)\n"
            f"   r/{post.subreddit} — https://reddit.com{post.permalink}\n"
        )

    return {
        "content": f"## Reddit Search: {query}\n\n" + "\n".join(lines),
        "metadata": {"source": "Reddit/praw", "query": query, "count": len(lines)},
    }
