"""Companion to merchdesc_test.py: of Omega's Sep-2026 agentic transactions, how many are on cards in the two
consistent-shopper panels that EARNEST.COMMON.CE_PRIME_OMEGA_PANEL_TXNS keeps (i.e. visible through Josh's view)?
Also Omega's total Sep-2026 transactions in and out of those panels, for a per-million rate. Appends to results/merchdesc_test.txt."""
import os, time
import snowflake.connector

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "merchdesc_test.txt")
O = "SHARE_CE_PRIME_ENRICHED_OMEGA_2822.PRIME_OMEGA"
A = """({c} ILIKE '%linkagnt*%' OR (REGEXP_LIKE({c}, '(^|.*[^a-z.])link\\\\* .*', 'i')
       AND ({c} ILIKE '%www.link.co%' OR {c} ILIKE '%south san fra%')))"""
sql = f"""WITH mid AS (SELECT merchid FROM {O}.MID_V1_0 WHERE {A.format(c='merchdesc')}),
p AS (SELECT DISTINCT cardlinkid FROM {O}.CARDLINK_PANEL_V1_0
      WHERE panel IN ('aggregate_consistent_shopper_2019_v2', 'aggregate_consistent_shopper_2022_v2')),
x AS (SELECT a.cardlinkid FROM {O}.PRIME_OMEGA_STATIC.AFFECTED_ACCOUNTS_092026 a),
t AS (SELECT t.transid, t.merchid IN (SELECT merchid FROM mid) AS agentic,
             t.cardlinkid IN (SELECT cardlinkid FROM p) AND t.cardlinkid NOT IN (SELECT cardlinkid FROM x) AS in_view
      FROM {O}.TRANS_V1_0 t
      WHERE t.trans_date >= '2026-09-01' AND t.trans_date < '2026-10-01' AND t.filedate >= '2026-08-31')
SELECT in_view, COUNT(DISTINCT transid) AS txns, COUNT(DISTINCT IFF(agentic, transid, NULL)) AS agentic_txns
FROM t GROUP BY 1 ORDER BY 1"""
sql = sql.replace(f"{O}.PRIME_OMEGA_STATIC", "SHARE_CE_PRIME_ENRICHED_OMEGA_2822.PRIME_OMEGA_STATIC")
con = snowflake.connector.connect(connection_name="default", warehouse=os.getenv("CARD_INV_WAREHOUSE", "LARGE"))
cur = con.cursor()
cur.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 3000")
t0 = time.time()
cur.execute(sql)
res = [tuple(d[0] for d in cur.description)] + cur.fetchall()
with open(OUT, "a", encoding="utf-8") as f:
    f.write(f"\n== 5 Omega Sep-26 txns and agentic txns, in vs out of Josh's view panels ({time.time() - t0:.0f}s)\n" + "\n".join(map(str, res)) + "\n")
print(res)
