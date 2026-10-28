-- inv1_ratio.sql: read-only pulls for the GTA VI vs BF6 ratio investigation (2026-10-27).
-- Each block is run by inv1_ratio.py (pull step) into gta/.cache/inv1_<name>.parquet.
-- Blocks are separated by lines of the form "-- @name <name>".

-- @name titles
-- Mailbox-level rows for the comparison titles, each scoped to its pre-order window (+ launch month).
-- Broad description match here; base-game / platform / add-on classification is done in Python.
select mailbox_id, merchant_name, order_date, description, item_price, item_quantity, order_id,
       case
         when order_date between '2022-05-01' and '2022-11-30' and description ilike '%modern warfare%' then 'MWII'
         when order_date between '2022-03-01' and '2023-02-28' and description ilike '%hogwarts%' then 'HOGWARTS'
         when order_date between '2023-05-01' and '2023-11-15' and description ilike '%spider%man%2%' then 'SPIDERMAN2'
         when order_date between '2024-05-15' and '2024-11-30' and description ilike '%black ops%6%' then 'BO6'
         when order_date between '2025-06-01' and '2025-12-15' and description ilike '%black ops%7%' then 'BO7'
       end as title
from share_niq.srs.items_extended
where order_date between '2022-03-01' and '2025-12-15'
  and (   (order_date between '2022-05-01' and '2022-11-30' and description ilike '%modern warfare%')
       or (order_date between '2022-03-01' and '2023-02-28' and description ilike '%hogwarts%')
       or (order_date between '2023-05-01' and '2023-11-15' and description ilike '%spider%man%2%')
       or (order_date between '2024-05-15' and '2024-11-30' and description ilike '%black ops%6%')
       or (order_date between '2025-06-01' and '2025-12-15' and description ilike '%black ops%7%'))
  and merchant_name not in ('eBay','Etsy','Temu','TikTok','Mercari','Whatnot')

-- @name franchise
-- Monthly aggregates for annual console franchises and big AAA releases 2024-01..2026-10 (channel-share trend).
select date_trunc('month', order_date) mon, merchant_name, description,
       count(*) n_rows, count(distinct mailbox_id) n_mb, median(item_price) med_price
from share_niq.srs.items_extended
where order_date between '2024-01-01' and '2026-10-27'
  and description ilike any ('%madden nfl 2%', '%nba 2k2%', '%college football 2%', '%ea sports fc%', '%fc 25%', '%fc 26%', '%fc 27%',
                             '%call of duty%', '%black ops%', '%modern warfare%', '%battlefield%6%', '%monster hunter wilds%',
                             '%assassin%shadows%', '%ghost of y%', '%borderlands 4%', '%resident evil requiem%', '%007 first light%',
                             '%wolverine%', '%mafia%old country%', '%death stranding 2%', '%doom%dark ages%')
  and merchant_name not in ('eBay','Etsy','Temu','TikTok','Mercari','Whatnot')
  and merchant_name not ilike '% Cancellation'
group by 1, 2, 3

-- @name volume
-- Per-member PSN / Microsoft Store receipt volume by month for the active 6_12_12 panel (all members and a fixed
-- cohort that joined before 2024-01-01), plus total receipt rows as a parse/coverage control.
with p as (
  select m.mailbox_id, iff(m.entry_date < '2024-01-01', 1, 0) fixed
  from share_niq.srs.mailboxes_enhanced m
  join share_niq.srs.active_panel_users a on a.mailbox_id = m.mailbox_id and a.active_panel = '6_12_12_Month_Aging')
select date_trunc('month', i.order_date) mon, p.fixed,
       count(distinct i.mailbox_id) mb_any,
       count(*) rows_any,
       count_if(i.merchant_name = 'Sony Entertainment Network') rows_psn,
       count(distinct iff(i.merchant_name = 'Sony Entertainment Network', i.mailbox_id, null)) mb_psn,
       count_if(i.merchant_name = 'Sony Entertainment Network' and i.item_price > 0) rows_psn_paid,
       count(distinct iff(i.merchant_name = 'Sony Entertainment Network' and i.item_price > 0, i.mailbox_id, null)) mb_psn_paid,
       count_if(i.merchant_name = 'Sony Entertainment Network' and i.item_price >= 20 and i.description ilike '%(Game%') rows_psn_game,
       count(distinct iff(i.merchant_name = 'Sony Entertainment Network' and i.item_price >= 20 and i.description ilike '%(Game%', i.mailbox_id, null)) mb_psn_game,
       count_if(i.merchant_name = 'Microsoft store') rows_mss,
       count(distinct iff(i.merchant_name = 'Microsoft store', i.mailbox_id, null)) mb_mss,
       count_if(i.merchant_name = 'Microsoft store' and i.item_price >= 20) rows_mss_20,
       count(distinct iff(i.merchant_name = 'Microsoft store' and i.item_price >= 20, i.mailbox_id, null)) mb_mss_20,
       count(distinct iff(i.merchant_name in ('Steam','Origin','Epic Games'), i.mailbox_id, null)) mb_pc
from share_niq.srs.items_extended i
join p on p.mailbox_id = i.mailbox_id
where i.order_date between '2024-01-01' and '2026-10-26'
group by 1, 2

-- @name active_all
-- Receipt-active mailboxes per month across all mailboxes (denominator for raw-unit normalisation of old titles).
select date_trunc('month', order_date) mon, count(distinct mailbox_id) mb_any
from share_niq.srs.items_extended
where order_date between '2022-01-01' and '2026-10-26'
group by 1
