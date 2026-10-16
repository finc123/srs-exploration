"""Shared helpers for the Zillow notebooks: Snowflake access, VA benchmarks, quarter helpers."""
from functools import lru_cache
from pathlib import Path

import pandas as pd
import snowflake.connector

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)


@lru_cache(maxsize=1)
def _conn():
    return snowflake.connector.connect(connection_name="default")


def q(sql: str) -> pd.DataFrame:
    """Run SQL and return a DataFrame with lower-case column names."""
    cur = _conn().cursor()
    try:
        df = cur.execute(sql).fetch_pandas_all()
    finally:
        cur.close()
    df.columns = [c.lower() for c in df.columns]
    return df


def va(kpi: str | None = None) -> pd.DataFrame:
    """Visible Alpha benchmarks (reported + consensus), pulled via the audited SRS MCP kpi_data action."""
    df = pd.read_csv(DATA / "va_benchmarks.csv", parse_dates=["period_end"])
    df["quarter"] = df["period_end"].dt.to_period("Q")
    return df if kpi is None else df[df["kpi"] == kpi].reset_index(drop=True)


def backtest_stats(df: pd.DataFrame, est: str = "estimate", rep: str = "reported", cons: str = "consensus") -> pd.Series:
    """Out-of-sample accuracy of an estimate vs reported, and vs consensus, over rows where all exist."""
    d = df.dropna(subset=[est, rep])
    err = d[est] / d[rep] - 1
    out = {"n": len(d), "mape": err.abs().mean(), "bias": err.mean()}
    dc = d.dropna(subset=[cons])
    if len(dc):
        cerr = dc[cons] / dc[rep] - 1
        out["cons_mape"] = cerr.abs().mean()
        # direction hit: does (estimate vs consensus) call the beat/miss correctly?
        hit = ((dc[est] > dc[cons]) == (dc[rep] > dc[cons]))
        out["beat_miss_hit_rate"] = hit.mean()
        out["n_cons"] = len(dc)
    return pd.Series(out)
