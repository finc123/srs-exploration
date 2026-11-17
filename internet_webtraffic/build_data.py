"""Build app/data.json for the Internet Web Traffic Tracker page.

    ..\\.venv\\Scripts\\python.exe build_data.py

Source: SIMILARWEB.COMMON.VISITS_V2, WW, marketing_channels_desktop_visits.
  * total = sum of all desktop channels for the day
  * genai = the gen_ai channel
Both are turned into TR7D (trailing 7-day average of daily visits, blank unless all
7 days exist) and y/y = TR7D(t) / TR7D(t - 364) - 1.
  * share = TR7D(genai) / TR7D(total), level only
The page does no maths: it only
picks arrays out of `series` by domain and type.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
OUT = HERE / "app" / "data.json"

CATEGORIES = [
    {"key": "otas", "label": "OTAs", "domains": ["booking.com", "expedia.com", "airbnb.com"]},
    {"key": "marketplaces", "label": "Marketplaces", "domains": ["ebay.com", "etsy.com", "stubhub.com"]},
    {"key": "ecommerce", "label": "E-Commerce", "domains": ["chewy.com", "wayfair.com"]},
    {"key": "realestate", "label": "Real Estate", "domains": ["zillow.com"]},
    {"key": "social", "label": "Social Media", "domains": ["reddit.com", "pinterest.com"]},
]
DOMAINS = [d for c in CATEGORIES for d in c["domains"]]
WINDOW = 7
SHIFT = 364


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def q(sql: str) -> pd.DataFrame:
    import snowflake.connector
    conn = snowflake.connector.connect(connection_name=os.getenv("SNOWFLAKE_CONNECTION", "default"))
    try:
        df = conn.cursor().execute(sql).fetch_pandas_all()
    finally:
        conn.close()
    df.columns = [c.lower() for c in df.columns]
    return df


def load() -> pd.DataFrame:
    """One row per (domain, date): desktop total and gen_ai visits."""
    domains = ", ".join(f"'{d}'" for d in DOMAINS)
    return q(f"""
        SELECT domain, date,
               SUM(value)                              AS total,
               SUM(IFF(channel = 'gen_ai', value, 0))  AS genai,
               COUNT_IF(channel = 'gen_ai')            AS has_genai
        FROM SIMILARWEB.COMMON.VISITS_V2
        WHERE country = 'WW' AND metric = 'marketing_channels_desktop_visits'
          AND domain IN ({domains})
        GROUP BY domain, date
    """)


def tr7d_yoy(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    tr = s.rolling(WINDOW, min_periods=WINDOW).mean()
    yoy = tr / tr.shift(SHIFT) - 1
    return tr, yoy.replace([np.inf, -np.inf], np.nan)


def clean(s: pd.Series, digits: int) -> list:
    return [None if pd.isna(v) else round(float(v), digits) for v in s]


def main() -> None:
    raw = load()
    raw["date"] = pd.to_datetime(raw["date"])
    raw.loc[raw["has_genai"] == 0, "genai"] = np.nan          # no gen_ai row that day = missing, not zero
    missing = sorted(set(DOMAINS) - set(raw["domain"]))
    if missing:
        raise SystemExit(f"no data for {missing}")

    days = pd.date_range(raw["date"].min(), raw["date"].max(), freq="D")
    series = {}
    for d in DOMAINS:
        g = raw[raw["domain"] == d].set_index("date").reindex(days)
        series[d] = {}
        tr7d = {}
        for t in ("total", "genai"):
            tr7d[t], yoy = tr7d_yoy(g[t].astype(float))
            series[d][t] = {"tr7d": clean(tr7d[t], 0), "yoy": clean(yoy, 4)}
        # GenAI share of total: ratio of the two TR7Ds; level only, no y/y.
        series[d]["share"] = {"tr7d": clean(tr7d["genai"] / tr7d["total"].where(tr7d["total"] > 0), 5)}

    # Sanity: Wayfair October 2026 monthly sums agreed in session (desktop total 33.1m, GenAI 0.447m).
    w = raw[(raw["domain"] == "wayfair.com") & (raw["date"].dt.strftime("%Y-%m") == "2026-10")]
    log(f"wayfair Oct-26: total {w['total'].sum() / 1e6:.1f}m, genai {w['genai'].sum() / 1e6:.3f}m")
    last = {d: raw.loc[raw["domain"] == d, "date"].max().date().isoformat() for d in DOMAINS}
    log(f"dates {days[0].date()} to {days[-1].date()}; latest per domain: {last}")

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "SIMILARWEB.COMMON.VISITS_V2 (WW, marketing_channels_desktop_visits)",
        "start": days[0].date().isoformat(),
        "end": days[-1].date().isoformat(),
        "categories": CATEGORIES,
        "series": series,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    log(f"wrote {OUT.relative_to(HERE)} ({OUT.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
