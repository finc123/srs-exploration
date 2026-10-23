WITH hs AS (SELECT subject_id, CASE
     WHEN subject = 'ChatGPT - Your new plan' THEN 'signup'
     WHEN subject ILIKE 'ChatGPT - Your plan % not renew' THEN 'will_not_renew'
     WHEN subject ILIKE 'We%d love your feedback on why you canceled%' THEN 'cancel_feedback'
     WHEN subject ILIKE 'Your % access will end soon' THEN 'access_end_soon'
     WHEN subject ILIKE 'Final reminder: Your % access ends soon' THEN 'final_reminder'
     WHEN subject ILIKE 'Please update your % payment method' THEN 'update_payment'
     WHEN subject ILIKE '%payment was unsuccessful%' THEN 'payment_failed'
     WHEN subject ILIKE 'Don%t lose access to ChatGPT%' THEN 'dont_lose_access'
     WHEN subject ILIKE 'ChatGPT - Your updated plan' THEN 'updated_plan'
     WHEN subject ILIKE 'Welcome to ChatGPT Plus' THEN 'welcome_plus' END k
  FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAIL_HEADER WHERE domain='openai'),
ev AS (SELECT DISTINCT e.mailbox_id, e.email_sent_date d, hs.k FROM SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAILS e JOIN hs ON e.subject_id=hs.subject_id WHERE hs.k IS NOT NULL AND e.email_sent_date >= '2025-06-01')
SELECT k, DATE_TRUNC('month', d) m, COUNT(*) n, COUNT(DISTINCT mailbox_id) mbx FROM ev GROUP BY 1,2 ORDER BY 1,2
