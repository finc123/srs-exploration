"""Gemini (Google One AI tiers) consumer web-subscription filter for card panels.

classify(df, panel) -> one row per Google One / Google Storage payment that sits on an AI-tier price
point (AI Premium / AI Pro, Ultra, AI Plus) or on the 2TB plan after it absorbed AI Plus (2026-01-27).

Google bills AI and storage tiers under the same descriptor ("GOOGLE *Google One", "GOOGLE *Google
Storage"), so the tier is read from the amount. Where an AI price equals a storage price (US $19.99 =
AI Pro monthly / 100GB annual; $99.99 = Ultra 5x monthly / 2TB annual / 20TB monthly; $199.99 = AI
Pro annual / Ultra 20x monthly; ...), the cadence is read from the uid's own same-price payment gaps
(user rule): a payment with a same-price neighbour 25-40d before or after = monthly; a one-off = the
annual reading; a one-off within the last 40 days of data = 'pending' (kept, provisional monthly
reading unless that is storage). The 2024-25 'GOOGLE ONE AI PREMIUM' descriptor is AI-only and
forces ai_pro.

Pure storage price points (e.g. $1.99, $2.99, pre-2026 $9.99) are not candidates and are not returned
unless include_storage=True (then tier='storage', keep=False).

Tiers: ai_pro (incl. 2024-25 "AI Premium"), ultra ($249.99 legacy / 20x), ultra_5x, ai_plus,
ai_plus_2tb (2TB plan incl. AI Plus since 2026-01-27; kept, own plan id), storage, ambiguous
(NYE-promo $/EUR 99.99 one-offs only).
"""
import re

import numpy as np
import pandas as pd

PROVIDER = "gemini"

# Google One / Google Storage descriptors. ONE/STORAGE must end the token, or be glued to a known
# location / phone / URL token (bank truncation), which excludes Play developers such as
# "GOOGLE ONEMT SGP", "GOOGLE ONESOFT", "GOOGLE ONECENT TECH", "GOOGLE ONEBUTTON".
INCLUDE_RE = re.compile(
    r"GOOGLE\W*G1(?:SK|AI)|GOOGLE\W*G1 "      # SKU descriptors from 2026-09-15 (GOOGLE *G1SK002M, *G1AI101M)
    r"|GOOGLE\W*TTTTT"                       # Fable masks the SKU token as 'ttttt' (window-limited below)
    r"|GOOGLE\W*GOOGLE MOUNTAIN VIE"          # truncated generic form (user decision 2026-10-26, see report)
    r"|GOOGLE\W*(?:GOOGLE\W*)?(?:ONE|STORAGE)"
    r"(?=[^A-Z]|$|XXX|G\.?CO|MOUNTAIN|LONDON|DUBLIN|HALIFAX|INTERNET|GOOGLE|PURCHASE|SUPPORT|PAYMENT)"
)
# Account transfers that merely mention Google One in a memo.
EXCLUDE_RE = re.compile(r"^(?:TO |XFER TO|DEPOSIT)|TO LOAN|TO SHARE|TRANSFER FROM")
# Reported (not returned) exclusions: crypto exchange, Cloud/API, Workspace, Play apps named Gemini.
OTHER_EXCLUSIONS = {
    "gemini_trust_crypto": r"GEMINI ?(?:TRUST|MOONBASE|PAY|CARDPYMT)|GEMINI.{0,5}CARDPYMT|^GEMINI CARDPYMT",
    "google_cloud_api": r"GOOGLE\W*CLOUD|GOOGLE\W*GCP|AI STUDIO",
    "google_workspace": r"GSUITE|G SUITE|WORKSPACE",
    "play_apps_gemini_named": r"GOOGLE\W*GEMINI ?(?:NET|STUDIO|MAN)",
}

FABLE = {"uk", "de", "fr", "es", "it"}
REGION = {"omega": "us", "uk": "uk", "de": "eu", "fr": "eu", "es": "eu", "it": "eu"}
US_TAX_MAX = 1.115   # US list prices exclude sales tax (0-10.25% seen)
M_GAP = (25, 40)     # same-price gap read as monthly (user rule)
A_GAP = (300, 430)   # same-price gap read as annual
PENDING_DAYS = 40    # one-offs this close to the effective panel end are 'pending' (no repeat possible yet)
AI_DESCR_RE = re.compile(r"AI PREM")  # 'GOOGLE ONE AI PREMIUM' (US Apr-24..Mar-25; also UK/EU): AI-only
SKU_RE = re.compile(r"G1(SK|AI)(\d{3})([MA])?")
# Full SKU codes -> tier. Truncated codes (G1SK00, G1AI10, bare G1) fall back to amounts.
SKU_TIER = {"AI101": "ai_pro", "AI102": "ultra", "AI103": "ai_plus", "SK003": "ai_plus_2tb",
            "SK008": "ai_pro",   # 19.99 M / 199.99 A: legacy AI Premium plan
            "SK001": "storage", "SK002": "storage", "SK004": "storage", "SK005": "storage",
            "SK006": "storage", "SK007": "storage", "SK009": "storage"}
TTTTT_WINDOW = (pd.Timestamp("2026-09-01"), pd.Timestamp("2026-10-31"))

T = pd.Timestamp
NYE_PROMO = (T("2025-12-23"), T("2026-01-15"))   # AI Pro annual $99.99 / EUR 99.99 promo
ULTRA5X = T("2026-05-19")
AIPLUS = T("2026-01-27")
AIPLUS400 = T("2026-06-08")
EU_AIPLUS = T("2025-11-01")
END = T("2099-12-31")

# Rule = (price, valid_from, valid_to, monthly_tier, annual_tier, no_evidence)
#   only monthly_tier (annual None) -> always monthly; only annual -> always annual.
#   both -> monthly if a same-price neighbour 25-40d away, else annual (one-off); in the last 40
#     days a one-off is 'pending' and takes the monthly reading (or the annual one if monthly is
#     storage). no_evidence is only used as 'promo': NYE window one-offs are storage if they renew
#     a prior annual, otherwise ambiguous (AI Pro promo annual vs 2TB annual).
#   'ultra_5x' monthly at $/EUR 99.99 / GBP 79.99 is storage (20TB) if the uid already paid it
#   monthly before 2026-05-19.
RULES = {
    "us": [
        (19.99, T("2024-02-08"), END, "ai_pro", "storage", "amb"),
        (199.99, T("2025-05-20"), ULTRA5X - pd.Timedelta(days=1), None, "ai_pro", None),
        (199.99, ULTRA5X, END, "ultra", "ai_pro", "A"),
        (99.99, *NYE_PROMO, "storage", "ai_pro", "promo"),
        (99.99, AIPLUS, ULTRA5X - pd.Timedelta(days=1), "storage", "ai_plus_2tb", "A"),
        (99.99, ULTRA5X, END, "ultra_5x", "ai_plus_2tb", "A"),
        (249.99, T("2025-05-20"), T("2026-07-31"), "ultra", "storage", "amb"),
        (124.99, T("2025-05-20"), T("2026-06-30"), "ultra", None, None),            # 3-month intro
        (9.99, AIPLUS, END, "ai_plus_2tb", None, None),
        (7.99, AIPLUS, T("2026-07-31"), "ai_plus", None, None),
        (3.99, AIPLUS, END, "ai_plus", None, None),                                  # 2-month intro
        (4.99, AIPLUS400, END, "ai_plus", None, None),
        (49.99, AIPLUS400, END, "storage", "ai_plus", "A"),                          # vs 10TB monthly
    ],
    "uk": [
        (18.99, T("2024-02-08"), END, "ai_pro", None, None),
        (9.49, T("2024-02-08"), END, "ai_pro", None, None),                          # 50%-off promo
        (189.99, T("2025-05-20"), ULTRA5X - pd.Timedelta(days=1), None, "ai_pro", None),
        (189.99, ULTRA5X, END, "ultra", "ai_pro", "A"),
        (234.99, T("2025-05-20"), END, "ultra", None, None),
        (119.99, T("2025-05-20"), T("2026-06-30"), "ultra", None, None),
        (79.99, AIPLUS, ULTRA5X - pd.Timedelta(days=1), "storage", "ai_plus_2tb", "A"),
        (79.99, ULTRA5X, END, "ultra_5x", "ai_plus_2tb", "A"),
        (7.99, AIPLUS, END, "ai_plus_2tb", None, None),
        (3.49, T("2025-12-01"), END, "ai_plus", None, None),                         # UK intro seen from Dec-25
        (6.99, T("2025-12-01"), T("2026-07-31"), "ai_plus", None, None),
        (4.49, AIPLUS400, END, "ai_plus", None, None),
        (44.99, AIPLUS400, END, None, "ai_plus", None),
    ],
    "eu": [
        (21.99, T("2024-02-08"), END, "ai_pro", None, None),
        (10.99, T("2024-02-08"), END, "ai_pro", None, None),                         # 50%-off promo
        (219.99, T("2025-05-20"), ULTRA5X - pd.Timedelta(days=1), None, "ai_pro", None),
        (219.99, ULTRA5X, END, "ultra", "ai_pro", "A"),
        (274.99, T("2025-05-20"), END, "ultra", None, None),
        (139.99, T("2025-05-20"), T("2026-06-30"), "ultra", None, None),
        (99.99, *NYE_PROMO, "storage", "ai_pro", "promo"),
        (99.99, AIPLUS, ULTRA5X - pd.Timedelta(days=1), "storage", "ai_plus_2tb", "A"),
        (99.99, ULTRA5X, END, "ultra_5x", "ai_plus_2tb", "A"),
        (9.99, AIPLUS, END, "ai_plus_2tb", None, None),
        (7.99, EU_AIPLUS, T("2026-07-31"), "ai_plus", None, None),                   # DE launch seen Nov-25
        (3.99, EU_AIPLUS, END, "ai_plus", None, None),
        (6.99, EU_AIPLUS, T("2026-04-30"), "ai_pro", None, None),                    # promo, then EUR 21.99
        (79.99, AIPLUS, T("2026-07-31"), None, "ai_plus", None),
        (4.99, AIPLUS400, END, "ai_plus", None, None),
        (49.99, AIPLUS400, END, None, "ai_plus", None),
    ],
}
# Intro prices: a payment 20-45d after one of these, on a full Ultra price, counts as monthly.
ULTRA_INTRO = {"us": [124.99], "uk": [119.99], "eu": [139.99]}


def _std(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    if panel == "omega":
        amt = df["amount"].astype(float)
        out = pd.DataFrame({"uid": df["uid"].astype(str).values, "dt": pd.to_datetime(df["dt"]).values,
                            "amount": amt.abs().values, "currency": df["currency"].values,
                            "descr": df["descr"].astype(str).values})
        out["refund"] = ((df["transtype"].str.lower() == "credit") | (amt <= 0)).values
        out["lag_bad"] = False
        out["business"] = False
    else:
        so = df["spendout"].fillna(0).astype(float)
        si = df["spendin"].fillna(0).astype(float)
        out = pd.DataFrame({"uid": df["uid"].astype(str).values, "dt": pd.to_datetime(df["dt"]).values,
                            "amount": np.where(so < 0, -so, si), "currency": df["currency"].values,
                            "descr": df["descr"].astype(str).values})
        out["refund"] = ((si > 0) & (so >= 0)).values
        out["lag_bad"] = False  # report-lag filter removed (user): holes read as churn
        out["business"] = (df["usertype"] != "C").values
    return out


def provider_mask(descr: pd.Series) -> pd.Series:
    """Boolean mask of Google One / Google Storage rows (computed on unique descriptors)."""
    u = pd.Series(descr.astype(str).unique())
    up = u.str.upper()
    ok = up.str.contains(INCLUDE_RE) & ~up.str.contains(EXCLUDE_RE)
    return descr.astype(str).isin(set(u[ok]))


def _base(amount: np.ndarray, region: str) -> np.ndarray:
    prices = sorted({r[0] for r in RULES[region]})
    base = np.full(len(amount), np.nan)
    for p in prices:
        if region == "us":
            m = (amount >= p - 0.005) & (amount <= p * US_TAX_MAX + 0.005)
        else:
            m = np.abs(amount - p) <= 0.015
        base[m & np.isnan(base)] = p
    return base


def _gaps(d: pd.DataFrame, key: str) -> tuple:
    """Days to previous / next payment within the same (uid, key) group. d must be sorted."""
    same = (d["uid"].values[1:] == d["uid"].values[:-1]) & (d[key].values[1:] == d[key].values[:-1])
    days = np.diff(d["dt"].values).astype("timedelta64[D]").astype(float)
    gp = np.full(len(d), np.nan)
    gn = np.full(len(d), np.nan)
    gp[1:] = np.where(same, days, np.nan)
    gn[:-1] = np.where(same, days, np.nan)
    return gp, gn


def _effective_end(dt: pd.Series) -> pd.Timestamp:
    """Last date before the panel's trailing data hole/latency: the start of the first of the last
    10 weeks whose row count is < 75% of the median of the 8 weeks before it (else max date)."""
    w = dt.dt.to_period("W").value_counts().sort_index()
    w = w[w.index <= dt.max().to_period("W")]
    for i in range(max(8, len(w) - 10), len(w)):
        if w.iloc[i] < 0.75 * w.iloc[i - 8:i].median():
            return w.index[i].start_time - pd.Timedelta(days=1)
    return dt.max()


def classify(df: pd.DataFrame, panel: str, include_storage: bool = False) -> pd.DataFrame:
    region = REGION[panel]
    d = df.loc[provider_mask(df["descr"])]
    d = _std(d, panel)
    if panel == "omega":
        d = d[d["currency"] == "USD"]
    tt = d["descr"].str.upper().str.contains("TTTTT")
    d = d[~tt | ((d["dt"] >= TTTTT_WINDOW[0]) & (d["dt"] <= TTTTT_WINDOW[1]))]
    d = d.reset_index(drop=True)
    panel_end = _effective_end(d["dt"])  # e.g. ~2026-09-16 in the Oct-26 extracts (hole after)

    d["base"] = _base(d["amount"].values, region)
    d["reason"] = "ok"
    d.loc[d["business"], "reason"] = "business_user"
    d.loc[d["amount"] <= 1.0, "reason"] = "zero_or_auth"
    d.loc[d["refund"], "reason"] = "refund_or_credit"
    d = d.sort_values(["uid", "dt", "amount"], kind="mergesort").reset_index(drop=True)
    dup = d.duplicated(["uid", "dt", "amount"]) & (d["reason"] == "ok")
    d.loc[dup, "reason"] = "duplicate"

    # Rule lookup
    rcols = ["mt", "at", "ne"]
    for c in rcols:
        d[c] = None
    d["rule"] = -1
    for i, (p, lo, hi, mt, at, ne) in enumerate(RULES[region]):
        m = (d["base"] == p) & (d["dt"] >= lo) & (d["dt"] <= hi) & (d["rule"] < 0)
        d.loc[m, "rule"] = i
        d.loc[m, "mt"], d.loc[m, "at"], d.loc[m, "ne"] = mt, at, ne
    # Cadence evidence from the uid's own same-price valid payments (all dates, so that e.g. a 2024
    # $19.99 renewal sees its 2023 predecessor even though 2023 $19.99 is not a candidate).
    v = d[d["base"].notna() & (d["reason"] == "ok")].sort_values(["uid", "base", "dt"], kind="mergesort")
    gp, gn = _gaps(v, "base")
    isM = lambda g: (g >= M_GAP[0]) & (g <= M_GAP[1])
    isA = lambda g: (g >= A_GAP[0]) & (g <= A_GAP[1])
    ev = pd.Series(np.where(isM(gp) | isM(gn), "M", np.where(isA(gp) | isA(gn), "A", "")), index=v.index)
    prevA = pd.Series(isA(gp), index=v.index)
    # Ultra intro lead-in: previous valid payment (any price) 20-45d earlier at an intro price.
    w = d[d["base"].notna() & (d["reason"] == "ok")].sort_values(["uid", "dt"], kind="mergesort")
    same_uid = np.r_[False, w["uid"].values[1:] == w["uid"].values[:-1]]
    pdays = np.r_[np.nan, np.diff(w["dt"].values).astype("timedelta64[D]").astype(float)]
    pbase = np.r_[np.nan, w["base"].values[:-1]]
    lead = same_uid & (pdays >= 20) & (pdays <= 45) & np.isin(pbase, ULTRA_INTRO[region])
    lead = pd.Series(lead, index=w.index)
    d["ev"] = ev.reindex(d.index).fillna("")
    d.loc[lead[lead].index.intersection(d.index), "ev"] = d.loc[lead[lead].index, "ev"].replace("", "M")
    d["prevA"] = prevA.reindex(d.index).fillna(False).astype(bool)
    # Legacy 20TB monthly at the Ultra 5x price: uid paid it monthly before 2026-05-19.
    p5 = {"us": 99.99, "eu": 99.99, "uk": 79.99}[region]
    legacy = d[(d["base"] == p5) & (d["ev"] == "M") & (d["dt"] < ULTRA5X)]["uid"].unique()
    sku = d["descr"].str.upper().str.extract(SKU_RE)
    key = sku[0] + sku[1]
    d["sku_tier"] = key.map(SKU_TIER)
    d["sku_cad"] = sku[2]
    if not include_storage:
        # SKU-coded AI rows are candidates even at promo/intro amounts outside the rule bands.
        d = d[(d["rule"] >= 0) | (d["sku_tier"].notna() & (d["sku_tier"] != "storage"))].reset_index(drop=True)

    mt, at, ne, ev_ = d["mt"], d["at"], d["ne"], d["ev"]
    recent = d["dt"] > panel_end - pd.Timedelta(days=PENDING_DAYS)
    norule = d["rule"] < 0
    only_m, only_a = at.isna() & mt.notna(), mt.isna() & at.notna()
    both = mt.notna() & at.notna()
    promo = both & (ne == "promo") & (ev_ != "M")
    # Recent one-offs: an annual renewal (same price 300-430d earlier) is annual, not pending.
    pend = both & ~promo & (ev_ != "M") & recent & ~d["prevA"]
    # Pending default = monthly reading (e.g. $19.99 -> ai_pro_M), except where monthly is storage or
    # the rare Ultra 5x vs the common 2TB annual ($/EUR 99.99, GBP 79.99) -> annual reading.
    to_a = mt.isin(["storage", "ultra_5x"])
    pend_tier = np.where(to_a, at, mt)
    pend_cad = np.where(to_a, "A", "M")
    conds = [norule, only_m, only_a, both & (ev_ == "M") & (ne == "promo"), both & (ev_ == "M"),
             promo & d["prevA"], promo, pend, both]
    tier = np.select(conds, ["storage", mt, at, "storage", mt, "storage", "ambiguous", pend_tier, at], "ambiguous")
    cad = np.select(conds, [None, "M", "A", "M", "M", "A", None, pend_cad, "A"], None)
    # AI-only descriptor ('GOOGLE ONE AI PREMIUM') overrides a storage reading.
    aid = d["descr"].str.upper().str.contains(AI_DESCR_RE) & d["base"].notna()
    tier = np.where(aid, "ai_pro", tier)
    cad = np.where(aid, np.where(only_a, "A", "M"), cad)
    amb_reason = np.where(tier == "ambiguous", "ambiguous_ai_pro_promo_A_vs_2tb_A", None)
    st, sc = d["sku_tier"], d["sku_cad"]
    has_sku = st.notna()
    tier = np.where(has_sku, st, tier)
    cad = np.where(has_sku, sc.fillna(pd.Series(cad, index=d.index)).fillna("M"), cad)
    d["pending"] = pend.values & ~aid.values & ~has_sku.values
    d["pend1999"] = d["pending"] & (d["base"] == 19.99) & (mt == "ai_pro")
    d["tier"], d["cadence"] = tier, cad
    leg = (d["tier"] == "ultra_5x") & d["uid"].isin(legacy)
    d.loc[leg, "tier"] = "storage"

    d["plan"] = np.where(d["cadence"].notna(), d["tier"].astype(str) + "_" + d["cadence"].fillna(""),
                         d["tier"].astype(str))
    ok = d["reason"] == "ok"
    d.loc[ok & (d["tier"] == "storage"), "reason"] = "storage_tier"
    d.loc[ok & leg, "reason"] = "storage_tier_20tb_legacy"
    am = ok & (d["tier"] == "ambiguous")
    d.loc[am, "reason"] = pd.Series(amb_reason, index=d.index)[am]
    d.loc[ok & d["pend1999"], ["tier", "cadence", "plan"]] = ["ambiguous", None, "ambiguous"]
    d.loc[ok & d["pend1999"], "reason"] = "pending_19_99"
    d.loc[ok & d["pending"] & ~d["pend1999"] & (d["tier"] != "storage"), "reason"] = "pending_provisional"
    d.loc[d["tier"] == "ambiguous", ["cadence"]] = None
    d["keep"] = d["reason"].isin(["ok", "pending_provisional"])
    d["provider"] = PROVIDER
    d["channel"] = "web"
    return d[["uid", "dt", "amount", "currency", "descr", "provider", "tier", "cadence", "plan",
              "channel", "keep", "reason"]].reset_index(drop=True)
