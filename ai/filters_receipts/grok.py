"""Grok e-receipt filter. Two provider ids:

  grok    SuperGrok / Lite / Heavy / Plus (xAI). Apple 'Grok AI : SuperGrok (Monthly)' (US) or
          'grok - ai assistant || supergrok (monthly)' (EU); Google Play 'SuperGrok (Grok AI) Auto-renewing
          subscription' / 'supergrok (grok - assistant ia)de xai'; EU Stripe 'grok xai : supergrok' and
          'xai, llc : supergrok'; EU PayPal funding a Play purchase (seller 'google', 'supergrok (grok - as...').
          The X Subscription (2026-10-10) would map to tiers xsub_* but no receipt names it yet.
  grok_x  X Premium+ (Apple 'X : X Premium Plus (Monthly)', Play 'Premium+ (X)', EU Stripe 'x : x premium plus').
          Basic / Premium (fka Twitter Blue) are returned keep=False, reason 'x_non_plus_tier'; creator
          subscriptions ('@name subscription (X)') reason 'x_creator_sub'.

Excluded: Grok credits ('grok credits', 'extra usage credits', 'xai prepaid credits'), trials / $0, unpriced
Apple confirmations ('SuperGrok $30.00 /month', '... free trial. Price: ...'), unrelated apps (Grok Bot, Grokio,
ngrok, groksi snacks, ITVX / Roblox / Deezer 'premium+', HelloFresh '1 x premium recipe', ...), refunds, spam.
US 'Twitter : Payment' rows are unpriced X Money / tips (ordertotal $0-$170k) and are excluded ('x_payment_unpriced').

Cadence from the text ('Monthly' / '(1 month)' / 'mensuel' ... vs 'Annual' / '(1 year)' ...), else from the amount
relative to the tier's monthly list price. Apple 'SuperGrok (3 Months)' is the $30-for-3-months retention offer:
plan supergrok_M with `period_months` = 3 (extra column; the engine only knows M/A).
"""
import re

import numpy as np
import pandas as pd

COLS = ["uid", "dt", "country", "provider", "tier", "cadence", "plan", "channel", "kind", "amount", "currency",
        "end_date", "renews", "keep", "reason", "period_months", "descr"]
FX_USD = {"USD": 1.0, "EUR": 1 / 0.88, "GBP": 1 / 0.76}  # rough; used only for cadence-by-amount
MONTHLY_USD = {"supergrok": 30, "lite": 10, "heavy": 300, "plus": 100, "premium_plus": 40, "premium": 8,
               "basic": 3, "xsub_plus": 10, "xsub_premium": 30, "xsub_super": 100, "xsub_ultra": 260}

# ------------------------------------------------------------------ patterns (lowercased text)
NOT_GROK = re.compile(r"grok ?bot|grokio|grommr|feabie|ngrok|groksi|ongrok|grokker|groke\b|grokking|agrok|udemy")
GROK_RE = re.compile(r"super ?grok|(?<![a-z])grok(?![a-z])|x\.ai corp|grok xai|xai, llc|(?<![a-z])xai(?![a-z])")
GROK_CREDITS = re.compile(r"credits?\b|prepaid")
GROK_PAYMENT = re.compile(r"payment to (?:grok )?xai")
X_CTX = re.compile(
    r"(?:^|\| ?)(?:x|twitter|twitter, inc\.|x \([^)]*twitter\))\s*(?:\|\||:|\|)"   # EU apple / stripe app prefix
    r"|^(?:x|twitter) (?:x premium|twitter blue)"                                       # US iTunes cancellation
    r"|^x (?:premium|twitter)|^x :"                                                     # US iTunes 'X : X Premium'
    r"|\((?:x|twitter)\)|from twitter inc|from x corp|x corp\.?\)|^twitter$|^x corp")
X_PLUS = re.compile(r"premium ?(?:plus|\+)|premiumplus")
X_BASIC = re.compile(r"basic")
X_PREMIUM = re.compile(r"premium|twitter blue|blue")
X_CREATOR = re.compile(r"@\S+ subscription|subscription \((?:x|twitter)\)|super follow")

ANNUAL = re.compile(r"annual|yearly|\b1 year|annuel|jahrlich|jährlich|\banual|annuale|12 mo|\b1 an\b|1 jahr|1 a[nñ]o|1 anno")
MONTHLY = re.compile(r"monthly|1 month|mensuel|monatlich|mensile|mensual|/ ?month|/mo\b|1 mois|1 monat|1 mes\b|1 mese")
QUARTER = re.compile(r"\b3 (?:months|mois|monate|mesi|meses)")
TRIAL = re.compile(r"trial|probeabo|essai|prueba|prova gratuita|gratuit|kostenlos")
CANCEL_TXT = re.compile(r"will be cancel|has been cancel|cancell?ed|will end on|has ended|annul|gek[uü]ndigt|cancelad")
REFUND = re.compile(r"refund|rembours|erstattung|reembolso|rimborso")
BUSINESS = re.compile(r"business|team|enterprise")
UNPRICED_CONFIRM = re.compile(r"\$\d+(?:\.\d+)? ?/ ?(?:month|year)|price:|starting [a-z]{3} \d")
END_RE = re.compile(r"(?:on|until)\s+(?:([a-z]{3})[a-z]*\.? (\d{1,2})|(\d{1,2}) ([a-z]{3})[a-z]*\.?),?(?: (\d{4}))?")
PRORATION = re.compile(r"unused time|remaining time")
XSUB_LAUNCH = pd.Timestamp("2026-10-10")
# The X Subscription sold in the Grok app (Play 'Premium (Grok) Auto-renewing subscription' from 2026-10-12)
XSUB_RE = re.compile(r"^(plus|premium|super|ultra) \(grok|grok(?: ai| - ai chat & video)?(?: :)? (plus|premium|super|ultra)\b")
XSUB_X_RE = re.compile(r"^(plus|super|ultra)(?: annual)? \((?:x)\)")
SPAM = re.compile(r'"order_is_spam":"?1')  # is_deleted / is_trash are genuine receipts the user later deleted


def _channel_us(m: str) -> str:
    m = m.lower()
    if m.startswith("itunes") or m.startswith("apple"):
        return "apple"
    if m.startswith("google play"):
        return "google_play"
    if m.startswith(("twitter", "x corp", "xai", "x.ai", "grok")) or m == "x":
        return "direct"
    if m.startswith("paypal"):
        return "paypal"
    return "other"


def _channel_eu(merchant: pd.Series, seller: pd.Series) -> pd.Series:
    m, s = merchant.fillna("").str.lower(), seller.fillna("").str.lower()
    ch = np.select(
        [m.eq("apple"), m.eq("google play"), m.eq("paypal") & s.str.startswith("google"), m.eq("stripe"),
         m.eq("paypal")],
        ["apple", "google_play", "google_play", "stripe", "paypal"], "other")
    return pd.Series(ch, index=merchant.index)


def _end_date(text: str, dt: pd.Timestamp):
    m = END_RE.search(text)
    if not m:
        return pd.NaT
    mon, day = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
    year = int(m.group(5)) if m.group(5) else dt.year
    e = pd.to_datetime(f"{mon} {day} {year}", format="%b %d %Y", errors="coerce")
    if not m.group(5) and pd.notna(e) and e < dt.normalize() - pd.Timedelta(days=31):
        e = e + pd.DateOffset(years=1)  # 'will end on Jan 3' sent in December
    return e


def _grok_tier(t: str):
    if re.search(r"heavy|supergrok ?pro\b", t):
        return "heavy"
    if re.search(r"super ?grok ?plus", t):
        return "plus"
    if re.search(r"super ?grok ?lite|supergroklite", t):
        return "lite"
    if re.search(r"x subscription", t):
        return "xsub"
    if re.search(r"super ?grok", t):
        return "supergrok"
    return None


def _grok_band(usd: float):
    """Tier from amount, for rows that name no plan (bare Apple app name, 'payment to grok xai')."""
    if pd.isna(usd):
        return None
    if 26 <= usd <= 44:
        return "supergrok"
    if 8.5 <= usd <= 13:
        return "lite"
    return None


def _x_tier(t: str):
    if X_CREATOR.search(t):
        return "creator"
    if X_PLUS.search(t):
        return "premium_plus"
    if X_BASIC.search(t):
        return "basic"
    if X_PREMIUM.search(t):
        return "premium"
    return None


def _x_band(local: float):
    """PayPal 'twitter' payee rows carry no plan name: local VAT-inclusive price bands (see filters/grok.py)."""
    if pd.isna(local) or local <= 0:
        return None
    if local < 6:
        return "basic"
    if local < 14:
        return "premium"
    if local < 60:
        return "premium_plus"
    if local < 130:
        return "premium"      # Premium annual 84-115
    if local < 520:
        return "premium_plus"  # Premium+ annual 168-460
    return None


def _cadence(t: str, tier, usd: float):
    if QUARTER.search(t):
        return "M", 3
    if ANNUAL.search(t):
        return "A", 12
    if MONTHLY.search(t):
        return "M", 1
    base = MONTHLY_USD.get(tier)
    if base and pd.notna(usd) and usd > base * (5 if tier not in ("premium_plus",) else 3):
        return "A", 12
    return "M", 1


def _prep(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    if panel == "us":
        merch = df["merchant_name"].fillna("")
        descr = df["descr"].fillna("")
        d = pd.DataFrame({"uid": df["uid"].astype(str), "dt": pd.to_datetime(df["dt"]), "country": "us",
                          "merchant": merch, "t": descr.str.lower().str.strip(),
                          "amount": pd.to_numeric(df["item_price"], errors="coerce"), "currency": "USD",
                          "channel": merch.map(_channel_us), "is_cancel": merch.str.contains("(?i)cancel"),
                          "refund": False, "spam": False, "descr": descr})
        tw = merch.str.lower().isin(["twitter", "x", "x corp"])
        d.loc[tw, "t"] = "twitter : " + d.loc[tw, "t"]
        return d
    seller = df["seller_name"].fillna("")
    prod = df["product_name"].fillna("")
    descr = df["descr"].fillna("")
    t = (seller + " | " + prod + " | " + descr).str.lower().str.strip()
    et = df["email_type"].fillna("").str.lower()
    attrs = df["order_attributes"].fillna("")
    return pd.DataFrame({"uid": df["uid"].astype(str), "dt": pd.to_datetime(df["dt"]),
                         "country": df["country"].str.lower(), "merchant": df["merchant_name"].fillna(""),
                         "t": t, "amount": pd.to_numeric(df["item_price"], errors="coerce"),
                         "currency": df["order_currency"].fillna("").str.upper(),
                         "channel": _channel_eu(df["merchant_name"], seller),
                         "is_cancel": et.str.contains("cancel"), "refund": et.str.startswith("return"),
                         "spam": attrs.str.contains(SPAM), "descr": (prod + " | " + descr).str.strip(" |")})


def classify(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    panel = panel.lower()
    d = _prep(df, panel)
    # cheap prefilter on the row text
    pre = d["t"].str.contains(r"grok|xai|x\.ai|premium|twitter|x corp|\(x\)|^x ", regex=True)
    d = d[pre & d["channel"].ne("other")].copy()
    t = d["t"]
    is_grok = t.str.contains(GROK_RE) & ~t.str.contains(NOT_GROK)
    if panel == "eu":
        # Stripe/PayPal: the payee must be xAI; Apple: app name must be a Grok app
        is_grok &= ~(d["channel"].eq("stripe") & ~t.str.contains(r"grok xai|xai, llc"))
    is_x = t.str.contains(X_CTX) & ~is_grok & ~t.str.contains(r"robux|roblox|itvx|saver|unfollow|tweetbot")
    d = d[is_grok | is_x].copy()
    if d.empty:
        return pd.DataFrame(columns=COLS)
    d["fam"] = np.where(is_grok[d.index], "grok", "x")
    d["usd"] = d["amount"] * d["currency"].map(FX_USD).fillna(1.0)

    rows = []
    for r in d.itertuples(index=False):
        t = r.t
        reason = "ok"
        if r.fam == "grok":
            provider = "grok"
            tier = _grok_tier(t)
            xs = XSUB_RE.search(t)
            if tier is None and xs and r.dt >= XSUB_LAUNCH:
                tier = "xsub_" + (xs.group(1) or xs.group(2))
            if GROK_CREDITS.search(t):
                tier, reason = "credits", "credits"
            elif GROK_PAYMENT.search(t) or tier is None:
                tier = _grok_band(r.usd) if not r.is_cancel else None
                if tier is None and not r.is_cancel:
                    reason = "credits_or_unknown"
            if tier == "xsub":
                tier = "xsub_unknown"
        else:
            provider = "grok_x"
            tier = _x_tier(t)
            xs = XSUB_X_RE.search(t)
            if xs and r.dt >= XSUB_LAUNCH:  # X Subscription sold in the X app ('Plus (X)', from 2026-10-12)
                provider, tier = "grok", "xsub_" + xs.group(1)
            if tier is None and r.channel in ("paypal", "direct") and "payment" not in t:
                tier = _x_band(r.amount)
            if tier == "creator":
                reason = "x_creator_sub"
            elif tier in ("basic", "premium"):
                reason = "x_non_plus_tier"
            elif tier is None and not r.is_cancel:
                reason = "x_payment_unpriced" if "payment" in t else "x_unknown"
        cad, pm = _cadence(t, tier, r.usd)
        kind = "cancel" if (r.is_cancel or (CANCEL_TXT.search(t) and pd.isna(r.amount))) else "charge"
        if kind == "cancel":
            if "trial" in t and ("ended" in t or "end" in t):
                reason = "trial_end"
            elif reason in ("credits_or_unknown", "x_unknown", "x_payment_unpriced"):
                reason = "ok"
        else:
            if r.spam:
                reason = "spam"
            elif PRORATION.search(t):
                reason = "proration"
            elif r.refund or REFUND.search(t):
                reason = "refund"
            elif reason == "ok" and BUSINESS.search(t):
                reason = "business"
            elif reason == "ok" and (TRIAL.search(t) or (pd.notna(r.amount) and r.amount <= 0)):
                reason = "trial"
            elif reason == "ok" and (pd.isna(r.amount) or UNPRICED_CONFIRM.search(t)):
                reason = "unpriced_confirmation"
            elif reason == "ok" and r.channel == "paypal" and provider == "grok":
                reason = "reseller"  # e.g. g2a 'supergrok 1 month' keys
        plan = f"{tier}_{cad}" if tier and tier not in ("credits", "creator") else f"unknown_{cad}"
        rows.append((r.uid, r.dt, r.country, provider, tier, cad, plan, r.channel, kind,
                     r.amount if kind == "charge" else np.nan, r.currency,
                     _end_date(t, r.dt) if kind == "cancel" else pd.NaT, reason, pm, r.descr))
    out = pd.DataFrame(rows, columns=["uid", "dt", "country", "provider", "tier", "cadence", "plan", "channel",
                                      "kind", "amount", "currency", "end_date", "reason", "period_months", "descr"])
    out["end_date"] = pd.to_datetime(out["end_date"])
    # PayPal-funded Play purchases are google_play; a remaining paypal/grok charge is a reseller key (excluded).
    out["renews"] = out["channel"].isin(["apple", "google_play", "stripe", "paypal"])
    # de-duplicate repeated line items (same uid, day, channel, plan, amount); also the Play receipt + PayPal
    # receipt for one Play purchase (both channel google_play)
    ok = out["reason"].eq("ok")
    key = ["uid", "dt", "channel", "provider", "plan", "kind", "amount"]
    srt = out.assign(_o=~ok).sort_values(["_o"] + key, kind="mergesort")
    dup = srt.duplicated(key, keep="first") & ~srt["_o"]
    out.loc[dup[dup].index, "reason"] = "duplicate"
    out["keep"] = out["reason"].eq("ok")
    out = out.sort_values(["provider", "uid", "dt"], kind="mergesort").reset_index(drop=True)
    return out[COLS]
