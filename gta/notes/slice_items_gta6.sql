-- GTA VI pre-purchases in Slice e-receipt item data (SRS_SLICE.COMMON.ITEMS_V)
-- Written 2026-10-27. All read-only.
--
-- PERFORMANCE NOTE: ITEMS_V is a view over share_niq.srs.items_extended LEFT JOINed to
-- mailboxes_enhanced / active_panel_users ('6_12_12_Month_Aging') / quality_merchants.
-- Text scans over >1 week of ITEMS_V time out in the SRS MCP tool; scan the base table
-- share_niq.srs.items_extended for discovery (same rows and item columns), and use ITEMS_V
-- (or the joins below) only when you need PANEL / QUALITY. A full Jun-Oct scan of the base
-- table took ~5 min on the DATA_TEAM warehouse through the local connector.

------------------------------------------------------------------------------------------
-- 1. Schema + view definition
------------------------------------------------------------------------------------------
select column_name, data_type
from SRS_SLICE.INFORMATION_SCHEMA.COLUMNS
where table_schema = 'COMMON' and table_name = 'ITEMS_V'
order by ordinal_position;

select get_ddl('view', 'SRS_SLICE.COMMON.ITEMS_V');

------------------------------------------------------------------------------------------
-- 2. Freshness
------------------------------------------------------------------------------------------
select max(order_date) mx_order, max(last_updated) mx_upd, max(email_sent_time) mx_email, count(*) n
from SRS_SLICE.COMMON.ITEMS_V
where order_date >= '2026-10-01';

------------------------------------------------------------------------------------------
-- 3. Discovery: every GTA-ish description since May (pulled locally, then classified in pandas)
------------------------------------------------------------------------------------------
select *
from share_niq.srs.items_extended
where order_date >= '2026-05-01'
  and (description ilike '%grand theft%' or regexp_like(description, '.*\\bGTA.*', 'is'));

-- Candidate GTA VI / GTA 6 regex (also catches 'GTA 6', 'GTA6', 'GTAVI'; excludes 'VICE CITY',
-- 'GTA V', 'GTA ONLINE', 'GTA+', Trilogy). In practice every true game row says 'Grand Theft Auto VI';
-- short forms ('GTA 6', 'GTA6') appear only on eBay/Etsy/Temu/TikTok merch.
--   regexp_like(description, '.*(GRAND THEFT AUTO|\\bGTA)[^A-Z0-9]{0,3}(VI|6)([^A-Z0-9].*|$)', 'is')

------------------------------------------------------------------------------------------
-- 4. RECOMMENDED FILTER: GTA VI base game (Standard + Ultimate), order receipts
------------------------------------------------------------------------------------------
with gta6 as (
  select t.*,
         replace(t.merchant_name, ' Cancellation', '')                    as merchant,
         t.merchant_name ilike '% Cancellation'                           as is_cancel,
         iff(t.description ilike '%ultimate%', 'Ultimate', 'Standard')    as edition,
         case when t.merchant_name ilike 'Sony Entertainment Network%' then 'PS5'
              when t.merchant_name ilike 'Microsoft store%'            then 'Xbox'
              when regexp_like(t.description, '.*(PLAY ?STATION|PS5).*', 'is') then 'PS5'
              when t.description ilike '%xbox%'                         then 'Xbox' end as platform,
         iff(t.digital_good = 'Y', 'Digital (PSN / MS Store)', 'Retail code-in-box') as fmt,
         t.item_price * greatest(t.item_quantity, 1)                      as usd
  from share_niq.srs.items_extended t
  where t.order_date >= '2026-06-24'
    and t.description ilike '%grand theft auto%'
    and regexp_like(t.description, '.*GRAND THEFT AUTO[^A-Z0-9]{0,3}VI([^A-Z0-9].*|$)', 'is')
    and not regexp_like(t.description,
          '.*(UPGRADE|DUALSENSE|CONTROLLER|ALBUM|VINYL|\\bCD\\b|POSTER|SHIRT|\\bTEE\\b|UNOFFICIAL|COVER ART).*', 'is')
    and t.merchant_name not in ('eBay', 'Etsy', 'Temu', 'TikTok', 'Mercari', 'Whatnot')
)
select merchant, is_cancel,
       count(*) rows_, count(distinct order_id) orders, count(distinct user_id) users,
       sum(item_quantity) units, round(sum(usd), 2) usd,
       min(order_date) first_date,
       sum(iff(edition = 'Ultimate', 1, 0)) ultimate_rows,
       sum(iff(platform = 'PS5', 1, 0)) ps5_rows, sum(iff(platform = 'Xbox', 1, 0)) xbox_rows
from gta6
group by 1, 2
order by is_cancel, rows_ desc;

-- 4b. Ultimate Edition upgrade add-on ($20) tracked separately
--   ... same filter but: and t.description ilike '%ultimate edition upgrade%'

-- 4c. Panel / quality flags (ITEMS_V columns) for the same rows: join back on order_id + item_id
--   select v.panel, v.quality, count(*) from SRS_SLICE.COMMON.ITEMS_V v join gta6 g using (order_id, item_id)
--   where v.order_date >= '2026-06-24' and v.description ilike '%grand theft auto%' group by 1, 2;

------------------------------------------------------------------------------------------
-- 5. Weekly trend per merchant (launch-week inflection)
------------------------------------------------------------------------------------------
-- (reuse the gta6 CTE)
-- select date_trunc('week', order_date) wk, merchant, count(*) rows_, count(distinct user_id) users
-- from gta6 where not is_cancel group by 1, 2 order by 1, 2;

------------------------------------------------------------------------------------------
-- 6. Soft dedupe (same user x merchant x description x order_total x day, different order_id)
------------------------------------------------------------------------------------------
-- select count(*) from (
--   select user_id, merchant, description, order_total, order_date, count(*) n
--   from gta6 where not is_cancel group by 1,2,3,4,5 having n > 1);

------------------------------------------------------------------------------------------
-- 7. Blind-spot check: are the stores present at all, and do they carry item descriptions?
------------------------------------------------------------------------------------------
select merchant_name, count(*) n, count(item_price) n_priced, count(distinct order_id) orders,
       sum(iff(description ilike '%playstation%' or description ilike '%xbox%'
               or description ilike '%nintendo switch%', 1, 0)) n_console_items
from share_niq.srs.items_extended
where order_date between '2026-06-25' and '2026-06-26'
  and merchant_name in ('Walmart', 'Walmart Cancellation', 'Rockstar Games', 'Steam', 'Sony',
                        'Sony Entertainment Network', 'Microsoft store', 'Epic Games', 'Nintendo',
                        'GameStop', 'Best Buy', 'Target', 'Amazon', 'Costco', 'Sam''s Club')
group by 1 order by 2 desc;

select merchant_name, description, count(*) n
from share_niq.srs.items_extended
where order_date between '2026-06-24' and '2026-06-27'
  and merchant_name in ('Walmart', 'Rockstar Games')
  and (description ilike '%playstation 5%' or description ilike '%ps5%' or description ilike '%xbox series%'
       or description ilike '%theft%' or description ilike '%rockstar%' or merchant_name = 'Rockstar Games')
group by 1, 2 order by 3 desc limit 60;
