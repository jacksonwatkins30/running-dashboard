"""One-off: fastest N consecutive miles for each calendar year, from Garmin FIT files.

Run from GitHub Actions (.github/workflows/backfill-year-records.yml, started by hand).
Downloads the original FIT file for every run in Garmin Connect since 2024 and runs
the same rolling-window search the daily sync uses for all-time records, but keeps
the best per year. Writes data/records_by_year.json:

  {"2024": {"1": {duration_s, pace_min_mi, date, name, run_id}, ...}, "2025": {...}, ...}

Run names and ids are taken from data/runs.json when the run is already there
(matched by date and distance), so they line up with the rest of the page.
It also prints, per year, how many runs in runs.json Garmin had a FIT file for.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

from sync_garmin import (DATA, RUN_TYPES, best_windows, connect, load_json,
                         parse_fit, run_from_activity, save_json)

START = "2024-01-01"


def match_run(rec: dict, runs: list[dict]) -> dict | None:
    for r in runs:
        if r["id"] == rec["id"]:
            return r
    for r in runs:
        if r["date"] == rec["date"] and abs((r.get("dist_mi") or 0) - rec["dist_mi"]) <= 0.15:
            return r
    return None


def main():
    runs = load_json(DATA / "runs.json", [])
    api = connect()

    acts = api.get_activities_by_date(START, date.today().isoformat()) or []
    acts = [a for a in acts if (a.get("activityType") or {}).get("typeKey", "") in RUN_TYPES]
    acts.sort(key=lambda a: a.get("startTimeLocal", ""))
    print(f"{len(acts)} runs in Garmin Connect since {START}")

    by_year: dict[str, dict] = defaultdict(dict)
    covered: dict[str, set] = defaultdict(set)
    skipped = 0
    for i, act in enumerate(acts, 1):
        rec = run_from_activity(act, None)
        if not rec:
            continue
        known = match_run(rec, runs) or rec
        year = known["date"][:4]
        try:
            blob = api.download_activity(act["activityId"], dl_fmt=api.ActivityDownloadFormat.ORIGINAL)
            pts, _ = parse_fit(blob)
        except Exception as e:
            print(f"  FIT skipped {rec['date']} {rec['id']}: {e}")
            skipped += 1
            continue
        if len(pts) <= 10:
            continue
        covered[year].add(known["id"])
        for n, secs in best_windows(pts).items():
            cur = by_year[year].get(str(n))
            if cur is None or secs < cur["duration_s"] - 0.05:
                by_year[year][str(n)] = {"duration_s": round(secs, 1), "pace_min_mi": round(secs / 60 / n, 4),
                                         "date": known["date"], "name": known["name"], "run_id": known["id"]}
        if i % 25 == 0:
            print(f"  {i}/{len(acts)} processed")
        time.sleep(0.3)  # be gentle with Garmin

    out = {y: dict(sorted(v.items(), key=lambda kv: int(kv[0]))) for y, v in sorted(by_year.items())}
    save_json(DATA / "records_by_year.json", out, compact=False)

    # A faster stretch found here is also an all-time record
    records = load_json(DATA / "records.json", {})
    for recs in out.values():
        for n, r in recs.items():
            cur = records.get(n)
            if cur is None or r["duration_s"] < cur["duration_s"] - 0.05:
                records[n] = r
    save_json(DATA / "records.json", dict(sorted(records.items(), key=lambda kv: int(kv[0]))), compact=False)

    lines = ["Year | runs on dashboard | with Garmin FIT | longest N"]
    for y in sorted({r["date"][:4] for r in runs}):
        total = sum(1 for r in runs if r["date"][:4] == y)
        n = max((int(k) for k in out.get(y, {})), default=0)
        lines.append(f"{y} | {total} | {len(covered.get(y, ()))} | {n} mi")
    lines.append(f"FIT downloads skipped: {skipped}")
    print("\n".join(lines))
    gh = os.environ.get("GITHUB_STEP_SUMMARY")
    if gh:
        Path(gh).write_text("### Per-year records backfill\n```\n" + "\n".join(lines) + "\n```\n")

    tok = os.environ.get("GARMIN_TOKENS_OUT")
    if tok:
        Path(tok).write_text(api.client.dumps())


if __name__ == "__main__":
    main()
