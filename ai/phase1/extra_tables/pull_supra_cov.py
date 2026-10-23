import snowflake.connector as sc
con = sc.connect(connection_name="default", warehouse="ANALYST_XL", network_timeout=7200)
cur = con.cursor(); cur.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 7200")
cur.execute("""SELECT mailbox_id AS uid, DATE_TRUNC('month', email_sent_date) AS m, COUNT(*) n
FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAILS WHERE email_sent_date >= '2025-01-01' GROUP BY 1,2""")
df = cur.fetch_pandas_all(); df.columns=[c.lower() for c in df.columns]
df.to_parquet("supra_mbx_month.parquet", index=False); print(len(df), df.uid.nunique())
