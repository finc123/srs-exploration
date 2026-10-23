"""Cursor (Anysphere, `cursor`): e-receipt filter (NIQ US items, Fox EU items).

Where paid Cursor receipts are (checked 2026-10-19):
  US  merchant 'Cursor' (9 item texts: 'Cursor Pro plan', 'Cursor', 'Cursor Ultra', 'free plan for Cursor' ...) is
      ALWAYS unpriced (item_price and ordertotal null, ~22k rows 2023-08..2026-02): plan-welcome / plan-change emails,
      not charges ('unpriced_confirmation'). No Stripe / Anysphere / 'cursor.com' receipt exists in ITEMS_LIVE.
      The only priced Cursor receipts are Apple in-app (Cursor iOS app, from 2026-06-29):
      'Cursor : Pro (Monthly)' $25.99, 'Cursor : Pro+ (Monthly)' $77.99, 'Cursor : Ultra (Monthly)' $259.99.
      'Cursor Pro $25.99 /month' is the unpriced Apple confirmation (not a charge).
      Cancels: 'Cursor Cancellation' sender ('canceled your subscription', no plan, direct web) and
      'iTunes Cancellation' 'Cursor Pro (1 month)'.
  EU  seller_name 'cursor' only (merchant_name never contains cursor):
      stripe   'cursor : cursor pro' - all but one in 2024-07..2024-08 (a Fox parser window), never renews
               -> excluded ('stripe_parser_window').
      paypal   payment-direct_payment*, no product name, Pro-sized EUR amounts, monthly renewals visible.
      klarna   payment-bnpl (DE lines 'kaufbetrag' = USD amount + 'wechselkurs' = FX line; order_total = EUR).
      apple    'cursor || pro (monthly|mensuel)' GBP 25 / EUR 30, bare 'cursor' EUR 30 / 90 (from 2026-06).
      amazon   'Cursor' fitness brand (treadmills) and everything else -> not matched.
  Direct US web and EU stripe have no usable paid receipts: those channels are left out (keep=False), not imputed.
Unrelated '%cursor%' (Precursor, Medcursor, Quick Cursor, Cursorblade, cursor packs, 'Cursor Pro' $14.99 iOS app
before 2026, 'Cursor AI - Assistant Guide', 'Cursor Highlighter' ...) never match the patterns below.
"""
import json
import re

import numpy as np
import pandas as pd

PROVIDER = "cursor"
APPLE_LAUNCH = pd.Timestamp("2026-06-01")   # Cursor iOS app in-app purchases first seen 2026-06-29
ULTRA_LAUNCH = pd.Timestamp("2025-06-16")
PROMO_START = pd.Timestamp("2026-03-01")

COLS = ["uid", "dt", "country", "provider", "tier", "cadence", "plan", "channel", "kind", "amount", "currency",
        "end_date", "renews", "keep", "reason", "descr"]

# US Apple: 'Cursor : Pro (Monthly)'; EU Apple: 'cursor || pro (mensuel)'
APPLE_PRICED_RE = re.compile(r"^\s*cursor\s*(?::|\|\|)\s*(pro\+|pro plus|pro|ultra)\s*\(([^)]*)\)\s*$", re.I)
APPLE_BARE_RE = re.compile(r"^\s*cursor\s*$", re.I)
APPLE_CONFIRM_RE = re.compile(r"^\s*cursor (pro\+|pro|ultra) \$[\d.]+ /(month|year)", re.I)
APPLE_CANCEL_RE = re.compile(r"^\s*cursor (pro\+|pro|ultra) \((1 month|1 year)\)", re.I)
US_DIRECT_RE = re.compile(r"^(cursor( pro| ultra| business| team)?( plan)?|(free )?plan for cursor|your teams plan is now active)$", re.I)
ANNUAL_RE = re.compile(r"annual|yearly|1 year|annuel|j[aä]hrlich|annuale|anual", re.I)

# Net USD list prices -> local amount bands (approx FX; EU from 2026 with VAT).
FX = {"USD": 1.0, "EUR": 0.90, "GBP": 0.78}
APPLE_USD = {"pro": 25.99, "proplus": 77.99, "ultra": 259.99}


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=COLS)


def _tier_txt(t: str):
    t = (t or "").lower().replace(" plus", "+")
    if "ultra" in t:
        return "ultra"
    if "pro+" in t:
        return "proplus"
    if "pro" in t:
        return "pro"
    return None


def _band(usd: float, dt: pd.Timestamp):
    """Plan from a USD-equivalent amount (gross, VAT/tax and FX headroom)."""
    if pd.isna(usd):
        return None, None
    if 15.0 <= usd <= 31.5:
        return "pro", "M"
    if 8.5 <= usd < 13.5 and dt >= PROMO_START:
        return "pro", "M"          # $10 first-month promo
    if 34.0 <= usd <= 50.0:
        return "team", "M"
    if 50.0 < usd <= 95.0:
        return "proplus", "M"
    if 160.0 <= usd <= 320.0:
        if dt < ULTRA_LAUNCH:
            return "pro", "A"
        return ("pro", "A") if usd < 199.5 else ("ultra", "M")
    return None, None


def _flags(attr: pd.Series) -> pd.Series:
    def f(s):
        try:
            a = json.loads(s).get("aux_data", {}) or {}
        except Exception:
            return False
        return any(str(a.get(k)) == "1" for k in ("order_is_spam",))
    return attr.fillna("{}").map(f)


def _finish(d: pd.DataFrame) -> pd.DataFrame:
    d["plan"] = np.where(d["tier"].notna() & d["cadence"].notna(),
                         d["tier"].astype(str) + "_" + d["cadence"].astype(str), "unknown_M")
    d.loc[d["kind"].eq("cancel") & d["tier"].isna(), "cadence"] = "M"
    d["provider"] = PROVIDER
    d["_day"] = d["dt"].dt.normalize()
    d["_ok"] = d["reason"].ne("ok")
    d = d.sort_values(["uid", "_day", "_ok", "dt"], kind="stable")
    dup = d["reason"].eq("ok") & d.duplicated(["uid", "_day", "channel", "kind", "plan", "amount"])
    d.loc[dup, "reason"] = "duplicate"
    d["keep"] = d["reason"].eq("ok")
    d["end_date"] = pd.to_datetime(d["end_date"])
    return d[COLS].reset_index(drop=True)


def _us(df: pd.DataFrame) -> pd.DataFrame:
    merch = df["merchant_name"].fillna("")
    descr = df["descr"].fillna("").str.strip()
    apple = merch.eq("iTunes")
    sel = (merch.eq("Cursor") & descr.str.match(US_DIRECT_RE)) | merch.eq("Cursor Cancellation") \
        | (apple & (descr.str.match(APPLE_PRICED_RE) | descr.str.match(APPLE_CONFIRM_RE))) \
        | (merch.eq("iTunes Cancellation") & descr.str.match(APPLE_CANCEL_RE))
    d = df[sel].copy()
    if d.empty:
        return _empty()
    d["descr"] = d["descr"].fillna("").str.strip()
    d["dt"] = pd.to_datetime(d["dt"])
    m = d["merchant_name"]
    d["channel"] = np.where(m.str.startswith("iTunes"), "apple", "direct")
    d["kind"] = np.where(m.str.contains("Cancellation"), "cancel", "charge")
    d["amount"] = pd.to_numeric(d["item_price"], errors="coerce")
    d["tier"] = d["descr"].map(_tier_txt)
    d.loc[m.eq("Cursor Cancellation"), "tier"] = None
    d["cadence"] = np.where(d["descr"].str.contains(ANNUAL_RE), "A", "M")
    d.loc[d["tier"].isna(), "cadence"] = None
    d["end_date"] = pd.NaT
    d["renews"] = d["channel"].eq("apple")
    d["country"] = "us"

    reason = pd.Series("ok", index=d.index, dtype=object)
    ch = d["kind"].eq("charge")
    lo = d["tier"].map(APPLE_USD).fillna(np.inf)
    reason[ch & d["channel"].eq("apple") & ~d["amount"].between(lo * 0.99, lo * 1.15)] = "out_of_band"
    reason[ch & (d["amount"].isna() | (d["amount"] <= 0))] = "unpriced_confirmation"
    reason[d["descr"].str.contains(r"(?i)business|team|free plan")] = "non_consumer_or_free"
    reason[d["channel"].eq("direct")] = np.where(ch[d["channel"].eq("direct")], reason[d["channel"].eq("direct")],
                                                 "channel_no_paid_receipts")
    reason[d["channel"].eq("apple") & (d["dt"] < APPLE_LAUNCH)] = "pre_launch"
    d["reason"] = reason
    d.loc[~ch, "amount"] = np.nan
    d["currency"] = np.where(ch, "USD", None)
    return _finish(d)


def _eu(df: pd.DataFrame) -> pd.DataFrame:
    seller = df["seller_name"].fillna("").str.lower().str.strip()
    merch = df["merchant_name"].fillna("").str.lower()
    pn = df["product_name"].fillna("").str.lower().str.strip()
    apple = merch.eq("apple") & (pn.str.match(APPLE_PRICED_RE) | pn.str.match(APPLE_BARE_RE))
    sel = apple | (seller.eq("cursor") & merch.isin(["stripe", "paypal", "klarna"]))
    d = df[sel].copy()
    if d.empty:
        return _empty()
    d["descr"] = d["product_name"].fillna("").str.lower().str.strip()
    d["dt"] = pd.to_datetime(d["dt"])
    mm = d["merchant_name"].str.lower()
    d["channel"] = mm.map({"apple": "apple", "stripe": "stripe", "paypal": "paypal", "klarna": "other"})
    d["kind"] = "charge"
    d["currency"] = d["order_currency"].str.upper()
    amt = pd.to_numeric(d["item_price"], errors="coerce")
    # Klarna: item lines are USD amount + FX line; the EUR charge is order_total (one row per order)
    kl = d["channel"].eq("other")
    amt[kl] = pd.to_numeric(d.loc[kl, "order_total"], errors="coerce")
    d["amount"] = amt
    usd = d["amount"] / d["currency"].map(FX)

    tier, cad = [], []
    for t, u, x, c in zip(d["descr"], usd, d["dt"], d["channel"]):
        tt = _tier_txt(t) if c == "apple" and t != "cursor" else None
        if c == "apple" and tt is None:
            tt = "pro" if 20 <= u <= 45 else ("proplus" if 60 <= u <= 130 else ("ultra" if u >= 200 else None))
        if tt:
            tier.append(tt); cad.append("A" if ANNUAL_RE.search(t) else "M")
        else:
            b = _band(u, x); tier.append(b[0]); cad.append(b[1])
    d["tier"], d["cadence"] = tier, cad
    d["end_date"] = pd.NaT
    d["renews"] = d["channel"].isin(["apple", "paypal", "other"])

    reason = pd.Series("ok", index=d.index, dtype=object)
    reason[d["tier"].isna()] = "out_of_band"
    reason[d["tier"].eq("team")] = "team_amount"
    reason[d["amount"].isna() | (d["amount"] <= 5)] = "small_or_unpriced"
    reason[kl & ~d["email_type"].eq("payment-bnpl")] = "bnpl_non_payment"
    reason[kl & d["descr"].str.contains("wechselkurs")] = "fx_line"
    reason[~kl & ~d["email_type"].fillna("").str.startswith(("order", "payment"))] = "non_payment_email"
    reason[d["channel"].eq("stripe")] = "stripe_parser_window"
    reason[d["channel"].eq("apple") & (d["dt"] < APPLE_LAUNCH)] = "pre_launch"
    reason[_flags(d["order_attributes"])] = "spam"
    d["reason"] = reason
    # Klarna: keep one row per order (several item lines carry the same order_total)
    kdup = kl & d["reason"].eq("ok") & d.duplicated(["uid", "order_id"])
    d.loc[kdup, "reason"] = "duplicate"
    d.loc[d["tier"].eq("team"), "tier"] = None
    return _finish(d)


def classify(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    return _eu(df) if panel == "eu" else _us(df)
