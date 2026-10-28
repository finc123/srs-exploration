-- inv2: Roblox-related item rows in NIQ Slice (base table; ITEMS_V times out on text scans).
-- All history through 2026-10-27. Classification into channels is done in inv2_roblox.py.
-- ~8.5M rows, ~1 min on ANALYST_XL. Cached to .cache/roblox_rows.parquet.
select mailbox_id, merchant_name, order_date, order_id,
       left(description, 160) description, item_price, item_quantity, order_total
from share_niq.srs.items_extended
where order_date between '2015-01-01' and '2026-10-27'
  and (description ilike '%robux%' or description ilike '%roblox%' or merchant_name ilike 'roblox%')
