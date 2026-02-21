"""Example: Fetch historical China weather data (years of daily records).

Demonstrates downloading long-term historical weather for Chinese cities via:
  1. Open-Meteo Archive API  -- ERA5 reanalysis, 1940-present, free, no auth
  2. data.cma.cn REST API    -- official CMA data, 1951-present, requires API key

Usage:
    # Open-Meteo (no auth needed, works immediately)
    python examples/china_weather_historical.py

    # CMA official API (requires free registration at data.cma.cn)
    CMA_API_KEY=your_key python examples/china_weather_historical.py --cma

    # Custom city and date range
    python examples/china_weather_historical.py --city Beijing --start 2000-01-01 --end 2023-12-31

    # Export to CSV
    python examples/china_weather_historical.py --city Shanghai --start 2020-01-01 --end 2024-12-31 --output shanghai_weather.csv
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import os
from dataclasses import dataclass, field
from pathlib import Path

from maestro_fetch import fetch, batch_fetch
from maestro_fetch.core.config import FetchConfig

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

CITY_COORDS: dict[str, tuple[float, float]] = {
    "Beijing": (39.9042, 116.4074),
    "Shanghai": (31.2304, 121.4737),
    "Guangzhou": (23.1291, 113.2644),
    "Shenzhen": (22.5431, 114.0579),
    "Chengdu": (30.5728, 104.0668),
    "Wuhan": (30.5928, 114.3055),
    "Hangzhou": (30.2741, 120.1551),
    "Harbin": (45.8038, 126.5350),
    "Lhasa": (29.6520, 91.1721),
    "Urumqi": (43.8256, 87.6168),
    "Chongqing": (29.5630, 106.5516),
    "Nanjing": (32.0603, 118.7969),
    "Xian": (34.2658, 108.9541),
    "Kunming": (25.0389, 102.7183),
    "Changsha": (28.2282, 112.9388),
}

# CMA station IDs for major cities (used with data.cma.cn API)
CMA_STATION_IDS: dict[str, str] = {
    "Beijing": "54511",
    "Shanghai": "58362",
    "Guangzhou": "59287",
    "Shenzhen": "59493",
    "Chengdu": "56294",
    "Wuhan": "57494",
    "Hangzhou": "58457",
    "Harbin": "50953",
    "Lhasa": "55591",
    "Urumqi": "51463",
}


@dataclass
class DailyRecord:
    city: str
    date: str
    temp_max: float | None = None
    temp_min: float | None = None
    temp_mean: float | None = None
    precipitation_mm: float | None = None
    wind_speed_max: float | None = None
    humidity_mean: float | None = None


# ---------------------------------------------------------------------------
# Strategy 1: Open-Meteo Archive API
# ---------------------------------------------------------------------------
# Free, no auth, ERA5 reanalysis data from 1940 to present.
# Rate limit: 10,000 req/day, 5,000/hour, 600/min.
# Max single request: ~366 days. For longer ranges, chunk by year.

def _chunk_date_range(start: str, end: str, chunk_days: int = 365) -> list[tuple[str, str]]:
    """Split a date range into chunks of at most chunk_days."""
    from datetime import datetime, timedelta
    fmt = "%Y-%m-%d"
    s = datetime.strptime(start, fmt)
    e = datetime.strptime(end, fmt)
    chunks = []
    while s < e:
        chunk_end = min(s + timedelta(days=chunk_days - 1), e)
        chunks.append((s.strftime(fmt), chunk_end.strftime(fmt)))
        s = chunk_end + timedelta(days=1)
    return chunks


async def fetch_open_meteo_historical(
    city: str,
    start_date: str,
    end_date: str,
) -> list[DailyRecord]:
    """Fetch historical daily weather from Open-Meteo Archive API.

    Data source: ERA5 reanalysis (ECMWF), 1940-present.
    Resolution: ~10km grid, daily aggregates.
    Variables: temperature (max/min/mean), precipitation, wind, humidity.
    """
    lat, lon = CITY_COORDS[city]
    chunks = _chunk_date_range(start_date, end_date)

    print(f"[Open-Meteo] {city}: {start_date} -> {end_date} ({len(chunks)} chunk(s))")

    urls = []
    for cs, ce in chunks:
        url = (
            f"https://archive-api.open-meteo.com/v1/archive?"
            f"latitude={lat}&longitude={lon}"
            f"&start_date={cs}&end_date={ce}"
            f"&daily=temperature_2m_max,temperature_2m_min,temperature_2m_mean,"
            f"precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean"
            f"&timezone=Asia/Shanghai"
        )
        urls.append(url)

    results = await batch_fetch(urls, concurrency=3)

    records: list[DailyRecord] = []
    for result in results:
        raw = result.content.strip().strip("`").strip()
        data = json.loads(raw)
        if "error" in data and data["error"]:
            print(f"  [WARN] API error: {data.get('reason', 'unknown')}")
            continue
        daily = data["daily"]
        for i, date in enumerate(daily["time"]):
            records.append(DailyRecord(
                city=city,
                date=date,
                temp_max=daily["temperature_2m_max"][i],
                temp_min=daily["temperature_2m_min"][i],
                temp_mean=daily["temperature_2m_mean"][i],
                precipitation_mm=daily["precipitation_sum"][i],
                wind_speed_max=daily["wind_speed_10m_max"][i],
                humidity_mean=daily["relative_humidity_2m_mean"][i],
            ))

    print(f"  -> {len(records)} daily records retrieved")
    return records


# ---------------------------------------------------------------------------
# Strategy 2: data.cma.cn REST API
# ---------------------------------------------------------------------------
# Official CMA data, 1951-present, requires free API key registration.
# Endpoint: http://api.data.cma.cn/api
# Supports 1-30 stations per query.

async def fetch_cma_historical(
    city: str,
    start_date: str,
    end_date: str,
    api_key: str,
) -> list[DailyRecord]:
    """Fetch historical daily weather from CMA official API.

    Requires: free registration at data.cma.cn to obtain API key.
    Data: real surface observations from 699+ Chinese stations, 1951-present.
    """
    station_id = CMA_STATION_IDS.get(city)
    if not station_id:
        print(f"  [SKIP] No CMA station ID for {city}")
        return []

    # CMA API expects times as YYYYMMDDHHMMSS
    time_start = start_date.replace("-", "") + "000000"
    time_end = end_date.replace("-", "") + "235959"

    url = (
        f"http://api.data.cma.cn/api?"
        f"key={api_key}"
        f"&interfaceId=getSurfEleByTimeRangeAndStaID"
        f"&dataCode=SURF_CHN_MUL_DAY"
        f"&timeRange=[{time_start},{time_end}]"
        f"&staIDs={station_id}"
        f"&elements=Station_Id_C,Year,Mon,Day,TEM_Max,TEM_Min,TEM_Avg,PRE_Time_2020,WIN_S_Max,RHU_Avg"
        f"&dataFormat=json"
    )

    print(f"[CMA API] {city} (station {station_id}): {start_date} -> {end_date}")

    result = await fetch(url)
    raw = result.content.strip().strip("`").strip()
    data = json.loads(raw)

    if data.get("returnCode") != 0:
        msg = data.get("returnMessage", "unknown error")
        print(f"  [ERROR] CMA API: {msg}")
        return []

    records: list[DailyRecord] = []
    for row in data.get("DS", []):
        date_str = f"{row['Year']}-{int(row['Mon']):02d}-{int(row['Day']):02d}"
        records.append(DailyRecord(
            city=city,
            date=date_str,
            temp_max=_safe_float(row.get("TEM_Max")),
            temp_min=_safe_float(row.get("TEM_Min")),
            temp_mean=_safe_float(row.get("TEM_Avg")),
            precipitation_mm=_safe_float(row.get("PRE_Time_2020")),
            wind_speed_max=_safe_float(row.get("WIN_S_Max")),
            humidity_mean=_safe_float(row.get("RHU_Avg")),
        ))

    print(f"  -> {len(records)} daily records retrieved")
    return records


def _safe_float(v: object) -> float | None:
    if v is None or v == "" or v == 999999:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_csv(records: list[DailyRecord], path: str) -> None:
    """Export records to CSV."""
    import csv
    fields = [
        "city", "date", "temp_max", "temp_min", "temp_mean",
        "precipitation_mm", "wind_speed_max", "humidity_mean",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            writer.writerow({
                "city": r.city,
                "date": r.date,
                "temp_max": r.temp_max,
                "temp_min": r.temp_min,
                "temp_mean": r.temp_mean,
                "precipitation_mm": r.precipitation_mm,
                "wind_speed_max": r.wind_speed_max,
                "humidity_mean": r.humidity_mean,
            })
    print(f"\nExported {len(records)} records to {path}")


def print_summary(records: list[DailyRecord]) -> None:
    """Print statistical summary of fetched records."""
    if not records:
        print("No records to summarize.")
        return

    temps = [r.temp_mean for r in records if r.temp_mean is not None]
    precip = [r.precipitation_mm for r in records if r.precipitation_mm is not None]
    cities = sorted(set(r.city for r in records))
    dates = sorted(r.date for r in records)

    print(f"\n{'=' * 60}")
    print(f"Summary: {len(records)} daily records")
    print(f"{'=' * 60}")
    print(f"Cities: {', '.join(cities)}")
    print(f"Date range: {dates[0]} -> {dates[-1]}")
    print(f"Temperature (mean): {min(temps):.1f} ~ {max(temps):.1f} C (avg {sum(temps)/len(temps):.1f} C)")
    if precip:
        rainy_days = sum(1 for p in precip if p > 0.1)
        total_rain = sum(precip)
        print(f"Precipitation: {total_rain:.0f}mm total, {rainy_days} rainy days ({rainy_days/len(precip)*100:.0f}%)")

    # Per-year breakdown
    years: dict[str, list[float]] = {}
    for r in records:
        y = r.date[:4]
        if r.temp_mean is not None:
            years.setdefault(y, []).append(r.temp_mean)

    print(f"\nAnnual mean temperature:")
    for y in sorted(years.keys()):
        vals = years[y]
        print(f"  {y}: {sum(vals)/len(vals):.1f} C ({len(vals)} days)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch historical China weather data")
    p.add_argument("--city", default="Beijing", choices=list(CITY_COORDS.keys()))
    p.add_argument("--start", default="2020-01-01", help="Start date (YYYY-MM-DD)")
    p.add_argument("--end", default="2024-12-31", help="End date (YYYY-MM-DD)")
    p.add_argument("--output", help="Export to CSV file path")
    p.add_argument("--cma", action="store_true", help="Use CMA official API (needs CMA_API_KEY env)")
    return p.parse_args()


async def main() -> None:
    args = parse_args()

    if args.cma:
        api_key = os.environ.get("CMA_API_KEY")
        if not api_key:
            print("ERROR: Set CMA_API_KEY environment variable.")
            print("Register free at https://data.cma.cn/ to get your API key.")
            sys.exit(1)
        records = await fetch_cma_historical(args.city, args.start, args.end, api_key)
    else:
        records = await fetch_open_meteo_historical(args.city, args.start, args.end)

    print_summary(records)

    if args.output:
        export_csv(records, args.output)


if __name__ == "__main__":
    asyncio.run(main())
