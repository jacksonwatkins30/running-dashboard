# Running Ledger (jacksonwatkins30.github.io/running-dashboard)

Single-page GitHub Pages dashboard. `index.html` holds markup, styles and logic; all run data lives in `data/`.

## Data
- `data/runs.json` — one object per run: `id, name, date, week (%Y-W%W, Monday-start), month, year, dow, dist_mi, moving_time_s, pace_min_mi, avg_hr, max_hr, elev_gain_ft, calories, avg_cadence (single-foot spm), relative_effort (Strava-only, null for Garmin), training_load, gear, source?`. History through 2026-10-19 came from Strava; later runs come from Garmin (`source: "garmin"`).
- `data/lifts.json` — `{date, name, calories, dow, week, year}`.
- `data/records.json` — fastest N consecutive miles, keyed by N: `{duration_s, pace_min_mi, date, name, run_id}`.
- `data/splits/<run_id>.json` — per-mile splits and half times for Garmin-synced runs; used by the race breakdown pop-up.
- `data/sync_config.json` (optional) — `default_gear` (shoe credited when Garmin has none) and `gear_aliases` (Garmin gear name → name used in `SHOES`).

## Daily sync
`.github/workflows/sync.yml` runs `scripts/sync_garmin.py` daily from noon Eastern (two UTC crons + a gate that lets through any run at or after noon New York time, since GitHub often starts scheduled runs hours late) and commits any new data, which redeploys Pages. Auth: `GARMIN_TOKENS` repo secret, created with `scripts/garmin_login.py`. Garmin rotates tokens, so refreshed tokens are kept in the Actions cache, encrypted with that secret. On failure the workflow opens a `sync-failure` issue.

## Page
- Every header number (totals, per-year, averages, YTD label, state-perimeter fact, latest run, lifts year label) is computed from the data on load — never hand-edit numbers.
- Races: the `RACES` array near the bottom of `index.html`. Add an `official` time when results post; past races appear on the trophy shelf automatically by date.
- Marathon Training tab: `MARATHON_BLOCKS` lists the race toggles (keys match `RACES`). NYC 2026 shows its real plan (`PLANNED_WEEKS`); other races show the `BLOCK_WEEKS` (18) weeks ending on race week, from actual runs, starting at the first week with a logged run (renumbered from week 1). Add a new marathon by adding its toggle.
- Runs tab: a dot per day by year, shaded by that day's miles (under 4, 4–6, 6–9, 9–13, 13+), built from `data/runs.json` on load.
- Lifts tab: same dot grid, filled on lift days, one block per year back to the first year with runs.
- Tabs: Overview, Marathon Training, Runs, Lifts, Races, Records. Run log, Ask, avg pace by month, pace-vs-distance and HR-vs-pace were removed.
- Overview rows: Total miles, Total runs (with runs per week), Avg miles per run.
- Runs tab also has the runs-by-weekday bar chart (stacked by year).
- Records tab: headline cards (1, 3, 6, 13, 26 mi; "New" within 30 days), a pace curve colored by year set, and pace bars for every distance 1–26.
- New shoes: add to `SHOES` (gear string must match `gear` in runs) and its markup block on the Overview tab.
- Look: "Finish line" — Manrope text, Geist SemiBold numbers, ink `#141414`, race orange accent `#F26B1D` (current year, highlights; `--accent-text` `#B44A0C` where it is text), blue `#457B9D` and pale aqua `#A8DADC` for earlier years and secondary data, ground `#F7F7F5`. Race ribbons, medals and shoe colors are real-object colors, not theme colors. Chart y-axis padding (~15% headroom) in `setMonthlyView()` and `distChart` is intentional.
