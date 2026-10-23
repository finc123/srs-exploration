"""Pulls hashed samples of one transaction day from each short-listed table, for the subset / overlap analysis.

Two samples per table, both from one shared hash so they line up across tables that share an id namespace:
  - txn sample:    MOD(ABS(HASH(txn_id)), 1000) = 0    -> are the same transaction ids present in both tables?
  - member sample: MOD(ABS(HASH(member_id)), 2000) = 0 -> same panelists? and, within them, same (date, amount) rows?
The partner / source transaction id is sampled the same way, since ids may only match across vendors on that column.
Also records full-day totals (distinct txns / members) for scale. Prunes on the file-date column (>= the day).
Output: results/overlap/<key>.parquet (sample rows) and results/overlap/totals.csv. Resumable: skips keys already done.
Env: CARD_INV_WAREHOUSE (default LARGE)."""
import os, time, threading
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import snowflake.connector

DAY = "2026-09-10"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "overlap")
WAREHOUSE = os.getenv("CARD_INV_WAREHOUSE", "LARGE")
os.makedirs(OUT, exist_ok=True)

# key: (table, txn id, partner id, member id, date, file date, amount, descriptor)
O, T = "SHARE_CE_PRIME_ENRICHED_OMEGA_2822.PRIME_OMEGA.TRANS_V1_0", "SHARE_CE_PRIME_ENRICHED_TAU_2822.PRIME_TAU.TRANS_V1_0"
Y = "SHARE_CE_SPEND_201_PRIME_EX_TAU.FEED{n}_PANELS.FEED{n}_{k}_PANELS_V1_0"
E279 = "SHARE_EARNEST_279.{s}.SPEND_279_TRANSACTIONS_V3_0"
SOURCES = {
    "omega": (O, "TRANSID", "PARTNER_TRANSID", "CARDLINKID", "TRANS_DATE", "FILEDATE", "TRANS_AMOUNT", "MERCHID"),
    "tau": (T, "TRANSID", "PARTNER_TRANSID", "CARDLINKID", "TRANS_DATE", "FILEDATE", "TRANS_AMOUNT", "MERCHID"),
    "e279_prime": (E279.format(s="PRIME"), "EARNEST_TRANSACTION_ID", "PARTNER_TRANSACTION_ID", "MEMBER_ID", "TRANSACTION_DATE", "FILE_CREATE_DATE", "TRANSACTION_AMOUNT", "BILLING_DESCRIPTION"),
    "e279_tau": (E279.format(s="PRIME_TAU"), "EARNEST_TRANSACTION_ID", "PARTNER_TRANSACTION_ID", "MEMBER_ID", "TRANSACTION_DATE", "FILE_CREATE_DATE", "TRANSACTION_AMOUNT", "BILLING_DESCRIPTION"),
    "earnest_pdd": ("EARNEST.PDD.TXNS", "EARNEST_TRANSACTION_ID", "PARTNER_TRANSACTION_ID", "MEMBER_ID", "TRANSACTION_DATE", "FILE_CREATE_DATE", "TRANSACTION_AMOUNT", "BILLING_DESCRIPTION"),
    "fable_fr_v2": ("SHARE_FABLE.FABLE_SIGNAL.FR_V2_TXN", "FDTXNKEY", None, "FDUSERKEY", "TXNDATE", None, "SPENDOUT", "DESCRIPTION"),
    "fable_fr_v3": ("SHARE_FABLE.FABLE_SIGNAL.FR_V3_TXN", "FDTXNKEY", None, "FDUSERKEY", "TXNDATE", None, "SPENDOUT", "DESCRIPTION"),
}
for n in (3, 4, 6):
    for k in ("CARD", "BANK"):
        SOURCES[f"yodlee_f{n}_{k.lower()}"] = (Y.format(n=n, k=k), f"UNIQUE_{k}_TRANSACTION_ID", None, "UNIQUE_MEM_ID",
                                               "TRANSACTION_DATE", "PANEL_FILE_CREATED_DATE", "AMOUNT", "DESCRIPTION")

tl = threading.local()


def cur():
    if not hasattr(tl, "con"):
        tl.con = snowflake.connector.connect(connection_name="default", warehouse=WAREHOUSE)
        tl.con.cursor().execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 3600")
    return tl.con.cursor()


def h(col, m):
    return f"MOD(ABS(HASH({col})), {m}) = 0"


def run(key):
    path = os.path.join(OUT, f"{key}.parquet")
    if os.path.exists(path):
        return key, "cached", 0
    tab, tid, pid, mid, d, f, amt, desc = SOURCES[key]
    prune = f" AND {f} >= '{DAY}'" if f else ""
    pcol = pid or "NULL"
    sql = f"""WITH day AS (SELECT {tid} AS txn_id, {pcol} AS partner_id, {mid} AS member_id, {d} AS txn_date, {amt} AS amount,
                                  LEFT({desc}, 120) AS descr
                           FROM {tab} WHERE {d} = '{DAY}'{prune})
              SELECT 'row' AS kind, txn_id, partner_id, member_id, txn_date, amount, descr,
                     {h('txn_id', 1000)} AS s_txn, {h('member_id', 2000)} AS s_mem, {h('partner_id', 1000)} AS s_partner, NULL AS n
              FROM day WHERE {h('txn_id', 1000)} OR {h('member_id', 2000)} OR {h('partner_id', 1000)}
              UNION ALL SELECT 'n_txn', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, COUNT(DISTINCT txn_id) FROM day
              UNION ALL SELECT 'n_rows', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, COUNT(*) FROM day
              UNION ALL SELECT 'n_member', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, COUNT(DISTINCT member_id) FROM day"""
    t = time.time()
    c = cur()
    c.execute(sql)
    df = c.fetch_pandas_all()
    df.columns = [x.lower() for x in df.columns]
    secs = round(time.time() - t, 1)
    df.to_parquet(path, index=False)
    tot = df[df.kind != "row"].set_index("kind").n.to_dict()
    pd.DataFrame([{"key": key, "table": tab, "day": DAY, **tot, "sample_rows": (df.kind == "row").sum(), "seconds": secs}]) \
        .to_csv(os.path.join(OUT, "totals.csv"), mode="a", index=False, header=not os.path.exists(os.path.join(OUT, "totals.csv")))
    return key, "ok", secs


if __name__ == "__main__":
    # biggest first so the long scans overlap
    order = ["omega", "yodlee_f3_bank", "yodlee_f6_bank", "tau", "e279_prime", "e279_tau", "yodlee_f4_bank"] + \
            [k for k in SOURCES if k not in {"omega", "yodlee_f3_bank", "yodlee_f6_bank", "tau", "e279_prime", "e279_tau", "yodlee_f4_bank"}]
    import sys
    if len(sys.argv) > 1:
        order = sys.argv[1:]
    with ThreadPoolExecutor(6) as ex:
        futs = {k: ex.submit(run, k) for k in order}
        for k, fut in futs.items():
            try:
                print(*fut.result(), flush=True)
            except Exception as e:
                print("ERROR", k, str(e)[:300], flush=True)
