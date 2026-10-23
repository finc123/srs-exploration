"""Perplexity consumer subscription filter (web + Google Play) for card panels (omega US + Fable uk/de/fr/es/it).

classify(df, panel) -> one row per candidate Perplexity payment with plan label and keep flag.

Plans (USD list, billed in USD everywhere; EU/UK add VAT on top from ~Aug 2024 (EU) / ~Oct 2025 (UK)):
  pro_M      $20/mo                       (also $10 promo months: referral credit / 50% retention offer)
  pro_A      $200/yr
  max_M      $200/mo   (from 2025-07-02; collides with pro_A -> descriptor word / uid payment gaps)
  max_A      $2,000/yr (from 2025-07-02)
  pro_disc_M  $4.99/mo  discounted Pro billed under the "Pro" product (Nov-2024 one-month intro offer; 2026Q1
                        multi-month cohort, median 4 payments; possibly education). Also sustained $10 payers
                        (>=4 payments at $10, never $20).
Kept channels: web (incl. PayPal-funded) and Google Play ("GOOGLE *PERPLEXITY ...", same price points: $19.99,
$199.99 + tax). Excluded: Samsung Galaxy Store / Apple, Enterprise Pro/Max seats (ENT descriptors, $40/$325 multiples),
API credits ("CREDITS", "API CREDIT", exact US $5.00 and $5/$10 top-ups within 20 days), "Computer" usage credits,
merch store (PROSHOP / "Perplexity Supply"), name collisions (Tour Perplexity Games, PerplexAI Limassol, ...),
payroll/ACH credits, refunds, <=$1.5 auths, Fable business users, same uid+day+amount duplicates.

Descriptor note: from ~2026-06-08 to ~2026-10-04 Perplexity's Stripe descriptor dropped the brand ("PRO WWW.PERPLEXIT
CA", "PRO SAN FRANCISCO CA", Fable "pro", "cb pro", "compra pro, san francisco, ..."), then came back as "PERPLEXITY PRO"
from ~2026-10-05. The keyword prefilter (%perplexity%) misses the brandless rows. classify() recognises them (token
residual == product word, dt >= 2026-06-01, non-round GBP/EUR amount, uid with branded Perplexity history or MCC
5815/5734) if they are present in df, i.e. once the extract is widened.
"""
import re
import numpy as np
import pandas as pd

PROVIDER = "perplexity"

# USD per local unit, monthly (card-scheme rates). GBP: median "vrate/@ rate" quoted in UK descriptors (all AI rows).
# EUR: implied from the DE/FR Perplexity Pro cluster ($20, or $23.80/$24.00 incl. VAT from 2024-08); 2026-07..10
# thin -> filled from the few rows available. Tolerance bands absorb +/-3% error and bank FX fees.
_GBP = {
    "2023-01": 1.213, "2023-02": 1.204, "2023-03": 1.210, "2023-04": 1.239, "2023-05": 1.244, "2023-06": 1.259,
    "2023-07": 1.281, "2023-08": 1.268, "2023-09": 1.243, "2023-10": 1.212, "2023-11": 1.227, "2023-12": 1.261,
    "2024-01": 1.267, "2024-02": 1.260, "2024-03": 1.268, "2024-04": 1.245, "2024-05": 1.253, "2024-06": 1.268,
    "2024-07": 1.285, "2024-08": 1.281, "2024-09": 1.312, "2024-10": 1.302, "2024-11": 1.262, "2024-12": 1.261,
    "2025-01": 1.232, "2025-02": 1.246, "2025-03": 1.287, "2025-04": 1.306, "2025-05": 1.326, "2025-06": 1.350,
    "2025-07": 1.348, "2025-08": 1.340, "2025-09": 1.346, "2025-10": 1.336, "2025-11": 1.309, "2025-12": 1.334,
    "2026-01": 1.341, "2026-02": 1.358, "2026-03": 1.330, "2026-04": 1.344, "2026-05": 1.345, "2026-06": 1.333,
    "2026-07": 1.333, "2026-08": 1.348, "2026-09": 1.348, "2026-10": 1.319,
}
_EUR = {
    "2023-01": 1.080, "2023-02": 1.070, "2023-03": 1.070, "2023-04": 1.095, "2023-05": 1.085, "2023-06": 1.081,
    "2023-07": 1.105, "2023-08": 1.090, "2023-09": 1.067, "2023-10": 1.050, "2023-11": 1.090, "2023-12": 1.096,
    "2024-01": 1.093, "2024-02": 1.078, "2024-03": 1.087, "2024-04": 1.067, "2024-05": 1.081, "2024-06": 1.070,
    "2024-07": 1.084, "2024-08": 1.101, "2024-09": 1.109, "2024-10": 1.082, "2024-11": 1.053, "2024-12": 1.048,
    "2025-01": 1.026, "2025-02": 1.035, "2025-03": 1.079, "2025-04": 1.132, "2025-05": 1.125, "2025-06": 1.143,
    "2025-07": 1.171, "2025-08": 1.163, "2025-09": 1.171, "2025-10": 1.157, "2025-11": 1.155, "2025-12": 1.165,
    "2026-01": 1.166, "2026-02": 1.177, "2026-03": 1.152, "2026-04": 1.166, "2026-05": 1.166, "2026-06": 1.157,
    "2026-07": 1.159, "2026-08": 1.159, "2026-09": 1.140, "2026-10": 1.114,
}
VAT = {"omega": 0.0, "uk": 0.20, "de": 0.19, "fr": 0.20, "es": 0.21, "it": 0.22}
MAX_LAUNCH = pd.Timestamp("2025-07-02")
BRANDLESS_FROM = pd.Timestamp("2026-06-01")

# ---- descriptor regexes (applied to UPPERCASE, whitespace-collapsed descriptor) ----
INCLUDE = re.compile(r"PERPLEX")     # branded rows; brandless rows are detected by _residual() below
COLLISION = re.compile(
    r"TOUR\*? ?PERPLEXITY|PERPLEXITY GAMES|PERPLEXITYG|HIGHPERPLEX|MYCRUSH|PERPLEXITY SUP|SUPPLY|"
    r"PROSH|PROS HOP|PERPLEXAI|PERPLEXT|PERPLEXING|PERPLEXED|SUPERPLEX|PERPLEXCITY|PERPLEXODUS|PERPLEXHEAL|"
    r"PAYROLL|ACH CREDIT|OUTGOING WIRE|WEFUNDER|BAL ADJ")
GOOGLE = re.compile(r"GOOGLE")
OTHER_STORE = re.compile(r"SAMSUNG|APPLE\.COM|APPLE COM")
ENT = re.compile(r"\bENT (?:PRO|MAX)\b|PERPLEXITY ENT")
API = re.compile(r"CREDITS|\bAPI\b")
COMPUTER = re.compile(r"\bCOMPUTER\b")

# Brandless descriptors (2026-06-08 .. 2026-10-04): strip bank/processor noise tokens, numbers and the
# "WWW.PERPLEXIT" city field; what remains must be exactly a Perplexity product word.
_NOISE = set("""CB DU USD EUR EURO EUROS CARTE NO USA US SAN FRANCISCO FRANCISC FRANCIS FRANCI FRANCIS FRA CA CAUS
INT'L VISA PURCHASE CARD PAYMENT TO AT COMPRA EN PAGO TARJETA TARJ TARJ. CON LA ETATS UNIS D'AME D'AMERIQUE COM CHA
RATE VRATE MAS N-S TRN FEE PURCH WITHDRAWAL DC RECURRING PYMT REF MERCHANT CATEGORY CODE CHECK POINT OF SALE DEBIT
ORIGINE LE TJ OP.TARJ.COMPRA COMERCIO CO COMISION APPLE PAY EL COMISIÓN N/A - . @ * D M""".split())
_PRODUCT = {"PRO": "pro", "PRO*": "pro", "PRO* TRIAL OVER": "pro", "PRO*TRIAL OVER": "pro", "PRO TRIAL OVER": "pro",
            "PRO* TRIAL": "pro", "MAX": "max", "ENT PRO": "ent", "ENT MAX": "ent", "CREDITS": "api",
            "API CREDIT": "api", "API": "api", "COMPUTER": "computer"}


def _residual(D: str, strict: bool = False) -> str:
    toks = [t.strip(".,:;") for t in re.split(r"[\s;:/()]+|,(?!\d)", D)]
    keep, prev = [], ""
    for t in toks:
        drop = (not t or t in _NOISE or "PERPLEX" in t or "#" in t
                or (re.fullmatch(r"[\d.,*+-]+(?:VRATE|MAS|N-S|VISA)?", t) is not None   # amounts, rates, ids
                    and (not strict or len(t) >= 4 or re.search(r"[.,]", t) is not None))
                or (t == "<NAME>" and prev == "SAN"))                                # masked "San Francisco"
        if not drop:
            keep.append(t)
        prev = t
    return " ".join(keep)


def _norm(panel: str, df: pd.DataFrame) -> pd.DataFrame:
    if panel == "omega":
        d = pd.DataFrame({
            "uid": df["uid"], "dt": pd.to_datetime(df["dt"]), "descr": df["descr"].fillna(""),
            "currency": df["currency"], "amount": pd.to_numeric(df["amount"], errors="coerce").astype(float),
            "is_credit": df["transtype"].str.lower().ne("debit"), "usertype": "C", "mcc": "",
        })
    else:
        so = pd.to_numeric(df["spendout"], errors="coerce").fillna(0.0)
        si = pd.to_numeric(df["spendin"], errors="coerce").fillna(0.0)
        dt = pd.to_datetime(df["dt"])
        d = pd.DataFrame({
            "uid": df["uid"], "dt": dt, "descr": df["descr"].fillna(""), "currency": df["currency"],
            "amount": np.where(so < 0, -so, si), "is_credit": (si > 0) | (so >= 0),
            "usertype": df["usertype"], "mcc": df["mcc"].astype(str) if "mcc" in df else "",
        })
    d["D"] = d["descr"].str.upper().str.replace(r"\s+", " ", regex=True).str.strip()
    return d


def _fx(panel: str, d: pd.DataFrame) -> pd.Series:
    if panel == "omega":
        return pd.Series(1.0, index=d.index)
    tbl = _GBP if panel == "uk" else _EUR
    ym = d["dt"].dt.strftime("%Y-%m")
    last = max(tbl)
    return ym.map(lambda m: tbl.get(m, tbl[last] if m > last else tbl[min(tbl)]))


def _band(usd: float, base: float, panel: str) -> bool:
    """usd-equivalent amount matches list `base` (incl. US sales tax or EU/UK VAT, plus FX tolerance)."""
    if panel == "omega":
        return base * 0.985 <= usd <= base * 1.115
    for mult in (1.0, 1.0 + VAT[panel]):
        if base * mult * 0.92 <= usd <= base * mult * 1.10:
            return True
    return False


def _amount_class(usd: float, panel: str) -> str:
    for base, lab in ((4.99, "p5"), (10.0, "p10"), (20.0, "p20"), (200.0, "p200"), (2000.0, "p2000")):
        if _band(usd, base, panel):
            return lab
    return "none"


def classify(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    panel = panel.lower()
    d = _norm(panel, df)
    branded = d["D"].str.contains(INCLUDE)
    resid = pd.Series([_residual(x, strict=not b) for x, b in zip(d["D"], branded)], index=d.index)
    d["prod"] = resid.map(_PRODUCT).fillna("")
    brandless = ~branded & d["prod"].ne("") & (d["dt"] >= BRANDLESS_FROM)
    hist = set(d.loc[branded & ~d["D"].str.contains(COLLISION), "uid"])
    cand = (branded | brandless) & ~d["D"].str.contains(COLLISION)
    d = d[cand].copy()
    d["brandless"] = brandless[cand]
    # bare Fable "max"/"pro" (no suffix) also used by other merchants (e.g. HBO Max at GBP 17): require an amount match
    d["bare"] = d["brandless"] & d["D"].str.fullmatch(r"(?:CB )?(?:PRO|MAX)")
    d["provider"] = PROVIDER
    d["channel"] = np.select([d["D"].str.contains(GOOGLE), d["D"].str.contains(OTHER_STORE)],
                             ["google_play", "other"], "web")
    d["usd"] = d["amount"] * _fx(panel, d)
    d["aclass"] = [_amount_class(u, panel) for u in d["usd"]]

    reason = pd.Series("ok", index=d.index, dtype=object)

    def rej(mask, why):
        reason[(reason == "ok") & mask] = why

    rej(d["currency"].ne("USD") if panel == "omega" else d["currency"].isin(["GBP", "EUR"]).eq(False), "currency")
    rej(d["is_credit"], "refund_credit")
    rej(d["usertype"].ne("C"), "business_user")
    # (no reportdate-vs-dt lag filter: per user decision, late-reported rows are kept)
    rej(d["usd"] <= 1.5, "auth_small")
    # Google Play billing is kept (user decision); Samsung Galaxy Store / Apple are excluded
    rej(d["channel"].eq("other"), "other_store")
    rej(d["D"].str.contains(ENT) | d["prod"].eq("ent"), "enterprise")
    rej((d["D"].str.contains(API) & d["prod"].ne("pro")) | d["prod"].eq("api"), "api_credits")
    rej(d["D"].str.contains(COMPUTER) | d["prod"].eq("computer"), "usage_computer")
    rej(d["bare"] & d["aclass"].eq("none"), "bare_descr_no_amount_match")
    # brandless MAX descriptors (FR "cb du max" = HBO Max etc.) only count at Max amounts
    bl_max = d["brandless"] & d["prod"].eq("max")
    rej(bl_max & ~d["aclass"].isin(["p200", "p2000"]), "brandless_max_low_amount")
    # brandless descriptors ("PRO", "CB PRO", "PRO SAN FRANCISCO CA", ...) are only considered from 2026-06-01 (see
    # BRANDLESS_FROM); earlier the same words belong to other merchants (e.g. FR "pro", ~200-300 rows/month in 2026H1)
    # EU/UK Perplexity charges are USD converted -> never round in GBP/EUR; round brandless amounts are other merchants
    if panel != "omega":
        rej(d["brandless"] & (d["amount"] * 100).round().mod(100).eq(0), "brandless_round_amount")
    # brandless rows need a uid with branded Perplexity payments (any date) or a Perplexity MCC: in Jan-May 2026 the
    # same descriptor forms matched ~30-115 payers/month in FR/IT, none of whom ever paid a branded Perplexity charge
    rej(d["brandless"] & ~d["uid"].isin(hist) & ~d["mcc"].isin(["5815", "5734"]), "brandless_no_history")
    # de-duplicate pending/posted repeats: same uid + day + amount (keep first)
    dup = d.duplicated(["uid", "dt", "amount"]) & reason.eq("ok")
    rej(dup, "duplicate")
    # Enterprise seat amounts on a generic descriptor ($40 multiples / $325) - non-consumer
    seat = [any(_band(u / k, 40.0, panel) for k in range(1, 11)) or _band(u, 325.0, panel) or _band(u, 400.0, panel)
            for u in d["usd"]]
    rej(pd.Series(seat, index=d.index) & d["aclass"].eq("none"), "enterprise_amount")
    rej(d["aclass"].eq("none"), "unmatched_amount")
    # $5/$10 credit top-ups on the generic descriptor: exact US $5.00, or a second $5/$10-band charge within 20 days
    # (the $4.99 subscription recurs every ~30 days; credit top-ups cluster within a week)
    if panel == "omega":
        rej(d["amount"].round(2).eq(5.0), "credits_amount")
    sm = d[reason.eq("ok") & d["aclass"].isin(["p5", "p10"])].sort_values(["uid", "dt"])
    gp = sm.groupby("uid")["dt"].diff().dt.days
    gn = sm.groupby("uid")["dt"].diff(-1).dt.days.abs()
    rej(pd.Series(((gp <= 20) | (gn <= 20)).reindex(d.index, fill_value=False), index=d.index), "credits_amount")

    # ---- plan assignment ----
    tier = pd.Series(None, index=d.index, dtype=object)
    cad = pd.Series(None, index=d.index, dtype=object)
    word_max = d["prod"].eq("max")
    word_pro = d["prod"].eq("pro")
    a = d["aclass"]
    tier[a.eq("p20")] = "pro"; cad[a.eq("p20")] = "M"
    tier[a.eq("p10")] = "pro"; cad[a.eq("p10")] = "M"          # referral / retention 50% months
    tier[a.eq("p5")] = "pro_disc"; cad[a.eq("p5")] = "M"
    tier[a.eq("p2000")] = "max"; cad[a.eq("p2000")] = "A"

    # sustained $10 payers (>=4 payments in the band, never $20) -> discounted Pro rather than a promo month
    ok = reason.eq("ok")
    p10 = d[ok & a.eq("p10")].groupby("uid").size()
    p20u = set(d.loc[ok & a.eq("p20"), "uid"])
    disc10 = set(p10[p10 >= 4].index) - p20u
    m10 = a.eq("p10") & d["uid"].isin(disc10)
    tier[m10] = "pro_disc"

    # $200 band: Pro annual vs Max monthly
    m200 = a.eq("p200")
    tier[m200 & word_max] = "max"; cad[m200 & word_max] = "M"
    tier[m200 & word_pro & ~word_max] = "pro"; cad[m200 & word_pro & ~word_max] = "A"
    pre = m200 & (d["dt"] < MAX_LAUNCH) & tier.isna()
    tier[pre] = "pro"; cad[pre] = "A"
    rest = m200 & tier.isna()
    if rest.any():
        last_dt = d["dt"].max()
        s = d[m200 & ok].sort_values(["uid", "dt"])
        gaps = s.groupby("uid")["dt"].diff().dt.days
        nxt = s.groupby("uid")["dt"].diff(-1).dt.days.abs()
        g_uid = pd.concat([gaps, nxt], axis=1).min(axis=1).groupby(s["uid"]).agg(list)
        for i in d.index[rest]:
            u, t = d.at[i, "uid"], d.at[i, "dt"]
            gl = [g for g in g_uid.get(u, []) if pd.notna(g)]
            if any(24 <= g <= 45 for g in gl):
                tier[i], cad[i] = "max", "M"
            elif any(330 <= g <= 400 for g in gl):
                tier[i], cad[i] = "pro", "A"
            elif (last_dt - t).days >= 75:      # no repeat within the following 75 days -> annual
                tier[i], cad[i] = "pro", "A"
            else:
                tier[i], cad[i] = "ambiguous", None
                rej(pd.Series(d.index == i, index=d.index), "ambiguous")

    plan = (tier.fillna("none") + "_" + cad.fillna("X")).where(tier.notna(), None)
    plan[tier.eq("ambiguous")] = "ambiguous"
    out = pd.DataFrame({
        "uid": d["uid"], "dt": d["dt"], "amount": d["amount"].round(2), "currency": d["currency"],
        "descr": d["descr"], "provider": PROVIDER, "tier": tier, "cadence": cad, "plan": plan,
        "channel": d["channel"], "keep": reason.eq("ok") & tier.notna() & tier.ne("ambiguous"), "reason": reason,
        "usd_eq": d["usd"].round(2),
    })
    return out.sort_values(["uid", "dt"]).reset_index(drop=True)
