"""Gemini (Google One AI tiers) e-receipt filter (NIQ Slice US / NIQ Fox EU).

classify(df, panel, include_storage=False) -> one row per candidate Google One / Google AI item with
uid, dt, country, provider, tier, cadence, plan, channel, kind, amount, currency, end_date, renews, keep, reason.

Unlike the card filter (filters/gemini.py, amount-based), receipts NAME the plan, so the tier is read from text:
  'Google AI Pro (2 TB)/(5 TB)/(10 TB)', 'Google One AI Premium (2 TB)'   -> ai_pro
  'Google AI Plus (200GB)/(400 GB)', bare 'Google AI Plus'               -> ai_plus
  'Google AI Plus (2 TB)', and bare '2 TB' / 'Premium' Google One on or after 2026-01-27 -> ai_plus_2tb
  'Google AI Ultra (30 TB)' -> ultra ; 'Google AI Ultra (20 TB)' (the $99.99 5x tier) -> ultra_5x
  '100 GB', '200 GB', '30 GB', '5 TB', '2 TB' before 2026-01-27, 'Basic/Standard plan' -> storage (excluded)
Cadence from the receipt's period text ('(Monthly)', '(1 year)', 'mensuel', 'jahrliches'...), else amount bands.

Cancels (US only; Fox has no Google cancellation emails):
  'Google One Cancellation'  '<plan> plan has ended / has been canceled' (trial endings excluded)
  'Google Play Cancellation' 'Google One (<plan>) subscription will end on Sep 30' or the plan-less
                             'Your Google One subscription ... will be canceled on Sep 30, 2026' / 'has been canceled'
  'iTunes Cancellation'      'Google Gemini Google AI Pro (2 TB) (1 month)'
Plan-less cancels take the plan of the uid's latest Google One charge in the prior 400 days (storage -> rejected);
with no prior charge they stay 'unknown_M' (kept; the engine resolves them at provider level).

Rejected: storage-only plans (not returned unless include_storage=True), US 'Google One' welcome emails
(unpriced), Apple unpriced confirmations ('... $19.99 /month', '1 month ... free trial'), $0 trials, partner
resellers (Verizon/Fios/DirecTV/Google Store/Best Buy bundles), grey-market keys (G2A, Driffle...), Klarna
'google one' payments with no plan text, PayPal-for-Google-Play notifications duplicating a Play receipt.
"""
import json
import re

import numpy as np
import pandas as pd

PROVIDER = "gemini"
OUT_COLS = ["uid", "dt", "country", "provider", "tier", "cadence", "plan", "channel", "kind", "amount", "currency",
            "end_date", "renews", "keep", "reason"]
AI_PLUS_2TB_FROM = pd.Timestamp("2026-01-27")

G1_RX = r"google one|google ai (?:pro|plus|ultra|premium|plan)|gemini advanced"
ANNUAL = (r"\((?:yearly|annual|1 year|annuel|annuale|anual|anualmente|jahrlich\w*|jährlich\w*|jahr)\)"
          r"|\byearly access\b|/ ?year\b")
MONTHLY = (r"\((?:monthly|1 month|mensuel|mensile|mensual|mensualmente|monatlich|monat|al mese|chaque mois|"
           r"maandelijks)\)|/ ?month\b")
APPLE_CONFIRM = r"\$ ?\d+\.\d\d ?/|usd \d+\.\d\d ?/|free trial|price:|every month|starting"
NOT_PLAN = r"ai credits|add on|add-on|google one time|home premium"  # credit packs, Home add-on, DAZN 'one time' pass
RESELLERS = r"\b(?:g2a|driffle|gamivo|kinguin\w*|k4g|eneba|etsy|ebay|cdkeys|mmoga)\b"
PARTNERS = r"verizon|fios|directv|google store|best buy|t-mobile|at&t"

MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                          "september", "october", "november", "december"])}
MONTHS.update({"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
               "nov": 11, "dec": 12})


def _end_date(text: str, dt=None):
    """'will be canceled on Sep 30, 2026' / '28 September 2026' / 'will end on Sep 30' (year from dt) -> Timestamp."""
    m = re.search(r"\b([a-z]{3,9})\.? (\d{1,2}),? (20\d\d)\b", text)
    if m and m.group(1) in MONTHS:
        return pd.Timestamp(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
    m = re.search(r"\b(\d{1,2}) ([a-z]{3,9}),? (20\d\d)\b", text)
    if m and m.group(2) in MONTHS:
        return pd.Timestamp(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
    m = re.search(r"(?:end|ends|canceled|cancelled)\s+on\s+([a-z]{3,9})\.? (\d{1,2})\b", text)
    if m and m.group(1) in MONTHS and dt is not None and not pd.isna(dt):
        try:
            e = pd.Timestamp(dt.year, MONTHS[m.group(1)], int(m.group(2)))
        except ValueError:
            return pd.NaT
        return e + pd.DateOffset(years=1) if e < dt - pd.Timedelta(days=60) else e
    return pd.NaT


def _tier_text(t: str) -> str:
    """Tier from plan text (date-independent). '2tb' = bare 2 TB / Premium Google One (date decides later)."""
    if "ai ultra" in t:
        return "ultra_5x" if re.search(r"20 ?tb", t) else ("ultra" if re.search(r"30 ?tb", t) else "ultra_any")
    if re.search(r"ai pro\b|google one ai premiu|google ai premium|gemini advanced", t):
        return "ai_pro"
    if "ai plus" in t:
        return "ai_plus_2tb" if re.search(r"\b2 ?t[bo]\b", t) else "ai_plus"
    if re.search(r"google ai plan", t):
        return "unknown"
    if re.search(r"\b2 ?t[bo]\b|(?<!ai )premium plan|premium 2 ?tb", t):
        return "2tb"
    if re.search(r"\b\d+ ?(?:gb|go|tb)\b|basic plan|standard plan|lite\b", t):
        return "storage"
    return "unknown"


def _flags_set(attr) -> bool:
    """Only is_spam is excluded; is_deleted / is_trash are genuine receipts the user later deleted."""
    if not isinstance(attr, str) or '"1"' not in attr:
        return False
    try:
        aux = json.loads(attr).get("aux_data", {}) or {}
    except ValueError:
        return False
    return str(aux.get("order_is_spam", "0")) == "1"


def _by_unique(s: pd.Series, f) -> pd.Series:
    u = pd.unique(s)
    return s.map(dict(zip(u, map(f, u))))


# ----------------------------------------------------------------------------------------------------------- EU
def _eu(df: pd.DataFrame) -> pd.DataFrame:
    low = lambda c: df[c].fillna("").astype(str).str.lower()
    merch, seller = low("merchant_name"), low("seller_name")
    pt = low("product_name") + " | " + low("descr")
    hit = pt.str.contains(G1_RX) | seller.isin(["google one"])
    d = df[hit]
    m, sel, t = merch[hit], seller[hit], pt[hit]

    ch = pd.Series("other", index=d.index)
    ch[m.eq("apple")] = "apple"
    ch[m.eq("google play")] = "google_play"
    g_seller = sel.isin(["google", "google one", "noreply+support"])
    ch[m.eq("paypal") & g_seller] = "paypal"
    ch[m.eq("klarna")] = "other"

    out = pd.DataFrame({"uid": d["uid"], "dt": pd.to_datetime(d["dt"]), "country": d["country"].str.lower(),
                        "channel": ch, "amount": pd.to_numeric(d["item_price"], errors="coerce"),
                        "currency": d["order_currency"].str.upper(), "_t": t, "kind": "charge"})
    reason = pd.Series("ok", index=d.index)

    def rej(mask, why):
        reason[(reason == "ok") & mask] = why

    rej(d["order_attributes"].map(_flags_set), "spam")
    rej(m.eq("paypal") & ~g_seller, "reseller_key")
    rej(t.str.contains(RESELLERS) | sel.str.contains(RESELLERS), "reseller_key")
    rej(t.str.contains(NOT_PLAN), "not_a_plan")
    rej(m.eq("klarna"), "no_plan_text")
    rej(~m.isin(["apple", "google play", "paypal", "klarna"]), "unrelated")
    rej(m.eq("apple") & t.str.contains(APPLE_CONFIRM), "unpriced_confirmation")
    rej(sel.str.contains("probeabo") | t.str.contains(r"\btrial\b|probeabo"), "trial")
    rej(out["amount"].fillna(0).le(0), "zero_or_unpriced")
    rej(~d["email_type"].fillna("order").isin(["order", "payment-direct_payment", "payment-bnpl",
                                               "payment-direct_payment-in store"]), "not_a_charge")
    out["reason"] = reason
    return out


# ----------------------------------------------------------------------------------------------------------- US
US_MERCH = {"Google Play": "google_play", "Google Play Cancellation": "google_play", "Google One": "google_play",
            "Google One Cancellation": "google_play", "iTunes": "apple", "iTunes Cancellation": "apple"}


def _us(df: pd.DataFrame) -> pd.DataFrame:
    mn = df["merchant_name"].fillna("").astype(str)
    google_m = mn.isin(list(US_MERCH))
    partner_m = mn.str.lower().str.contains(PARTNERS)
    pre = google_m | partner_m
    d = df[pre]
    descr = d["descr"].fillna("").astype(str).str.lower()
    m = mn[pre]
    hit = _by_unique(descr, lambda x: bool(re.search(G1_RX, x)))
    hit |= m.eq("Google One Cancellation")
    d, descr, m = d[hit], descr[hit], m[hit]

    ch = m.map(US_MERCH).fillna("other")
    canc = m.str.contains("Cancellation")
    out = pd.DataFrame({"uid": d["uid"], "dt": pd.to_datetime(d["dt"]), "country": "us", "channel": ch,
                        "amount": pd.to_numeric(d["item_price"], errors="coerce"), "currency": "USD",
                        "_t": descr, "kind": np.where(canc, "cancel", "charge")})
    reason = pd.Series("ok", index=d.index)

    def rej(mask, why):
        reason[(reason == "ok") & mask] = why

    rej(ch.eq("other"), "partner_reseller")
    rej(descr.str.contains(r"refund"), "refund")
    rej(m.eq("Google One"), "welcome_confirmation")
    rej(descr.str.contains(NOT_PLAN), "not_a_plan")
    rej(canc & descr.str.contains(r"trial (?:has ended|ended|will end)"), "trial_end")
    rej(~canc & ch.eq("apple") & descr.str.contains(APPLE_CONFIRM), "unpriced_confirmation")
    rej(~canc & descr.str.contains(r"trial") & out["amount"].fillna(0).le(0), "trial")
    rej(~canc & out["amount"].fillna(0).le(0), "zero_or_unpriced")
    out["reason"] = reason
    return out


# ------------------------------------------------------------------------------------------------------ common
def _cadence(t: str) -> str:
    if re.search(ANNUAL, t):
        return "A"
    if re.search(MONTHLY, t):
        return "M"
    return ""


A_MIN = {"ai_pro": 60, "ai_plus": 25, "ai_plus_2tb": 45, "storage": 1e9, "ultra": 1e9, "ultra_5x": 1e9,
         "unknown": 1e9}


def classify(df: pd.DataFrame, panel: str, include_storage: bool = False) -> pd.DataFrame:
    panel = panel.lower()
    out = _eu(df) if panel == "eu" else _us(df)
    if out.empty:
        return pd.DataFrame(columns=OUT_COLS)
    out["provider"] = PROVIDER
    tier = _by_unique(out["_t"], _tier_text)
    tier[tier.eq("2tb")] = np.where(out.loc[tier.eq("2tb"), "dt"] >= AI_PLUS_2TB_FROM, "ai_plus_2tb", "storage")
    ua = tier.eq("ultra_any")
    tier[ua] = np.where(out.loc[ua, "amount"].between(85, 150), "ultra_5x", "ultra")
    out["tier"] = tier

    cad = _by_unique(out["_t"], _cadence)
    amt_a = out["amount"] >= out["tier"].map(A_MIN).fillna(1e9)
    out["cadence"] = np.where(cad.ne(""), cad, np.where(amt_a, "A", "M"))
    canc = out["kind"].eq("cancel")
    out.loc[canc & cad.eq(""), "cadence"] = "M"

    out.loc[out["tier"].eq("storage") & out["reason"].eq("ok"), "reason"] = "storage"
    out.loc[~canc & out["tier"].eq("unknown") & out["reason"].eq("ok"), "reason"] = "no_plan_text"

    # Plan-less cancels: take the plan of the uid's latest Google One charge (any tier, priced) in the prior 400d
    unk = canc & out["tier"].eq("unknown") & out["reason"].eq("ok") & ~out["_t"].str.contains("google ai plan")
    if unk.any():
        hist = out.loc[~canc & out["amount"].gt(0) & out["channel"].ne("other") & out["tier"].ne("unknown"),
                       ["uid", "dt", "tier", "cadence"]].sort_values("dt")
        q = out.loc[unk, ["uid", "dt"]].reset_index().sort_values("dt")
        j = pd.merge_asof(q, hist.rename(columns={"dt": "hdt"}), left_on="dt", right_on="hdt", by="uid",
                          direction="backward", tolerance=pd.Timedelta(days=400)).set_index("index")
        out.loc[j.index, "tier"] = j["tier"].fillna("unknown")
        out.loc[j.index, "cadence"] = j["cadence"].fillna("M")
        st = j.index[j["tier"].eq("storage")]
        out.loc[st, "reason"] = "storage_by_history"
        # no visible Google One charge: cannot tell AI from storage (~90% of Google One is storage) -> not counted
        out.loc[j.index[j["tier"].isna()], "reason"] = "no_plan_no_history"
    out["plan"] = out["tier"] + "_" + out["cadence"]
    out.loc[out["tier"].eq("unknown"), "plan"] = "unknown_M"

    out["end_date"] = pd.NaT
    if canc.any():
        out.loc[canc, "end_date"] = [_end_date(x, dd) for x, dd in zip(out.loc[canc, "_t"], out.loc[canc, "dt"])]
    out["end_date"] = pd.to_datetime(out["end_date"])
    out.loc[canc, ["amount", "currency"]] = [np.nan, None]
    out["renews"] = out["channel"].isin(["google_play", "apple", "paypal"])

    # De-duplicate repeated line items, then PayPal notifications of a Google Play charge (EU: same uid, plan,
    # amount within 3 days of a kept Play receipt)
    key = ["uid", "dt", "channel", "plan", "kind", "_amt"]
    out["_amt"] = out["amount"].round(2)
    ok = out["reason"].eq("ok")
    dup = out[ok].duplicated(key)
    out.loc[dup[dup].index, "reason"] = "duplicate"
    pp = out["reason"].eq("ok") & out["channel"].eq("paypal")
    if pp.any():
        gp = out.loc[out["reason"].eq("ok") & out["channel"].eq("google_play"), ["uid", "plan", "_amt", "dt"]]
        a = out.loc[pp, ["uid", "plan", "_amt", "dt"]].reset_index()
        j = a.merge(gp.rename(columns={"dt": "gdt"}), on=["uid", "plan", "_amt"])
        j = j[(j["gdt"] - j["dt"]).abs() <= pd.Timedelta(days=3)]
        out.loc[j["index"].unique(), "reason"] = "dup_of_google_play"

    out["keep"] = out["reason"].eq("ok")
    if not include_storage:
        out = out[~out["reason"].isin(["storage", "storage_by_history"])]
    return out[OUT_COLS].reset_index(drop=True)
