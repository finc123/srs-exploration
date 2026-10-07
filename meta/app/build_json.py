"""Build meta_muse.json (and METHODOLOGY.md) for the Meta Muse page.

    ..\\..\\.venv\\Scripts\\python.exe build_json.py            # pull what's missing, then build
    ..\\..\\.venv\\Scripts\\python.exe build_json.py --offline  # build from the local cache only

Loads are cached under .cache/ as parquet:
  * card rows and panel totals per (source, day). Days older than REFRESH_DAYS
    are read from cache; newer days are re-pulled every run, because panel
    volume keeps filling in (the monorepo job does the same with a trailing
    delete + insert).
  * NIQ and SensorTower once per run date (single small queries).

The sections then run as SQL in DuckDB over tables named srs_slice.meta.*, the
same SQL the monorepo exporter will run in Snowflake. The payload envelope
matches roblox.json: {schema_version, generated_at, freshness, sections}, plus
`summary` and `methodology`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pandas as pd

import sections as S

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
OUT_JSON = HERE / "meta_muse.json"
OUT_MD = HERE / "METHODOLOGY.md"
SCHEMA_VERSION = 1
WORKERS = 8


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Snowflake (lazy: --offline never connects)
# ---------------------------------------------------------------------------
_conn = None
_conn_lock = threading.Lock()


def q(sql: str) -> pd.DataFrame:
    global _conn
    with _conn_lock:
        if _conn is None:
            import snowflake.connector
            _conn = snowflake.connector.connect(connection_name=os.getenv("SNOWFLAKE_CONNECTION", "default"))
    df = _conn.cursor().execute(sql).fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    return df


def cached(path: Path, sql: str, fresh: bool, offline: bool) -> pd.DataFrame:
    """Read `path` if it exists and is allowed to be reused, else run `sql` and write it."""
    if path.exists() and (not fresh or offline):
        return pd.read_parquet(path)
    if offline:
        raise FileNotFoundError(f"--offline and no cache for {path.relative_to(HERE)}")
    df = q(sql)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df


# ---------------------------------------------------------------------------
# Loads
# ---------------------------------------------------------------------------
def slug(s: str) -> str:
    return s.lower().replace(" ", "_")


CARD_KINDS = {"card_rows": S.card_rows_sql, "panel_totals": S.panel_total_sql}
KIND_SOURCES = {"card_rows": S.CARD_SOURCES, "panel_totals": S.DENOMINATOR_SOURCES}


def day_path(kind: str, src: dict, d: date) -> Path:
    return CACHE / kind / slug(src["name"]) / f"{d.isoformat()}.parquet"


def ranges(days: list[date], max_days: int | None) -> list[tuple[date, date]]:
    """Contiguous runs of `days`, each cut to at most `max_days` long."""
    out: list[list[date]] = []
    for d in sorted(days):
        if out and d - out[-1][-1] == timedelta(days=1) and (max_days is None or len(out[-1]) < max_days):
            out[-1].append(d)
        else:
            out.append([d])
    return [(r[0], r[-1]) for r in out]


def pull_range(kind: str, src: dict, start: date, end: date) -> None:
    """One query for [start, end], split into one cache file per day (empty days included)."""
    df = q(CARD_KINDS[kind](src, start.isoformat(), end.isoformat()))
    day = pd.to_datetime(df["day"]).dt.date if len(df) else pd.Series([], dtype=object)
    for d in pd.date_range(start, end).date:
        p = day_path(kind, src, d)
        p.parent.mkdir(parents=True, exist_ok=True)
        df[day == d].to_parquet(p, index=False)


def load_cards(run_date: date, offline: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    days = list(pd.date_range(S.CARD_START, run_date - timedelta(days=1)).date)
    refresh_from = run_date - timedelta(days=S.REFRESH_DAYS)
    jobs = []
    for kind in CARD_KINDS:
        for src in KIND_SOURCES[kind]:
            need = [d for d in days if not day_path(kind, src, d).exists() or (d >= refresh_from and not offline)]
            if need and offline:
                raise FileNotFoundError(f"--offline and {len(need)} uncached days for {kind} / {src['name']}")
            jobs += [(kind, src, a, b) for a, b in ranges(need, src["max_days"])]

    log(f"cards: {len(jobs)} queries for {len(S.CARD_SOURCES)} sources x {len(days)} days")
    t0 = time.time()
    with ThreadPoolExecutor(WORKERS) as pool:
        futs = {pool.submit(pull_range, *j): j for j in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            kind, src, a, b = futs[fut]
            fut.result()
            if b > a or i % 25 == 0 or i == len(jobs):
                log(f"  {i}/{len(jobs)} {kind} {src['name']} {a}..{b} ({time.time() - t0:.0f}s)")

    def read(kind: str) -> pd.DataFrame:
        return pd.concat([pd.read_parquet(day_path(kind, s, d)) for s in KIND_SOURCES[kind] for d in days],
                         ignore_index=True)
    return read("card_rows"), read("panel_totals")


def load_single(name: str, sql: str, run_date: date, offline: bool) -> pd.DataFrame:
    path = CACHE / name / f"{run_date.isoformat()}.parquet"
    if offline and not path.exists():
        latest = sorted((CACHE / name).glob("*.parquet"))
        if not latest:
            raise FileNotFoundError(f"--offline and no cache for {name}")
        path = latest[-1]
    log(f"{name}: {'cache' if path.exists() else 'query'}")
    return cached(path, sql, fresh=False, offline=offline)


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def to_duckdb(tables: dict[str, tuple[pd.DataFrame, list[str]]]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("ATTACH ':memory:' AS srs_slice")
    con.execute("CREATE SCHEMA srs_slice.meta")
    for name, (df, date_cols) in tables.items():
        con.register("_df", df)
        casts = ", ".join(f"CAST({c} AS DATE) AS {c}" for c in date_cols)
        con.execute(f"CREATE TABLE srs_slice.meta.{name} AS SELECT * REPLACE ({casts}) FROM _df")
        con.unregister("_df")
    return con


def densify_tr7d(df: pd.DataFrame, sec: dict, start: str, through: str | None) -> pd.DataFrame:
    """One row per calendar day per key combo, plus a *_TR7D column per measure.

    TR7D = mean of the 7 calendar days ending on DATE, only when all 7 are
    present (fill_zero sections: a day absent from the scan is a true zero).
    """
    keys, measures = sec["keys"], sec["measures"]
    end = through or (df.DATE.max() if len(df) else start)
    cal = pd.date_range(start, end).strftime("%Y-%m-%d")
    combos = df[keys].drop_duplicates() if keys else pd.DataFrame(index=[0])
    if keys and combos.empty:
        return df.assign(**{f"{m}_TR7D": None for m in measures})
    frames = []
    for _, combo in combos.iterrows():
        g = df
        for k in keys:
            g = g[g[k] == combo[k]]
        g = g.set_index("DATE").reindex(cal)
        g.index.name = "DATE"
        for k in keys:
            g[k] = combo[k]
        for m in measures:
            s = pd.to_numeric(g[m], errors="coerce")
            if sec["fill_zero"]:
                s = s.fillna(0)
            g[m] = s
            tr = s.rolling(S.TR_DAYS, min_periods=S.TR_DAYS).mean()
            # 3 decimals for small counts; whole numbers once values are large (DAU, downloads), to keep the payload small.
            g[f"{m}_TR7D"] = tr.round(3) if tr.abs().max(skipna=True) < 1e4 else tr.round(0)
        frames.append(g.reset_index())
    out = pd.concat(frames, ignore_index=True)
    return out[["DATE", *keys, *[c for m in measures for c in (m, f"{m}_TR7D")]]]


def add_derived(df: pd.DataFrame, derived: dict) -> pd.DataFrame:
    for col, (num, den, scale) in derived.items():
        d = pd.to_numeric(df[den], errors="coerce")
        df[col] = (pd.to_numeric(df[num], errors="coerce") / d.where(d > 0) * scale).round(4)
    return df


def records(df: pd.DataFrame) -> list[dict]:
    df = df.astype(object).where(df.notna(), None)
    return df.to_dict("records")


def summary_rows(sections: dict[str, pd.DataFrame]) -> list[dict]:
    out = []
    for item in S.SUMMARY:
        df = sections[item["section"]]
        share = item.get("share_of")
        denom = df
        for k, v in item["where"].items():
            df = df[df[k] == v]
            if share and k != share["key"]:
                denom = denom[denom[k] == v]
        s = pd.to_numeric(df.groupby("DATE")[item["col"]].sum(min_count=1), errors="coerce").dropna()
        if share:
            denom = denom[denom[share["key"]].isin(share["values"])]
            # Only days where every app in the set has a value, so a missing app can't inflate the share.
            full = denom.groupby("DATE")[item["col"]].count() == len(share["values"])
            d = pd.to_numeric(denom.groupby("DATE")[item["col"]].sum(min_count=1), errors="coerce")
            s = (s / d[full]).dropna()
        if s.empty:
            out.append(dict(LABEL=item["label"], AS_OF=None, VALUE=None, PRIOR_7D=None, WOW=None))
            continue
        as_of = s.index.max()
        prior_d = (date.fromisoformat(as_of) - timedelta(days=7)).isoformat()
        prior = s.get(prior_d)
        wow = (s[as_of] / prior - 1) if prior else None
        out.append(dict(LABEL=item["label"], SECTION=item["section"], COLUMN=item["col"], AS_OF=as_of,
                        KIND="share" if share else "level",
                        VALUE=round(float(s[as_of]), 4), PRIOR_7D=None if prior is None else round(float(prior), 4),
                        WOW=None if wow is None else round(float(wow), 4)))
    return out


def methodology_payload() -> list[dict]:
    return [dict(KEY=s["key"], TITLE=s["title"], SOURCE=s["methodology"]["source"],
                 FILTERS=[dict(RULE=r, WHY=w) for r, w in s["methodology"]["filters"]],
                 DEDUPE=s["methodology"]["dedupe"], MEASURE=s["methodology"]["measure"],
                 LAG=s["methodology"]["lag"]) for s in S.SECTIONS]


def methodology_md(params: dict) -> str:
    lines = [
        "# Meta Muse: methodology",
        "",
        "_Generated by `build_json.py` from `sections.py`. Edit the methodology there, not here._",
        "",
        "Every series is published **daily** and as **TR7D**, the mean of the 7 calendar days ending on "
        "each date. TR7D is left empty unless all 7 days are present and inside that source's complete-through "
        "date, so a partial week never reads as a drop. Ratios (per million, shares) are computed from 7-day "
        "sums, not by averaging daily ratios.",
        "",
        f"Muse launched on {S.LAUNCH}. Card and e-receipt windows start {S.CARD_START} to give a pre-launch "
        f"baseline; SensorTower starts {S.APP_START}.",
        "",
        "**Why two sources for subscriptions?** They see different halves of the market: card panels see web "
        "sign-ups billed directly by Meta (`METAPAY META.COM`), but Apple card descriptors carry no app name. "
        "E-receipts see App Store and Google Play subscriptions by name, but Meta's own web billing sends "
        "no receipt the panel captures. Neither is double-counted against the other.",
        "",
        f"Complete-through dates for this build: cards {params['card_through']}, e-receipts {params['niq_through']}.",
        "",
    ]
    for s in S.SECTIONS:
        m = s["methodology"]
        lines += [f"## {s['title']}", "", f"`sections.{s['key']}`", "", f"**Source.** {m['source']}", "",
                  "**Filters.**", "", "| Rule | Why |", "|---|---|"]
        lines += [f"| {r} | {w} |" for r, w in m["filters"]]
        lines += ["", f"**Deduplication.** {m['dedupe']}", "", f"**Measure.** {m['measure']}", "",
                  f"**Lag.** {m['lag']}", ""]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="build from .cache only; never connect")
    ap.add_argument("--cache-cards", action="store_true",
                    help="reuse cached card days instead of re-pulling the last REFRESH_DAYS (NIQ/SensorTower still pull)")
    ap.add_argument("--run-date", default=date.today().isoformat())
    args = ap.parse_args()
    run_date = date.fromisoformat(args.run_date)
    t0 = time.time()

    card_rows, panel_totals = load_cards(run_date, args.offline or args.cache_cards)
    niq = load_single("niq_receipts", S.NIQ_SQL, run_date, args.offline)
    app = load_single("app_usage", S.APP_USAGE_SQL, run_date, args.offline)
    if _conn is not None:
        _conn.close()  # explicit close; leaving it to interpreter exit re-triggered the OAuth browser prompt

    con = to_duckdb({
        "card_txns": (card_rows, ["day"]),
        "panel_totals": (panel_totals, ["day"]),
        "niq_receipts": (niq, ["order_date"]),
        "app_usage": (app, ["date"]),
    })
    params = dict(
        card_start=S.CARD_START,
        card_through=(run_date - timedelta(days=S.CARD_LAG_DAYS)).isoformat(),
        niq_through=(run_date - timedelta(days=S.NIQ_LAG_DAYS)).isoformat(),
        app_start=S.APP_START,
    )
    params["merch_start"] = (date.fromisoformat(params["card_through"]) - timedelta(days=27)).isoformat()

    frames: dict[str, pd.DataFrame] = {}
    for sec in S.SECTIONS:
        df = con.execute(sec["sql"].format(**params)).fetchdf()
        if sec["keys"] is not None:
            df = densify_tr7d(df, sec, params[sec["start"]], params[sec["through"]] if sec["through"] else None)
        frames[sec["key"]] = add_derived(df, sec.get("derived", {}))

    usage = frames["app_usage_daily"]
    freshness = [
        dict(DATASET="Card panels", MAX_DATE=params["card_through"]),
        dict(DATASET="E-receipts", MAX_DATE=params["niq_through"]),
        dict(DATASET="SensorTower downloads", MAX_DATE=usage.loc[usage.DOWNLOADS.notna(), "DATE"].max()),
        dict(DATASET="SensorTower DAU", MAX_DATE=usage.loc[usage.DAU.notna(), "DATE"].max()),
    ]
    payload = dict(
        schema_version=SCHEMA_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(),
        launch_date=S.LAUNCH,
        share_apps=S.SHARE_APPS,
        freshness=freshness,
        summary=summary_rows(frames),
        methodology=methodology_payload(),
        sections={k: records(v) for k, v in frames.items()},
    )
    body = json.dumps(payload, separators=(",", ":"), default=str)
    OUT_JSON.write_text(body, encoding="utf-8")
    OUT_MD.write_text(methodology_md(params), encoding="utf-8")
    counts = {k: len(v) for k, v in frames.items()}
    log(f"wrote {OUT_JSON.name} ({len(body) / 1024:.1f} KB) {counts} and {OUT_MD.name} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
