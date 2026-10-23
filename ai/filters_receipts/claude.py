"""Claude (Anthropic) consumer-subscription filter for the e-receipt panels.

classify(df, panel) -> one row per Claude candidate line item (kept or rejected); see filters_receipts/BRIEF.md.

US (NIQ / Slice ITEMS_LIVE)
  direct       merchant 'Anthropic', item 'Payment' (generic; plan from price, USD bands reused from
               filters/claude.py). $200-240 = Pro annual or Max 20x: an in-band repeat by the uid 25-40 days before
               or after -> max20_M, else pro_A (pending if inside the last 40 days of data).
               'Pro subscription' / 'Max subscription' items are unpriced confirmations (not charges).
  apple        merchant 'iTunes', 'Claude by Anthropic : Claude Pro - Monthly (Monthly)' (priced); the
               'Claude by Anthropic Claude Pro - Monthly $20.00 /month' rows are unpriced confirmations.
  google_play  'Claude Pro Subscription (Claude by Anthropic) Auto-renewing subscription', 'Claude Max (...)'.
  cancels      'Anthropic Cancellation' ('Claude Pro' / 'Claude Max'), 'iTunes Cancellation' and
               'Google Play Cancellation' items naming Claude by Anthropic.
EU (NIQ Fox)
  direct       merchant 'anthropic', product 'claude pro' / 'max plan - 5x' / 'max plan - 20x'
  stripe       merchant 'stripe', 'anthropic ireland, limited : claude pro' etc.
  apple        'claude by anthropic || claude pro - monthly (mensuel)' (period in the local language)
  google_play  'claude pro subscription (claude by anthropic)...', 'claude max (claude by anthropic)...', also
               the PayPal receipt of a Play purchase (seller 'google'), deduplicated against the Play receipt
  paypal       seller 'anthropic' / 'claude' (no product text: plan from price)
  other        Klarna, seller 'anthropic' / 'claude' (plan from price)
  PayPal / Klarna receipts that duplicate a merchant receipt (same uid within 3 days) are dropped.
  Fox has no Claude cancellation emails.
Excluded everywhere: Team / Enterprise plans, extra-usage / credits / API, gift purchases, unpriced rows, refunds,
spam-flagged Fox orders (is_spam only; deleted / trashed receipts are kept), unrelated 'claude' products (Monsieur Claude films, Claude Monet, clothing, courses).
"""
import re

import numpy as np
import pandas as pd

PROVIDER = "claude"
MAX_LAUNCH = pd.Timestamp("2025-04-09")
REPEAT = (25, 40)          # collision band repeat window (days)
PAYMETHOD_DUP_DAYS = 3

COLS = ["uid", "dt", "country", "provider", "tier", "cadence", "plan", "channel", "kind", "amount", "currency",
        "end_date", "renews", "keep", "reason", "note"]

# Pro monthly reference price by currency: plans are resolved from price / reference ('r') when the text is silent
# US direct 'Payment' list prices (pre-tax): lo, hi, tier, cadence
US_DIRECT = [(19.99, 20.00, "pro", "M"), (9.99, 10.00, "pro", "M"), (99.99, 100.00, "max5", "M"),
             (199.99, 200.00, "b200", ""), (215.99, 216.00, "pro", "A")]
PRO_REF = {"USD": 20.0, "GBP": 18.0, "EUR": 21.6}

USAGE = re.compile(r"extra usage|credit|recharge|usage\b|api\b")
TEAM = re.compile(r"team plan|\bteam\b|enterprise")
GIFT = re.compile(r"\bgift\b")
ANNUAL = re.compile(r"annual|annuel|j.hrlich|anual|annuale|yearly|/year|\(1 year\)|\d{4}\s*-\s*\w{3} \d+, \d{4}")
MONTHLY = re.compile(r"monthly|mensuel|monatlich|mensual|mensile|/month|1 month")
TRIAL = re.compile(r"trial|essai|prueba|prova|testzeitraum")
KLARNA_NOISE = re.compile(r"wechselkurs|exchange rate|service fee|servizio|tasso|taux|tipo de cambio")
MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
END_DATE = re.compile(rf"(?:on|until|ends?|expires?|through)\s+({MONTHS}\s+\d{{1,2}},?\s+\d{{4}})", re.I)


def _tier_text(t: pd.Series) -> pd.Series:
    return pd.Series(np.select(
        [t.str.contains(r"max 20x|max plan - 20x|20x"), t.str.contains(r"max 5x|max plan - 5x|5x"),
         t.str.contains(r"claude max|max subscription"), t.str.contains(r"claude pro|pro subscription|\bpro\b")],
        ["max20", "max5", "max", "pro"], default=""), index=t.index)


def _cad_text(t: pd.Series) -> pd.Series:
    return pd.Series(np.select([t.str.contains(ANNUAL), t.str.contains(MONTHLY)], ["A", "M"], default=""),
                     index=t.index)


def _resolve_price(x: pd.DataFrame) -> pd.DataFrame:
    """Fill tier / cadence from price where the text is silent. Writes 'b200' for the direct collision band."""
    ref = x.currency.map(PRO_REF).fillna(20.0)
    r = x.amount / ref
    apple_like = x.channel.isin(["apple", "google_play"])  # store prices: Pro A ~10.75-11x, Max 20x ~12.5-13.6x
    tier, cad, note = x.tier.copy(), x.cadence.copy(), x.note.copy()

    # 'claude max' with no multiplier (Google Play, Anthropic cancellations): 5x below 8x Pro
    m = tier.eq("max")
    tier[m & (r < 8)] = "max5"
    tier[m & (r >= 8)] = "max20"

    # Pro named: annual if >= 6x Pro, else monthly (promo half-price kept)
    m = tier.eq("pro") & cad.eq("")
    cad[m] = np.where(r[m] >= 6, "A", "M")
    note[tier.eq("pro") & r.between(0.4, 0.62)] = "promo_50pct"

    # no plan text: price bands (r in Pro multiples)
    m = tier.eq("")
    bands = [  # lo, hi, tier, cadence, note
        (0.45, 0.62, "pro", "M", "promo_50pct"), (0.95, 1.20, "pro", "M", ""),
        (4.95, 5.60, "max5", "M", ""), (6.0, 7.0, "max5", "M", "store_price"),
        (9.9, 12.2, "b200", "", ""), (12.4, 14.3, "max20", "M", "store_price"),
    ]
    for lo, hi, t_, c_, n_ in bands:
        b = m & r.between(lo, hi)
        if t_ == "max5" and n_ == "store_price":
            b &= apple_like
        if t_ == "max20":
            b &= apple_like
        tier[b], cad[b], note[b] = t_, c_, n_
    # store channels: the 9.9-12.2 band is Pro annual (Max 20x has its own store price)
    s = tier.eq("b200") & apple_like
    tier[s], cad[s] = "pro", "A"
    # named Max on the store or direct is always monthly
    cad[tier.isin(["max5", "max20"]) & cad.eq("")] = "M"
    x = x.assign(tier=tier, cadence=cad, note=note)
    return x


def _resolve_200(x: pd.DataFrame, data_end: pd.Timestamp) -> pd.DataFrame:
    """Direct collision band ($200 / GBP 180 / EUR 180 net; 9.9-12.2x Pro): repeat within 25-40 days -> Max 20x."""
    b = x[x.tier.eq("b200")].sort_values(["uid", "dt"])
    if b.empty:
        return x
    g = b.groupby("uid").dt
    prev, nxt = (b.dt - g.shift(1)).dt.days, (g.shift(-1) - b.dt).dt.days
    lo, hi = REPEAT
    monthly = (prev.between(lo, hi) | nxt.between(lo, hi)) & (b.dt >= MAX_LAUNCH)
    pending = ~monthly & (b.dt >= MAX_LAUNCH) & ((data_end - b.dt).dt.days < hi) & nxt.isna()
    x.loc[b.index, "tier"] = np.where(monthly, "max20", "pro")
    x.loc[b.index, "cadence"] = np.where(monthly, "M", "A")
    x.loc[b.index, "note"] = np.select([b.dt < MAX_LAUNCH, monthly, pending],
                                       ["pre_max_annual", "repeat_monthly", "pending"], default="one_off_annual")
    return x


def _spam(attrs: pd.Series) -> pd.Series:
    return attrs.fillna("").str.contains(r'"order_is_spam":"?1')


def _eu(df: pd.DataFrame) -> pd.DataFrame:
    m = df.merchant_name.fillna("").str.lower()
    s = df.seller_name.fillna("").str.lower()
    t = (df.product_name.fillna("") + " " + df.descr.fillna("")).str.lower()
    ch = pd.Series("", index=df.index)
    ch[(m == "anthropic")] = "direct"
    ch[(m == "stripe") & t.str.match(r"\s*anthropic(?! ?s technology)")] = "stripe"
    ch[(m == "apple") & t.str.match(r"\s*claude by anthropic")] = "apple"
    ch[(m == "google play") & t.str.contains("claude by anthropic")] = "google_play"
    ch[(m == "paypal") & s.eq("google") & t.str.contains(r"claude pro subscript|claude max \(claude|claude by anth")] = "gp_paypal"
    ch[(m == "paypal") & s.isin(["anthropic", "claude"])] = "paypal"
    ch[(m == "klarna") & s.isin(["anthropic", "claude"])] = "other"
    keep_ix = ch.ne("")
    d, t, ch = df[keep_ix], t[keep_ix], ch[keep_ix]
    x = pd.DataFrame({
        "uid": d.uid.astype(str), "dt": pd.to_datetime(d.dt), "country": d.country.str.lower(),
        "amount": pd.to_numeric(d.item_price, errors="coerce").astype(float),
        "currency": d.order_currency.str.upper(), "channel": ch, "kind": "charge", "text": t,
        "email_type": d.email_type.fillna(""), "spam": _spam(d.order_attributes),
    })
    x["tier"], x["cadence"] = _tier_text(t), _cad_text(t)
    x.loc[x.channel.isin(["paypal", "other"]), ["tier", "cadence"]] = ""  # payment-method text is not the plan
    reason = pd.Series("ok", index=x.index)
    rules = [  # later rules win
        (x.amount.isna() | (x.amount <= 0), "unpriced"),
        (x.channel.eq("direct") & t.str.match(r"\s*(<br>)?tax\b"), "tax_line"),
        (t.str.contains(TRIAL), "trial"),
        (x.channel.eq("other") & (t.str.contains(KLARNA_NOISE) | ~x.email_type.str.startswith("payment")),
         "payment_method_noise"),
        (x.channel.isin(["direct", "stripe"]) & ~t.str.contains(r"claude pro|max plan|\bmax\b|usage|credit|team|gift"),
         "other_product"),
        (t.str.contains(USAGE), "api_usage"),
        (t.str.contains(GIFT), "gift"),
        (t.str.contains(TEAM), "team"),
        (x.spam, "spam_flag"),
    ]
    for mask, r in rules:
        reason[mask] = r
    x["reason"] = reason
    return x


def _us(df: pd.DataFrame) -> pd.DataFrame:
    m = df.merchant_name.fillna("")
    t = df.descr.fillna("").str.lower()
    claude = t.str.contains("claude by anthropic|claude") & ~t.str.contains(r"monet|jean-claude|van damme")
    ch = pd.Series("", index=df.index)
    kind = pd.Series("charge", index=df.index)
    ch[m.eq("Anthropic")] = "direct"
    ch[m.eq("iTunes") & t.str.contains("claude by anthropic")] = "apple"
    ch[m.eq("Google Play") & t.str.contains("claude by anthropic")] = "google_play"
    ch[m.eq("Anthropic Cancellation")] = "direct"
    ch[m.eq("iTunes Cancellation") & t.str.contains("claude by anthropic")] = "apple"
    ch[m.eq("Google Play Cancellation") & t.str.contains("claude by anthropic")] = "google_play"
    kind[m.str.endswith("Cancellation")] = "cancel"
    sel = ch.ne("") & (claude | m.isin(["Anthropic", "Anthropic Cancellation"]))
    d, t, ch, kind = df[sel], t[sel], ch[sel], kind[sel]
    x = pd.DataFrame({
        "uid": d.uid.astype(str), "dt": pd.to_datetime(d.dt), "country": "us",
        "amount": pd.to_numeric(d.item_price, errors="coerce").astype(float), "currency": "USD",
        "channel": ch, "kind": kind, "text": t, "spam": False,
    })
    x["tier"], x["cadence"] = _tier_text(t), _cad_text(t)
    generic = x.channel.eq("direct") & x.kind.eq("charge") & t.str.strip().eq("payment")
    x.loc[generic, ["tier", "cadence"]] = ""
    # 'Payment' item_price is pre-tax: only exact list prices are plan charges (credits / usage / prorations are not)
    for lo, hi, t_, c_ in US_DIRECT:
        b = generic & x.amount.between(lo, hi)
        x.loc[b, "tier"], x.loc[b, "cadence"] = t_, c_
    x["_listed"] = ~generic | x.tier.ne("")
    # cancellations: stated end date; plan from text (Max multiplier unknown on Anthropic emails)
    canc = x.kind.eq("cancel")
    x.loc[canc, "end_date"] = pd.to_datetime(
        d.descr[canc].fillna("").str.extract(END_DATE, expand=False).str.replace(".", "", regex=False),
        errors="coerce", format="mixed")
    reason = pd.Series("ok", index=x.index)
    named = t.str.contains(r"claude|pro subscription|max subscription")
    rules = [
        (x.kind.eq("charge") & (x.amount.isna() | (x.amount <= 0)), "unpriced"),
        (x.kind.eq("charge") & x.channel.eq("apple") & t.str.contains(r"\$[\d.]+ ?/(?:month|year)") & x.amount.isna(),
         "unpriced_confirmation"),
        (x.channel.eq("direct") & x.kind.eq("charge") & ~generic & ~named, "other_product"),
        (generic & ~x._listed & x.amount.gt(0), "non_list_amount"),
        (x.channel.eq("direct") & x.kind.eq("cancel") & ~t.str.contains(r"claude (?:pro|max)"), "other_product"),
        (t.str.contains(TRIAL) & ~t.str.contains("subscription from anthropic"), "trial"),
        (t.str.contains(USAGE), "api_usage"),
        (t.str.contains(GIFT), "gift"),
        (t.str.contains(TEAM), "team"),
    ]
    for mask, r in rules:
        reason[mask] = r
    x["reason"] = reason
    return x


def _direct_usage_us(x: pd.DataFrame) -> None:
    """US 'Payment' rows carry no product text: Pro/Max list-price amounts are plan charges; everything else
    (credits, extra-usage top-ups, prorated upgrades) is excluded as usage. Pro-band rows paid 3+ times by the
    same uid within 20 days are auto-reload credit purchases, not plan charges."""
    g = x.channel.eq("direct") & x.kind.eq("charge") & x.reason.eq("ok") & x.text.str.strip().eq("payment")
    y = x[g].sort_values(["uid", "dt"])
    cnt = y.set_index("dt").groupby("uid").amount.rolling("20D").count().reset_index(level=0, drop=True)
    burst = pd.Series(cnt.values >= 3, index=y.index)
    # a burst marks every row of the uid's cluster: propagate backwards within 20 days
    y = y.assign(burst=burst)
    bdates = y[y.burst].groupby("uid").dt.apply(list)
    for i, (u, dt) in zip(y.index, zip(y.uid, y.dt)):
        if u in bdates.index and any(0 <= (b - dt).days <= 20 for b in bdates[u]):
            y.at[i, "burst"] = True
    x.loc[y.index[y.burst], "reason"] = "api_usage"


def _sub_items_us(x: pd.DataFrame) -> None:
    """US: the unpriced 'Pro subscription' / 'Max subscription' items Anthropic sends around a purchase confirm the
    plan of a $200 payment within 3 days. Measured: 97% of $200 payments next to a 'Pro subscription' item are
    one-offs (Pro annual). A 'Max subscription' item turns a one-off / pending $200 into Max 20x; a 'Pro subscription'
    item settles a pending $200 as Pro annual."""
    sub = x[x.channel.eq("direct") & x.text.str.strip().isin(["pro subscription", "max subscription"])]
    b = x[x.note.isin(["one_off_annual", "pending"]) & x.reason.eq("ok")]
    if sub.empty or b.empty:
        return
    j = b[["uid", "dt", "note"]].reset_index().merge(sub[["uid", "dt", "text"]], on="uid", suffixes=("", "_s"))
    j = j[(j.dt_s - j.dt).dt.days.abs().le(3)]
    mx = j.loc[j.text.str.contains("max"), "index"].unique()
    pro = j.loc[j.text.str.contains("pro") & j.note.eq("pending"), "index"]
    pro = np.setdiff1d(pro.unique(), mx)
    x.loc[mx, ["tier", "cadence", "note"]] = ["max20", "M", "max_item"]
    x.loc[pro, "note"] = "pro_item_annual"


def classify(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    x = _eu(df) if panel == "eu" else _us(df)
    if "end_date" not in x:
        x["end_date"] = pd.NaT
    x["end_date"] = pd.to_datetime(x["end_date"])
    x["note"] = ""
    if x.empty:
        return pd.DataFrame(columns=COLS)
    if panel != "eu":
        _direct_usage_us(x)

    ok = x.reason.eq("ok") & x.kind.eq("charge")
    x.loc[ok] = _resolve_price(x[ok])
    # direct / stripe / paypal / klarna: the collision band is resolved by recurrence (per uid, across channels)
    x = _resolve_200(x, x.dt.max()) if ok.any() else x
    if panel != "eu":
        _sub_items_us(x)
    # Pro named but sub-promo amount (tiny prorations, usage-like) / Max named at sub-Max amounts are prorated
    # upgrade charges: kept with the named plan (text first)
    x.loc[ok & x.tier.eq(""), "reason"] = "out_of_band"

    # cancels: Max multiplier unknown -> unknown_M; Pro -> pro_M unless 'annual' stated
    c = x.kind.eq("cancel")
    x.loc[c & x.tier.isin(["max", ""]), "tier"] = "unknown"
    x.loc[c & x.cadence.eq(""), "cadence"] = "M"

    x["provider"] = PROVIDER
    x["plan"] = np.where(x.tier.ne("") & x.cadence.ne(""), x.tier + "_" + x.cadence, None)
    x.loc[x.kind.eq("cancel"), ["amount", "currency"]] = [np.nan, None]

    # Play purchases paid with PayPal: Google Play channel, dropped if the Play receipt is there
    gp_pp = x.channel.eq("gp_paypal")
    x.loc[gp_pp, "channel"] = "google_play"
    x["_pm"] = gp_pp | x.channel.isin(["paypal", "other"])

    # exact duplicates
    k = x.reason.eq("ok")
    dup = k & x[k].duplicated(["uid", "dt", "channel", "kind", "plan", "amount"]).reindex(x.index, fill_value=False)
    x.loc[dup, "reason"] = "duplicate"
    # payment-method receipts duplicating a merchant receipt within 3 days
    k = x.reason.eq("ok") & x.kind.eq("charge")
    mer = x[k & ~x._pm]
    pm = x[k & x._pm]
    if len(pm):
        j = pm.reset_index().merge(mer[["uid", "dt", "channel"]].rename(columns={"dt": "dt2", "channel": "ch2"}),
                                    on="uid", how="inner")
        same = (j.dt2 - j.dt).dt.days.abs().le(PAYMETHOD_DUP_DAYS) & (
            j.channel.eq("google_play").eq(j.ch2.eq("google_play")))
        x.loc[j.loc[same, "index"].unique(), "reason"] = "duplicate_payment_method"

    x["renews"] = True
    x["keep"] = x.reason.eq("ok")
    x["amount"] = x.amount.round(2)
    return x[COLS].sort_values(["uid", "dt"]).reset_index(drop=True)
