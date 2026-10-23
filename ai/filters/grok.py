"""Grok consumer web-subscription filter for card panels. Covers two provider lines:

  grok    SuperGrok / Heavy / Lite / Plus billed directly by xAI (descriptor GROK XAI / XAI LLC / X.AI), plus
          "The X Subscription" (Plus/Premium/Super/Ultra) sold from 2026-10-10..12, which bills on the same xAI
          descriptor (tiers prefixed `xsub_`).
  grok_x  X Premium+ billed by X Corp (X CORP. PAID FEATURES / TWITTER PAID FEATURES). Basic and Premium (non-plus)
          share the descriptor; they are returned with keep=False, reason 'x_non_plus_tier'.

classify(df, panel) -> one row per candidate payment for either provider id with plan, keep flag and reason.

xAI charges round USD amounts everywhere (no US sales tax until the X Subscription; no VAT on top in Europe), so
European xAI rows are converted back to USD with the USD amount printed in the descriptor where present (UK) or a
monthly rate estimated from the SuperGrok $30 cluster. X Corp bills fixed local prices (VAT-inclusive in Europe;
EU/UK prices were reset to round VAT-inclusive amounts in 2025-07) plus US sales tax.
"""
import re

import numpy as np
import pandas as pd

FABLE_PANELS = {"uk": "GBP", "de": "EUR", "fr": "EUR", "es": "EUR", "it": "EUR"}
ROUGH_FX = {"GBP": 0.76, "EUR": 0.88}  # local per USD; seeds the cluster search only
US_TAX_MAX = 1.11
VAT = {"uk": 1.20, "de": 1.19, "fr": 1.20, "es": 1.21, "it": 1.22}

# ---------------------------------------------------------------- descriptors (lowercased)
XAI_RE = re.compile(r"grok ?xai|xai llc|(?<![a-z0-9])x\.ai/|x\.ai/about|\.ai/about|xaiabout|grok ai assis")
XAI_GP_RE = re.compile(r"google.{0,4}grok")
# Omega masks the token "X" (X CORP. PAID FEATURES -> "CORP. PAID FEATURES ABOUT. .COM TX"), so the masked forms
# are matched too; note the keywords.py prefilter ('%x corp%') does NOT capture them (see report).
X_RE = re.compile(
    r"x ?corp\.? ?paid|twitter paid|twitter pa\b|x\.com - paid|^x corp$|^twitter$"
    r"|corp\.? ?paid fea|corp\.? paid fe?$|corp\.? paid fe\b|corp\. pa (?:865|1355)|corp\. pax corp"
)
X_GP_RE = re.compile(r"google.{0,4}(?:twitter|x corp)")
X_EXCL_RE = re.compile(r"online ads|advertis|dev platform|paypal|bx corp")
XAI_EXCL_RE = re.compile(r"ngrok|grokio|grokker|groke\b|artifexai")
USD_IN_DESCR = re.compile(r"usd[ ,]*(\d{1,5}\.\d{2})|,(\d{1,5}\.\d{2}) usd|(\d{1,5}\.\d{2}) usd")

# ---------------------------------------------------------------- dates
SUPERGROK_LAUNCH = pd.Timestamp("2025-02-01")
HEAVY_LAUNCH = pd.Timestamp("2025-07-10")
LITE_LAUNCH = pd.Timestamp("2026-03-25")
PLUS_LAUNCH = pd.Timestamp("2026-05-01")     # $99/$100 monthly-gap payments appear from 2026-05
XSUB_LAUNCH = pd.Timestamp("2026-10-10")     # first X Subscription amounts ($8.xx / $15-16.xx) seen 10-10
PPLUS_LAUNCH = pd.Timestamp("2023-10-27")
EU_RESET = pd.Timestamp("2025-07-01")        # X EU/UK prices become round VAT-inclusive amounts

# ---------------------------------------------------------------- X Corp price points (local, incl. VAT)
# tier, cadence, price, valid_from
X_US = [
    ("premium_plus", "M", 16.0, PPLUS_LAUNCH), ("premium_plus", "M", 22.0, "2024-12-21"),
    ("premium_plus", "M", 40.0, "2025-02-18"),
    ("premium_plus", "A", 168.0, PPLUS_LAUNCH), ("premium_plus", "A", 229.0, "2024-12-21"),
    ("premium_plus", "A", 395.0, "2025-02-18"),
    ("premium", "M", 8.0, "2023-01-01"), ("premium", "A", 84.0, "2023-01-01"),
    ("basic", "M", 3.0, PPLUS_LAUNCH), ("basic", "A", 32.0, PPLUS_LAUNCH),
]
_PP_EU_M = [19.04, 19.20, 19.36, 19.52, 24.99, 25.20, 25.41, 25.62, 45.22, 45.60, 45.98, 46.36]
_PP_EU_A = [199.92, 201.60, 203.28, 204.96, 260.61, 262.80, 264.99, 267.18, 448.63, 452.40, 456.17, 459.94]
X_EU = ([("premium_plus", "M", p, PPLUS_LAUNCH) for p in _PP_EU_M]
        + [("premium_plus", "A", p, PPLUS_LAUNCH) for p in _PP_EU_A]
        + [("premium_plus", "M", 38.00, EU_RESET), ("premium_plus", "A", 377.00, EU_RESET),
           ("premium_plus", "M", 19.00, "2026-01-01")]  # 19.00 = 50%-off Premium+ promo (2026)
        + [("premium", "M", p, "2023-01-01") for p in (9.52, 9.60, 9.68, 9.76, 8.00)]
        + [("premium", "A", p, "2023-01-01") for p in (99.96, 100.80, 101.64, 102.48, 84.00)]
        + [("basic", "M", p, PPLUS_LAUNCH) for p in (3.57, 3.60, 3.63, 3.66, 3.00, 4.00)]
        + [("basic", "A", p, PPLUS_LAUNCH) for p in (38.08, 38.40, 38.72, 39.04)]
        + [("basic", "A", 30.00, "2025-06-01")]
        # Oct 2024 - Feb 2025 "40% off annual" promo (0.6 x list): Premium+ and Premium annual
        + [("premium_plus", "A", round(0.6 * p, 2), "2024-10-01") for p in (199.92, 201.60, 203.28, 204.96)]
        + [("premium", "A", round(0.6 * p, 2), "2024-10-01") for p in (99.96, 100.80, 101.64, 102.48)])
# Google Play in-app prices (US, + sales tax). Premium+ $22 (2023-10..2025-01), $30 (2025-01..02), $50 (2025-02-18..)
X_US_GP = [
    ("premium_plus", "M", 22.0, PPLUS_LAUNCH), ("premium_plus", "M", 30.0, "2025-01-01"),
    ("premium_plus", "M", 50.0, "2025-02-18"),
    ("premium", "M", 11.0, "2023-01-01"), ("premium", "A", 114.99, "2023-01-01"),
    ("basic", "M", 3.99, PPLUS_LAUNCH),
]
X_UK = [("premium_plus", "M", 19.20, PPLUS_LAUNCH), ("premium_plus", "M", 20.40, "2024-12-21"),
        ("premium_plus", "M", 37.20, "2025-02-18"), ("premium_plus", "M", 31.00, EU_RESET),
        ("premium_plus", "M", 15.50, "2026-01-01"),  # 50%-off promo
        ("premium_plus", "A", 201.60, PPLUS_LAUNCH), ("premium_plus", "A", 375.60, "2025-02-18"),
        ("premium_plus", "A", 313.00, EU_RESET),
        ("premium", "M", 9.60, "2023-01-01"), ("premium", "M", 8.00, "2023-01-01"),
        ("premium", "A", 100.80, "2023-01-01"), ("premium", "A", 84.00, "2023-01-01"),
        ("basic", "M", 3.60, PPLUS_LAUNCH), ("basic", "M", 3.00, PPLUS_LAUNCH), ("basic", "M", 4.00, "2026-01-01"),
        ("basic", "A", 38.40, PPLUS_LAUNCH), ("basic", "A", 30.00, EU_RESET),
        ("premium_plus", "A", 120.96, "2024-10-01"), ("premium", "A", 60.48, "2024-10-01")]  # 40%-off annual promo


# ---------------------------------------------------------------- helpers
def _std(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    if panel == "omega":
        amt = pd.to_numeric(df["amount"], errors="coerce").astype(float)
        out = pd.DataFrame({"uid": df["uid"].astype(str), "dt": pd.to_datetime(df["dt"]), "amount": amt.abs(),
                            "currency": df["currency"], "descr": df["descr"]})
        out["refund"] = ((df["transtype"].str.lower() == "credit").values | (amt <= 0).values)
        out["lag_bad"] = False
        out["business"] = False
    else:
        so = df["spendout"].fillna(0).astype(float)
        si = df["spendin"].fillna(0).astype(float)
        out = pd.DataFrame({"uid": df["uid"].astype(str), "dt": pd.to_datetime(df["dt"]),
                            "amount": np.where(so < 0, -so, si), "currency": df["currency"], "descr": df["descr"]})
        out["refund"] = ((si > 0) & (so >= 0)).values | (out["amount"] <= 0).values
        out["lag_bad"] = False  # reportdate-vs-dt filter deliberately NOT applied (user decision: holes read as churn)
        out["business"] = (df["usertype"] != "C").values
    return out.reset_index(drop=True)


def _brand(descr: pd.Series) -> pd.Series:
    low = descr.fillna("").str.lower().str.strip()
    xai = low.str.contains(XAI_RE) & ~low.str.contains(XAI_EXCL_RE) & ~low.str.contains("google")
    xai_gp = low.str.contains(XAI_GP_RE) & ~low.str.contains(XAI_EXCL_RE)
    x = low.str.contains(X_RE) & ~low.str.contains(X_EXCL_RE) & ~low.str.contains("google")
    x_gp = low.str.contains(X_GP_RE)
    kind = np.select([xai, xai_gp, x, x_gp], ["xai", "xai_gp", "x", "x_gp"], "none")
    return pd.Series(kind, index=descr.index)


def _usd_in_descr(descr: pd.Series) -> pd.Series:
    m = descr.fillna("").str.lower().str.extract(USD_IN_DESCR)
    return pd.to_numeric(m[0].fillna(m[1]).fillna(m[2]), errors="coerce")


def _monthly_rate(d: pd.DataFrame, panel: str) -> pd.Series:
    """Local currency per USD by month: descriptor-printed USD where present, else the SuperGrok $30 cluster."""
    rough = ROUGH_FX[FABLE_PANELS[panel]]
    per = d["dt"].dt.to_period("M")
    p = d[d["usd_txt"].notna() & (d["usd_txt"] > 1)]
    r_txt = (p["amount"] / p["usd_txt"]).groupby(per[p.index]).median()
    n_txt = p.groupby(per[p.index]).size()
    c = d[(d["amount"] / rough).between(26.5, 34.0)]
    r_cl = (c["amount"] / 30.0).groupby(per[c.index]).median()
    n_cl = c.groupby(per[c.index]).size()
    rate = r_txt[n_txt >= 5].combine_first(r_cl[n_cl >= 5])
    allm = pd.period_range(per.min(), per.max(), freq="M")
    return rate.reindex(allm).interpolate().ffill().bfill().fillna(rough)


def _near(u: pd.Series, p: float, us: bool, tol: float = 0.07) -> pd.Series:
    return u.between(p * 0.995, p * US_TAX_MAX + 0.01) if us else u.between(p * (1 - tol), p * (1 + tol))


def _gaps(d: pd.DataFrame, key: str) -> pd.Series:
    """Days to the nearest other payment (same uid, same `key` band), either side."""
    s = d.sort_values(["uid", key, "dt"], kind="mergesort")
    g = s.groupby(["uid", key])["dt"]
    prev = g.diff().dt.days
    nxt = -g.diff(-1).dt.days
    return pd.concat([prev, nxt], axis=1).min(axis=1).reindex(d.index)


# ---------------------------------------------------------------- xAI
def _classify_xai(d: pd.DataFrame, us: bool, vat: float = 1.0) -> None:
    """Web and Google Play rows. Play list prices are $x.99 ($29.99 SuperGrok, $9.99 Lite, $99.99, $299.99) and
    fall in the same bands as the web prices; the $9.90 / $99 web promos and X Subscription do not exist on Play."""
    u, dt = d["usd"], d["dt"]
    gp = d["channel"] == "google_play"
    cents = (d["amount"] * 100).round() % 100 != 0
    ok = d["reason"] == "ok"
    band = pd.Series("other", index=d.index)
    spec = [("b30", 30.0), ("b300", 300.0), ("b3000", 3000.0), ("b10", 10.0), ("b100", 100.0)]
    for name, p in spec:
        band[_near(u, p, us) & (band == "other")] = name
    if us:
        band[u.between(9.85, 9.95) & ~gp] = "b9_9"
        band[u.between(98.5, 99.5) & ~gp] = "b99"
    else:
        txt = d["usd_txt"] if "usd_txt" in d else pd.Series(np.nan, index=d.index)
        band[txt.between(9.85, 9.95)] = "b9_9"   # $9.90 vs $10 only separable where the USD amount is printed
        for name, p in spec:                      # EU Play prices are VAT-inclusive local prices
            band[gp & (band == "other") & _near(u / vat, p, False, 0.12)] = name
    d["band"] = band
    gkey = band + np.where(gp, "_gp", "")
    d["gkey"] = gkey
    gap = _gaps(d[ok], "gkey").reindex(d.index)
    d["gap"] = gap
    # any later subscription-sized xAI payment by the same uid (for single $300 / $100 payments)
    subsz = ok & band.isin(["b30", "b9_9", "b10", "b99", "b300"])
    nxt_sub = (d[subsz].sort_values(["uid", "dt"]).groupby("uid")["dt"].shift(-1) - d.loc[subsz, "dt"]).dt.days
    d["next_sub"] = nxt_sub.reindex(d.index)

    def setp(mask, tier, cad, why="ok", keep=True):
        m = mask & ok & d["tier"].isna()
        d.loc[m, ["tier", "cadence"]] = [tier, cad]
        d.loc[m, "keep"] = keep
        d.loc[m, "reason"] = why

    end = d["dt"].max()
    credit = gap < 20
    # --- The X Subscription (from 2026-10-10; US amounts carry sales tax)
    xs = (dt >= XSUB_LAUNCH) & ~gp
    # --- Google Play: $29.99 SuperGrok, $9.99 Lite (Play from 2025-10), $99.99 (from 2026-04, same timing as the
    #     web $99 Heavy promo -> heavy), $299.99 Heavy; $4.99 / $19.99 / $49.99 are in-app credit packs
    setp(gp & (band == "b10") & ~credit & (dt >= pd.Timestamp("2025-10-01")), "lite", "M")
    setp(gp & (band == "b100") & ~credit, "heavy", "M")
    if us:
        setp(xs & u.between(7.99, 8.9), "xsub_plus", "M")
        setp(xs & u.between(15.0, 16.7) & ~credit, "xsub_premium", "M", "ok")      # $30 at 50% off (launch promo)
        setp(xs & u.between(30.01, 33.4) & cents, "xsub_premium", "M")
        setp(xs & u.between(50.0, 55.6) & cents, "xsub_super", "M")                 # $100 at 50% off, taxed
        setp(xs & u.between(100.01, 111.1) & cents, "xsub_super", "M")
        setp(xs & u.between(200.0, 222.1) & cents, "xsub_ultra", "M")
    else:
        # Europe bills the X Subscription in round local prices (launch promo = 50% off the first month), observed
        # 10-10..10-15: UK 7 / 13 / 45 / 90 / 180 GBP; EUR 8 / 15.50-16 / 52.50 / 105
        a = d["amount"].round(2)
        ladder = ({"xsub_plus": [7.0], "xsub_premium": [13.0, 26.0], "xsub_super": [45.0, 90.0],
                   "xsub_ultra": [180.0]} if vat == 1.20 and d["currency"].eq("GBP").all() else
                  {"xsub_plus": [8.0], "xsub_premium": [15.5, 16.0, 31.0, 32.0], "xsub_super": [52.5, 105.0],
                   "xsub_ultra": [210.0]})
        for tier, prices in ladder.items():
            setp(xs & a.isin(prices), tier, "M")
        rnd = ((d["amount"] * 2).round(2) % 1 == 0)
        loc = xs & rnd & ~band.isin(["b30", "b300", "b10", "b100"]) & d["amount"].between(6.5, 230)
        setp(loc, "xsub", None, "ambiguous", keep=False)
    # --- SuperGrok
    setp((band == "b30") & (dt >= SUPERGROK_LAUNCH), "supergrok", "M")
    setp((band == "b9_9") & (dt >= pd.Timestamp("2026-04-01")), "supergrok", "M")  # $9.90 x3-month promo -> $30
    # --- Heavy / SuperGrok annual ($300 collision)
    b300 = band == "b300"
    setp(b300 & (dt < HEAVY_LAUNCH), "supergrok", "A")
    setp(b300 & gap.between(20, 45), "heavy", "M")
    setp(b300 & gap.between(320, 410), "supergrok", "A")
    setp(b300 & gap.between(45, 320), "heavy", "M")              # intermittent Heavy months
    setp(b300 & d["next_sub"].between(20, 300), "heavy", "M")     # paid again (any tier) within the year
    setp(b300, "ambiguous", None, "ambiguous", keep=False)
    setp(band == "b99", "heavy", "M")                             # $99 x3-month Heavy promo -> $300
    setp(band == "b3000", "heavy", "A")
    # --- Lite ($10) vs $10 credit top-ups
    b10 = band == "b10"
    setp(b10 & credit, "credits", None, "api_credits", keep=False)
    setp(b10 & (dt >= LITE_LAUNCH), "lite", "M")
    setp(b10, "credits", None, "api_credits", keep=False)
    # --- $100: Plus monthly / Lite annual / credits
    b100 = band == "b100"
    setp(b100 & credit, "credits", None, "api_credits", keep=False)
    setp(b100 & gap.between(20, 45) & (dt >= PLUS_LAUNCH), "plus", "M")
    setp(b100 & gap.between(320, 410), "lite", "A")
    setp(b100 & (dt < LITE_LAUNCH), "credits", None, "api_credits", keep=False)
    setp(b100 & d["next_sub"].between(20, 300), "ambiguous", None, "ambiguous", keep=False)
    setp(b100, "ambiguous", None, "ambiguous", keep=False)
    # --- everything else on the xAI descriptor: API / usage credit top-ups ($5, $20, $50 ...)
    setp(pd.Series(True, index=d.index), "credits", None, "api_credits", keep=False)


# ---------------------------------------------------------------- X Corp
def _classify_x(d: pd.DataFrame, panel: str) -> None:
    us = panel == "omega"
    ok = d["reason"] == "ok"
    gp = d["channel"] == "google_play"
    _apply_x_table(d, ok & ~gp, X_US if us else (X_UK if panel == "uk" else X_EU), us)
    if us:
        _apply_x_table(d, ok & gp, X_US_GP, us)
    rest = ok & d["tier"].isna()
    d.loc[rest, "reason"] = "x_other_amount"  # creator subscriptions, Verified Orgs, odd FX / prorations, EU Play
    d.loc[rest, "keep"] = False


def _apply_x_table(d: pd.DataFrame, ok: pd.Series, table: list, us: bool) -> None:
    a, dt = d["amount"], d["dt"]
    for tier, cad, p, start in table:
        hit = (a.between(p - 0.005, p * US_TAX_MAX + 0.01) if us else a.between(p - 0.015, p + 0.015))
        m = hit & ok & d["tier"].isna() & (dt >= pd.Timestamp(start))
        d.loc[m, ["tier", "cadence"]] = [tier, cad]
        d.loc[m, "keep"] = tier == "premium_plus"
        d.loc[m, "reason"] = "ok" if tier == "premium_plus" else "x_non_plus_tier"


# ---------------------------------------------------------------- main
def classify(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    panel = panel.lower()
    us = panel == "omega"
    d = _std(df, panel)
    d["kind"] = _brand(d["descr"])
    d = d[d["kind"] != "none"].copy()
    if us:
        d = d[d["currency"] == "USD"].copy()
    d["provider"] = np.where(d["kind"].str.startswith("xai"), "grok", "grok_x")
    d["channel"] = np.where(d["kind"].str.endswith("_gp"), "google_play", "web")
    d["tier"], d["cadence"], d["plan"] = None, None, None
    d["keep"] = False
    d["reason"] = "ok"

    for mask, why in [(d["refund"], "refund"),
                      (d["business"], "business_user"), (d["amount"] < 1.5, "auth")]:
        d.loc[(d["reason"] == "ok") & mask, "reason"] = why
    d = d.sort_values(["uid", "dt", "amount"], kind="mergesort")
    dup = d.duplicated(["uid", "dt", "amount", "provider"]) & (d["reason"] == "ok")
    d.loc[dup, "reason"] = "duplicate"

    parts = []
    xa = d[d["provider"] == "grok"].copy()
    if len(xa):
        if us:
            xa["usd"] = xa["amount"]
        else:
            xa["usd_txt"] = _usd_in_descr(xa["descr"])
            rate = _monthly_rate(xa[(xa["reason"] == "ok")], panel)
            r = xa["dt"].dt.to_period("M").map(rate).astype(float).fillna(ROUGH_FX[FABLE_PANELS[panel]])
            xa["usd"] = xa["usd_txt"].where(xa["usd_txt"].notna() & (xa["usd_txt"] > 1), xa["amount"] / r)
        _classify_xai(xa, us, 1.0 if us else VAT[panel])
        parts.append(xa)
    xx = d[d["provider"] == "grok_x"].copy()
    if len(xx):
        _classify_x(xx, panel)
        parts.append(xx)
    if not parts:
        return pd.DataFrame(columns=["uid", "dt", "amount", "currency", "descr", "provider", "tier", "cadence",
                                     "plan", "channel", "keep", "reason"])
    out = pd.concat(parts)
    out["keep"] = out["keep"].astype(bool) & (out["reason"] == "ok")
    has = out["tier"].notna() & out["cadence"].notna()
    out.loc[has, "plan"] = out.loc[has, "tier"] + "_" + out.loc[has, "cadence"]
    out.loc[out["tier"] == "ambiguous", "plan"] = "ambiguous"
    out.loc[out["tier"] == "xsub", "plan"] = "ambiguous"
    out = out.sort_values(["provider", "uid", "dt"], kind="mergesort")
    return out[["uid", "dt", "amount", "currency", "descr", "provider", "tier", "cadence", "plan", "channel",
                "keep", "reason"]].reset_index(drop=True)
