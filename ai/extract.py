"""Candidate extract for AI-subscription tracking on card panels.

Omega (US): 2022 consistent-shopper panel (aggregate_consistent_shopper_2022_v2), base share tables
(same rows as EARNEST.COMMON.CE_PRIME_OMEGA_PANEL_TXNS restricted to IN_AGG_CS2022, without the per-symbol fan-out).
Fable (EU): SHARE_FABLE.FABLE_SIGNAL {UK_V2, DE_V2, FR_V3, ES_V2, IT_V2}_TXN, consumer and business users kept
(business is excluded at analysis time).

Outputs to .cache/:
  {panel}_ai_txn.parquet   every transaction whose descriptor matches keywords.KEYWORDS (from 2023-01-01)
  {panel}_spells.parquet   activity spells per member: runs of transaction days with gaps <= 35 days (from 2022-11-01)
  omega_panel.parquet      panel members + weight

Usage: python extract.py [omega|uk|de|fr|es|it ...] [--txn-only]
"""
import sys, time
from pathlib import Path
import snowflake.connector as sc
from keywords import where_sql

CACHE = Path(__file__).parent / ".cache"
OMEGA = "SHARE_CE_PRIME_ENRICHED_OMEGA_2822.PRIME_OMEGA"
FABLE = {"uk": "UK_V2_TXN", "de": "DE_V2_TXN", "fr": "FR_V3_TXN", "es": "ES_V2_TXN", "it": "IT_V2_TXN"}
TXN_START, ACT_START, GAP = "2023-01-01", "2022-11-01", 35
TXN_ONLY = "--txn-only" in sys.argv


def spells_sql(daily: str) -> str:
    """`daily` yields distinct (uid, dt); returns one row per activity spell."""
    return f"""
    WITH d AS ({daily}),
    g AS (SELECT uid, dt, IFF(DATEDIFF(day, LAG(dt) OVER (PARTITION BY uid ORDER BY dt), dt) <= {GAP}, 0, 1) AS new_spell FROM d),
    s AS (SELECT uid, dt, SUM(new_spell) OVER (PARTITION BY uid ORDER BY dt ROWS UNBOUNDED PRECEDING) AS spell FROM g)
    SELECT uid, spell, MIN(dt) AS spell_start, MAX(dt) AS spell_end, COUNT(*) AS active_days FROM s GROUP BY 1, 2"""


def pull(cur, sql, name):
    t = time.time()
    cur.execute(sql)
    df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    df.to_parquet(CACHE / f"{name}.parquet", index=False)
    print(f"{name}: {len(df):,} rows, {time.time() - t:.0f}s", flush=True)
    return df


def omega(cur):
    cur.execute(f"""CREATE OR REPLACE TEMPORARY TABLE panel AS
        SELECT cardlinkid, weight FROM {OMEGA}.CARDLINK_PANEL_V1_0 p
        WHERE panel = 'aggregate_consistent_shopper_2022_v2'
          AND NOT EXISTS (SELECT 1 FROM {OMEGA}_STATIC.AFFECTED_ACCOUNTS_092026 a WHERE a.cardlinkid = p.cardlinkid)""")
    pull(cur, "SELECT * FROM panel", "omega_panel")
    cur.execute(f"CREATE OR REPLACE TEMPORARY TABLE cand AS SELECT merchid, merchdesc FROM {OMEGA}.MID_V1_0 WHERE {where_sql('merchdesc')}")
    pull(cur, f"""SELECT t.transid, t.cardlinkid AS uid, t.cardid, t.merchid, c.merchdesc AS descr, t.trans_date AS dt,
                         t.partner_post_date, t.filedate, t.trans_amount AS amount, t.currency, t.transtype, t.cardtype, t.user_score
                  FROM {OMEGA}.TRANS_V1_0 t JOIN cand c ON c.merchid = t.merchid JOIN panel p ON p.cardlinkid = t.cardlinkid
                  WHERE t.filedate >= DATEADD(day, -7, '{TXN_START}'::DATE) AND t.trans_date >= '{TXN_START}'""", "omega_ai_txn")
    if TXN_ONLY:
        return
    pull(cur, spells_sql(f"""SELECT DISTINCT t.cardlinkid AS uid, t.trans_date AS dt FROM {OMEGA}.TRANS_V1_0 t
                             JOIN panel p ON p.cardlinkid = t.cardlinkid
                             WHERE t.filedate >= DATEADD(day, -7, '{ACT_START}'::DATE) AND t.trans_date >= '{ACT_START}'"""), "omega_spells")


def fable(cur, cc):
    tbl = f"SHARE_FABLE.FABLE_SIGNAL.{FABLE[cc]}"
    pull(cur, f"""SELECT fdtxnkey, fduserkey AS uid, description AS descr, txndate AS dt, posteddate, reportdate,
                         spendout, spendin, txncurrency AS currency, usertype, usercountry, tag, mcc, txntype, recordstatus,
                         paymentprocessorname, origmerchantcountry
                  FROM {tbl} WHERE txndate >= '{TXN_START}' AND {where_sql('description')}""", f"{cc}_ai_txn")
    if TXN_ONLY:
        return
    pull(cur, spells_sql(f"SELECT DISTINCT fduserkey AS uid, txndate AS dt FROM {tbl} WHERE txndate >= '{ACT_START}'"), f"{cc}_spells")
    pull(cur, f"SELECT fduserkey AS uid, usertype, cardtype, openbankingflag, startdate, enddate FROM SHARE_FABLE.FABLE_SIGNAL.USER_MASTER WHERE enddate = '2099-12-31' OR enddate >= '{ACT_START}'", "fable_users") if cc == "uk" else None


if __name__ == "__main__":
    CACHE.mkdir(exist_ok=True)
    con = sc.connect(connection_name="default", warehouse="ANALYST_XL", network_timeout=7200)
    cur = con.cursor()
    cur.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 7200")
    cur.execute("USE SCHEMA SRS_MCP.SANDBOX")  # temporary tables only; nothing persists
    for p in [a for a in sys.argv[1:] if not a.startswith("--")] or ["omega", *FABLE]:
        omega(cur) if p == "omega" else fable(cur, p)
