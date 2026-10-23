WITH h AS (SELECT subject_id, subject, from_addr FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAIL_HEADER WHERE domain='openai' AND from_addr NOT ILIKE '%@email.openai.com'),
e AS (SELECT e.email_type, e.mailbox_id, e.email_sent_date, h.subject, h.from_addr FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAILS e JOIN h ON e.subject_id=h.subject_id WHERE e.email_sent_date>='2025-10-01')
SELECT REGEXP_REPLACE(subject,'[0-9]','#') s, ANY_VALUE(email_type) t, COUNT(*) n, COUNT(DISTINCT mailbox_id) mbx FROM e
WHERE subject NOT ILIKE '%code%' AND subject NOT ILIKE '[Task%'
GROUP BY 1 ORDER BY 3 DESC LIMIT 45
