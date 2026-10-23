"""Claude (Anthropic) consumer web-subscription filter for the card panels.

classify(df, panel) -> one row per Claude candidate payment (kept or rejected), see filters/BRIEF.md.

Descriptors (uppercased before matching; Fable masks the word 'claude' as '<name>' in many rows):
  consumer web  CLAUDE.AI SUBSCRIPTION (to Jun 2026), ANTHROPIC* CLAUDE SUB / ANTHROPIC* CLAUDE (from 2026-05-30),
                issuer truncations (CLAUDE.AI SUBSCRIP, ANTHROPIC* CLAUDE S, ANTHROPIC* SUB, CLAUDEAI SUBSCRIPTION),
                masked forms (<NAME>.AI SUBSCRIPTION, ANTHROPIC* <NAME> SUB)
  team          ... CLAUDE TEAM / truncated CLAUDE TE, CLAUDE T / ANTHROPIC* TEAM
  google_play   GOOGLE *CLAUDE BY ANTH..., GOOGLE ANTHROPIC, PP*GOOGLE ANTHROPIC: KEPT (user decision 2026-10-19),
                channel='google_play', banded with Play price points (GP_BANDS); Apple stays excluded
  api_usage     bare ANTHROPIC (API console credits, auto-reload, Pro/Max extra-usage top-ups), EXCEPT bare rows at
                an exact GBP/EUR list price or at a list-price band repeated ~monthly by the uid (-> web, note bare_descr_*)
  other_product ANTHROPIC* CLAUDE CERT (certification)
  bank_fee      overdraft / NSF / French foreign-card fee lines quoting the merchant
Bare 'claude' is never matched (Claude Monet, Jean-Claude, personal transfers); PHILANTHROPIC and ANTHROPICS
(PortraitPro's maker) are excluded. Extra output column `note` records how a plan was assigned.

Plans: pro_M, pro_A, max5_M, max20_M. Pro annual and Max 20x monthly share one amount from 2025-04-09
($200 / GBP 180 / EUR 180 net), resolved per uid by the 2-month repeat rule (see _resolve_200). Prorated upgrade charges
(amounts between the list bands) take the plan of the uid's next regular payment within 45 days, else the plan
implied by the amount range.
"""
import re

import numpy as np
import pandas as pd

PROVIDER = "claude"
MAX_LAUNCH = pd.Timestamp("2025-04-09")   # Max launch; $200 Pro annual replaced $216
PROMO_START = pd.Timestamp("2025-01-01")  # 50%-off Pro promo months seen from here

# no word boundary before ANTHROPIC: IT strips punctuation (CRVANTHROPIC, KLARNAANTHROPIC)
CAND = re.compile(r"ANTHROPIC|CLAUDE ?\.?AI\b|CLAUDEAI|CLAUDE BY|<NAME>\.AI SUBSCRI|CLAU AI PRO")
FALSE_POS = re.compile(r"PHILANTHROP|MISANTHROP|ANTHROPICS\b")  # Anthropics Technology = PortraitPro
GOOGLE = re.compile(r"GOOGLE")
APPLE = re.compile(r"APPLE\.COM|ITUNES")
REFUND = re.compile(r"REFUND|REVERSAL|\bADJ-|DISPUTE|CHARGEBACK|\bRETURN")
# separate bank-fee lines that quote the merchant (overdraft / NSF in the US, French foreign-card fees)
FEE = re.compile(r"OVERDRAFT FEE|\bNSF\b|COURTESY PAY FEE|^(PRLV )?FRAIS\b|COMMISSION CB")
CERT = re.compile(r"CLAUDE CERT|<NAME> CERT")
TEAM = re.compile(r"TEAM|ANTHROPIC\*? ?:? ?(CLAUDE|<NAME>) ?TE|ANTHROPIC\*? ?:? ?(CLAUDE|<NAME>) T\b")
# 'ANTHROPIC*' (Stripe prefix) appears only with the consumer descriptor family from 2026-05-30 (team handled first)
SUB = re.compile(r"(?<!-)CLAUDE ?\.?AI\b|CLAUDEAI SUB|<NAME>\.AI SUBSCRI|CLAU AI PRO|ANTHROPIC ?:? ?CLAUDE"
                 r"|ANTHROPIC ?:? ?<NAME> SUB|ANTHROPIC\*")
# (bare 'ANTHROPIC <NAME>' without '*' or SUB is not consumer: in ES it is the API entity, likely masked 'IRELAND')
# GBP/EUR list prices (incl. VAT per country, and net of VAT) for bare 'ANTHROPIC' rows: API is billed in USD, so an
# exact local-currency list price on a bare descriptor is a consumer plan charge
EXACT = {"GBP": {9.0, 15.0, 18.0, 75.0, 90.0, 150.0, 180.0},
         "EUR": {10.71, 10.80, 10.89, 10.98, 18.0, 21.42, 21.60, 21.78, 21.96, 90.0, 107.10, 108.0, 108.90, 109.80,
                 180.0, 214.20, 216.0, 217.80, 219.60}}

# Amount bands by currency: (lo, hi, tier, cadence, note). Order matters (first match wins).
# 'b200' = the Pro-annual / Max-20x collision band, resolved per uid. 'pr_max5' / 'pr_max20' / 'pr_any' = prorated.
BANDS = {
    "USD": [  # list prices exclude sales tax: allow ~+11-15%
        (19.99, 23.00, "pro", "M", ""),
        (9.99, 11.20, "pro", "M", "promo_50pct"),
        (99.99, 111.50, "max5", "M", ""),           # also $100 win-back half-price Max 20x first month
        (199.99, 240.00, "b200", None, ""),
        (75.00, 99.98, "pr_max5", None, "prorated"),
        (111.51, 199.98, "pr_max20", None, "prorated"),
        (26.00, 74.99, "pr_any", None, "prorated"),
    ],
    "GBP": [
        (14.50, 19.50, "pro", "M", ""),               # GBP 18; 15 = net of VAT; 15.5-17.5 = legacy USD billing (FX)
        (8.50, 9.50, "pro", "M", "promo_50pct"),
        (89.50, 90.50, "max5", "M", ""),
        (74.50, 75.50, "max5", "M", "net_of_vat"),
        (179.50, 180.50, "b200", None, ""),
        (149.00, 151.00, "b200", None, "net_of_vat"),
        (190.00, 200.00, "b200", None, ""),           # GBP 194.40 Pro annual (Nov 2024 - Apr 2025)
        (60.00, 89.49, "pr_max5", None, "prorated"),
        (90.51, 179.49, "pr_max20", None, "prorated"),
        (22.00, 59.99, "pr_any", None, "prorated"),
    ],
    "EUR": [
        (17.00, 23.90, "pro", "M", ""),               # EUR 18 net + 19-22% VAT; 18 = net; legacy USD billing (FX);
                                                      # FR bank adds FX fee into the line (21.60*1.029+1.40 = 23.63)
        (8.50, 11.50, "pro", "M", "promo_50pct"),
        (104.00, 113.50, "max5", "M", ""),          # 112.5 = 108 + FR bank FX fee
        (89.50, 90.50, "max5", "M", "net_of_vat"),
        (210.00, 226.00, "b200", None, ""),         # 223.7 = 216 + FR bank FX fee
        (179.00, 181.00, "b200", None, "net_of_vat"),
        (225.00, 240.00, "b200", None, ""),           # EUR 231-237 Pro annual (Nov 2024 - Apr 2025)
        (60.00, 103.99, "pr_max5", None, "prorated"),
        (113.51, 209.99, "pr_max20", None, "prorated"),
        (25.00, 59.99, "pr_any", None, "prorated"),
    ],
}
# Google Play price points (from the data): US Pro $19.99, Max 5x $124.99, Max 20x $249.99, Pro annual ~$214.99,
# each + sales tax; GBP/EUR Play amounts cluster at the web Pro / Max 5x prices. No Pro-annual / Max-20x collision.
GP_BANDS = {
    "USD": [(19.50, 23.00, "pro", "M", ""), (124.50, 140.00, "max5", "M", ""), (200.00, 240.00, "pro", "A", ""),
            (249.00, 285.00, "max20", "M", "")],
    "GBP": [(14.50, 21.00, "pro", "M", ""), (85.00, 110.00, "max5", "M", "")],
    "EUR": [(16.50, 24.00, "pro", "M", ""), (100.00, 135.00, "max5", "M", "")],
}
MONTHLY = (20, 45)     # gap (days) to the next regular payment that a prorated charge borrows its plan from
REPEAT = (25, 40)      # collision band: same-uid in-band repeat this many days apart = Max 20x monthly
NEAR_DUP_DAYS = 3      # same uid + same list band within this many days = one payment posted twice


def _norm(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    if panel == "omega":
        amt = pd.to_numeric(df["amount"], errors="coerce").astype(float)
        out = pd.DataFrame({
            "uid": df["uid"].astype(str), "dt": pd.to_datetime(df["dt"]), "amount": amt,
            "currency": df["currency"], "descr": df["descr"].fillna(""),
            "_credit": (df["transtype"].str.lower() != "debit") | (amt <= 0),
            "_business": False,
        })
    else:
        out_amt = -df["spendout"].fillna(0).astype(float)
        inflow = df["spendin"].fillna(0).astype(float)
        dt = pd.to_datetime(df["dt"])
        out = pd.DataFrame({
            "uid": df["uid"].astype(str), "dt": dt, "amount": np.where(out_amt > 0, out_amt, inflow),
            "currency": df["currency"], "descr": df["descr"].fillna(""),
            "_credit": (inflow > 0) | (out_amt <= 0),
            "_business": df["usertype"].ne("C"),
        })
    return out.reset_index(drop=True)


def _descr_class(d: str) -> str:
    if FALSE_POS.search(d) or not CAND.search(d):
        return "none"
    if REFUND.search(d):
        return "refund"
    if FEE.search(d):
        return "fee"
    if GOOGLE.search(d):
        return "google_play"
    if APPLE.search(d):
        return "app_store"
    if CERT.search(d):
        return "other_product"
    if TEAM.search(d):
        return "team"
    if SUB.search(d):
        return "sub"
    if "ANTHROPIC" in d:
        return "plain"
    return "none"


def _rescue_plain(x: pd.DataFrame) -> None:
    """Bare 'ANTHROPIC' = API / usage credits, except (a) an exact GBP/EUR list price, or (b) a list-price-band amount
    repeated by the same uid 26-35 days apart (calendar recurrence; API auto-reload follows usage, not the calendar)."""
    pl = (x.cls == "plain") & ~x._credit
    exact = pl & np.array([round(a, 2) in EXACT.get(c, ()) for a, c in zip(x.amount, x.currency)], dtype=bool)
    bands = [_band(a, c) for a, c in zip(x.amount, x.currency)]
    # list-price bands only (not promo / net-of-VAT amounts, which collide with round API credit purchases)
    inband = pl & np.array([b[0] in ("pro", "max5", "b200") and not b[2] for b in bands], dtype=bool)
    y = x[inband].assign(a=lambda d: d.amount.round(0)).sort_values(["uid", "a", "dt"])
    g = y.groupby(["uid", "a"]).dt
    prev, nxt = (y.dt - g.shift(1)).dt.days, (g.shift(-1) - y.dt).dt.days
    rec = y.index[prev.between(26, 35) | nxt.between(26, 35)]
    x.loc[exact[exact].index, "note"] = "bare_descr_exact_price"
    x.loc[rec.difference(exact[exact].index), "note"] = "bare_descr_recurring"
    x.loc[exact[exact].index.union(rec), "cls"] = "sub"
    x.loc[x.cls == "plain", "cls"] = "api_usage"


def _band(amount: float, currency: str, table: dict = BANDS):
    for lo, hi, tier, cad, note in table.get(currency, []):
        if lo <= amount <= hi:
            return tier, cad, note
    return None, None, ""


def _resolve_200(p: pd.DataFrame, data_end: pd.Timestamp) -> pd.DataFrame:
    """Pro annual vs Max 20x monthly for the collision band (rows with tier == 'b200').

    Descriptors do not delineate the two (same descriptor families and Omega merchids; no 'MAX' text), so the
    user's 2-month rule applies: an in-band payment with another in-band payment by the same uid 25-40 days
    before or after = Max 20x monthly; a one-off = Pro annual; a one-off in the last 40 days of data cannot be
    tested yet = Pro annual provisional (note 'pending'). Before Max launch the band can only be Pro annual."""
    p = p.sort_values(["uid", "dt"]).copy()
    b = p[p.tier == "b200"].copy()
    g = b.groupby("uid").dt
    prev, nxt = (b.dt - g.shift(1)).dt.days, (g.shift(-1) - b.dt).dt.days
    lo, hi = REPEAT
    monthly = (prev.between(lo, hi) | nxt.between(lo, hi)) & (b.dt >= MAX_LAUNCH)
    pending = ~monthly & (b.dt >= MAX_LAUNCH) & ((data_end - b.dt).dt.days < hi) & nxt.isna()
    b["tier"] = np.where(monthly, "max20", "pro")
    b["cadence"] = np.where(monthly, "M", "A")
    note2 = np.select([b.dt < MAX_LAUNCH, monthly, pending], ["pre_max_annual", "repeat_monthly", "pending"],
                      default="one_off_annual")
    old = b["note"].astype(str)
    p.loc[b.index, "tier"] = b.tier
    p.loc[b.index, "cadence"] = b.cadence
    p.loc[b.index, "note"] = np.where(old.eq(""), note2, old + ";" + note2)
    return p


def _resolve_prorated(p: pd.DataFrame) -> pd.DataFrame:
    """Prorated charges take the next regular plan within 45 days, else the plan implied by the amount range."""
    p = p.sort_values(["uid", "dt"]).copy()
    is_pr = p.tier.isin(["pr_max5", "pr_max20", "pr_any"])
    regular = p.tier.isin(["pro", "max5", "max20"])
    # next regular row strictly after this one: shift within uid, then back-fill within uid
    nxt = p[["dt", "tier", "cadence"]].where(regular).groupby(p.uid).shift(-1)
    nxt = nxt.groupby(p.uid).bfill()
    close = is_pr & ((nxt.dt - p.dt).dt.days.between(0, MONTHLY[1]))
    fallback = {"pr_max5": ("max5", "M"), "pr_max20": ("max20", "M"), "pr_any": (None, None)}
    for i in p.index[is_pr]:
        if close.at[i] and nxt.at[i, "tier"] in ("pro", "max5", "max20"):
            p.at[i, "tier"], p.at[i, "cadence"] = nxt.at[i, "tier"], nxt.at[i, "cadence"]
        elif p.at[i, "dt"] < MAX_LAUNCH:
            # no Max before launch: a large odd amount is a monthly->annual Pro switch net of credit
            p.at[i, "tier"], p.at[i, "cadence"] = ("pro", "A") if p.at[i, "tier"] == "pr_max20" else (None, None)
        else:
            p.at[i, "tier"], p.at[i, "cadence"] = fallback[p.at[i, "tier"]]
    return p


def classify(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    cols = ["uid", "dt", "amount", "currency", "descr", "provider", "tier", "cadence", "plan", "channel", "keep",
            "reason", "note"]
    x = _norm(df, panel)
    up = x.descr.str.upper()
    uniq = pd.Series(up.unique())
    x["cls"] = up.map(dict(zip(uniq, uniq.map(_descr_class))))
    x = x[x.cls != "none"].copy()
    if x.empty:
        return pd.DataFrame(columns=cols)

    x["note"] = ""
    _rescue_plain(x)
    x["provider"] = PROVIDER
    x["channel"] = np.select([x.cls == "google_play", x.cls == "sub"], ["google_play", "web"], default="other")
    x["tier"], x["cadence"] = None, None

    # rejection reasons, in priority order
    want_cur = "USD" if panel == "omega" else ("GBP" if panel == "uk" else "EUR")
    reason = pd.Series("ok", index=x.index)
    rules = [
        (x.cls == "refund", "refund"),
        (x.cls == "fee", "bank_fee"),
        (x._credit, "refund"),
        (x.currency != want_cur, "currency"),
        (x.amount <= 1.0, "auth"),
        (x._business, "business_user"),
        (x.cls == "app_store", "app_store"),
        (x.cls == "team", "team"),
        (x.cls == "api_usage", "api_usage"),
        (x.cls == "other_product", "other_product"),
    ]
    for mask, r in reversed(rules):
        reason[mask] = r
    x["reason"] = reason

    # de-duplicate pending/posted repeats among the remaining web candidates
    cand = x.reason == "ok"
    dup = cand & x[cand].duplicated(["uid", "dt", "amount"]).reindex(x.index, fill_value=False)
    x.loc[dup, "reason"] = "duplicate"
    cand = x.reason == "ok"

    # amount bands
    bands = [_band(a, c, GP_BANDS if ch == "google_play" else BANDS)
             for a, c, ch in zip(x.loc[cand, "amount"], x.loc[cand, "currency"], x.loc[cand, "channel"])]
    x.loc[cand, "tier"] = [b[0] for b in bands]
    x.loc[cand, "cadence"] = [b[1] for b in bands]
    bnote = pd.Series([b[2] for b in bands], index=x.index[cand])
    old = x.loc[cand, "note"]
    x.loc[cand, "note"] = np.where(old.eq(""), bnote, np.where(bnote.eq(""), old, old + ";" + bnote))
    promo_early = cand & (bnote.reindex(x.index) == "promo_50pct") & (x.dt < PROMO_START)
    x.loc[promo_early, ["tier", "cadence"]] = [None, None]

    # near-duplicates: same uid + same list band within NEAR_DUP_DAYS (Fable FR posts one charge under several
    # descriptor variants / with and without the bank's FX fee, a few days apart)
    c = x[cand & x.tier.isin(["pro", "max5", "b200"])].sort_values(["uid", "tier", "dt"])
    gap = c.groupby(["uid", "tier"]).dt.diff().dt.days
    near = c.index[gap.le(NEAR_DUP_DAYS)]
    x.loc[near, "reason"] = "duplicate"
    x.loc[near, ["tier", "cadence"]] = [None, None]
    cand = x.reason == "ok"

    p = x[cand & x.tier.notna()]
    p = _resolve_200(p, x.dt.max())
    p = _resolve_prorated(p)
    x.loc[p.index, ["tier", "cadence", "note"]] = p[["tier", "cadence", "note"]]

    cand = x.reason == "ok"
    x.loc[cand & x.tier.isna(), "reason"] = "out_of_band"
    x["plan"] = np.where(x.tier.isin(["pro", "max5", "max20"]), x.tier.astype(str) + "_" + x.cadence.astype(str), None)
    x["keep"] = x.reason == "ok"
    x["amount"] = x.amount.round(2)
    return x[cols].sort_values(["uid", "dt"]).reset_index(drop=True)
