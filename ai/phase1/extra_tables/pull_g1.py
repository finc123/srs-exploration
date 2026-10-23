import snowflake.connector as sc
con = sc.connect(connection_name="default", warehouse="ANALYST_XL", network_timeout=3600); cur = con.cursor()
cur.execute("""WITH h AS (SELECT subject_id, subject FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAIL_HEADER WHERE domain='google' AND from_addr='googleone-noreply@google.com'
 AND (subject ILIKE '%plan has ended%' OR subject ILIKE '%cancel%' OR subject ILIKE '%will end%' OR subject ILIKE '%expir%'))
SELECT e.mailbox_id uid, e.email_sent_date dt, h.subject FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAILS e JOIN h ON e.subject_id=h.subject_id WHERE e.email_sent_date>='2024-01-01'""")
df = cur.fetch_pandas_all(); df.columns=[c.lower() for c in df.columns]; df.to_parquet("supra_googleone_end.parquet", index=False)
import re; df["s"]=df.subject.str.replace(r"[0-9]","#",regex=True).str.replace(r",\s*__.*$","",regex=True)
print(len(df)); print(df.s.value_counts().head(15).to_string())
