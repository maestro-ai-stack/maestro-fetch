"""
@meta
name: arxiv/search
description: Search arXiv papers by keyword
category: academic
args:
  query: {required: true, description: "Search query", example: "transformer attention"}
  max_results: {required: false, description: "Max results", default: 10}
requires: []
output: markdown
"""
import re


async def run(ctx, query, max_results=10):
    url = f"http://export.arxiv.org/api/query?search_query=all:{query}&max_results={max_results}"
    resp = await ctx.fetch(url)
    text = resp.text

    entries = re.findall(r"<entry>(.*?)</entry>", text, re.DOTALL)
    lines = []
    for entry in entries:
        title = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
        summary = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
        link = re.search(r"<id>(.*?)</id>", entry)
        published = re.search(r"<published>(.*?)</published>", entry)

        t = title.group(1).strip().replace("\n", " ") if title else "Unknown"
        s = summary.group(1).strip().replace("\n", " ")[:200] if summary else ""
        l = link.group(1).strip() if link else ""
        p = published.group(1)[:10] if published else ""

        lines.append(f"### {t}\n\n{p} | [{l}]({l})\n\n{s}...\n")

    return {
        "content": f"## arXiv: {query}\n\n" + "\n---\n".join(lines),
        "metadata": {"source": "arXiv", "query": query, "count": len(entries)},
    }
