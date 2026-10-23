WITH h AS (SELECT subject_id FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAIL_HEADER WHERE domain='openai' AND subject = 'ChatGPT - Your new plan'),
s AS (SELECT DISTINCT e.mailbox_id, e.email_sent_date d FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAILS e JOIN h ON e.subject_id=h.subject_id WHERE e.email_sent_date BETWEEN '2026-01-01' AND '2026-08-31'),
i AS (SELECT DISTINCT mailbox_id, TO_DATE(email_sent_time) d FROM SHARE_NIQ.SRS.ITEMS_EXTENDED WHERE merchant_id=4070 AND order_date BETWEEN '2025-12-25' AND '2026-09-05'),
im AS (SELECT DISTINCT mailbox_id FROM SHARE_NIQ.SRS.ITEMS_EXTENDED WHERE order_date >= '2026-01-01'),
sm AS (SELECT s.mailbox_id, s.d, MAX(IFF(i.mailbox_id IS NOT NULL,1,0)) hit FROM s LEFT JOIN i ON i.mailbox_id=s.mailbox_id AND ABS(DATEDIFF(day,i.d,s.d))<=1 GROUP BY 1,2),
im2 AS (SELECT i.mailbox_id, i.d, MAX(IFF(s.mailbox_id IS NOT NULL,1,0)) hit FROM i LEFT JOIN s ON i.mailbox_id=s.mailbox_id AND ABS(DATEDIFF(day,i.d,s.d))<=1 WHERE i.d BETWEEN '2026-01-01' AND '2026-08-31' GROUP BY 1,2)
SELECT (SELECT COUNT(*) FROM sm) supra, (SELECT SUM(hit) FROM sm) supra_in_ie, (SELECT COUNT(*) FROM sm JOIN im USING (mailbox_id)) supra_mbx_in_ie,
       (SELECT COUNT(*) FROM im2) ie, (SELECT SUM(hit) FROM im2) ie_in_supra
