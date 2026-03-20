"""
@meta
name: reddit/hot
description: Reddit hot posts from a subreddit (public JSON API)
category: social
args:
  subreddit: {required: true, description: "Subreddit name without r/", example: "technology"}
  limit: {required: false, description: "Number of posts", default: 10}
requires: []
output: markdown
"""


async def run(ctx, subreddit, limit=10):
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    resp = await ctx.fetch(url, headers={"User-Agent": "maestro-fetch/0.2"})
    data = resp.json()

    posts = data.get("data", {}).get("children", [])
    lines = []
    for i, post in enumerate(posts, 1):
        d = post.get("data", {})
        title = d.get("title", "")
        score = d.get("score", 0)
        comments = d.get("num_comments", 0)
        url_post = f"https://reddit.com{d.get('permalink', '')}"
        lines.append(
            f"{i}. **{title}** ({score} pts, {comments} comments)\n   {url_post}\n"
        )

    return {
        "content": f"## r/{subreddit} - Hot\n\n" + "\n".join(lines),
        "metadata": {
            "source": "Reddit",
            "subreddit": subreddit,
            "count": len(posts),
        },
    }
