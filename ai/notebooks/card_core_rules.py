"""Engine for card_gross_adds.ipynb: AI subscription payments, TR30 subscribers and gross adds on the Omega 2022 panel.

Source: EARNEST.COMMON.TXNS_CORE_V for the five brands, plus unbranded rows from the Omega share by descriptor
(ChatGPT web and Play, Muse web and Play, Claude and Perplexity Play, Perplexity's brandless Jun-Oct 2026 descriptor,
Google One's SKU-code descriptors from 2026-09-15: their merchids have no main brand, so TXNS_CORE never picks them up). Same row logic as TXNS_CORE:
2022 consistent-shopper panel, affected accounts excluded.

pull()      -> .cache/card_core/raw.parquet (one row per transid) and panel.parquet (member count, weight sum)
classify()  -> one row per candidate payment with family, plan, keep
daily()     -> daily subscriber payments, TR30 subscribers and gross adds by provider / plan
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).resolve().parent.parent / ".cache" / "card_core"
PLANS = Path(__file__).resolve().parent.parent / "plans"
OMEGA = "SHARE_CE_PRIME_ENRICHED_OMEGA_2822.PRIME_OMEGA"
BRANDS = {29847: "claude", 27440: "chatgpt", 32111: "gemini", 29069: "perplexity", 11021: "muse"}
START = "2023-01-01"
PANEL = "aggregate_consistent_shopper_2022_v2"
COLS = """transid, memid, trans_date AS dt, filedate, trans_amount AS amount, currency, transtype,
          billing_description AS descr, weight_agg_cs2022 AS weight"""


def pull(warehouse="ANALYST_XL"):
    import snowflake.connector as sc
    CACHE.mkdir(parents=True, exist_ok=True)
    cur = sc.connect(connection_name="default", warehouse=warehouse, network_timeout=7200).cursor()
    cur.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 7200")

    def get(sql):
        cur.execute(sql)
        df = cur.fetch_pandas_all()
        df.columns = [c.lower() for c in df.columns]
        return df

    # brands: Google One only above storage prices ($1.99 / $2.99), Facebook only from 2026-06 (Muse launched 2026-09-08)
    brand = get(f"""SELECT brand_id, {COLS} FROM EARNEST.COMMON.TXNS_CORE_V
        WHERE weight_agg_cs2022 IS NOT NULL AND trans_date >= '{START}'
          AND (brand_id IN (29847, 27440, 29069)
               OR (brand_id = 32111 AND trans_date >= '2024-01-01' AND ABS(trans_amount) >= 3.5)
               OR (brand_id = 11021 AND trans_date >= '2026-06-01'))""")
    # unbranded ChatGPT and Muse direct merchids, same panel logic as TXNS_CORE (source.sql)
    extra = get(f"""
        WITH panel AS (
            SELECT cardlinkid, weight FROM {OMEGA}.CARDLINK_PANEL_V1_0 p
            WHERE panel = '{PANEL}'
              AND NOT EXISTS (SELECT 1 FROM {OMEGA}_STATIC.AFFECTED_ACCOUNTS_092026 a WHERE a.cardlinkid = p.cardlinkid)),
        mids AS (
            SELECT d.merchid, d.merchdesc FROM {OMEGA}.MID_V1_0 d
            LEFT JOIN {OMEGA}.MID_MATCH_V1_0 m ON m.merchid = d.merchid
            WHERE m.main_brand_id IS NULL
              AND d.merchdesc ILIKE ANY ('%CHATGPT%', '%OPENAI%', '%METAPAY%META.COM%', '%MUSE FROM META%',
                                         '%CLAUDE BY%', '%CLAUDEAI%', '%CLAUDE.AI%', '%ANTHROPIC%', '%PERPLEX%',
                                         '%GOOGLE%G1SK%', '%GOOGLE%G1AI%'))
        SELECT CASE WHEN c.merchdesc ILIKE '%CHATGPT%' THEN -27440
                    WHEN c.merchdesc ILIKE ANY ('%G1SK%', '%G1AI%') THEN -32111
                    WHEN c.merchdesc ILIKE ANY ('%CLAUDE BY%', '%CLAUDEAI%', '%CLAUDE.AI%', '%ANTHROPIC%') THEN -29847
                    WHEN c.merchdesc ILIKE '%PERPLEX%' THEN -29069
                    WHEN c.merchdesc ILIKE '%OPENAI%' THEN -27440
                    ELSE -11021 END AS brand_id,
               t.transid, t.cardlinkid AS memid, t.trans_date AS dt, t.filedate, t.trans_amount AS amount, t.currency,
               t.transtype, c.merchdesc AS descr, p.weight
        FROM {OMEGA}.TRANS_V1_0 t
        JOIN mids c ON c.merchid = t.merchid
        JOIN panel p ON p.cardlinkid = t.cardlinkid
        WHERE t.filedate >= DATEADD(day, -7, '{START}'::DATE) AND t.trans_date >= '{START}'""")
    raw = pd.concat([brand, extra], ignore_index=True).drop_duplicates("transid")
    raw["provider"] = raw.brand_id.abs().map(BRANDS)
    raw["source"] = np.where(raw.brand_id > 0, "txns_core", "omega_unbranded")
    raw["amount"] = raw.amount.astype(float)
    raw["weight"] = raw.weight.astype(float)
    raw["dt"] = pd.to_datetime(raw.dt)
    raw.to_parquet(CACHE / "raw.parquet", index=False)

    panel = get(f"""SELECT COUNT(*) AS members, SUM(weight) AS weight_sum FROM {OMEGA}.CARDLINK_PANEL_V1_0 p
        WHERE panel = '{PANEL}'
          AND NOT EXISTS (SELECT 1 FROM {OMEGA}_STATIC.AFFECTED_ACCOUNTS_092026 a WHERE a.cardlinkid = p.cardlinkid)""")
    panel.astype(float).to_parquet(CACHE / "panel.parquet", index=False)
    return raw, panel


# ---- step 3: descriptor research ---------------------------------------------------------------------------------
# Descriptor families per provider, first match wins (upper-cased descriptor). Bank prefixes ('POINT OF SALE
# WITHDRAWAL', 'DC : PURCH') don't matter because the patterns are searched anywhere in the string.
FAMILIES = {
    "claude": [
        ("Google Play", r"GOOGLE"),
        ("Team", r"TEAM|CLAUDE TE\b|CLAUDE T\b"),
        ("CLAUDE.AI SUBSCRIPTION", r"CLAUDE ?\.?AI|CLAUDEAI"),
        ("ANTHROPIC* CLAUDE SUB", r"ANTHROPIC\*? ?:? ?CLAUDE S"),
        ("ANTHROPIC* CLAUDE", r"ANTHROPIC\*? ?:? ?CLAUDE"),
        ("ANTHROPIC* (other)", r"ANTHROPIC\*"),
        ("bare ANTHROPIC", r"ANTHROPIC"),
    ],
    "chatgpt": [
        ("Google Play", r"GOOGLE"),
        ("CHATGPT SUBSCR", r"CHATGPT ?SU"),
        ("CHATGPT (other)", r"CHATGPT"),
        ("bare OPENAI", r"OPENAI"),
    ],
    "gemini": [
        ("GOOGLE ONE AI PREMIUM", r"AI PREM"),
        ("Google One SKU code", r"G1(?:AI|SK)"),
        ("GOOGLE ONE", r"GOOGLE ONE|GOOGLE \*GOOGLE O|GOOGLE GOOGLE O"),
        ("GOOGLE STORAGE", r"STORAGE"),
    ],
    "perplexity": [
        ("Google Play", r"GOOGLE"),
        ("Enterprise", r"\bENT\b"),
        ("credits / API", r"CREDIT|\bAPI\b|COMPUTER"),
        ("PERPLEXITY PRO", r"PERPLEXITY PRO|PRO WWW\.PERPLEX"),
        ("WWW.PERPLEXITY.AI", r"PERPLEX"),
    ],
    "muse": [
        ("METAPAY META.COM (web)", r"METAPAY ?(?:\d{4} )?META\.COM"),
        ("GOOGLE *MUSE FROM META", r"MUSE FROM META"),
        ("GOOGLE *FACEBOOK (Play)", r"GOOGLE.{0,3}FACEBOOK"),
        ("FACEBK (ads)", r"FACEBK"),
        ("PayPal / Meta Platforms", r"PAYPAL|PP\*|METAPLATFOR"),
    ],
}
TAX = 1.12  # US list prices exclude sales tax


def family(descr: pd.Series, provider: str) -> pd.Series:
    up = descr.fillna("").str.upper()
    u = pd.Series(up.unique())
    pats = [(n, re.compile(p)) for n, p in FAMILIES[provider]]
    lab = u.map(lambda d: next((n for n, p in pats if p.search(d)), "other"))
    return up.map(dict(zip(u, lab)))


def price_points(provider: str) -> pd.DataFrame:
    """US consumer list prices (paid plans) from plans/{provider}_prices.csv, with validity windows."""
    p = pd.read_csv(PLANS / f"{provider}_prices.csv")
    p = p[(p.region == "US") & (p["consumer(Y/N)"] == "Y")].copy()
    p["price"] = pd.to_numeric(p.price_incl_tax, errors="coerce")
    p = p[p.price > 0]
    p["valid_from"] = pd.to_datetime(p.valid_from).fillna(pd.Timestamp("2019-01-01"))
    p["valid_to"] = pd.to_datetime(p.valid_to).fillna(pd.Timestamp("2099-01-01"))
    return p[["plan", "cadence", "price", "valid_from", "valid_to"]].reset_index(drop=True)


def in_price_band(x: pd.DataFrame, provider: str) -> pd.Series:
    """True where the amount sits on a US list price valid on that date, allowing 0-12% sales tax and $0.02 below."""
    hit = pd.Series(False, index=x.index)
    for r in price_points(provider).itertuples():
        hit |= x.amount.between(r.price - 0.02, r.price * TAX) & x.dt.between(r.valid_from, r.valid_to)
    return hit


def recurring(x: pd.DataFrame, by=("memid", "family"), lo=26, hi=35) -> pd.Series:
    """True where the same member has another payment in the same group lo-hi days before or after."""
    y = x.sort_values([*by, "dt"])
    g = y.groupby(list(by)).dt
    prev, nxt = (y.dt - g.shift(1)).dt.days, (g.shift(-1) - y.dt).dt.days
    return (prev.between(lo, hi) | nxt.between(lo, hi)).reindex(x.index)


def research(raw: pd.DataFrame, provider: str):
    """Per descriptor family: volume, amounts, price-band match and monthly recurrence (debits only)."""
    x = raw[(raw.provider == provider) & (raw.amount > 0) & raw.transtype.str.lower().eq("debit")].copy()
    x["family"] = family(x.descr, provider)
    x["on_price"] = in_price_band(x, provider)
    x["recurring"] = recurring(x)
    x["both"] = x.on_price & x.recurring
    t = x.groupby("family").agg(rows=("transid", "size"), members=("memid", "nunique"), first=("dt", "min"),
                                last=("dt", "max"), median_amt=("amount", "median"), pct_on_price=("on_price", "mean"),
                                pct_recurring=("recurring", "mean"), pct_both=("both", "mean"))
    t[["first", "last"]] = t[["first", "last"]].apply(lambda s: s.dt.date)
    return t.sort_values("rows", ascending=False), x


# ---- step 3b: classification (rules from the Oct-19 Omega filters: same descriptors, same panel) -----------------
def classify(raw: pd.DataFrame) -> pd.DataFrame:
    import importlib
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    out = []
    for p in BRANDS.values():
        d = raw[raw.provider == p].rename(columns={"memid": "uid"})
        c = importlib.import_module(f"filters.{p}").classify(d, "omega")
        out.append(c.assign(provider=p))
    c = pd.concat(out, ignore_index=True).rename(columns={"uid": "memid"})
    c["dt"] = pd.to_datetime(c.dt)
    return c


# ---- step 4: metrics ---------------------------------------------------------------------------------------------
ADD_GAP, ADD_GAP_ANNUAL, WINDOW = 75, 400, 30


def tr_distinct(pay: pd.DataFrame, key: str, days: pd.DatetimeIndex, window=WINDOW, weight=None) -> pd.DataFrame:
    """Distinct members per key with a payment in the trailing `window` days, for every day in `days`.
    Each payment covers [dt, dt+window); a member's overlapping covers for a key are merged, then +1/-1 events
    are summed by day."""
    y = pay.sort_values(["memid", key, "dt"]).reset_index(drop=True)
    end = y.dt + pd.Timedelta(days=window)
    grp = [y.memid, y[key]]
    run_max = end.groupby(grp).shift(1).groupby(grp).cummax()
    run = (run_max.isna() | (y.dt > run_max)).cumsum()
    iv = pd.DataFrame({key: y[key], "start": y.dt, "end": end, "w": y[weight] if weight else 1.0}).groupby(run).agg(
        **{key: (key, "first")}, start=("start", "min"), end=("end", "max"), w=("w", "first"))
    ev = pd.concat([iv[[key, "start", "w"]].rename(columns={"start": "d"}),
                    iv[[key, "end", "w"]].rename(columns={"end": "d"}).assign(w=lambda d: -d.w)])
    s = ev.groupby([key, "d"]).w.sum().unstack(key, fill_value=0).sort_index().cumsum()
    return s.reindex(s.index.union(days)).ffill().fillna(0).reindex(days)


def gross_adds(pay: pd.DataFrame, key: str) -> pd.DataFrame:
    """A payment is a gross add when the member's previous payment for the same key is more than 75 days earlier
    (400 days after an annual payment), or there is none."""
    y = pay.sort_values(["memid", key, "dt"])
    g = y.groupby(["memid", key])
    gap = (y.dt - g.dt.shift(1)).dt.days
    lim = np.where(g.cadence.shift(1).eq("A"), ADD_GAP_ANNUAL, ADD_GAP)
    return y[gap.isna() | (gap > lim)]


def daily(pay: pd.DataFrame, key: str, start="2024-01-01", weight=None) -> dict:
    """Daily subscriber payments, TR30 subscribers, daily and TR30 gross adds, by key (one column per key)."""
    days = pd.date_range(start, pay.dt.max())
    w = (lambda d: d[weight]) if weight else (lambda d: pd.Series(1.0, index=d.index))
    one = pay.drop_duplicates(["memid", key, "dt"])
    pays = one.assign(w=w(one)).groupby(["dt", key]).w.sum().unstack(key).reindex(days).fillna(0)
    subs = tr_distinct(pay, key, days, weight=weight)
    a = gross_adds(pay, key)
    full = pd.date_range(pay.dt.min(), pay.dt.max())  # roll over full history so the first window isn't empty
    adds = a.assign(w=w(a)).groupby(["dt", key]).w.sum().unstack(key).reindex(full).fillna(0)
    return {"payments": pays, "tr30_subs": subs, "adds": adds.reindex(days),
            "tr30_adds": adds.rolling(WINDOW, min_periods=1).sum().reindex(days)}
