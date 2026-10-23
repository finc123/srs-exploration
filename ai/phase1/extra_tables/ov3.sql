WITH c AS (SELECT item_id, mailbox_id, merchant_id, order_date, description FROM SHARE_NIQ.SRS.CANCELLATION_ITEMS
           WHERE merchant_id IN (20122,3452,20191,4078,20139,20140) AND order_date >= '2022-01-01'
             AND (merchant_name||' '||COALESCE(description,'')) ILIKE ANY ('%chatgpt%','%chat gpt%','%openai%','%anthropic%','%claude%','%google ai%','%gemini%','%ai premium%','%grok%','%x premium%','%premium+%','%muse%','%power plan%','%perplexity%','%cursor%','%ai pro%')),
e AS (SELECT item_id FROM SHARE_NIQ.SRS.ITEMS_EXTENDED WHERE merchant_id IN (20122,3452,20191,4078,20139,20140) AND order_date >= '2021-12-01'),
act AS (SELECT mailbox_id FROM SHARE_NIQ.SRS.MAILBOXES_ENHANCED WHERE status='ACTIVE')
SELECT c.merchant_id, COUNT(*) n_ci_ai, COUNT_IF(e.item_id IS NULL) ci_only, COUNT_IF(e.item_id IS NULL AND c.mailbox_id IN (SELECT mailbox_id FROM act)) ci_only_active
FROM c LEFT JOIN e ON c.item_id=e.item_id GROUP BY 1 ORDER BY 1
