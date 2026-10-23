WITH c AS (SELECT item_id, order_id, mailbox_id, merchant_id, order_date, description FROM SHARE_NIQ.SRS.CANCELLATION_ITEMS
           WHERE merchant_id IN (20122,3452,20191,4078,20139,20140) AND order_date >= '2025-10-01'),
e AS (SELECT item_id, order_id, mailbox_id FROM SHARE_NIQ.SRS.ITEMS_EXTENDED
           WHERE merchant_id IN (20122,3452,20191,4078,20139,20140) AND order_date >= '2025-09-01'),
co AS (SELECT c.* FROM c LEFT JOIN e ON c.item_id=e.item_id WHERE e.item_id IS NULL)
SELECT co.merchant_id, COUNT(*) n, COUNT(DISTINCT co.mailbox_id) mbx,
  COUNT_IF(co.order_id IN (SELECT order_id FROM e)) order_in_ie,
  COUNT_IF(co.mailbox_id IN (SELECT mailbox_id FROM SHARE_NIQ.SRS.MAILBOXES_ENHANCED WHERE status='ACTIVE')) active_mbx,
  COUNT_IF(co.mailbox_id IN (SELECT DISTINCT mailbox_id FROM e)) mbx_in_ie
FROM co GROUP BY 1;
