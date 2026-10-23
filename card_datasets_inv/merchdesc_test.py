"""Can Prime Omega's per-merchant descriptor (MID_V1_0.MERCHDESC) find agentic (Stripe Link agent) transactions?
1. Forward: Muse's agentic Yodlee transactions for Sep 2026 -> same transaction in Omega (PARTNER_TRANSID) -> its MERCHDESC.
2. Reverse: MERCHIDs whose MERCHDESC matches the agentic pattern -> Omega transactions on those merchants in Sep 2026,
   and how many of those are in Yodlee feeds 3/4/6 (i.e. what Omega adds beyond Muse).
3. 279 PRIME_TAU (Tau panel, per-transaction BILLING_DESCRIPTION): agentic transactions in Sep 2026 (Muse can't see these).
Writes results/merchdesc_test.txt."""
import os, time
import snowflake.connector

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "merchdesc_test.txt")
O = "SHARE_CE_PRIME_ENRICHED_OMEGA_2822.PRIME_OMEGA"
AGENTIC = """({c} ILIKE '%linkagnt*%' OR (REGEXP_LIKE({c}, '(^|.*[^a-z.])link\\\\* .*', 'i')
              AND ({c} ILIKE '%www.link.co%' OR {c} ILIKE '%south san fra%')))"""
Q = {
    "1 forward: Muse agentic Sep-26 found in Omega, by MERCHDESC match": f"""
        WITH m AS (SELECT DISTINCT txn_id, day FROM SRS_MCP.META.MUSE_CARD_TXNS
                   WHERE signal = 'agentic' AND day >= '2026-09-01' AND day < '2026-10-01'),
        o AS (SELECT t.partner_transid, t.merchid FROM {O}.TRANS_V1_0 t
              WHERE t.trans_date >= '2026-08-28' AND t.trans_date < '2026-10-04' AND t.filedate >= '2026-08-28'
                AND t.partner_transid IN (SELECT txn_id FROM m))
        SELECT (SELECT COUNT(*) FROM m) AS muse_agentic, COUNT(DISTINCT o.partner_transid) AS found_in_omega,
               COUNT(DISTINCT IFF({AGENTIC.format(c='d.merchdesc')}, o.partner_transid, NULL)) AS merchdesc_agentic,
               COUNT(DISTINCT IFF(d.merchdesc ILIKE '%link%', o.partner_transid, NULL)) AS merchdesc_has_link
        FROM o LEFT JOIN {O}.MID_V1_0 d ON d.merchid = o.merchid""",
    "1b examples of Omega MERCHDESC for Muse agentic txns": f"""
        WITH m AS (SELECT DISTINCT txn_id, description FROM SRS_MCP.META.MUSE_CARD_TXNS
                   WHERE signal = 'agentic' AND day >= '2026-09-01' AND day < '2026-10-01')
        SELECT LEFT(m.description, 60), LEFT(d.merchdesc, 60), COUNT(*) FROM m
        JOIN {O}.TRANS_V1_0 t ON t.partner_transid = m.txn_id
             AND t.trans_date >= '2026-08-28' AND t.trans_date < '2026-10-04' AND t.filedate >= '2026-08-28'
        LEFT JOIN {O}.MID_V1_0 d ON d.merchid = t.merchid GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 15""",
    "2 reverse: Omega Sep-26 txns on agentic-descriptor merchants": f"""
        WITH mid AS (SELECT merchid FROM {O}.MID_V1_0 WHERE {AGENTIC.format(c='merchdesc')}),
        o AS (SELECT t.partner_transid, t.cardlinkid FROM {O}.TRANS_V1_0 t
              WHERE t.trans_date >= '2026-09-01' AND t.trans_date < '2026-10-01' AND t.filedate >= '2026-08-31'
                AND t.merchid IN (SELECT merchid FROM mid))
        SELECT (SELECT COUNT(*) FROM mid) AS agentic_merchids, COUNT(DISTINCT o.partner_transid) AS omega_agentic_txns,
               COUNT(DISTINCT o.cardlinkid) AS omega_agentic_members,
               COUNT(DISTINCT IFF(o.partner_transid IN (SELECT txn_id FROM SRS_MCP.META.MUSE_CARD_TXNS WHERE signal = 'agentic'),
                                  o.partner_transid, NULL)) AS also_in_muse
        FROM o""",
    "3 279 PRIME_TAU agentic Sep-26 (Tau panel; not in Yodlee)": f"""
        SELECT COUNT(DISTINCT earnest_transaction_id), COUNT(DISTINCT member_id)
        FROM SHARE_EARNEST_279.PRIME_TAU.SPEND_279_TRANSACTIONS_V3_0
        WHERE transaction_date >= '2026-09-01' AND transaction_date < '2026-10-01' AND file_create_date >= '2026-08-31'
          AND {AGENTIC.format(c='billing_description')}""",
}

con = snowflake.connector.connect(connection_name="default", warehouse=os.getenv("CARD_INV_WAREHOUSE", "LARGE"))
cur = con.cursor()
cur.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 3000")
with open(OUT, "a", encoding="utf-8") as f:
    for name, sql in Q.items():
        t = time.time()
        try:
            cur.execute(sql)
            res = [tuple(d[0] for d in cur.description)] + cur.fetchall()
        except Exception as e:
            res = [f"ERROR {str(e)[:300]}"]
        f.write(f"\n== {name} ({time.time() - t:.0f}s)\n" + "\n".join(map(str, res)) + "\n")
        f.flush()
