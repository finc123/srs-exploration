"""Steam players for the Steam Trends page: app/steam-share/players.json.

Monthly players for today's top games, from bots.steam (the sync_steam_universe / sync_steam_ccu workflows):

- Games: today's SteamCharts top 1,000 (bots.steam.universe, latest snapshot, top_rank <= 1,000), games only
  (bots.steam.games.is_game; software such as Wallpaper Engine is left out). Top 100 = top_rank <= 100.
- Players per game per month = the game's highest SteamCharts reading in the month (bots.steam.steamcharts_history).
  SteamCharts stores one point per month (the month's peak) before ~Aug 2026, daily peaks to ~Sep 2026 and hourly
  readings for the last ~30 days, so the monthly peak is the only measure that is the same on every base. An average
  of the points would mix peaks with hourly readings and show a false drop.
- Total = sum of the games' monthly peaks (peaks fall at different hours, so this is above the true concurrent peak).
- Survivorship: the games are today's top games, so earlier years hold fewer of them (a game launched in 2024 adds
  nothing before 2024). The top 100 is less affected than the top 1,000.
- The current month runs to the latest SteamCharts reading (end).
- live: our own 30-min polling (bots.steam.ccu, from 19 Nov 2026): players summed over every polled game at the
  latest complete slot.

Run: uv run python players/build_players.py   (from steam/notebooks)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import snowflake.connector

OUT = Path(__file__).resolve().parents[1] / "app" / "steam-share" / "players.json"
FROM = "2012-07-01"   # SteamCharts history starts Jul 2012

MONTHLY_SQL = f"""
WITH u AS (
    SELECT u.appid, u.top_rank
    FROM bots.steam.universe u
    JOIN bots.steam.games g USING (appid)
    WHERE u.snapshot_date = (SELECT MAX(snapshot_date) FROM bots.steam.universe)
      AND u.top_rank <= 1000
      AND NVL(g.is_game, TRUE)
), m AS (
    SELECT h.appid, u.top_rank, DATE_TRUNC('month', h.ts) :: DATE AS month, MAX(h.players) AS peak, MAX(h.ts) AS last_ts
    FROM bots.steam.steamcharts_history h
    JOIN u USING (appid)
    WHERE h.ts >= '{FROM}'
    GROUP BY 1, 2, 3
)
SELECT
    month,
    SUM(peak) AS top1000,
    COUNT(*) AS top1000_games,
    SUM(IFF(top_rank <= 100, peak, 0)) AS top100,
    COUNT_IF(top_rank <= 100) AS top100_games,
    MAX(last_ts) AS last_ts
FROM m
GROUP BY 1
ORDER BY 1
"""

LIVE_SQL = """
WITH s AS (
    SELECT slot_utc, SUM(player_count) AS players, COUNT(player_count) AS games
    FROM bots.steam.ccu
    GROUP BY 1
)
SELECT slot_utc, players, games, (SELECT MIN(slot_utc) FROM bots.steam.ccu) AS since
FROM s
WHERE games >= 0.95 * (SELECT MAX(games) FROM s)   -- latest complete slot
ORDER BY slot_utc DESC
LIMIT 1
"""


def fetch(con, sql: str) -> pl.DataFrame:
    cur = con.cursor()
    cur.execute(sql)
    return pl.from_arrow(cur.fetch_arrow_all()).rename(str.lower)


def main() -> None:
    con = snowflake.connector.connect(connection_name="default", warehouse="ANALYST_XL", network_timeout=600)
    m, live = fetch(con, MONTHLY_SQL), fetch(con, LIVE_SQL)
    end = m["last_ts"].max()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "players": {
            "start": m["month"][0].isoformat(),
            "end": end.date().isoformat(),
            "top1000": m["top1000"].cast(pl.Int64).to_list(),
            "top1000_games": m["top1000_games"].to_list(),
            "top100": m["top100"].cast(pl.Int64).to_list(),
            "top100_games": m["top100_games"].to_list(),
            "live": {"slot": live["slot_utc"][0].isoformat(timespec="minutes"), "players": int(live["players"][0]),
                     "games": int(live["games"][0]), "since": live["since"][0].date().isoformat()},
        },
    }
    OUT.write_text(json.dumps(payload, separators=(",", ":")))
    p = payload["players"]
    print(f"{OUT.name}: {len(p['top1000'])} months {p['start']} to {p['end']}; last full month top 1,000 {p['top1000'][-2]:,}, "
          f"top 100 {p['top100'][-2]:,}; live {p['live']}")


if __name__ == "__main__":
    main()
