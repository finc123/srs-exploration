WITH h AS (SELECT subject_id, CASE WHEN subject ILIKE '%plan has ended%' OR subject ILIKE '%cancel%' OR subject ILIKE '%will end%' OR subject ILIKE '%expir%' THEN 'end'
   WHEN subject ILIKE 'welcome%google ai%' THEN 'welcome_ai' END k
  FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAIL_HEADER WHERE domain='google' AND from_addr='googleone-noreply@google.com' AND subject ILIKE ANY ('%google ai%','%ai premium%','%gemini%','%google one%'))
SELECT k, DATE_TRUNC('month', e.email_sent_date) m, COUNT(*) n, COUNT(DISTINCT e.mailbox_id) mbx FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAILS e JOIN h ON e.subject_id=h.subject_id
WHERE k IS NOT NULL AND e.email_sent_date>='2025-06-01' GROUP BY 1,2 ORDER BY 1,2
