"""Cursor (Anysphere) consumer web-subscription filter for card panels.

classify(df, panel) -> one row per Cursor-branded candidate payment with plan, keep flag and reason.
Cursor bills in USD everywhere; European amounts are FX-converted (and VAT-inclusive from ~2026-03),
so European rows are converted back to gross USD with a monthly rate estimated from the Pro cluster.
"""
import re

import numpy as np
import pandas as pd

PROVIDER = "cursor"
MON = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"

# Cursor-branded rows (lowercased descriptor). Order of tests: usage -> bnpl -> subscription.
USAGE_RE = re.compile(rf"cursor usage|cursor usag\b|cursor,? (?:mid )?(?:{MON})\b|cursor mid\b")
BNPL_RE = re.compile(r"klarna\s?\*\s?cursor")
SUB_RE = re.compile(
    r"cursor,? ?ai ?power"        # CURSOR, AI POWERED IDE (+ truncations / bank wrappers)
    r"|cursor, ai\b|cursor, power|cursor usa\b"
    r"|cursor\.com|cursorcom|httpscursor|cursor\.so\b|^cursor usd\b"
    r"|^cursor$"                  # UK: bare 'cursor' (mcc 5734 / 0, Pro-sized amounts)
    r"|pwp cursor"                # privacy.com virtual card
    r"|zilch \* cursor, a"
)

# Net (ex-tax) USD list prices.
PRO_M, PRO_A, PROPLUS_M, ULTRA_M, TEAM_SEAT = 20.0, 192.0, 60.0, 200.0, 40.0
ULTRA_LAUNCH = pd.Timestamp("2025-06-16")
PROPLUS_LAUNCH = pd.Timestamp("2025-07-01")
PROMO_START = pd.Timestamp("2026-03-01")  # one-off $10 (50% off first Pro month); ~half followed by $20 Pro

FABLE_PANELS = {"uk": "GBP", "de": "EUR", "fr": "EUR", "es": "EUR", "it": "EUR"}
VAT = {"uk": 1.20, "de": 1.19, "fr": 1.20, "es": 1.21, "it": 1.22}
ROUGH_FX = {"GBP": 0.78, "EUR": 0.90}  # local per USD, only used to seed the cluster search
FEE_HI = {"fr": 1.13}  # FR banks fold FX commission (~5-13%) into the amount; others ~3%
US_TAX_MAX = 1.15  # sales tax up to ~11%; Canadian HST 13-15% cards also seen ($23.00)


def _std(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    if panel == "omega":
        out = pd.DataFrame({
            "uid": df["uid"].astype(str),
            "dt": pd.to_datetime(df["dt"]),
            "amount": df["amount"].astype(float),
            "currency": df["currency"],
            "descr": df["descr"],
        })
        out["refund"] = (df["transtype"].str.lower() == "credit").values | (out["amount"] <= 0).values
        out["amount"] = out["amount"].abs()
        out["business"] = False
    else:
        so = df["spendout"].fillna(0).astype(float)
        si = df["spendin"].fillna(0).astype(float)
        out = pd.DataFrame({
            "uid": df["uid"].astype(str),
            "dt": pd.to_datetime(df["dt"]),
            "amount": np.where(so < 0, -so, si),
            "currency": df["currency"],
            "descr": df["descr"],
        })
        out["refund"] = ((si > 0) & (so >= 0)).values
        # No reportdate-vs-dt filter: late-reported payments are kept (dropping them punched holes read as churn).
        out["business"] = (df["usertype"] != "C").values
    return out.reset_index(drop=True)


def _brand(descr: pd.Series) -> pd.Series:
    low = descr.fillna("").str.lower().str.replace("\\", "", regex=False).str.strip()  # FR escapes commas: "cursor\, ai"
    kind = np.where(low.str.contains(SUB_RE), "sub", "none")
    kind = np.where(low.str.contains(BNPL_RE), "bnpl", kind)
    kind = np.where(low.str.contains(USAGE_RE), "usage", kind)
    return pd.Series(kind, index=descr.index)


def _monthly_rate(d: pd.DataFrame, panel: str) -> pd.Series:
    """Local currency per USD by month, from the Pro $20 (net) and $20*VAT (gross) clusters."""
    rough = ROUGH_FX[FABLE_PANELS[panel]]
    vat = VAT[panel]
    x = d["amount"] / rough
    m = d["dt"].dt.to_period("M")
    net = d[x.between(17.5, 22.2)].assign(r=lambda t: t["amount"] / PRO_M)
    gross = d[x.between(17.5 * vat, 22.2 * vat) & ~x.between(17.5, 22.2)].assign(
        r=lambda t: t["amount"] / (PRO_M * vat))
    both = pd.concat([net, gross])
    rate = both.groupby(both["dt"].dt.to_period("M"))["r"].median()
    cnt = both.groupby(both["dt"].dt.to_period("M")).size()
    rate = rate[cnt >= 5]
    allm = pd.period_range(m.min(), m.max(), freq="M")
    rate = rate.reindex(allm).interpolate().ffill().bfill().fillna(rough)
    return rate


def classify(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    panel = panel.lower()
    us = panel == "omega"
    d = _std(df, panel)
    d["kind"] = _brand(d["descr"])
    d = d[d["kind"] != "none"].copy()
    if us:
        d = d[d["currency"] == "USD"]
    d["provider"] = PROVIDER
    d["tier"], d["cadence"], d["plan"] = None, None, None
    d["channel"] = np.where(d["kind"] == "bnpl", "other", "web")
    d["keep"] = False
    d["reason"] = "ok"

    vatf = 1.0 if us else VAT[panel]
    if us:
        d["usd"] = d["amount"]
    else:
        rate = _monthly_rate(d[(d["kind"] == "sub") & ~d["refund"]], panel)
        d["usd"] = d["amount"] / d["dt"].dt.to_period("M").map(rate).astype(float).fillna(ROUGH_FX[FABLE_PANELS[panel]])

    # --- rejections in priority order
    for mask, why in [(d["refund"], "refund"), (d["kind"] == "usage", "usage"), (d["kind"] == "bnpl", "bnpl"),
                      (d["business"], "business_user"), (d["usd"] < 1.6, "auth")]:
        d.loc[(d["reason"] == "ok") & mask, "reason"] = why
    d = d.sort_values(["uid", "dt", "amount"], kind="mergesort")
    dup = d.duplicated(["uid", "dt", "amount", "kind"]) & (d["reason"] == "ok")
    d.loc[dup, "reason"] = "duplicate"

    # --- amount bands (gross USD)
    u = d["usd"]
    if us:
        def band(p, lo=0.995, hi=US_TAX_MAX):
            return u.between(p * lo, p * hi + 0.01)
        pro, proplus, team = band(PRO_M), band(PROPLUS_M), band(TEAM_SEAT)
        team_mult = band(2 * TEAM_SEAT) | band(3 * TEAM_SEAT) | band(384.0)
        hi_zone = u.between(PRO_A * 0.995, ULTRA_M * US_TAX_MAX + 0.01)
    else:
        fee_hi = FEE_HI.get(panel, 1.075)

        def band(p, lo=0.95, hi=fee_hi):
            return u.between(p * lo, p * hi) | u.between(p * lo * vatf, p * hi * vatf)
        pro, proplus, team = band(PRO_M), band(PROPLUS_M), band(TEAM_SEAT)
        team_mult = band(2 * TEAM_SEAT) | band(3 * TEAM_SEAT) | band(384.0)
        hi_zone = band(PRO_A, 0.93) | band(ULTRA_M, 0.93)

    ok = d["reason"] == "ok"

    def setp(mask, tier, cad):
        d.loc[mask, ["tier", "cadence"]] = [tier, cad]
        d.loc[mask, "plan"] = f"{tier}_{cad}"

    setp(ok & pro, "pro", "M")
    setp(ok & band(PRO_M / 2) & (d["dt"] >= PROMO_START) & d["plan"].isna(), "pro", "M")  # promo month
    setp(ok & proplus & (d["dt"] >= PROPLUS_LAUNCH), "proplus", "M")
    d.loc[ok & team & d["plan"].isna(), "reason"] = "team_amount"
    d.loc[ok & team_mult & d["plan"].isna() & ~hi_zone, "reason"] = "team_amount"

    # Pro annual ($192) vs Ultra ($200): resolve by the uid's own gap between hi-zone payments.
    hz = d[ok & hi_zone & d["plan"].isna()].copy()
    if len(hz):
        hz = hz.sort_values(["uid", "dt"])
        g_prev = hz.groupby("uid")["dt"].diff().dt.days
        g_next = -hz.groupby("uid")["dt"].diff(-1).dt.days
        gaps = pd.concat([g_prev, g_next], axis=1)
        monthly = gaps.apply(lambda c: c.between(20, 45)).any(axis=1)
        annual = gaps.apply(lambda c: c.between(300, 430)).any(axis=1)
        net = hz["usd"] / np.where(hz["usd"] > ULTRA_M * 1.12, vatf, 1.0)  # strip VAT for Fable gross amounts
        pre_ultra = hz["dt"] < ULTRA_LAUNCH
        if us:
            near_pro = hz["usd"] < ULTRA_M - 0.005               # 192.00-199.99: only Pro A (taxed)
            # above $213.12 (= $192 + 11% tax) or exactly $200.00 (untaxed Ultra)
            near_ultra = (hz["usd"] > PRO_A * 1.11 + 0.01) | (hz["usd"].round(2) == ULTRA_M)
        else:
            near_pro = net < (PRO_A + ULTRA_M) / 2
            near_ultra = ~near_pro
        tier = pd.Series(None, index=hz.index, dtype=object)
        for mask, t in [(pre_ultra, "pro_A"), (monthly, "ultra_M"), (annual, "pro_A"), (near_pro, "pro_A"),
                        (near_ultra, "ultra_M")]:
            tier = tier.mask(tier.isna() & mask, t)
        for t, (tr, cad) in {"pro_A": ("pro", "A"), "ultra_M": ("ultra", "M")}.items():
            setp(d.index.isin(tier[tier == t].index), tr, cad)
        d.loc[tier[tier.isna()].index, "reason"] = "ambiguous"

    d.loc[(d["reason"] == "ok") & d["plan"].isna(), "reason"] = "unclassified_amount"
    d["keep"] = (d["reason"] == "ok") & d["plan"].notna()

    cols = ["uid", "dt", "amount", "currency", "descr", "provider", "tier", "cadence", "plan", "channel", "keep",
            "reason"]
    return d[cols].sort_values(["uid", "dt"], kind="mergesort").reset_index(drop=True)
