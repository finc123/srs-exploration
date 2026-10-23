"""Companion to merchdesc_test.py: agentic transactions in Prime Tau (2822) via its MERCHDESC, Sep 2026,
and how many of them are in 279 PRIME_TAU. Appends to results/merchdesc_test.txt."""
import os, time
import snowflake.connector

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "merchdesc_test.txt")
T = "SHARE_CE_PRIME_ENRICHED_TAU_2822.PRIME_TAU"
A = """({c} ILIKE '%linkagnt*%' OR (REGEXP_LIKE({c}, '(^|.*[^a-z.])link\\\\* .*', 'i')
       AND ({c} ILIKE '%www.link.co%' OR {c} ILIKE '%south san fra%')))"""
sql = f"""WITH mid AS (SELECT merchid FROM {T}.MID_V1_0 WHERE {A.format(c='merchdesc')}),
o AS (SELECT t.partner_transid, t.cardlinkid FROM {T}.TRANS_V1_0 t
      WHERE t.trans_date >= '2026-09-01' AND t.trans_date < '2026-10-01' AND t.filedate >= '2026-08-31'
        AND t.merchid IN (SELECT merchid FROM mid)),
e AS (SELECT DISTINCT partner_transaction_id FROM SHARE_EARNEST_279.PRIME_TAU.SPEND_279_TRANSACTIONS_V3_0
      WHERE transaction_date >= '2026-08-28' AND transaction_date < '2026-10-04' AND file_create_date >= '2026-08-28'
        AND {A.format(c='billing_description')})
SELECT (SELECT COUNT(*) FROM mid) AS agentic_merchids, COUNT(DISTINCT o.partner_transid) AS tau_agentic_txns,
       COUNT(DISTINCT o.cardlinkid) AS tau_agentic_members,
       COUNT(DISTINCT IFF(o.partner_transid IN (SELECT partner_transaction_id FROM e), o.partner_transid, NULL)) AS also_in_279_tau
FROM o"""
con = snowflake.connector.connect(connection_name="default", warehouse=os.getenv("CARD_INV_WAREHOUSE", "LARGE"))
cur = con.cursor()
cur.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 3000")
t = time.time()
cur.execute(sql)
res = [tuple(d[0] for d in cur.description)] + cur.fetchall()
with open(OUT, "a", encoding="utf-8") as f:
    f.write(f"\n== 4 Prime Tau (2822) Sep-26 agentic via MERCHDESC ({time.time() - t:.0f}s)\n" + "\n".join(map(str, res)) + "\n")
print(res)
