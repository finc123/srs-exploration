"""Muse from Meta: web-billed (direct) consumer subscriptions on card panels.

Rule reused from meta/app/sections.py (muse_web_sql / WEB_BUCKETS / plan_sql):
  descriptor  METAPAY META.COM <ST>  (no '*'; METAPAY* is Meta Pay P2P / other merchants)
  price point Power 15.99-17.60, Max 79.99-88.00 USD (web $16 / $80 before sales tax, +10% tax headroom)
Monthly only (no annual plan exists). US launch 2026-09-08 (partial day 09-07 in SensorTower), so in-band
charges dated before 2026-09-07 are rejected. The same descriptor carried pre-Muse Meta subscriptions
(Meta One Core $7.99, ~$11.99-13.25 legacy plan, Meta One Premium / Verified $19.99-21.99): rejected as look-alikes.
Google Play billing (GOOGLE *MUSE FROM META) is kept as channel='google_play' at Play price points
(Power $20, Max $100, + up to ~11% sales tax).
Muse is not launched in the UK/EU: Fable rows are returned but never kept (reason 'region_not_launched').
"""
import re
import numpy as np
import pandas as pd

PROVIDER = "muse"
LAUNCH = pd.Timestamp("2026-09-07")
WEB_BUCKETS = {"power": (15.99, 17.60), "max": (79.99, 88.00)}
PLAY_BUCKETS = {"power": (19.99, 22.20), "max": (99.99, 111.00)}
# Pre-Muse Meta subscriptions on the same descriptor (bands include up to ~11% sales tax).
LOOKALIKES = [("meta_one_core", 7.99, 8.87), ("legacy_meta_sub", 11.99, 13.30), ("meta_one_premium", 19.99, 22.19)]

WEB_RE = re.compile(r"METAPAY ?(?:\d{4} )?META\.COM", re.I)
STAR_RE = re.compile(r"METAPAY ?\*", re.I)
GPLAY_RE = re.compile(r"GOOGLE ?\*? ?MUSE FROM META", re.I)
FEE_RE = re.compile(r"COURTESY PAY FEE|INTERNATIONAL SERVICE FEE|SERVICE ASSESS|RETURN|PROVISIONAL CREDIT|DISPUTE", re.I)

COLS = ["uid", "dt", "amount", "currency", "descr", "provider", "tier", "cadence", "plan", "channel", "keep", "reason"]


def _band(a: float, buckets: dict = WEB_BUCKETS):
    for tier, (lo, hi) in buckets.items():
        if lo <= a <= hi:
            return tier
    return None


def _lookalike(a: float):
    for name, lo, hi in LOOKALIKES:
        if lo <= a <= hi:
            return name
    return None


def _normalise(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    if panel == "omega":
        out = pd.DataFrame({"uid": df["uid"], "dt": pd.to_datetime(df["dt"]),
                            "amount": pd.to_numeric(df["amount"], errors="coerce").astype(float),
                            "currency": df["currency"], "descr": df["descr"],
                            "credit": df["transtype"].str.lower().eq("credit"), "business": False})
    else:
        spendout = pd.to_numeric(df["spendout"], errors="coerce").fillna(0.0)
        spendin = pd.to_numeric(df["spendin"], errors="coerce").fillna(0.0)
        dt = pd.to_datetime(df["dt"])
        out = pd.DataFrame({"uid": df["uid"], "dt": dt, "amount": np.where(spendout < 0, -spendout, -spendin),
                            "currency": df["currency"], "descr": df["descr"],
                            "credit": (spendin > 0) & (spendout >= 0), "business": df["usertype"].ne("C")})
    return out


def classify(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    d = df[df["descr"].notna()]
    web = d["descr"].str.contains(WEB_RE) & ~d["descr"].str.contains(STAR_RE)
    gp = d["descr"].str.contains(GPLAY_RE)
    d = _normalise(d[web | gp], panel)
    if d.empty:
        return pd.DataFrame(columns=COLS)
    d["channel"] = np.where(d["descr"].str.contains(GPLAY_RE), "google_play", "web")
    d["provider"] = PROVIDER
    d["cadence"] = "M"
    d["tier"] = [_band(a, WEB_BUCKETS if c == "web" else PLAY_BUCKETS) for a, c in zip(d["amount"], d["channel"])]
    d["plan"] = d["tier"].map(lambda t: f"{t}_M" if t else None)

    reason = pd.Series("ok", index=d.index, dtype=object)
    look = d["amount"].map(_lookalike)
    a = d["amount"]
    # Order: later assignments take precedence (most fundamental last).
    reason[d["tier"].isna()] = "out_of_band"
    lk = d["tier"].isna() & look.notna() & d["channel"].eq("web")
    reason[lk] = "lookalike_" + look[lk].astype(str)
    reason[d["tier"].notna() & (d["dt"] < LAUNCH)] = "pre_launch"
    reason[d["business"]] = "business_user"
    if panel != "omega":
        reason[:] = "region_not_launched"  # no UK/EU launch: never kept
    reason[d["descr"].str.contains(FEE_RE)] = "fee_or_adjustment"
    reason[(panel == "omega") & d["currency"].ne("USD")] = "non_usd"
    reason[a.abs() <= 1.0] = "auth_le_1"
    reason[d["credit"] | (a <= 0)] = "refund_credit"

    d["reason"] = reason
    d["keep"] = reason.eq("ok")
    d["amount"] = d["amount"].abs()
    d = d.sort_values(["uid", "dt", "amount", "keep"], ascending=[True, True, True, False], kind="mergesort")
    dup = d.duplicated(["uid", "dt", "amount"], keep="first")
    d.loc[dup, "keep"] = False
    d.loc[dup, "reason"] = "duplicate_same_day"
    d["dt"] = d["dt"].dt.date
    return d[COLS].reset_index(drop=True)
