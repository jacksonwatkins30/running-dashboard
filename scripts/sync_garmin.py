"""Pull new runs and lifts from Garmin Connect into data/*.json.

Runs daily from GitHub Actions (.github/workflows/sync.yml). Needs Garmin
tokens in the GARMINTOKENS env var (JSON string or a path to a token folder),
created once with scripts/garmin_login.py.

What it does for each new activity:
  runs  -> data/runs.json (same schema as the original Strava data)
  lifts -> data/lifts.json
  each new run's FIT file -> data/splits/<id>.json (per-mile splits, halves)
                          -> data/records.json (fastest N consecutive miles)
                          -> data/records_by_year.json (same, per calendar year,
                             once the backfill workflow has created it)
"""
from __future__ import annotations

import io
import json
import os
import sys
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SPLITS = DATA / "splits"
MILE_M = 1609.344
RUN_TYPES = {"running", "treadmill_running", "trail_running", "track_running",
             "street_running", "indoor_running", "virtual_run", "ultra_run"}
LIFT_TYPES = {"strength_training"}


# ---------- helpers (pure, unit-testable) ----------
def load_json(p: Path, default):
    return json.loads(p.read_text()) if p.exists() else default


def save_json(p: Path, obj, compact=True):
    p.parent.mkdir(parents=True, exist_ok=True)
    if compact and isinstance(obj, list):
        body = "[\n" + ",\n".join(json.dumps(o, separators=(",", ":")) for o in obj) + "\n]\n"
    else:
        body = json.dumps(obj, indent=1) + "\n"
    p.write_text(body)


def date_fields(d: date) -> dict:
    return {
        "date": d.isoformat(),
        "week": d.strftime("%Y-W%W"),       # Monday-start, matches existing data
        "month": d.strftime("%Y-%m"),
        "year": d.year,
        "dow": d.strftime("%A"),
    }


def local_date(act: dict) -> date:
    # startTimeLocal is the watch's local time, so late-evening runs keep their real date
    return datetime.strptime(act["startTimeLocal"][:19], "%Y-%m-%d %H:%M:%S").date()


def r1(x, n=1):
    return None if x is None else round(float(x), n)


def run_from_activity(act: dict, gear: str | None) -> dict | None:
    dist_m = act.get("distance") or 0
    if dist_m < 100:
        return None
    dist_mi = dist_m / MILE_M
    moving = act.get("movingDuration") or act.get("elapsedDuration") or act.get("duration")
    if not moving:
        return None
    cadence = act.get("averageRunningCadenceInStepsPerMinute")
    rec = {
        "id": str(act["activityId"]),
        "name": act.get("activityName") or "Run",
        **date_fields(local_date(act)),
        "dist_mi": round(dist_mi, 2),
        "moving_time_s": int(round(moving)),
        "pace_min_mi": round(moving / 60 / dist_mi, 4),
        "avg_hr": r1(act.get("averageHR")),
        "max_hr": r1(act.get("maxHR")),
        "elev_gain_ft": r1((act.get("elevationGain") or 0) * 3.28084),
        "calories": r1(act.get("calories")),
        # Garmin counts both feet; the Strava history counts one
        "avg_cadence": r1(cadence / 2) if cadence else None,
        "relative_effort": None,            # Strava-only metric
        "training_load": r1(act.get("activityTrainingLoad")),
        "gear": gear,
        "source": "garmin",
    }
    return rec


def lift_from_activity(act: dict) -> dict:
    d = local_date(act)
    f = date_fields(d)
    return {"date": f["date"], "name": act.get("activityName") or "Strength",
            "calories": r1(act.get("calories")), "dow": f["dow"], "week": f["week"], "year": f["year"]}


def is_duplicate_run(rec: dict, runs: list[dict]) -> bool:
    for r in runs:
        if r["id"] == rec["id"]:
            return True
        if r["date"] == rec["date"] and abs((r.get("dist_mi") or 0) - rec["dist_mi"]) <= 0.15:
            return True  # same run already imported from the Strava history
    return False


def is_duplicate_lift(rec: dict, lifts: list[dict]) -> bool:
    return any(l["date"] == rec["date"] for l in lifts)


def time_at(points: list[tuple[float, float]], dist: float, start: int = 0) -> tuple[float | None, int]:
    """Interpolated elapsed time at a distance; returns (time, index) to resume from."""
    i = max(start, 1)
    while i < len(points) and points[i][1] < dist:
        i += 1
    if i >= len(points):
        return None, len(points)
    (t0, d0), (t1, d1) = points[i - 1], points[i]
    if d1 == d0:
        return t1, i
    return t0 + (t1 - t0) * (dist - d0) / (d1 - d0), i


def clean_points(raw: list[tuple[float, float, float | None]]):
    """(t_seconds, dist_m, hr) sorted, monotonic distance, gaps removed (pauses)."""
    pts, hr = [], []
    last_d = -1.0
    for t, d, h in raw:
        if d is None or t is None or d < last_d:
            continue
        pts.append((t, d))
        hr.append(h)
        last_d = d
    return pts, hr


def mile_splits(pts, hrs) -> dict | None:
    if len(pts) < 10:
        return None
    total_d = pts[-1][1]
    total_t = pts[-1][0] - pts[0][0]
    out, prev_t, idx, n = [], pts[0][0], 1, 1
    hr_i = 0
    while n * MILE_M <= total_d:
        t, idx = time_at(pts, n * MILE_M, idx)
        seg_hr = [h for (tt, _), h in zip(pts[hr_i:idx], hrs[hr_i:idx]) if h]
        out.append({"mile": n, "dist_mi": 1.0, "duration_s": round(t - prev_t, 1),
                    "avg_hr": round(sum(seg_hr) / len(seg_hr)) if seg_hr else None})
        prev_t, hr_i, n = t, idx, n + 1
    rem = total_d - (n - 1) * MILE_M
    if rem > 0.05 * MILE_M:
        seg_hr = [h for h in hrs[hr_i:] if h]
        out.append({"mile": f"{rem / MILE_M:.1f}", "dist_mi": round(rem / MILE_M, 2),
                    "duration_s": round(pts[-1][0] - prev_t, 1),
                    "avg_hr": round(sum(seg_hr) / len(seg_hr)) if seg_hr else None})
    half_t, _ = time_at(pts, total_d / 2)
    first = half_t - pts[0][0] if half_t is not None else None
    return {"total_s": round(total_t, 1), "first_half_s": r1(first), "second_half_s": r1(total_t - first) if first else None,
            "miles": out}


def best_windows(pts) -> dict[int, float]:
    """Fastest time to cover N consecutive miles anywhere in the run, N = 1..floor(miles)."""
    best = {}
    total_d = pts[-1][1] - pts[0][1]
    for n in range(1, int(total_d // MILE_M) + 1):
        span = n * MILE_M
        j, fastest = 1, None
        for i in range(len(pts)):
            target = pts[i][1] + span
            if target > pts[-1][1]:
                break
            if j < i + 1:
                j = i + 1
            t, j = time_at(pts, target, j)
            if t is None:
                break
            dt = t - pts[i][0]
            if fastest is None or dt < fastest:
                fastest = dt
        if fastest:
            best[n] = fastest
    return best


def update_records(records: dict, run: dict, best: dict[int, float]) -> list[int]:
    changed = []
    for n, secs in best.items():
        cur = records.get(str(n))
        if cur is None or secs < cur["duration_s"] - 0.05:
            records[str(n)] = {"duration_s": round(secs, 1), "pace_min_mi": round(secs / 60 / n, 4),
                               "date": run["date"], "name": run["name"], "run_id": run["id"]}
            changed.append(n)
    return changed


def parse_fit(blob: bytes):
    import fitparse
    if blob[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".fit"))
            blob = z.read(name)
    ff = fitparse.FitFile(io.BytesIO(blob))
    raw, t0 = [], None
    for msg in ff.get_messages("record"):
        v = msg.get_values()
        ts, d = v.get("timestamp"), v.get("distance")
        if ts is None or d is None:
            continue
        if t0 is None:
            t0 = ts
        raw.append(((ts - t0).total_seconds(), float(d), v.get("heart_rate")))
    return clean_points(raw)


# ---------- Garmin I/O ----------
def connect():
    from garminconnect import Garmin
    tokens = os.environ.get("GARMINTOKENS")
    if not tokens:
        sys.exit("GARMINTOKENS is not set. Run scripts/garmin_login.py once and save the output as the GARMIN_TOKENS secret.")
    api = Garmin()
    api.login(tokens)
    return api


def activity_gear(api, act_id) -> str | None:
    try:
        gear = api.get_activity_gear(act_id) or []
        if gear:
            g = gear[0]
            return g.get("displayName") or g.get("customMakeModel")
    except Exception:
        pass
    return None


def main():
    runs = load_json(DATA / "runs.json", [])
    lifts = load_json(DATA / "lifts.json", [])
    records = load_json(DATA / "records.json", {})
    year_records = load_json(DATA / "records_by_year.json", {})
    config = load_json(DATA / "sync_config.json", {})
    aliases = config.get("gear_aliases", {})
    known_gear = {r["gear"] for r in runs if r.get("gear")}
    last_gear = next((r["gear"] for r in sorted(runs, key=lambda r: r["date"], reverse=True) if r.get("gear")), None)
    default_gear = config.get("default_gear") or last_gear

    last = max([r["date"] for r in runs] + [l["date"] for l in lifts] + ["2024-01-01"])
    start = (date.fromisoformat(last) - timedelta(days=2)).isoformat()
    today = date.today().isoformat()

    api = connect()
    acts = api.get_activities_by_date(start, today) or []
    acts.sort(key=lambda a: a.get("startTimeLocal", ""))
    new_runs, new_lifts, pr_changes = [], [], []

    for act in acts:
        kind = (act.get("activityType") or {}).get("typeKey", "")
        if kind in RUN_TYPES:
            gname = activity_gear(api, act["activityId"])
            gname = aliases.get(gname, gname)
            gear = gname if gname in known_gear else default_gear
            rec = run_from_activity(act, gear)
            if not rec or is_duplicate_run(rec, runs):
                continue
            try:
                blob = api.download_activity(act["activityId"], dl_fmt=api.ActivityDownloadFormat.ORIGINAL)
                pts, hrs = parse_fit(blob)
                sp = mile_splits(pts, hrs)
                if sp:
                    sp["run_id"] = rec["id"]
                    save_json(SPLITS / f"{rec['id']}.json", sp, compact=False)
                if len(pts) > 10:
                    best = best_windows(pts)
                    pr_changes += [(n, rec["date"]) for n in update_records(records, rec, best)]
                    update_records(year_records.setdefault(rec["date"][:4], {}), rec, best)
            except Exception as e:  # a missing FIT never blocks the run itself
                print(f"  FIT skipped for {rec['id']}: {e}")
            runs.append(rec)
            new_runs.append(rec)
        elif kind in LIFT_TYPES:
            rec = lift_from_activity(act)
            if not is_duplicate_lift(rec, lifts):
                lifts.append(rec)
                new_lifts.append(rec)

    runs.sort(key=lambda r: r["date"])
    lifts.sort(key=lambda l: l["date"])
    if new_runs or new_lifts:
        save_json(DATA / "runs.json", runs)
        save_json(DATA / "lifts.json", lifts)
        save_json(DATA / "records.json", records, compact=False)
        if year_records:
            save_json(DATA / "records_by_year.json", year_records, compact=False)

    # keep the refreshed tokens for the next run (the workflow caches them encrypted)
    out = os.environ.get("GARMIN_TOKENS_OUT")
    if out:
        Path(out).write_text(api.client.dumps())

    summary = [f"{len(new_runs)} new run(s), {len(new_lifts)} new lift(s)"]
    summary += [f"  run  {r['date']}  {r['dist_mi']:.2f} mi  {r['name']}" for r in new_runs]
    summary += [f"  PR   {n} mi  ({d})" for n, d in pr_changes]
    print("\n".join(summary))
    gh = os.environ.get("GITHUB_STEP_SUMMARY")
    if gh:
        Path(gh).write_text("### Garmin sync\n```\n" + "\n".join(summary) + "\n```\n")


if __name__ == "__main__":
    main()
