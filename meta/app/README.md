# Meta Muse app prototype

Prototype of `apps.srsinvest.com/internet/meta_muse/` before it moves into the monorepo
(`workflows/jobs/meta/meta_muse.yaml`). See the plan in
`~/.claude/plans/okay-now-i-want-floofy-lemon.md`.

| File | What it is |
|---|---|
| `sections.py` | Source loads (Snowflake SQL), report sections (portable SQL), methodology and summary tiles: the single source of truth |
| `build_json.py` | Pulls loads into `.cache/`, runs the sections in DuckDB, writes `meta_muse.json` and `METHODOLOGY.md` |
| `index.html` | Draft page (Chart.js, no build step). Same `DATA_KEY` switch as the Roblox page |
| `METHODOLOGY.md` | Generated; do not edit by hand |
| `web_traffic_snapshot.csv` | SimilarWeb muse.ai visits (US, WW) pulled via the API on 2026-10-08; used only until the Snowflake pipeline carries muse.ai |
| `benchmark_snapshot.xlsx` | SensorTower portal export for Clubhouse (not in CORE): US daily downloads, DAU by country |
| `.cache/` | Parquet cache of loads (git-ignored) |

## Run

```powershell
cd meta\app
..\..\.venv\Scripts\python.exe build_json.py            # pulls what's missing (browser OAuth on first connect)
..\..\.venv\Scripts\python.exe build_json.py --offline  # rebuild from cache only, seconds
..\..\.venv\Scripts\python.exe -m http.server 8000      # then open http://localhost:8000/
```

The first run fills the cache from 2026-08-01. Later runs re-pull only the last
`REFRESH_DAYS` (14) of card days, plus NIQ and SensorTower once per run date.

## Load cost (what makes it fast or slow)

- **Yodlee feed tables are not clustered on `transaction_date`.** F3 bank is 62B rows / 4 TB,
  and a one-day query is a full scan of about a minute. They prune well on
  `panel_file_created_date`, and rows never land in a file created more than a day before the
  transaction. So each Yodlee source is ONE range query with
  `panel_file_created_date >= start - 2`.
- **279 PRIME_TAU** times out on multi-day text scans, so it is one query per day. On a small
  warehouse these queue behind the Yodlee bank scans, which makes the first build slow. The
  monorepo job only refreshes 14 days.
- **SensorTower CORE** is unclustered (about 20 GB scanned whatever the filter), so it is read
  once per run.

## Status as of 2026-10-07

- **SensorTower:**
  - Muse is its own app, "Muse from Meta" (`6aa0b99dd70c1a09e42dc613`).
  - It covers the US from 09-07 and CA from 09-14, nowhere else.
  - Meta AI US downloads fell by about 60% in launch week; DAU fell about 35% by late September.
  - Use `country_code IN ('US','WW')` only. `WW` is an aggregate row.
- **Lag:** cards are complete through T-5 (volume keeps filling for about 10 days), NIQ through
  T-1, SensorTower downloads through T-2 and DAU through T-3.
- **v1 card sources are Yodlee F3/4/6 only.** 279 PRIME_TAU was dropped on 2026-10-07. It
  adds about 3 agentic transactions a day (about 10%) and no web Muse, it is a 12.5M
  transactions/day panel that would distort the per-million rate, and its one-query-per-day
  load takes about 2.5 minutes a day on an analyst warehouse. `sections.SOURCE_279_PRIME_TAU`
  keeps it ready for the monorepo job, as a raw count only.

## Status as of 2026-10-08

- Team-review updates are built:
  - Sections are reordered (usage and ad spend, benchmark, share, web traffic, subscriber flows, agentic) on one shared date axis.
  - The separate web and in-app subscription charts are dropped; subscriber flows replace them. `muse_web_daily` and `muse_inapp_daily` stay in the payload because their methodology defines the card and e-receipt filters.
  - New sources: Pathmatics ad spend, SimilarWeb muse.ai visits and a launch benchmark (Clubhouse from `benchmark_snapshot.xlsx`, day 0 = 2020-12-15).
  - New flow sections: `inapp_flows_daily` and `web_flows_daily`. Web flows use `SUB_GAP_DAYS` and `TENURE_DAYS` (both 35) and the `member_tenure` load.
  - The agentic merchant table has a cardholders column, and the page shows example records.
- SimilarWeb muse.ai comes from the API snapshot until the Snowflake pipeline loads it (expected 2026-10-09 around 08:00). The next build switches automatically; the freshness line names the source.
- Reading the Clubhouse workbook needs `openpyxl` (added to the exploration project). The parsed result is cached under `.cache/clubhouse/`.

## Caveats for the page footer

- On 2026-09-23 Stripe renamed the descriptor from `LINKAGNT*` to `LINK*`. Both forms are matched.
- Muse Max (web $80 / in-app $100) is a handful of members a day, so treat it as directional.
- Cards cannot see in-app Muse (Apple descriptors carry no app name). E-receipts cannot see web
  Muse (Meta's direct billing sends no captured receipt). The two are complementary and are never
  added together.
- Web Muse first charges appear around 2026-09-17, nine days after launch. The cause is not
  confirmed (possible billing delay, trial or slow web adoption).
- Pathmatics ad spend is digital only, not TV. The team suspects budget has moved to TV.
- Card flows use a 35-day rule. A gross add is a payment after 35 days with no payment, by a member
  in the panel for over 35 days. A cancellation is 35 days with no payment, counted only if the member
  is still active in the panel. The first possible card cancellation is 2026-10-22.
- Apple's priced Muse receipts have no app name (`Power Plan` / `Maximum Plan`). The current filter
  catches only Apple's unpriced sign-up confirmations, so the Apple series counts new subscriptions,
  not payments (see `investigations/android_crosscheck.ipynb`). Fix pending sign-off.
