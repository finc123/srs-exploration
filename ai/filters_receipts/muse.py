"""Muse from Meta (`muse`): e-receipt filter (NIQ US; Fox EU has none).

Rules (reused from meta/app/sections.py NIQ_SQL, plus the Apple quirk):
  Apple charge   merchant iTunes, item 'Power Plan' / 'Maximum Plan' (bare, no app name) or
                 'Power Plan : Power Plan (Monthly)' (renewal form), priced, dated >= 2026-09-07.
                 A pre-launch control (2025-01..2026-08) shows no bare 'Power Plan'/'Maximum Plan' iTunes items.
  Apple confirm  'Muse from Meta Power Plan $20.00 /month' is UNPRICED: a confirmation, not a charge.
  Google Play    'Power Plan (Muse from Meta) Auto-renewing subscription', priced.
  Cancels        cancellation senders (iTunes / Google Play / Muse Cancellation) naming 'Muse from Meta',
                 or 'will end on' / 'canceled' text on a Muse item.
Monthly only. Price bands: Power 19.99-22.20, Max 99.99-111.00 USD (in-app $20 / $100, + tax headroom).
Muse web billing (METAPAY META.COM, $16 / $80) sends no NIQ receipt: Meta's own receipts cover only API tokens
(Muse Spark / Wonder) and Muse Code ($5 / $15 / $50), which are excluded (not in the keyword extract anyway).
Not launched in the UK/EU: EU rows are never kept ('region_not_launched').
"""
import re
import numpy as np
import pandas as pd

PROVIDER = "muse"
LAUNCH = pd.Timestamp("2026-09-07")
BANDS = {"power": (19.99, 22.20), "max": (99.99, 111.00)}

APPLE_BARE_RE = re.compile(r"^\s*(power|maximum) plan(\s*:\s*(power|maximum) plan\s*\((monthly|1 month)\))?\s*$", re.I)
MUSE_RE = re.compile(r"muse from meta", re.I)
TIER_RE = re.compile(r"\b(power|maximum|max)\b", re.I)
CANCEL_TXT_RE = re.compile(r"cancel|will end on|has ended|expire", re.I)
TRIAL_RE = re.compile(r"trial", re.I)
END_RE = re.compile(r"(?:on|until)\s+([A-Z][a-z]{2,8})\.? (\d{1,2})(?:,? (\d{4}))?")
PRORATION_RE = re.compile(r"\(muse from meta\)\s*$", re.I)  # Play item without 'Auto-renewing subscription'


COLS = ["uid", "dt", "country", "provider", "tier", "cadence", "plan", "channel", "kind", "amount", "currency",
        "end_date", "renews", "keep", "reason", "descr"]


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=COLS)


def _tier(text: str):
    m = TIER_RE.search(text or "")
    if not m:
        return None
    return "power" if m.group(1).lower() == "power" else "max"


def _band(a):
    if pd.isna(a):
        return None
    for t, (lo, hi) in BANDS.items():
        if lo <= a <= hi:
            return t
    return None


def _end_date(text: str, dt: pd.Timestamp):
    m = END_RE.search(text or "")
    if not m:
        return pd.NaT
    year = int(m.group(3)) if m.group(3) else dt.year
    e = pd.to_datetime(f"{m.group(1)[:3]} {m.group(2)} {year}", format="%b %d %Y", errors="coerce")
    if not m.group(3) and pd.notna(e) and e < dt.normalize() - pd.Timedelta(days=31):
        e = e + pd.DateOffset(years=1)  # 'will end on Jan 3' sent in December
    return e


def _channel(merchant: str) -> str:
    m = (merchant or "").lower()
    if m.startswith("itunes") or m.startswith("apple"):
        return "apple"
    if m.startswith("google play"):
        return "google_play"
    return "other"


def _eu(df: pd.DataFrame) -> pd.DataFrame:
    txt = (df["product_name"].fillna("") + " " + df["descr"].fillna("") + " " + df["seller_name"].fillna(""))
    d = df[txt.str.contains(MUSE_RE)]
    if d.empty:
        return _empty()
    out = pd.DataFrame({"uid": d["uid"], "dt": pd.to_datetime(d["dt"]), "country": d["country"],
                        "provider": PROVIDER, "tier": None, "cadence": "M", "plan": None,
                        "channel": d["merchant_name"].map(_channel), "kind": "charge",
                        "amount": pd.to_numeric(d["item_price"], errors="coerce"),
                        "currency": d["order_currency"].str.upper(), "end_date": pd.NaT, "renews": True,
                        "keep": False, "reason": "region_not_launched", "descr": d["product_name"]})
    return out[COLS]


def classify(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    if panel == "eu":
        return _eu(df)
    merch = df["merchant_name"].fillna("")
    descr = df["descr"].fillna("")
    is_apple = merch.str.match(r"(?i)itunes|apple")
    bare = is_apple & descr.str.match(APPLE_BARE_RE)
    muse = descr.str.contains(MUSE_RE) | merch.str.contains(r"(?i)^muse")
    d = df[bare | muse].copy()
    if d.empty:
        return _empty()
    d["descr"] = d["descr"].fillna("")
    d["merchant_name"] = d["merchant_name"].fillna("")
    d["dt"] = pd.to_datetime(d["dt"])
    d["amount"] = pd.to_numeric(d["item_price"], errors="coerce")
    d["channel"] = d["merchant_name"].map(_channel)
    is_cancel = d["merchant_name"].str.contains(r"(?i)cancel") | d["descr"].str.contains(CANCEL_TXT_RE)
    d["kind"] = np.where(is_cancel, "cancel", "charge")
    d["tier"] = [_tier(t) or _band(a) for t, a in zip(d["descr"], d["amount"])]
    d["cadence"] = "M"
    d["plan"] = np.where(d["tier"].notna(), d["tier"].astype(str) + "_M", "unknown_M")
    d["end_date"] = [(_end_date(t, x) if k == "cancel" else pd.NaT) for t, x, k in zip(d["descr"], d["dt"], d["kind"])]
    d["end_date"] = pd.to_datetime(d["end_date"])
    d["renews"] = d["channel"].isin(["apple", "google_play"])

    reason = pd.Series("ok", index=d.index, dtype=object)
    ch = d["kind"].eq("charge")
    band = d["amount"].map(_band)
    # later assignments take precedence
    reason[ch & band.isna()] = "out_of_band"
    reason[ch & band.notna() & d["tier"].notna() & (band != d["tier"])] = "tier_price_mismatch"
    reason[ch & d["channel"].eq("google_play") & d["descr"].str.contains(PRORATION_RE) & band.isna()] = "upgrade_proration"
    reason[ch & (d["amount"].isna() | (d["amount"] <= 0))] = "unpriced_confirmation"
    reason[ch & d["descr"].str.contains(TRIAL_RE)] = "trial"
    reason[d["kind"].eq("cancel") & d["descr"].str.contains(r"(?i)trial (?:has )?end")] = "trial_end"
    reason[d["channel"].eq("other")] = "other_sender"
    reason[d["dt"] < LAUNCH] = "pre_launch"
    d["reason"] = reason
    d["currency"] = np.where(ch, "USD", None)
    d.loc[~ch, "amount"] = np.nan
    d["country"] = "us"
    d["provider"] = PROVIDER

    # de-duplicate repeated line items (same uid, day, channel, kind, plan, amount)
    d["_day"] = d["dt"].dt.normalize()
    d["_ok"] = d["reason"].ne("ok")
    d = d.sort_values(["uid", "_day", "_ok", "dt"], kind="stable")
    dup = d["reason"].eq("ok") & d.duplicated(["uid", "_day", "channel", "kind", "plan", "amount"])
    d.loc[dup, "reason"] = "duplicate"
    d["keep"] = d["reason"].eq("ok")
    return d[COLS].reset_index(drop=True)
