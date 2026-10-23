"""Perplexity e-receipt filter (NIQ Slice US / NIQ Fox EU).

classify(df, panel) -> one row per candidate Perplexity item with
uid, dt, country, provider, tier, cadence, plan, channel, kind, amount, currency, end_date, renews, keep, reason.

Plans: pro (M/A), max (M/A), pro_edu (M). Enterprise, credits (API / usage top-ups), trials, $0 partner promos,
grey-market resold keys (G2A, Kinguin...), courses/hardware that mention Perplexity are rejected.
See perplexity_report.md for the evidence behind each rule.
"""
import json
import re

import numpy as np
import pandas as pd

PROVIDER = "perplexity"
OUT_COLS = ["uid", "dt", "country", "provider", "tier", "cadence", "plan", "channel", "kind", "amount", "currency",
            "end_date", "renews", "keep", "reason"]

ANNUAL = r"\b(annual|yearly|annuel|annuale|annuo|anual|jahrlich\w*|jährlich\w*|1 year|12 months|year|yr)\b"
MONTHLY = r"\b(monthly|mensuel|mensile|mensual|monatlich|month|mo)\b"
RESELLERS = r"\b(?:g2a|kinguin\w*|gamivo|flowdigital|eneba|ebay)\b"
CREDITS = r"\bcredits?\b"
ENTERPRISE = r"\benterprise\b|\bent pro\b|\bteam\b|\bbusiness\b"
TRIAL = r"trial|probeabo|essai|prueba|prova gratuita|free|gratis|offert|complimentary"
UNRELATED = r"nexbot|parlons ia|udemy|masterclass|formation|course"

MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                          "september", "october", "november", "december"])}
MONTHS.update({"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
               "nov": 11, "dec": 12})


def _end_date(text: str, dt=None):
    """'... will end on Sep 30, 2026' / '30 September 2026' / 'will end on Jun 18' (year from dt) -> Timestamp."""
    m = re.search(r"\b([a-z]{3,9})\.? (\d{1,2}),? (20\d\d)\b", text)
    if m and m.group(1) in MONTHS:
        return pd.Timestamp(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
    m = re.search(r"\b(\d{1,2}) ([a-z]{3,9}),? (20\d\d)\b", text)
    if m and m.group(2) in MONTHS:
        return pd.Timestamp(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d\d)\b", text)
    if m:
        try:
            return pd.Timestamp(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            return pd.NaT
    m = re.search(r"\b(?:end|ends|ended|expire|expires|on)\s+(?:on\s+)?([a-z]{3,9})\.? (\d{1,2})\b", text)
    if m and m.group(1) in MONTHS and dt is not None and not pd.isna(dt):
        try:
            e = pd.Timestamp(dt.year, MONTHS[m.group(1)], int(m.group(2)))
        except ValueError:
            return pd.NaT
        return e + pd.DateOffset(years=1) if e < dt - pd.Timedelta(days=60) else e
    return pd.NaT


def _tier(t: str) -> str:
    if re.search(ENTERPRISE, t):
        return "enterprise"
    if re.search(r"\bmax\b", t):
        return "max"
    if re.search(r"educat|student", t):
        return "pro_edu"
    if re.search(r"\bpro\b", t) or "perplexity" in t:
        return "pro"
    return "unknown"


def _cadence(t: str, amount: float, tier: str) -> str:
    if re.search(ANNUAL, t):
        return "A"
    if re.search(MONTHLY, t):
        return "M"
    if pd.isna(amount) or amount <= 0:
        return "M"
    # amount bands (local currency ~ USD): Pro M 5-35, Pro A 120-300, Max M 150-300, Max A >= 1500
    if tier == "max":
        return "A" if amount >= 1000 else "M"
    return "A" if amount >= 100 else "M"


def _flags_set(attr) -> bool:
    if not isinstance(attr, str) or not attr:
        return False
    try:
        aux = json.loads(attr).get("aux_data", {}) or {}
    except ValueError:
        return False
    return any(str(aux.get(k, "0")) == "1" for k in ("order_is_spam",))


# ----------------------------------------------------------------------------------------------------------- EU
def _eu(df: pd.DataFrame) -> pd.DataFrame:
    s = lambda c: df[c].fillna("").astype(str).str.lower()
    merch, seller, prod, descr = s("merchant_name"), s("seller_name"), s("product_name"), s("descr")
    text = merch + " | " + seller + " | " + prod + " | " + descr
    d = df[text.str.contains("perplexity", regex=False)].copy()
    t = text.loc[d.index]
    m, sel = merch.loc[d.index], seller.loc[d.index]
    plan_txt = (s("product_name") + " " + s("descr")).loc[d.index]

    ch = pd.Series("other", index=d.index)
    ch[m.eq("apple")] = "apple"
    ch[m.eq("google play") | (m.eq("paypal") & sel.eq("google"))] = "google_play"
    ch[m.eq("stripe")] = "stripe"
    ch[m.eq("perplexity")] = "direct"
    ch[m.eq("paypal") & sel.str.contains("perplexity")] = "paypal"

    out = pd.DataFrame({"uid": d["uid"], "dt": pd.to_datetime(d["dt"]), "country": d["country"].str.lower(),
                        "channel": ch, "amount": pd.to_numeric(d["item_price"], errors="coerce"),
                        "currency": d["order_currency"].str.upper(), "_t": plan_txt, "_all": t})
    out["kind"] = np.where(d["email_type"].fillna("").str.contains("cancel"), "cancel", "charge")

    reason = pd.Series("ok", index=d.index)

    def rej(mask, why):
        reason[(reason == "ok") & mask] = why

    rej(d["order_attributes"].map(_flags_set), "spam")
    rej(t.str.contains(UNRELATED) | ~(m.isin(["apple", "google play", "paypal", "stripe", "perplexity",
                                              "samsunggalaxystore"]) | sel.str.contains("perplexity")), "unrelated")
    rej(m.eq("stripe") & ~t.str.contains("perplexity ai, inc"), "unrelated")
    rej(m.eq("paypal") & ~sel.isin(["google"]) & ~sel.str.contains("perplexity"), "reseller_key")
    rej(t.str.contains(RESELLERS), "reseller_key")
    rej(plan_txt.str.contains(CREDITS), "credits")
    rej(plan_txt.str.contains(ENTERPRISE), "enterprise")
    # Fox 'perplexity' sender: unpriced 'perplexity pro' activation/welcome emails, ~1 per user, never recurring
    rej(ch.eq("direct") & out["amount"].fillna(0).le(0), "unpriced_confirmation")
    rej(t.str.contains(TRIAL) & out["amount"].fillna(0).le(0), "trial_or_promo")
    rej(out["amount"].fillna(0).le(0), "zero_or_unpriced")
    out["reason"] = reason
    return out


# ----------------------------------------------------------------------------------------------------------- US
def _us(df: pd.DataFrame) -> pd.DataFrame:
    merch = df["merchant_name"].fillna("").astype(str).str.lower()
    descr = df["descr"].fillna("").astype(str).str.lower()
    text = merch + " | " + descr
    d = df[text.str.contains("perplexity", regex=False)].copy()
    t, m, ds = text.loc[d.index], merch.loc[d.index], descr.loc[d.index]

    ch = pd.Series("other", index=d.index)
    ch[m.str.contains("itunes|apple")] = "apple"
    ch[m.str.contains("google play")] = "google_play"
    ch[m.str.contains("perplexity")] = "direct"
    ch[m.str.contains("paypal")] = "paypal"
    ch[m.str.contains("stripe")] = "stripe"
    is_cancel = m.str.contains("cancellation")

    out = pd.DataFrame({"uid": d["uid"], "dt": pd.to_datetime(d["dt"]), "country": "us", "channel": ch,
                        "amount": pd.to_numeric(d["item_price"], errors="coerce"), "currency": "USD",
                        "_t": ds, "_all": t})
    out["kind"] = np.where(is_cancel, "cancel", "charge")

    reason = pd.Series("ok", index=d.index)

    def rej(mask, why):
        reason[(reason == "ok") & mask] = why

    known = m.str.contains("itunes|apple|google play|perplexity|paypal|stripe|samsung")
    rej(~known | t.str.contains(UNRELATED), "unrelated")
    rej(t.str.contains(RESELLERS), "reseller_key")
    rej(ds.str.contains(CREDITS), "credits")
    rej(ds.str.contains(ENTERPRISE), "enterprise")
    if "record_status" in d:
        rej(d["record_status"].fillna("").astype(str).str.lower().str.contains("delet|refund"), "record_status")
    rej(ds.str.contains(r"refund"), "refund")
    canc = out["kind"].eq("cancel")
    # Cancels: drop trial endings ('Perplexity Pro trial has ended' etc.)
    rej(canc & ds.str.contains(r"trial"), "trial_end")
    rej(~canc & ds.str.contains(r"trial") & out["amount"].fillna(0).le(0), "trial_or_promo")
    # Apple confirmations 'Perplexity Pro $20.00/month' are unpriced -> not charges
    rej(~canc & out["amount"].fillna(0).le(0), "zero_or_unpriced")
    out["reason"] = reason
    return out


def classify(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    panel = panel.lower()
    out = _eu(df) if panel == "eu" else _us(df)
    if out.empty:
        return pd.DataFrame(columns=OUT_COLS)
    out["provider"] = PROVIDER
    out["tier"] = out["_t"].map(_tier)
    # bare app-name rows ('perplexity - fragen sie etwas') have no plan text: Pro by default, Max by amount
    out.loc[out["tier"].eq("unknown"), "tier"] = "pro"
    out["cadence"] = [_cadence(t, a, tr) for t, a, tr in zip(out["_t"], out["amount"], out["tier"])]
    # Max monthly is ~10x Pro monthly; a bare 'pro'-less app row at >= 150/month with monthly text is Max
    out.loc[out["tier"].eq("pro_edu"), "cadence"] = "M"
    out["plan"] = out["tier"] + "_" + out["cadence"]
    canc = out["kind"].eq("cancel")
    no_plan = canc & ~out["_t"].str.contains(r"\bpro\b|\bmax\b|educat")
    out.loc[no_plan, ["tier", "plan"]] = ["unknown", "unknown_M"]
    out.loc[canc, ["amount", "currency"]] = [np.nan, None]
    out["end_date"] = pd.NaT
    out.loc[canc, "end_date"] = [_end_date(x, d) for x, d in zip(out.loc[canc, "_all"], out.loc[canc, "dt"])]
    out["end_date"] = pd.to_datetime(out["end_date"])
    rej_ent = out["tier"].eq("enterprise") & out["reason"].eq("ok")
    out.loc[rej_ent, "reason"] = "enterprise"
    # renewal receipts: app stores / PayPal / Stripe renew; Perplexity direct sends no priced receipts
    out["renews"] = ~out["channel"].eq("direct")
    out["keep"] = out["reason"].eq("ok")
    # de-duplicate repeated line items (same uid, day, channel, plan, kind, amount)
    out = out.sort_values(["uid", "dt", "keep"], ascending=[True, True, False])
    out = out.drop_duplicates(["uid", "dt", "channel", "plan", "kind", "amount", "reason"])
    return out[OUT_COLS].reset_index(drop=True)
