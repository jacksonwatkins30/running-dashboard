"""Per-year fastest N consecutive miles from an unzipped Strava archive (GPX / FIT.gz / TCX.gz).

One-off, for history Garmin doesn't have (2024-2025). Usage:
  python scripts/strava_archive_records.py <unzipped archive dir> <out.json>
Then merge <out.json> into data/records_by_year.json, keeping the faster time for each N.
GPX distances are scaled to Strava's own distance for that run, since raw
point-to-point GPS distance runs 2-4% long.
"""
import csv, gzip, io, json, math, sys, xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime

import os
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO + '/scripts')
from sync_garmin import best_windows, clean_points, parse_fit  # noqa: E402

ARCH = sys.argv[1]
OUT = sys.argv[2]


def hav(a, b):
    R = 6371008.8
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def ts(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()


def gpx_points(data):
    root = ET.fromstring(data)
    pts = []
    for el in root.iter():
        if el.tag.endswith('trkpt'):
            t = next((c.text for c in el if c.tag.endswith('time')), None)
            if t:
                pts.append((ts(t), float(el.get('lat')), float(el.get('lon'))))
    raw, d, prev = [], 0.0, None
    t0 = pts[0][0] if pts else 0
    for t, la, lo in pts:
        if prev:
            step = hav(prev[1:], (la, lo))
            dt = t - prev[0]
            if dt <= 0 or step / dt > 8.0:   # drop GPS jumps faster than ~3:20/mi
                continue
            d += step
        raw.append((t - t0, d, None))
        prev = (t, la, lo)
    return clean_points(raw)


def tcx_points(data):
    root = ET.fromstring(data)
    raw, t0 = [], None
    for el in root.iter():
        if el.tag.endswith('Trackpoint'):
            t = next((c.text for c in el if c.tag.endswith('Time')), None)
            d = next((c.text for c in el if c.tag.endswith('DistanceMeters')), None)
            if t and d:
                tt = ts(t)
                t0 = tt if t0 is None else t0
                raw.append((tt - t0, float(d), None))
    return clean_points(raw)


def points(path):
    data = open(path, 'rb').read()
    if path.endswith('.gz'):
        data = gzip.decompress(data)
    if '.fit' in path:
        return parse_fit(data)
    if '.tcx' in path:
        return tcx_points(data.strip())
    return gpx_points(data)


runs = {r['id']: r for r in json.load(open(REPO + '/data/runs.json'))}
rows = list(csv.reader(open(ARCH + '/activities.csv', encoding='utf-8')))
h = rows[0]
iI, iT, iF = h.index('Activity ID'), h.index('Activity Type'), h.index('Filename')
by_year, done, skipped = defaultdict(dict), defaultdict(int), []
for r in rows[1:]:
    if r[iT] != 'Run' or not r[iF]:
        continue
    run = runs.get(r[iI])
    if not run:
        skipped.append((r[iI], 'not on dashboard'))
        continue
    try:
        pts, _ = points(ARCH + '/' + r[iF])
    except Exception as e:
        skipped.append((r[iI], str(e)[:60]))
        continue
    if len(pts) <= 10:
        skipped.append((r[iI], 'no GPS track'))
        continue
    if '.fit' not in r[iF] and run.get('dist_mi'):
        # raw GPX point-to-point distance runs a few % long; scale to Strava's distance
        k = run['dist_mi'] * 1609.344 / pts[-1][1]
        pts = [(t, d * k) for t, d in pts]
    y = run['date'][:4]
    done[y] += 1
    for n, secs in best_windows(pts).items():
        cur = by_year[y].get(str(n))
        if cur is None or secs < cur['duration_s'] - 0.05:
            by_year[y][str(n)] = {'duration_s': round(secs, 1), 'pace_min_mi': round(secs / 60 / n, 4),
                                  'date': run['date'], 'name': run['name'], 'run_id': run['id']}
json.dump({y: dict(sorted(v.items(), key=lambda kv: int(kv[0]))) for y, v in sorted(by_year.items())}, open(OUT, 'w'), indent=1)
print('runs processed per year:', dict(done))
print('skipped:', len(skipped), skipped[:8])
