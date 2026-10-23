WITH h AS (SELECT subject_id, subject, from_addr FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAIL_HEADER WHERE domain='openai'),
e AS (SELECT e.email_type, e.mailbox_id, e.email_sent_date, h.subject, h.from_addr FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAILS e JOIN h ON e.subject_id=h.subject_id WHERE e.email_sent_date>='2025-10-01')
SELECT email_type, from_addr, REGEXP_REPLACE(subject,'[0-9]','#') s, COUNT(*) n, COUNT(DISTINCT mailbox_id) mbx FROM e GROUP BY 1,2,3 QUALIFY ROW_NUMBER() OVER (PARTITION BY email_type ORDER BY n DESC)<=10 ORDER BY 1, 4 DESC
