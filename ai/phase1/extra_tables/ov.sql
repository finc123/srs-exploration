WITH c AS (SELECT item_id, order_id, mailbox_id, merchant_id, merchant_name, order_date, description FROM SHARE_NIQ.SRS.CANCELLATION_ITEMS
           WHERE merchant_id IN (20122,3452,20191,4078,20139,20140,4213) AND order_date >= '2025-10-01'),
e AS (SELECT item_id, order_id, mailbox_id, merchant_id, order_date FROM SHARE_NIQ.SRS.ITEMS_EXTENDED
           WHERE merchant_id IN (20122,3452,20191,4078,20139,20140,4213) AND order_date >= '2025-10-01')
SELECT COALESCE(c.merchant_id, e.merchant_id) mid, COUNT(c.item_id) n_ci, COUNT(e.item_id) n_ie,
  COUNT_IF(c.item_id IS NOT NULL AND e.item_id IS NOT NULL) both_, COUNT_IF(e.item_id IS NULL) ci_only, COUNT_IF(c.item_id IS NULL) ie_only
FROM c FULL OUTER JOIN e ON c.item_id = e.item_id GROUP BY 1 ORDER BY 1
