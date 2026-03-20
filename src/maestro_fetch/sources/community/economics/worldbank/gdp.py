"""
@meta
name: worldbank/gdp
description: World Bank GDP data by country code (ISO 3166)
category: economics
args:
  country: {required: true, description: "ISO 3166 country code", example: "CN"}
  years: {required: false, description: "Number of recent years", default: 20}
requires: []
output: markdown
"""


async def run(ctx, country, years=20):
    url = f"https://api.worldbank.org/v2/country/{country}/indicator/NY.GDP.MKTP.CD?format=json&per_page={years}&mrv={years}"
    resp = await ctx.fetch(url)
    data = resp.json()
    if len(data) < 2:
        return {"content": "No data found.", "metadata": {}}

    rows = data[1]
    lines = ["| Year | GDP (USD) |", "|------|-----------|"]
    for row in rows:
        year = row.get("date", "")
        value = row.get("value")
        formatted = f"${value:,.0f}" if value else "N/A"
        lines.append(f"| {year} | {formatted} |")

    return {
        "content": f"## GDP - {country}\n\nSource: World Bank\n\n" + "\n".join(lines),
        "metadata": {
            "source": "World Bank",
            "indicator": "NY.GDP.MKTP.CD",
            "country": country,
        },
    }
