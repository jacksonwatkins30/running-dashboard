# Running Ledger (jacksonwatkins30.github.io/running-dashboard)

Single-page GitHub Pages dashboard. `index.html` holds markup, styles and logic; all run data lives in `data/`.

## Data
- `data/runs.json` — one object per run: `id, name, date, week (%Y-W%W, Monday-start), month, year, dow, dist_mi, moving_time_s, pace_min_mi, avg_hr, max_hr, elev_gain_ft, calories, avg_cadence (single-foot spm), relative_effort (Strava-only, null for Garmin), training_load, gear, source?`. History through 2026-10-19 came from Strava; later runs come from Garmin (`source: "garmin"`).
- `data/lifts.json` — `{date, name, calories, dow, week, year}`.
- `data/records.json` — fastest N consecutive miles, keyed by N: `{duration_s, pace_min_mi, date, name, run_id}`.
- `data/splits/<run_id>.json` — per-mile splits and half times for Garmin-synced runs; used by the race breakdown pop-up.
- `data/sync_config.json` (optional) — `default_gear` (shoe credited when Garmin has none) and `gear_aliases` (Garmin gear name → name used in `SHOES`).

## Daily sync
`.github/workflows/sync.yml` runs `scripts/sync_garmin.py` at noon Eastern (two UTC crons + a New York-time gate) and commits any new data, which redeploys Pages. Auth: `GARMIN_TOKENS` repo secret, created with `scripts/garmin_login.py`. Garmin rotates tokens, so refreshed tokens are kept in the Actions cache, encrypted with that secret. On failure the workflow opens a `sync-failure` issue.

## Page
- Every header number (totals, per-year, averages, YTD label, state-perimeter fact, latest run, lifts year label) is computed from the data on load — never hand-edit numbers.
- Races: the `RACES` array near the bottom of `index.html`. Add an `official` time when results post; past races appear on the trophy shelf automatically by date.
- New shoes: add to `SHOES` (gear string must match `gear` in runs) and its markup block on the Overview tab.
- Look: "Alpine" — Manrope text, Geist SemiBold numbers, navy `#0F1B2D`, blue `#2563EB`, ground `#F3F6F9`. Chart y-axis padding (~15% headroom) in `setMonthlyView()` and `distChart` is intentional.
