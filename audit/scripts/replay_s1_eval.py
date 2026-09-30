#!/usr/bin/env python3
"""Replay evaluation script for S1 Physical Weather Corroboration.

Evaluates labelled historical weather events against Open-Meteo archive data
and computes time-shift (+30 days) and space-shift (+100 km) negative controls.

ACCURACY: NOT MEASURED
Formal precision/recall measurement is deferred until full ground-truth dataset
annotation campaign with dual-station calibration.
"""

import asyncio
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

# Ensure back-end is in path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "back-end"))

from app.intelligence.physical_corroboration.config import default_physical_config
from app.intelligence.physical_corroboration.evaluator import evaluate
from app.intelligence.physical_corroboration.models import (
    PhysicalCorroborationVerdict,
    PhysicalObservation,
    PhysicalSourceType,
)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def load_events(csv_path: Path) -> list[dict[str, str]]:
    """Synchronously load evaluation events from CSV."""
    with open(csv_path, encoding="utf-8") as f:
        valid_lines = [line for line in f if not line.strip().startswith("#")]
        return list(csv.DictReader(valid_lines))


async def fetch_archive_weather(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    dt: datetime,
) -> PhysicalObservation | None:
    """Fetch hourly weather from Open-Meteo historical archive API."""
    date_str = dt.strftime("%Y-%m-%d")
    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "start_date": date_str,
        "end_date": date_str,
        "hourly": "precipitation,wind_speed_10m,wind_gusts_10m,temperature_2m",
    }
    try:
        res = await client.get(ARCHIVE_URL, params=params, timeout=10.0)
        if res.status_code != 200:
            return None
        data = res.json()
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            return None

        # Find closest hour
        target_iso = dt.strftime("%Y-%m-%dT%H:00")
        idx = (
            times.index(target_iso)
            if target_iso in times
            else min(dt.hour, len(times) - 1)
        )

        precip = hourly.get("precipitation", [0.0])[idx]
        wind_spd = hourly.get("wind_speed_10m", [0.0])[idx]
        wind_gust = hourly.get("wind_gusts_10m", [None])[idx]
        temp = hourly.get("temperature_2m", [None])[idx]

        obs_time = datetime.fromisoformat(times[idx]).replace(tzinfo=timezone.utc)

        return PhysicalObservation(
            source_name="OPEN_METEO_ARCHIVE",
            source_type=PhysicalSourceType.MODEL,
            station_or_grid_id=f"grid_{lat:.2f}_{lon:.2f}",
            latitude=lat,
            longitude=lon,
            observed_at=obs_time,
            rainfall_1h_mm=float(precip) if precip is not None else 0.0,
            rainfall_24h_mm=float(sum(filter(None, hourly.get("precipitation", [])))),
            wind_speed_kmh=float(wind_spd) if wind_spd is not None else 0.0,
            wind_gust_kmh=float(wind_gust) if wind_gust is not None else None,
            temperature_c=float(temp) if temp is not None else None,
        )
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        print(
            f"Warning: Failed to fetch weather for ({lat}, {lon}) at {date_str}: {exc}",
            file=sys.stderr,
        )
        return None


async def evaluate_event(
    client: httpx.AsyncClient,
    category: str,
    lat: float,
    lon: float,
    dt: datetime,
) -> tuple[PhysicalCorroborationVerdict, str, PhysicalObservation | None]:
    """Fetch observation and run pure physical corroboration evaluation."""
    obs = await fetch_archive_weather(client, lat, lon, dt)
    if not obs:
        return PhysicalCorroborationVerdict.NEUTRAL, "Data unavailable", None

    res = evaluate(
        category=category,
        observation=obs,
        incident_time=dt,
        incident_coords=(lat, lon),
        config=default_physical_config,
    )
    return res.verdict, res.explanation, obs


async def main() -> None:
    csv_path = ROOT_DIR / "audit" / "s1_labelled_events_TEMPLATE.csv"
    if not csv_path.exists():
        print(f"Error: Template not found at {csv_path}", file=sys.stderr)
        sys.exit(1)

    print("=" * 80)
    print("S1 PHYSICAL WEATHER CORROBORATION: REPLAY EVALUATION & CONTROLS")
    print("=" * 80)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"Dataset: {csv_path.name}")
    print()

    events = load_events(csv_path)

    print(f"Loaded {len(events)} labelled test events.")
    print("Running evaluation across:")
    print("  1. Ground-truth historical event (actual date & location)")
    print("  2. Time-shift negative control (+30 days)")
    print("  3. Space-shift negative control (+100 km north, +0.9° lat)")
    print("-" * 80)

    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient() as client:
        for ev in events:
            ev_id = ev["event_id"]
            cat = ev["category"]
            loc = ev["location"]
            lat = float(ev["latitude"])
            lon = float(ev["longitude"])
            dt_str = f"{ev['event_date']}T{ev['event_time_utc']}Z"
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

            print(f"Evaluating {ev_id} ({cat} @ {loc}, {ev['event_date']})...")

            # 1. Base event
            v_base, exp_base, obs_base = await evaluate_event(client, cat, lat, lon, dt)
            await asyncio.sleep(0.3)  # Gentle rate limit

            # 2. Time-shift control (+30 days)
            dt_shift = dt + timedelta(days=30)
            v_time, _, _ = await evaluate_event(client, cat, lat, lon, dt_shift)
            await asyncio.sleep(0.3)

            # 3. Space-shift control (+100 km north ~ +0.9 deg)
            lat_shift = min(lat + 0.9, 36.0)
            v_space, _, _ = await evaluate_event(client, cat, lat_shift, lon, dt)
            await asyncio.sleep(0.3)

            results.append(
                {
                    "event_id": ev_id,
                    "category": cat,
                    "location": loc,
                    "date": ev["event_date"],
                    "base_verdict": v_base.value,
                    "base_exp": exp_base,
                    "obs_base": obs_base,
                    "time_shift_verdict": v_time.value,
                    "space_shift_verdict": v_space.value,
                }
            )

    # Summary table
    print()
    print("=" * 110)
    print(
        f"{'Event ID':<13} {'Category':<22} {'Location':<14} {'Base Verdict':<14} {'+30d Control':<14} {'+100km Control':<14}"
    )
    print("-" * 110)
    for r in results:
        print(
            f"{r['event_id']:<13} {r['category']:<22} {r['location']:<14} {r['base_verdict']:<14} {r['time_shift_verdict']:<14} {r['space_shift_verdict']:<14}"
        )
    print("=" * 110)

    # Rates calculation
    n = len(results)

    def count_verdicts(key: str) -> dict[str, Any]:
        sup = sum(1 for r in results if r[key] == "SUPPORTS")
        con = sum(1 for r in results if r[key] == "CONTRADICTS")
        neu = sum(1 for r in results if r[key] == "NEUTRAL")
        return {
            "SUPPORTS": sup / n * 100,
            "CONTRADICTS": con / n * 100,
            "NEUTRAL": neu / n * 100,
            "counts": (sup, con, neu),
        }

    rates_base = count_verdicts("base_verdict")
    rates_time = count_verdicts("time_shift_verdict")
    rates_space = count_verdicts("space_shift_verdict")

    print("\nAGGREGATE CORROBORATION RATES:")
    print("-" * 80)
    print(f"{'Condition':<25} {'SUPPORTS':<15} {'CONTRADICTS':<15} {'NEUTRAL':<15}")
    print("-" * 80)
    print(
        f"{'Base Ground Truth Events':<25} {rates_base['SUPPORTS']:>5.1f}% ({rates_base['counts'][0]}/{n})   {rates_base['CONTRADICTS']:>5.1f}% ({rates_base['counts'][1]}/{n})   {rates_base['NEUTRAL']:>5.1f}% ({rates_base['counts'][2]}/{n})"
    )
    print(
        f"{'Time-Shift (+30 days)':<25} {rates_time['SUPPORTS']:>5.1f}% ({rates_time['counts'][0]}/{n})   {rates_time['CONTRADICTS']:>5.1f}% ({rates_time['counts'][1]}/{n})   {rates_time['NEUTRAL']:>5.1f}% ({rates_time['counts'][2]}/{n})"
    )
    print(
        f"{'Space-Shift (+100 km)':<25} {rates_space['SUPPORTS']:>5.1f}% ({rates_space['counts'][0]}/{n})   {rates_space['CONTRADICTS']:>5.1f}% ({rates_space['counts'][1]}/{n})   {rates_space['NEUTRAL']:>5.1f}% ({rates_space['counts'][2]}/{n})"
    )
    print("-" * 80)

    print("\n" + "=" * 80)
    print("STATUS NOTE: ACCURACY: NOT MEASURED")
    print("=" * 80)
    print("Reason: Model-based Open-Meteo archive evaluation demonstrates physical")
    print("signal corroboration vs. temporal/spatial controls. Ground-truth precision")
    print("and recall cannot be formally declared without full dual-station ground")
    print("truth and human annotation verification.")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
