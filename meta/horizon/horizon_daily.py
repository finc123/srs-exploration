"""Meta Horizon Worlds CCU: raw 72degree scrapes -> daily world + platform tables.

Source: s3://srs-vendors/72degree/metahorizon/data/detail/metahorizon_detail_<YYYY-MM-DD>-<HH>.csv
One file per scrape, 4 scrapes/day (00/06/12/18 UTC slots). Each file is the worlds on
the horizon.meta.com homepage (Popular + Hangout lists, ~64 worlds), so coverage
rotates with Meta's curation.

The series starts 2026-10-14 (SERIES_START). Earlier files came from a broken vendor
process: world detail pages (ccu) were scraped once per day and re-published by later
runs. drop_stale_scrapes() guards against that recurring.

The two outputs mirror the planned SRS_MCP.META views:
  HORIZON_WORLDS_DAILY   - one row per (date, world_id)
  HORIZON_PLATFORM_DAILY - one row per date
"""
import io
import re

import pandas as pd

BUCKET = "srs-vendors"
PREFIX = "72degree/metahorizon/data/detail/"
FILE_RE = re.compile(r"metahorizon_detail_(\d{4}-\d{2}-\d{2})-(\d{2})\.csv$")
TOP_NS = (10, 30)
MAX_SLOT_DRIFT_MIN = 15  # panel index: same slot on the anchor day must start within this many minutes
SERIES_START = pd.Timestamp("2026-10-14")
STALE_MIN_NONZERO = 10  # stale guard only fires with enough non-zero overlapping worlds to rule out chance


def load_snapshots(s3=None) -> pd.DataFrame:
    """One row per world per scrape from SERIES_START, stale scrapes removed.

    `date` / `slot` come from the filename (UTC run slot). Dropped scrapes are listed in
    `.attrs["stale_scrapes"]`.
    """
    import boto3

    s3 = s3 or boto3.client("s3")
    keys = [
        o["Key"]
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=PREFIX)
        for o in page.get("Contents", [])
        if FILE_RE.search(o["Key"])
    ]
    frames = []
    for key in sorted(keys):
        body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
        frames.append(parse_snapshot(pd.read_csv(io.BytesIO(body), encoding="utf-8"), key))
    snap = pd.concat(frames, ignore_index=True) if frames else parse_snapshot(pd.DataFrame(), "")
    return drop_stale_scrapes(snap[snap["date"] >= SERIES_START])


def drop_stale_scrapes(snap: pd.DataFrame) -> pd.DataFrame:
    """Drop scrapes whose CCU is a re-publication of the previous scrape.

    A scrape is stale if every world it shares with the previous scrape has identical ccu
    (and at least STALE_MIN_NONZERO of those are non-zero, so a quiet hour can't trigger it).
    Live CCU six hours apart never matches across dozens of worlds.
    """
    keys = list(snap.groupby(["date", "slot"]).groups)
    ccu = snap.set_index(["date", "slot", "world_id"])["ccu"]
    stale = []
    for prev_key, key in zip(keys, keys[1:]):
        prev, cur = ccu.loc[prev_key], ccu.loc[key]
        common = cur.index.intersection(prev.index)
        if (prev.loc[common] > 0).sum() >= STALE_MIN_NONZERO and cur.loc[common].equals(prev.loc[common]):
            stale.append(key)
    out = snap[~snap.set_index(["date", "slot"]).index.isin(stale)].reset_index(drop=True)
    out.attrs["stale_scrapes"] = stale
    return out


def parse_snapshot(df: pd.DataFrame, key: str) -> pd.DataFrame:
    m = FILE_RE.search(key)
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(m.group(1)) if m else pd.NaT,
            "slot": int(m.group(2)) if m else pd.NA,
            "world_id": df.get("id", pd.Series(dtype="int64")).astype("int64"),
            "world_name": df.get("name"),
            "owner_name": df.get("owner_name"),
            "ccu": df.get("ccu"),
            "capacity": df.get("capacity"),
            "scraped_at_utc": pd.to_datetime(df.get("InsertUpdateTime")),
            "file_name": key.rsplit("/", 1)[-1],
        }
    )
    # A world should appear once per scrape; keep the last row if the vendor ever repeats it.
    return out.drop_duplicates(["date", "slot", "world_id"], keep="last")


def build_worlds_daily(snap: pd.DataFrame) -> pd.DataFrame:
    """avg/max CCU per world per day over the scrapes the world appeared in (missing != 0)."""
    snap = snap.sort_values(["date", "slot"])
    g = snap.groupby(["date", "world_id"], sort=True)
    return (
        g.agg(
            world_name=("world_name", "last"),
            owner_name=("owner_name", "last"),
            avg_ccu=("ccu", "mean"),
            max_ccu=("ccu", "max"),
            n_snapshots=("slot", "nunique"),
        )
        .reset_index()
    )


def _top_n_sum(worlds: pd.DataFrame, col: str, n: int) -> pd.Series:
    """Sum of `col` over the top-n worlds per day, ranked by `col`.

    Only worlds present in every scrape that day are eligible, so a world featured for part
    of the day can't inflate the sum (keeps topN_ccu_avg <= total_ccu_avg).
    """
    day_scrapes = worlds.groupby("date")["n_snapshots"].transform("max")
    full_day = worlds[worlds["n_snapshots"] == day_scrapes]
    # world_id breaks ties so results are deterministic.
    ranked = full_day.sort_values(["date", col, "world_id"], ascending=[True, False, True])
    return ranked.groupby("date").head(n).groupby("date")[col].sum()


def _comparable_slots(snap: pd.DataFrame, cur_date, prev_date) -> list:
    """Slots scraped on both days whose start times are within MAX_SLOT_DRIFT_MIN of each other
    (after removing the whole-day gap between the two dates)."""
    start = snap.groupby(["date", "slot"])["scraped_at_utc"].min()
    cur, prev = start.xs(cur_date, level="date"), start.xs(prev_date, level="date")
    day_gap = pd.Timestamp(cur_date) - pd.Timestamp(prev_date)
    common = cur.index.intersection(prev.index)
    drift = ((cur.loc[common] - prev.loc[common]) - day_gap).abs()
    return list(drift[drift <= pd.Timedelta(minutes=MAX_SLOT_DRIFT_MIN)].index)


def _panel_index(snap: pd.DataFrame) -> pd.DataFrame:
    """Chain-linked matched-sample index (100 at first date).

    Each day is compared with its anchor - the most recent earlier day with a non-null index -
    on (world_id, slot) pairs present on both, so rotation of the featured list and partial
    days (fewer slots) don't move it. A slot is only compared if its scrape started within
    MAX_SLOT_DRIFT_MIN of the same slot on the anchor day.

    With no comparable pairs the index is null for that day and the anchor stays put, so the
    chain resumes against the last valid day once comparable scrapes return.
    """
    pairs = snap.set_index(["date", "slot", "world_id"])["ccu"]
    dates = sorted(snap["date"].unique())
    rows, level, anchor = [], 100.0, None
    for d in dates:
        if anchor is None:
            rows.append({"date": d, "panel_index": level, "n_matched_slots": pd.NA, "n_matched_worlds": pd.NA})
            anchor = d
            continue
        slots = _comparable_slots(snap, d, anchor)
        cur = pairs.xs(d, level="date")
        prev = pairs.xs(anchor, level="date")
        matched = cur.index.intersection(prev.index)
        matched = matched[matched.get_level_values("slot").isin(slots)]
        base = prev.loc[matched].sum()
        index = pd.NA
        if base > 0:
            level *= cur.loc[matched].sum() / base
            index, anchor = level, d
        rows.append(
            {
                "date": d,
                "panel_index": index,
                "n_matched_slots": len(slots),
                "n_matched_worlds": matched.get_level_values("world_id").nunique(),
            }
        )
    return pd.DataFrame(rows)


def build_platform_daily(snap: pd.DataFrame, worlds: pd.DataFrame | None = None) -> pd.DataFrame:
    worlds = build_worlds_daily(snap) if worlds is None else worlds
    per_scrape = snap.groupby(["date", "slot"])["ccu"].sum()
    out = pd.DataFrame(
        {
            "n_snapshots": snap.groupby("date")["slot"].nunique(),
            "n_worlds": snap.groupby("date")["world_id"].nunique(),
            "total_ccu_avg": per_scrape.groupby("date").mean(),
            "total_ccu_max": per_scrape.groupby("date").max(),
        }
    )
    for n in TOP_NS:
        out[f"top{n}_ccu_avg"] = _top_n_sum(worlds, "avg_ccu", n)
        out[f"top{n}_ccu_max"] = _top_n_sum(worlds, "max_ccu", n)
    out = out.reset_index().merge(_panel_index(snap), on="date", how="left")
    # One row per calendar day: a day with no scrapes shows n_snapshots = 0 and null metrics.
    if len(out):
        days = pd.date_range(out["date"].min(), out["date"].max(), freq="D", name="date")
        out = out.set_index("date").reindex(days).reset_index()
        out["n_snapshots"] = out["n_snapshots"].fillna(0).astype(int)
    return out
