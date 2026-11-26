# Running Dashboard (jacksonwatkins30.github.io/running-dashboard)

Single-page GitHub Pages dashboard. `index.html` holds markup, styles and logic; all run data lives in `data/`.

## Data
- `data/runs.json` — one object per run: `id, name, date, week (%Y-W%W, Monday-start), month, year, dow, dist_mi, moving_time_s, pace_min_mi, avg_hr, max_hr, elev_gain_ft, calories, avg_cadence (single-foot spm), relative_effort (Strava-only, null for Garmin), training_load, gear, source?`. Runs from Jun 2022 to Mar 28, 2024 came from an Apple Health export (`source: "apple_health"`, ids `ah-<start time>`); history through 2026-10-19 came from Strava; later runs come from Garmin (`source: "garmin"`). A lone 2018 run in Apple Health was left out so the year grids don't gain empty 2019–2021 blocks.
- `data/lifts.json` — `{date, name, calories, dow, week, year, source?}`. Jun 2022 – Apr 11, 2026 from Apple Health (Apple Watch strength workouts); later from Strava/Garmin.
- `data/records.json` — fastest N consecutive miles, keyed by N: `{duration_s, pace_min_mi, date, name, run_id}`.
- `data/records_by_year.json` — same, per calendar year `{"2025": {"1": {...}}}`. 2026 built by the hand-started `backfill-year-records.yml` workflow (`scripts/backfill_year_records.py`, Garmin FIT files); 2024–2025 from a one-time Strava archive (`scripts/strava_archive_records.py`, GPX scaled to Strava distance). Kept current by the daily sync.
- `data/marathons.json` — one entry per marathon: official result (time, place, bib, source link), official split checkpoints `[label, miles, seconds]`, and a hand-written `headline` + `summary` paragraphs. Splits come from the public results sites (NYRR, Chicago mika:timing, MCM RTRT.me). Add a new marathon here after it's run, and add its `official` time to `RACES`.
- `data/states.json` — 50 states: `perimeter_mi` (outer ring of the largest polygon, great-circle miles, from Census boundaries via us-atlas states-10m), an SVG `path` fit to a 300×300 box, and `text` `[x, y, room, in|out]` for where the hero text sits. Drives the hero map and the "more than the perimeter of" note.
- `data/routes/<run_id>.json` — the run's shape as an SVG path in a 100×100 box (no coordinates; first and last 400 m trimmed so it can't point to home). Written by the daily sync for each new Garmin run; `sync.yml` run by hand with input `routes=N` draws the last N. Shown in the Latest run card.
- `data/splits/<run_id>.json` — per-mile splits and half times for Garmin-synced runs; used by the race breakdown pop-up.
- `data/sync_config.json` (optional) — `default_gear` (shoe credited when Garmin has none) and `gear_aliases` (Garmin gear name → name used in `SHOES`).

## Daily sync
`.github/workflows/sync.yml` runs `scripts/sync_garmin.py` daily from noon Eastern (two UTC crons + a gate that lets through any run at or after noon New York time, since GitHub often starts scheduled runs hours late) and commits any new data, which redeploys Pages. Auth: `GARMIN_TOKENS` repo secret, created with `scripts/garmin_login.py`. Garmin rotates tokens, so refreshed tokens are kept in the Actions cache, encrypted with that secret. On failure the workflow opens a `sync-failure` issue.

## Page
- Every header number (totals, per-year, averages, YTD label, state-perimeter fact, latest run, lifts year label) is computed from the data on load — never hand-edit numbers.
- Races: the `RACES` array near the bottom of `index.html`. Add an `official` time when results post; past races appear on the trophy shelf automatically by date.
- Marathon Training tab: `MARATHON_BLOCKS` lists the race toggles (keys match `RACES`). NYC 2026 shows its real plan (`PLANNED_WEEKS`); other races show the `BLOCK_WEEKS` (18) weeks ending on race week, from actual runs, starting at the first week with a logged run (renumbered from week 1). Add a new marathon by adding its toggle.
- Runs tab: a dot per day by year, shaded by that day's miles (under 4, 4–6, 6–9, 9–13, 13+), built from `data/runs.json` on load.
- Lifts tab: same dot grid, filled on lift days, one block per year from the first year with a logged lift.
- Tabs: Overview, Marathon Training, Runs, Lifts, Races, Marathons, Records. Run log, Ask, avg pace by month, pace-vs-distance and HR-vs-pace were removed.
- Eyebrow ("Since June 2022") is the month of the first run. Overview rows: Total miles, Total runs (with runs per week), Avg miles per run. Distance distribution is stacked by year, totals on top, no y axis.
- Runs tab also has the runs-by-weekday bar chart (stacked by year).
- Records tab: headline cards (mile, 5 mi, 10 mi from `records.json`; half = 13-mi record extended to 13.1; marathon = best marathon finish in `RACES`), and a pace curve per year. A year in `data/records_by_year.json` plots its true fastest N straight miles; a year missing from it falls back to the fastest average pace of a run at least N miles.
- Marathons tab (right after Marathon Training): a pace-by-mile line chart for every marathon from `miles` in `data/marathons.json` (NYC official mile splits; Chicago and MCM from the watch GPS track scaled to 26.2), then one card per race with halves, split, places, summary and official splits.
- Hero: headline with the Latest run card under it (left); on the right, the outline of the next state whose perimeter is above lifetime miles, traced in orange for lifetime miles / perimeter, with the miles count and caption. Runs headline: days with a run, longest streak, busiest month.
- New shoes: add to `SHOES` (gear string must match `gear` in runs) and its markup block on the Overview tab.
- Look: "Finish line" — Manrope text, Geist SemiBold numbers, ink `#141414`, race orange accent `#F26B1D` (current year, highlights; `--accent-text` `#B44A0C` where it is text), blue `#457B9D` (2025), pale aqua `#A8DADC` (2024), sage `#9DB7A9` (2023) and sand `#D9D3C3` (2022) for earlier years and secondary data, ground `#F7F7F5`. Race ribbons, medals and shoe colors are real-object colors, not theme colors. Chart y-axis padding (~15% headroom) in `setMonthlyView()` and `distChart` is intentional.
