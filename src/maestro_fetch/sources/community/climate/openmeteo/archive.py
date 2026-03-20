"""
@meta
name: openmeteo/archive
description: Historical daily weather from Open-Meteo Archive API
category: climate
args:
  latitude: {required: true, description: "Latitude", example: "39.9"}
  longitude: {required: true, description: "Longitude", example: "116.4"}
  start_date: {required: true, description: "Start date YYYY-MM-DD", example: "2024-01-01"}
  end_date: {required: true, description: "End date YYYY-MM-DD", example: "2024-12-31"}
requires: []
output: markdown
"""


async def run(ctx, latitude, longitude, start_date, end_date):
    url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={latitude}&longitude={longitude}"
        f"&start_date={start_date}&end_date={end_date}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
    )
    resp = await ctx.fetch(url)
    data = resp.json()

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    t_max = daily.get("temperature_2m_max", [])
    t_min = daily.get("temperature_2m_min", [])
    precip = daily.get("precipitation_sum", [])

    lines = [
        "| Date | Max Temp (C) | Min Temp (C) | Precip (mm) |",
        "|------|-------------|-------------|-------------|",
    ]
    for i, date in enumerate(dates):
        lines.append(
            f"| {date} "
            f"| {t_max[i] if i < len(t_max) else 'N/A'} "
            f"| {t_min[i] if i < len(t_min) else 'N/A'} "
            f"| {precip[i] if i < len(precip) else 'N/A'} |"
        )

    return {
        "content": f"## Weather Archive ({latitude}, {longitude})\n\nSource: Open-Meteo\n\n"
        + "\n".join(lines),
        "metadata": {
            "source": "Open-Meteo",
            "latitude": latitude,
            "longitude": longitude,
        },
    }
