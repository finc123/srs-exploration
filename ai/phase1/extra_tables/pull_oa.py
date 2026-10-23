import snowflake.connector as sc, pandas as pd
sql = """WITH hs AS (SELECT subject_id, CASE
     WHEN subject = 'ChatGPT - Your new plan' THEN 'signup'
     WHEN subject ILIKE 'ChatGPT - Your plan % not renew' THEN 'will_not_renew'
     WHEN subject ILIKE 'We%d love your feedback on why you canceled%' THEN 'cancel_feedback'
     WHEN subject ILIKE 'Your % access will end soon' THEN 'access_end_soon'
     WHEN subject ILIKE 'Final reminder: Your % access ends soon' THEN 'final_reminder'
     WHEN subject ILIKE 'Please update your % payment method' THEN 'update_payment'
     WHEN subject ILIKE '%payment was unsuccessful%' THEN 'payment_failed'
     WHEN subject ILIKE 'Don%t lose access to ChatGPT%' THEN 'dont_lose_access'
     WHEN subject ILIKE 'ChatGPT - Your updated plan' THEN 'updated_plan'
     WHEN subject ILIKE 'Welcome to ChatGPT Plus' THEN 'welcome_plus'
     WHEN subject ILIKE 'New sign-in to your % account' THEN 'signin' END k, subject
  FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAIL_HEADER WHERE domain='openai')
SELECT e.mailbox_id AS uid, e.email_sent_date AS dt, hs.k, hs.subject, e.email_type FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAILS e JOIN hs ON e.subject_id=hs.subject_id
WHERE hs.k IS NOT NULL"""
con = sc.connect(connection_name="default", warehouse="ANALYST_XL", network_timeout=3600)
cur = con.cursor(); cur.execute(sql); df = cur.fetch_pandas_all(); df.columns = [c.lower() for c in df.columns]
df.to_parquet("supra_openai_events.parquet", index=False); print(len(df)); print(df.groupby('k').agg(n=('uid','size'), mn=('dt','min'), mx=('dt','max')))
# monthly coverage of all openai emails
cur.execute("""SELECT DATE_TRUNC('month', e.email_sent_date) m, COUNT(*) n, COUNT(DISTINCT e.mailbox_id) mbx FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAILS e
 JOIN SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAIL_HEADER h ON e.subject_id=h.subject_id WHERE h.domain='openai' AND e.email_sent_date>='2023-01-01' GROUP BY 1 ORDER BY 1""")
print(cur.fetch_pandas_all().to_string())
