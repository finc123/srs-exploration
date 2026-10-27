"""SQL and rules for card_ereceipt_comparison.ipynb: monthly gross adds, churn and net adds per AI provider x channel,
from the card panel (Omega 2022), the e-receipt panel (NIQ items_v) and Yipit. Plan: ../plans/26th_october_2026.txt.

Reused from other workstreams (review these alongside this file):
- card_core_rules.py           card pull pattern (TXNS_CORE_V for tagged rows + Omega TRANS_V1_0 for untagged merchids)
- ../filters/{provider}.py     card descriptor / price rules per provider (classify(df, "omega")); notes in *_report.md.
                               chatgpt.py matches the truncated 'CHATGP' form (fixed 2026-10-26)
- channel_rules.py             e-receipt gross-add series and cancellation de-duplication (75 / 400 / 45 days)
- _make_direct_v_channel.py    e-receipt sender and description filters per provider x channel
                               (direct_v_channel_comparison.ipynb, 2026-10-21); ported into RECEIPT_RULES below
- ../filters_receipts/grok.py  X Premium+ receipt patterns (+ grok_report.md: SpaceXAI LLC Play cancels)

pull_card()     -> .cache/card_ereceipt/card_raw.parquet      (CARD_TXNS_CORE_SQL + CARD_OMEGA_SQL)
pull_receipts() -> .cache/card_ereceipt/receipt_raw.parquet   (RECEIPT_SQL)
card_payments() -> kept subscription payments (one row per payment) with provider, channel, cadence
card_monthly()  -> gross adds / churn / net adds per provider x channel x month (40-day rule, 385 after an annual payment)
card_spend_daily() -> kept AI-plan spend and paying accounts per provider x day (app Provider Market Share 'Spend',
                   built by ../app/refresh_local.py; includes Muse)
panel_spend_daily() -> total panel spend at tagged merchants per day (Spend '% of Panel' denominator), cached
receipt_monthly() -> the same from e-receipts (first email in a series; cancellations only while subscribed)
yipit()         -> Yipit US Subscriber Behavior: gross adds (New + Re-Signup + Upgrade), churn, net adds
"""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

import channel_rules

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "card_ereceipt"
YIPIT_XLSX = ROOT / "plans" / "yipitdata_consumer_ai.xlsx"

PROVIDERS = ["chatgpt", "claude", "gemini", "perplexity", "grok"]
SPEND_PROVIDERS = PROVIDERS + ["muse"]  # the app's Spend metric covers Muse too (user decision 2026-10-27)
NAMES = {"chatgpt": "ChatGPT", "claude": "Claude", "gemini": "Gemini", "perplexity": "Perplexity", "grok": "Grok", "muse": "Muse"}
CHANNELS = ["direct", "google_play", "itunes"]  # card 'web' is reported as 'direct'
MONTHS = pd.period_range("2024-01", "2026-08", freq="M")

CUTOFF, CUTOFF_ANNUAL = 40, 385  # card churn: no further payment within 40 days (385 after an annual payment)
CARD_LAG = 10                    # card transactions are still posting for about 10 days

# ---- card SQL --------------------------------------------------------------------------------------------------------
OMEGA = "SHARE_CE_PRIME_ENRICHED_OMEGA_2822.PRIME_OMEGA"
PANEL = "aggregate_consistent_shopper_2022_v2"
CARD_START = "2023-01-01"  # a year of history before the first reported month, so early adds aren't renewals

# Tagged rows. Google One only above storage prices ($1.99 / $2.99); Facebook (Muse) only from 2026-06, as in
# card_core_rules.py (Muse launched 2026-09-08).
CARD_TXNS_CORE_SQL = f"""
SELECT brand_id, transid, memid, trans_date AS dt, filedate, trans_amount AS amount, currency, transtype,
       billing_description AS descr
FROM EARNEST.COMMON.TXNS_CORE_V
WHERE weight_agg_cs2022 IS NOT NULL AND trans_date >= '{CARD_START}'
  AND (brand_id IN (29847, 27440, 29069)                                  -- Anthropic, OpenAI, Perplexity
       OR (brand_id = 32111 AND trans_date >= '2024-01-01' AND ABS(trans_amount) >= 3.5)  -- Google One
       OR (brand_id = 11021 AND trans_date >= '2026-06-01'))                                 -- Facebook (Muse)
"""

# Untagged rows, same panel logic as TXNS_CORE (2022 consistent-shopper panel, affected accounts excluded):
# - AI merchids with no main brand (ChatGPT web + Play incl. truncated CHATGP, Claude/Perplexity Play, CLAUDEAI,
#   Perplexity brandless Jun-Oct 2026, Google One SKU codes from 2026-09-15, other untagged 'GOOGLE…ONE' merchids
#   such as 'GOOGLE ONE, MOUNTAIN VIEW, CA', Muse web 'METAPAY META.COM' and Play 'GOOGLE *MUSE FROM META')
# - the truncated generic 'GOOGLE *GOOGLE MOUNTAIN VIE' (carried many Google One charges, esp. Jul-Aug 2026;
#   user decision 2026-10-26: include, filters/gemini.py prices it)
# - Grok and X Premium+ whatever their brand: X.AI / X.COM are not in the TXNS_CORE brand selection.
#   Descriptor list = keywords.py 'grok' (+ masked X Corp forms from filters/grok.py X_RE).
CARD_OMEGA_SQL = f"""
WITH panel AS (
    SELECT cardlinkid FROM {OMEGA}.CARDLINK_PANEL_V1_0 p
    WHERE panel = '{PANEL}'
      AND NOT EXISTS (SELECT 1 FROM {OMEGA}_STATIC.AFFECTED_ACCOUNTS_092026 a WHERE a.cardlinkid = p.cardlinkid)),
mids AS (
    SELECT d.merchid, d.merchdesc,
           d.merchdesc ILIKE ANY ('%grok%', '%x.ai%', '%xai %', '% xai%', '%x corp%', '%xcorp%', '%twitter%',
                                  '%x premium%', '%corp. paid f%', '%corp paid f%', '%corp. pa 865%',
                                  '%corp. pa 1355%', '%corp. pax corp%') AS is_grok
    FROM {OMEGA}.MID_V1_0 d
    LEFT JOIN {OMEGA}.MID_MATCH_V1_0 m ON m.merchid = d.merchid
    WHERE (m.main_brand_id IS NULL
           AND d.merchdesc ILIKE ANY ('%CHATGP%', '%OPENAI%', '%CLAUDE BY%', '%CLAUDEAI%', '%CLAUDE.AI%', '%ANTHROPIC%',
                                      '%PERPLEX%', '%GOOGLE%G1SK%', '%GOOGLE%G1AI%', '%GOOGLE%ONE%',
                                      '%METAPAY%META.COM%', '%MUSE FROM META%'))
       OR d.merchdesc ILIKE 'GOOGLE%GOOGLE MOUNTAIN VIE%'
       OR d.merchdesc ILIKE ANY ('%grok%', '%x.ai%', '%xai %', '% xai%', '%x corp%', '%xcorp%', '%twitter%',
                                 '%x premium%', '%corp. paid f%', '%corp paid f%', '%corp. pa 865%',
                                 '%corp. pa 1355%', '%corp. pax corp%'))
SELECT CASE WHEN c.is_grok THEN 0
            WHEN c.merchdesc ILIKE '%CHATGP%' THEN -27440
            WHEN c.merchdesc ILIKE ANY ('%G1SK%', '%G1AI%') THEN -32111
            WHEN c.merchdesc ILIKE ANY ('%CLAUDE BY%', '%CLAUDEAI%', '%CLAUDE.AI%', '%ANTHROPIC%') THEN -29847
            WHEN c.merchdesc ILIKE '%PERPLEX%' THEN -29069
            WHEN c.merchdesc ILIKE ANY ('%METAPAY%META.COM%', '%MUSE FROM META%') THEN -11021
            WHEN c.merchdesc ILIKE ANY ('%GOOGLE%ONE%', 'GOOGLE%GOOGLE MOUNTAIN VIE%') THEN -32111
            ELSE -27440 END AS brand_id,                                    -- remaining: OPENAI
       t.transid, t.cardlinkid AS memid, t.trans_date AS dt, t.filedate, t.trans_amount AS amount, t.currency,
       t.transtype, c.merchdesc AS descr
FROM {OMEGA}.TRANS_V1_0 t
JOIN mids c ON c.merchid = t.merchid
JOIN panel p ON p.cardlinkid = t.cardlinkid
WHERE t.filedate >= DATEADD(day, -7, '{CARD_START}'::DATE) AND t.trans_date >= '{CARD_START}'
"""
BRAND_PROVIDER = {29847: "claude", 27440: "chatgpt", 32111: "gemini", 29069: "perplexity", 0: "grok", 11021: "muse"}
# Total panel spend per day, the denominator of the app's Spend '% of Panel' (user decision 2026-10-27): USD debits on
# merchids tagged to a brand (MID_MATCH main_brand_id). Untagged debits are left out: most are bank-account transfers,
# rent and bill payments (about 80% of all debits by value). Most AI charges are untagged, so they are not in it.
PANEL_SPEND_SQL = f"""
WITH panel AS (
    SELECT cardlinkid FROM {OMEGA}.CARDLINK_PANEL_V1_0 p
    WHERE panel = '{PANEL}'
      AND NOT EXISTS (SELECT 1 FROM {OMEGA}_STATIC.AFFECTED_ACCOUNTS_092026 a WHERE a.cardlinkid = p.cardlinkid))
SELECT t.trans_date AS date, SUM(t.trans_amount) AS spend
FROM {OMEGA}.TRANS_V1_0 t
JOIN panel p ON p.cardlinkid = t.cardlinkid
JOIN {OMEGA}.MID_MATCH_V1_0 m ON m.merchid = t.merchid AND m.main_brand_id IS NOT NULL
WHERE t.filedate >= DATEADD(day, -7, '{{start}}'::DATE) AND t.filedate < DATEADD(day, 60, '{{stop}}'::DATE)
  AND t.trans_date >= '{{start}}' AND t.trans_date < '{{stop}}'
  AND t.transtype = 'debit' AND t.currency = 'USD' AND t.trans_amount > 0
GROUP BY 1
"""

# ---- e-receipt SQL ---------------------------------------------------------------------------------------------------
# Panel: mailboxes that joined before 2023 and are still active (inactive mailboxes are dropped retroactively).
# History from ChatGPT's launch (2022-11) so pre-2023 subscriptions set the subscription state.
RECEIPT_START = "2022-11-01"
RECEIPT_RX = "chat ?gpt|open ?ai|claude|anthropic|gemini|google one|google ai|grok|perplexity"
RECEIPT_SQL = f"""
SELECT mailbox_id, merchant_id, merchant_name, order_date, email_sent_time, order_id, item_id, description, item_price
FROM srs_slice.common.items_v
WHERE order_date >= '{RECEIPT_START}'
  AND entry_date < '2023-01-01' AND mailbox_status = 'ACTIVE'
  AND (merchant_id IN (4070, 4078, 20127, 20139, 4212, 4213, 20187, 20191)   -- direct senders and their cancellations
       OR (merchant_id IN (5, 20122, 1493, 3452)                              -- iTunes / Google Play (+ cancellations)
           AND (REGEXP_LIKE(description, '.*({RECEIPT_RX}).*', 'is')
                OR description ILIKE ANY ('%twitter%', '%x corp%', '%spacexai%', '%(x)%', '%(x (formerly twitter))%',
                                          'x :%', 'x x %'))))
"""


def _cursor(warehouse):
    import snowflake.connector as sc
    cur = sc.connect(connection_name="default", warehouse=warehouse, network_timeout=7200).cursor()
    cur.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 7200")
    return cur


def _get(cur, sql):
    cur.execute(sql)
    df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    return df


def pull_card(warehouse="ANALYST_XL", save=True) -> pd.DataFrame:
    cur = _cursor(warehouse)
    raw = pd.concat([_get(cur, CARD_TXNS_CORE_SQL), _get(cur, CARD_OMEGA_SQL)], ignore_index=True).drop_duplicates("transid")
    raw["provider"] = raw.brand_id.abs().map(BRAND_PROVIDER)
    raw["source"] = np.where(raw.brand_id > 0, "txns_core", "omega_untagged")
    raw["amount"] = raw.amount.astype(float)
    raw["dt"] = pd.to_datetime(raw.dt)
    if save:
        CACHE.mkdir(parents=True, exist_ok=True)
        raw.to_parquet(CACHE / "card_raw.parquet", index=False)
    return raw


def panel_spend_daily(end: pd.Timestamp, refresh_days=45, warehouse="ANALYST_XL") -> pd.DataFrame:
    """Total tagged-merchant panel spend per day (PANEL_SPEND_SQL) to `end`, cached in panel_spend_daily.parquet.
    Only the last `refresh_days` of the cache are re-pulled (late-posting transactions): recent files prune well (about
    1 TB, 30 s on XL). Older dates are spread over the whole of TRANS_V1_0 (about 12.7 TB a query, 3-5 minutes), so a
    first run pulls a calendar year per query and saves after each; an interrupted run resumes from the cache."""
    path = CACHE / "panel_spend_daily.parquet"
    CACHE.mkdir(parents=True, exist_ok=True)
    out = pd.read_parquet(path) if path.exists() else None
    start = pd.Timestamp(CARD_START) if out is None else out.date.max() - pd.Timedelta(days=refresh_days)
    stop = end + pd.Timedelta(days=1)
    edges = pd.date_range(start, stop, freq="YS").union([start, stop])
    cur = _cursor(warehouse)
    for a, b in zip(edges[:-1], edges[1:]):
        new = _get(cur, PANEL_SPEND_SQL.format(start=a.date(), stop=b.date()))
        new = new.assign(date=pd.to_datetime(new.date), spend=new.spend.astype(float))
        out = new if out is None else pd.concat([out[(out.date < a) | (out.date >= b)], new], ignore_index=True)
        out = out.sort_values("date").reset_index(drop=True)
        out.to_parquet(path, index=False)
        print(f"panel spend {a.date()} to {b.date()}: {len(new)} days", flush=True)
    return out


def pull_receipts(warehouse="ANALYST_L") -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    raw = _get(_cursor(warehouse), RECEIPT_SQL)
    raw.to_parquet(CACHE / "receipt_raw.parquet", index=False)
    return raw


# ---- card rules ------------------------------------------------------------------------------------------------------
def _card_filter(p: str):
    """../filters/{p}.py loaded by path: that folder is a namespace package, so `import filters.x` would pick up any
    regular `filters` package on sys.path first (e.g. the srs engine's e-receipt filters in app/refresh_local.py)."""
    spec = importlib.util.spec_from_file_location(f"card_filters_{p}", ROOT / "filters" / f"{p}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def card_payments(raw: pd.DataFrame, providers=PROVIDERS) -> pd.DataFrame:
    """Kept consumer subscription payments, classified by ../filters/{provider}.py. Grok = SuperGrok (provider 'grok')
    + X Premium+ (filter provider 'grok_x'). Channel 'web' is reported as 'direct'."""
    out = []
    for p in providers:
        d = raw[raw.provider == p].rename(columns={"memid": "uid"})
        c = _card_filter(p).classify(d, "omega")
        out.append(c[c.keep.astype(bool)].assign(provider=p))
    pay = pd.concat(out, ignore_index=True)
    pay["dt"] = pd.to_datetime(pay.dt)
    pay["channel"] = pay.channel.replace({"web": "direct"})
    return pay[["uid", "provider", "channel", "dt", "plan", "cadence", "amount", "descr"]]


def card_spells(pay: pd.DataFrame, end: pd.Timestamp) -> pd.DataFrame:
    """One row per subscription spell per uid x provider x channel. A payment starts a new spell (a gross add) when the
    previous payment is more than 40 days earlier (385 if that payment was annual). Churn is dated at last payment
    + 40 (385) days, and only once that date + CARD_LAG has passed the data end; otherwise the spell is still open."""
    key = ["uid", "provider", "channel"]
    y = pay.sort_values([*key, "dt", "cadence"]).drop_duplicates([*key, "dt"], keep="last").reset_index(drop=True)
    g = y.groupby(key)
    cut = np.where(y.cadence.eq("A"), CUTOFF_ANNUAL, CUTOFF)
    prev_cut = pd.Series(cut, index=y.index).groupby([y[k] for k in key]).shift(1)
    new = g.dt.shift(1).isna() | ((y.dt - g.dt.shift(1)).dt.days > prev_cut)
    y["sid"], y["cut"] = new.cumsum(), cut
    s = y.groupby("sid").agg(**{k: (k, "first") for k in key}, start=("dt", "min"), last=("dt", "max"), cut=("cut", "last"))
    churn_dt = s["last"] + pd.to_timedelta(s.cut, unit="D")
    s["churn_dt"] = churn_dt.where(churn_dt + pd.Timedelta(days=CARD_LAG) <= end)
    return s.reset_index(drop=True)


def card_monthly(spells: pd.DataFrame) -> pd.DataFrame:
    """Gross adds (spell starts) and churn (spell churn dates) per provider x channel x month; uid counted once a month."""
    a = spells.assign(month=spells.start.dt.to_period("M")).groupby(["provider", "channel", "month"]).uid.nunique()
    c = spells.dropna(subset=["churn_dt"])
    c = c.assign(month=c.churn_dt.dt.to_period("M")).groupby(["provider", "channel", "month"]).uid.nunique()
    return _frame(a, c)


def card_spend_daily(pay: pd.DataFrame, end: pd.Timestamp) -> pd.DataFrame:
    """Observable AI-plan spend per provider x day: the sum of kept payment amounts (all channels; annual plans count
    on the day charged) and distinct paying accounts. Days after `end` - CARD_LAG are dropped (still posting).
    Unweighted, like every card count here."""
    last = end - pd.Timedelta(days=CARD_LAG)
    d = pay[pay.dt <= last]
    out = d.groupby(["provider", "dt"]).agg(spend=("amount", "sum"), accounts=("uid", "nunique")).reset_index()
    return out.rename(columns={"dt": "date"})


# ---- e-receipt rules (ported from _make_direct_v_channel.py) ---------------------------------------------------------
GP_PAY_RX = "auto-renewing subscription"  # Google Play paid receipt: priced, auto-renewing, not a 'your trial' notice
IT_SIGNUP_RX = r"/ ?(month|year|week)"     # iTunes unpriced confirmation ('... $20.00 /month'), not a free trial
IT_PAY_RX = r"\((monthly|annual|yearly|weekly)\)"
IT_ANNUAL_RX = r"annual|yearly|/ ?year|\(\d+ year\)"
CG_PLAN = r"^chatgpt (plus|go|pro)( \d+x?)?( subscription| plan)?( cancellation)?$"
G_AI = r"google ai|ai premium|ai pro\b|ai plus|ai ultra"
X_PLUS_IT = r"^x :? ?x premium plus"                        # 'X : X Premium Plus (Monthly)', cancel 'X X Premium Plus ...'
X_PLUS_GP = r"^premium\+ \(x( \(formerly twitter\))?\)"     # 'Premium+ (X) Auto-renewing subscription'
X_GP_ANY = r"\(x( \(formerly twitter\))?\) auto-renewing"   # any X tier on Play (to attribute untiered cancels)
X_GP_CANCEL = r"from twitter inc|from x corp"


def _prep(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df["d"] = df.description.str.lower().fillna("")
    df["dt"] = pd.to_datetime(df.order_date)
    df["priced"] = df.item_price.fillna(0) > 0
    df["channel"] = np.select([df.merchant_id.isin([1493, 3452]), df.merchant_id.isin([5, 20122])],
                              ["google_play", "itunes"], "direct")
    return df.reset_index(drop=True)


def _rules(df: pd.DataFrame) -> dict:
    """{(provider, channel): dict(signup=, pay=, cancel=, annual=)} boolean masks over df. Each entry is described in the
    notebook section for that provider."""
    has = lambda rx: df.d.str.contains(rx, regex=True)
    m = df.merchant_id
    gp_pay = m.eq(1493) & df.priced & has(GP_PAY_RX) & ~df.d.str.startswith("your trial")
    gp_can, it_conf, it_pay, it_can = m.eq(3452), m.eq(5) & ~df.priced & has(IT_SIGNUP_RX) & ~has("free trial"), \
        m.eq(5) & df.priced & has(IT_PAY_RX), m.eq(20122)
    it_ann = has(IT_ANNUAL_RX)
    F = pd.Series(False, index=df.index)
    R = {}

    # ChatGPT
    R["chatgpt", "direct"] = dict(signup=m.eq(4070) & has(CG_PLAN), pay=F, cancel=m.eq(4078) & has(CG_PLAN))
    R["chatgpt", "google_play"] = dict(signup=F, pay=gp_pay & has(r"\(chatgpt\) auto-renewing subscription"),
                                       cancel=gp_can & has("chatgpt"))
    it = has(r"^chatgpt ")
    R["chatgpt", "itunes"] = dict(signup=it & it_conf, pay=it & it_pay & ~has("credits"),
                                  cancel=it_can & has(r"^chatgpt chatgpt"), annual=it_ann)

    # Claude. Direct cancellations within 3 days of a welcome for a different tier are tier switches, not churn.
    ws = df[m.eq(20127) & df.d.isin(["pro subscription", "max subscription"])][["mailbox_id", "dt", "d"]]
    cn = df[m.eq(20139)][["mailbox_id", "dt", "d"]].reset_index()
    x = cn.merge(ws, on="mailbox_id", suffixes=("", "_w"))
    switch = df.index.isin(x[((x.dt_w - x.dt).dt.days.abs() <= 3)
                             & (x.d.str.split().str[-1] != x.d_w.str.split().str[0])]["index"].unique())
    R["claude", "direct"] = dict(signup=m.eq(20127) & df.d.isin(["pro subscription", "max subscription"]),
                                 pay=m.eq(20127) & df.d.eq("payment") & df.item_price.isin([20, 100, 200]),
                                 cancel=m.eq(20139) & ~switch)
    R["claude", "google_play"] = dict(signup=F, pay=gp_pay & has(r"\(claude by anthropic\) auto-renewing subscription"),
                                      cancel=gp_can & has("claude by anthropic"))
    it = has(r"^claude by anthropic")
    R["claude", "itunes"] = dict(signup=it & it_conf, pay=it & it_pay & ~has("credits"), cancel=it & it_can, annual=it_ann)

    # Gemini (Google AI plans). Direct = Google One welcome / end emails naming an AI plan.
    R["gemini", "direct"] = dict(signup=m.eq(20187) & has("^welcome") & has(G_AI), pay=F,
                                 cancel=m.eq(20191) & has(G_AI) & has(r"ended|cancell?ed") & ~has("trial has ended"))
    # Google Play: cancels rarely name the plan -> AI if named, or if the mailbox's last Google One Play receipt
    # (within 75 days before) was an AI plan. The May-Jun 2026 2TB -> 'Google AI Plus (2 TB)' same-price rename counts
    # as adds (user decision 2026-10-26, consistent with cards counting 2TB as AI Plus; Yipit counts it too).
    g1 = df[gp_pay & has(r"\(google one\)")][["mailbox_id", "dt", "d"]].sort_values("dt")
    gc = df[gp_can & has("google one")][["mailbox_id", "dt", "d"]].reset_index().sort_values("dt")
    last = pd.merge_asof(gc, g1.rename(columns={"dt": "pdt", "d": "pd_"}), left_on="dt", right_on="pdt", by="mailbox_id",
                         direction="backward", tolerance=pd.Timedelta(days=75))
    ai_can = df.index.isin(last[last.d.str.contains(G_AI) | last.pd_.fillna("").str.contains(G_AI)]["index"])
    R["gemini", "google_play"] = dict(signup=F, pay=gp_pay & has(r"\(google one\)") & has(G_AI), cancel=ai_can)
    it = has(G_AI)
    R["gemini", "itunes"] = dict(signup=it & it_conf, pay=it & m.eq(5) & df.priced & (has(IT_PAY_RX) | has(r"^google ai (plus|pro|ultra)")),
                                 cancel=it & it_can, annual=it_ann)

    # Perplexity
    R["perplexity", "direct"] = dict(signup=m.eq(4212) & has(r"^welcome to perplexity (pro|max)$"), pay=F,
                                     cancel=m.eq(4213) & ~has("trial has ended"))
    R["perplexity", "google_play"] = dict(signup=F, pay=gp_pay & has(r"perplexity (pro|max) \(perplexity.*auto-renewing subscription"),
                                          cancel=gp_can & has("perplexity"))
    it = has(r"perplexity (pro|max)")
    R["perplexity", "itunes"] = dict(signup=it & it_conf, pay=it & it_pay, cancel=it & it_can, annual=it_ann)

    # Grok = SuperGrok + X Premium+ (no direct receipts from xAI or X Corp).
    # Play X cancels ('X subscription from Twitter Inc') don't name the tier -> Premium+ if the mailbox's last X Play
    # receipt within 75 days before was Premium+ (same attribution as Google One).
    xr = df[gp_pay & has(X_GP_ANY)][["mailbox_id", "dt", "d"]].sort_values("dt")
    xc = df[gp_can & has(X_GP_CANCEL)][["mailbox_id", "dt"]].reset_index().sort_values("dt")
    last = pd.merge_asof(xc, xr.rename(columns={"dt": "pdt"}), left_on="dt", right_on="pdt", by="mailbox_id",
                         direction="backward", tolerance=pd.Timedelta(days=75))
    x_plus_can = df.index.isin(last[last.d.fillna("").str.contains(X_PLUS_GP)]["index"])
    R["grok", "google_play"] = dict(signup=F, pay=gp_pay & (has(r"super ?grok") | has(X_PLUS_GP)),
                                    cancel=(gp_can & has(r"x\.ai corp|spacexai|\(super ?grok")) | x_plus_can)
    it = has(r"super ?grok") | has(X_PLUS_IT)
    R["grok", "itunes"] = dict(signup=it & it_conf, pay=it & it_pay & ~has("credits"), cancel=it & it_can, annual=it_ann)
    return R


def receipt_events(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Gross adds and cancellations per provider x channel (mailbox_id, dt, provider, channel).
    adds: channel_rules.gross_adds (first sign-up / paid email in a series; new series after 75 days, 400 after an
    annual, or after a cancellation). cancels: channel_rules.churn_events (emails within 45 days = one cancellation),
    with `counted` = the mailbox had a gross add for the provider on ANY channel since its previous cancellation."""
    df = _prep(raw)
    adds, cans = [], []
    for (p, ch), r in _rules(df).items():
        ann = r.get("annual", pd.Series(False, index=df.index))
        sm = r["signup"] | r["pay"]
        sig = df.loc[sm, ["mailbox_id", "dt"]].assign(annual=ann[sm].values)
        can = df.loc[r["cancel"], ["mailbox_id", "dt"]]
        a = channel_rules.gross_adds(sig, can)
        adds.append(a[["mailbox_id", "dt"]].assign(provider=p, channel=ch))
        cans.append(channel_rules.churn_events(can, sig)[["mailbox_id", "dt"]].assign(provider=p, channel=ch))
    adds, cans = pd.concat(adds, ignore_index=True), pd.concat(cans, ignore_index=True)
    # A cancellation counts only if the event before it (any channel; adds first on the same day) is a gross add.
    ev = pd.concat([adds.assign(kind=0), cans.reset_index().assign(kind=1)]).sort_values(["provider", "mailbox_id", "dt", "kind"])
    prev = ev.groupby(["provider", "mailbox_id"]).kind.shift(1)
    ok = ev[(ev.kind == 1) & prev.eq(0)]["index"].astype(int)
    cans["counted"] = cans.index.isin(ok)
    return adds, cans


def receipt_monthly(adds: pd.DataFrame, cans: pd.DataFrame) -> pd.DataFrame:
    """Distinct mailboxes per provider x channel x month: gross adds, counted cancellations (churn)."""
    f = lambda x: x.assign(month=x.dt.dt.to_period("M")).groupby(["provider", "channel", "month"]).mailbox_id.nunique()
    return _frame(f(adds), f(cans[cans.counted]))


def _frame(adds: pd.Series, churn: pd.Series) -> pd.DataFrame:
    """Long table provider, channel, month, gross_adds, churn, net_adds over MONTHS, plus channel 'total' = sum."""
    idx = pd.MultiIndex.from_product([PROVIDERS, CHANNELS, MONTHS], names=["provider", "channel", "month"])
    t = pd.DataFrame({"gross_adds": adds, "churn": churn}).reindex(idx).fillna(0).astype(int)
    tot = t.groupby(level=["provider", "month"]).sum().assign(channel="total").set_index("channel", append=True)
    t = pd.concat([t, tot.reorder_levels(["provider", "channel", "month"])]).sort_index()
    t["net_adds"] = t.gross_adds - t.churn
    return t.reset_index()


# ---- Yipit -----------------------------------------------------------------------------------------------------------
def yipit(path=YIPIT_XLSX) -> pd.DataFrame:
    """'Monthly Metrics' tab, 'US Subscriber Behavior' block (header row 121, provider blocks from row 123):
    gross adds = New Signup + Re-Signup + Upgrade, churn = Churn, net adds = gross adds - churn. Provider totals."""
    import openpyxl
    rows = list(openpyxl.load_workbook(path, read_only=True, data_only=True)["Monthly Metrics"].iter_rows(values_only=True))
    head = rows[120]
    cols = [i for i, v in enumerate(head) if hasattr(v, "year")]
    out, prov = [], None
    for r in rows[122:]:
        if r[1] and str(r[1]).strip():
            prov = str(r[1]).strip().lower()
        elif prov and r[2]:
            for i in cols:
                v = r[i]
                out.append((prov, r[2], pd.Period(head[i], "M"), float(v) if isinstance(v, (int, float)) else np.nan))
    y = pd.DataFrame(out, columns=["provider", "metric", "month", "value"]).pivot_table(
        index=["provider", "month"], columns="metric", values="value", aggfunc="first")
    t = pd.DataFrame({"gross_adds": y[["New Signup", "Re-Signup", "Upgrade"]].sum(axis=1, min_count=1), "churn": y["Churn"]})
    t["net_adds"] = t.gross_adds - t.churn
    return t.reset_index()
