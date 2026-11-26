"""One-off: heart-rate drift for every long run (10+ mi) already on the dashboard.

Sources, in order: data/splits/<id>.json (Garmin runs), then an unzipped Strava
archive's activity files (FIT.gz with heart rate, or GPX with an hr extension).
Writes data/hr_drift.json; the daily sync adds new long runs after that.

  python scripts/backfill_hr_drift.py <unzipped strava archive dir>
"""
import csv
import gzip
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from sync_garmin import DATA, clean_points, hr_drift, load_json, mile_splits, parse_fit, save_json

ARCH = Path(sys.argv[1]) if len(sys.argv) > 1 else None


def gpx_points(data: bytes):
    import math
    R = 6371008.8
    root = ET.fromstring(data)
    raw, prev, d, t0 = [], None, 0.0, None
    for el in root.iter():
        if not el.tag.endswith("trkpt"):
            continue
        t = next((c.text for c in el if c.tag.endswith("time")), None)
        hr = next((c.text for c in el.iter() if c.tag.endswith("}hr") or c.tag == "hr"), None)
        if not t:
            continue
        ts = datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
        la, lo = float(el.get("lat")), float(el.get("lon"))
        if prev:
            p1, p2 = math.radians(prev[1]), math.radians(la)
            x = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo - prev[2]) / 2) ** 2
            step = 2 * R * math.asin(math.sqrt(x))
            if ts - prev[0] <= 0 or step / (ts - prev[0]) > 8:
                continue
            d += step
        t0 = ts if t0 is None else t0
        raw.append((ts - t0, d, float(hr) if hr else None))
        prev = (ts, la, lo)
    return clean_points(raw)


def main():
    runs = {r["id"]: r for r in load_json(DATA / "runs.json", [])}
    out = load_json(DATA / "hr_drift.json", {})
    files = {}
    if ARCH:
        rows = list(csv.reader(open(ARCH / "activities.csv", encoding="utf-8")))
        h = rows[0]
        files = {r[h.index("Activity ID")]: r[h.index("Filename")] for r in rows[1:] if r[h.index("Filename")]}
    for rid, run in runs.items():
        if run["dist_mi"] < 10 or rid in out:
            continue
        sp = None
        f = DATA / "splits" / f"{rid}.json"
        if f.exists():
            sp = load_json(f, None)
        elif rid in files:
            blob = (ARCH / files[rid]).read_bytes()
            if files[rid].endswith(".gz"):
                blob = gzip.decompress(blob)
            pts, hrs = parse_fit(blob) if ".fit" in files[rid] else gpx_points(blob)
            if pts and pts[-1][1] > 0 and ".fit" not in files[rid]:
                k = run["dist_mi"] * 1609.344 / pts[-1][1]  # raw GPX distance runs long; match Strava's
                pts = [(t, dd * k) for t, dd in pts]
            sp = mile_splits(pts, hrs) if pts else None
        dr = hr_drift(sp)
        if dr:
            out[rid] = {"date": run["date"], "name": run["name"], "dist_mi": run["dist_mi"], **dr}
    save_json(DATA / "hr_drift.json", dict(sorted(out.items(), key=lambda kv: kv[1]["date"])), compact=False)
    long_runs = sum(1 for r in runs.values() if r["dist_mi"] >= 10)
    print(f"{len(out)} of {long_runs} long runs have drift")


if __name__ == "__main__":
    main()
