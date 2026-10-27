-- Console-owner base for GTA VI pre-order scaling (NIQ Slice e-receipts)
-- Written 2026-10-27. All read-only; results cached as parquet under gta/.cache/ and classified in
-- pandas by notes/console_owners_rules.py + notes/console_owners.py (rules live in Python, not SQL,
-- so they can be iterated on the cached description aggregate without rescanning ~6.5bn rows).
-- Runtime on ANALYST_XL via local connector: q_desc ~90s, q_store_mb ~50s, q_rows ~3-4 min,
-- q_mb_activity ~2 min, SUPRA per-year loop ~1 min total.

------------------------------------------------------------------------------------------
-- 0. Inventory
------------------------------------------------------------------------------------------
-- mailbox tables: MAILBOXES_ENHANCED has ENTRY_DATE (= join date), EXIT_DATE, STATUS, PANEL_SOURCE
select table_name, column_name, data_type from share_niq.information_schema.columns
where table_schema='SRS' and table_name in ('MAILBOXES_ENHANCED','ACTIVE_PANEL_USERS',
  'SUPRA_QUALITY_MERCHANT_EMAIL_HEADER','SUPRA_QUALITY_MERCHANT_EMAILS') order by 1, ordinal_position;

select count(*) n, count(distinct mailbox_id) mb, min(entry_date), max(entry_date),
       sum(iff(entry_date<'2020-06-01',1,0)) pre2020, sum(iff(exit_date is null,1,0)) no_exit
from share_niq.srs.mailboxes_enhanced;                         -- 10,747,158 mailboxes; 4,830,124 joined pre Jun-2020

select active_panel, panel_type, count(*) from share_niq.srs.active_panel_users group by 1,2;
                                                                -- 6_12_12_Month_Aging = 1,076,109; FULL = 4,189,446

-- SUPRA domains: only 23 quality domains (google, netflix, roblox, openai, ...). No playstation / sony / xbox /
-- microsoft domain in either quality or non-quality header tables.
select 'Q' t, count(distinct domain) nd, listagg(distinct domain, ',') within group (order by domain)
from share_niq.srs.supra_quality_merchant_email_header;
select domain, subject, count(*) n from share_niq.srs.supra_quality_merchant_email_header
where subject ilike any ('%ps5%','%playstation%','%xbox%') group by 1,2 order by 3 desc limit 60;

-- console merchants in items
select merchant_name, count(*) n, count(distinct mailbox_id) mb, min(order_date), max(order_date)
from share_niq.srs.items_extended
where merchant_name ilike any ('%sony%','%playstation%','%xbox%','%microsoft%','%psn%')
group by 1 order by 2 desc;

-- q_items_by_year: receipt-active mailboxes per year (denominator for the by-year sanity check)
select year(order_date) y, count(*) n, count(distinct mailbox_id) mb
from share_niq.srs.items_extended group by 1 order by 1;

------------------------------------------------------------------------------------------
-- q_desc  (-> .cache/desc.parquet)
------------------------------------------------------------------------------------------
select merchant_name, description,
       count(*) n_rows, count(distinct mailbox_id) n_mb,
       median(item_price) med_price, min(item_price) min_price, max(item_price) max_price,
       min(order_date) first_date, max(order_date) last_date,
       hash(description) h
from share_niq.srs.items_extended
where description ilike any ('%ps5%','%ps 5%','%ps4%','%ps 4%','%ps3%','%playstation%','%play station%',
                             '%xbox%','%x box%','%series x%','%dualsense%','%dual sense%','%dualshock%',
                             '%psvr%','%ps vr%','%game pass%','%gamepass%','%psn%','%ps plus%')
   or merchant_name in ('Sony Entertainment Network','Microsoft store','Sony')
group by merchant_name, description
;

------------------------------------------------------------------------------------------
-- q_store_mb  (-> .cache/store_mb.parquet)
------------------------------------------------------------------------------------------
select mailbox_id, merchant_name, min(order_date) first_date, max(order_date) last_date, count(*) n_rows,
       count_if(order_date >= '2020-11-12') n_rows_post_ps5
from share_niq.srs.items_extended
where merchant_name in ('Sony Entertainment Network','Microsoft store')
group by 1,2
;

------------------------------------------------------------------------------------------
-- q_rows  (-> .cache/rows.parquet)
------------------------------------------------------------------------------------------
select mailbox_id, merchant_name, hash(description) h, order_date, item_price
from share_niq.srs.items_extended
where (merchant_name not in ('Sony Entertainment Network','Microsoft store')
       and description ilike any ('%ps5%','%ps 5%','%ps4%','%ps 4%','%ps3%','%playstation%','%play station%',
                             '%xbox%','%x box%','%series x%','%dualsense%','%dual sense%','%dualshock%',
                             '%psvr%','%ps vr%','%game pass%','%gamepass%','%psn%','%ps plus%'))
   or (merchant_name = 'Sony Entertainment Network'
       and description ilike any ('%ps5%','%ps 5%','%playstation%5%','%astro%playroom%'))
   or (merchant_name = 'Microsoft store'
       and description ilike any ('%xbox%','%x box%','%series x%','%game pass%','%gamepass%'))
;

------------------------------------------------------------------------------------------
-- q_mb  (-> .cache/mb.parquet)
------------------------------------------------------------------------------------------
select m.mailbox_id, m.entry_date, m.exit_date, m.status, m.panel_source,
       iff(p.mailbox_id is not null, 1, 0) in_panel_61212
from share_niq.srs.mailboxes_enhanced m
left join share_niq.srs.active_panel_users p
  on p.mailbox_id = m.mailbox_id and p.active_panel = '6_12_12_Month_Aging'
;

------------------------------------------------------------------------------------------
-- q_mb_activity  (-> .cache/mb_activity.parquet)
------------------------------------------------------------------------------------------
select mailbox_id, min(order_date) first_order, max(order_date) last_order, count(*) n_items
from share_niq.srs.items_extended
where merchant_name not ilike '% Cancellation'
group by 1
;

------------------------------------------------------------------------------------------
-- q_gta  (-> .cache/gta.parquet)
------------------------------------------------------------------------------------------
select distinct t.mailbox_id, t.merchant_name, t.order_date, t.description
from share_niq.srs.items_extended t
where t.order_date >= '2026-06-24'
  and t.description ilike '%grand theft auto%'
  and regexp_like(t.description, '.*GRAND THEFT AUTO[^A-Z0-9]{0,3}VI([^A-Z0-9].*|$)', 'is')
  and not regexp_like(t.description,
        '.*(UPGRADE|DUALSENSE|CONTROLLER|ALBUM|VINYL|\bCD\b|POSTER|SHIRT|\bTEE\b|UNOFFICIAL|COVER ART).*', 'is')
  and t.merchant_name not in ('eBay','Etsy','Temu','TikTok','Mercari','Whatnot')
  and t.merchant_name not ilike '% Cancellation'
;

------------------------------------------------------------------------------------------
-- q_supra_subj  (-> .cache/supra_subj.parquet)
------------------------------------------------------------------------------------------
select subject_id, domain, subject from share_niq.srs.supra_quality_merchant_email_header
where domain = 'google' and (
  regexp_like(subject, '^(__ )*(XBOX|XBOX GAME PASS|XBOX GAME PASS \(BETA\)|XBOX FAMILY SETTINGS|XBOX BETA|XBOX GAME STREAMING \(PREVIEW\)|PLAYSTATION APP|PLAYSTATION MESSAGES.*)( AND [0-9]+ MORE APPS?)? INSTALLED ON .*', 'i')
  or regexp_like(subject, '^(__ )*INSTALLED (XBOX|XBOX GAME PASS|XBOX GAME PASS \(BETA\)|XBOX FAMILY SETTINGS|XBOX BETA|XBOX GAME STREAMING \(PREVIEW\)|PLAYSTATION APP|PLAYSTATION MESSAGES.*)$', 'i')
  or regexp_like(subject, '.*(XBOX LIVE|PLAYSTATION NETWORK).*NOW HAS ACCESS.*', 'i')
  or regexp_like(subject, '.*LINKED XBOX TO .*GOOGLE ACCOUNT.*', 'i'))
;

------------------------------------------------------------------------------------------
-- q_supra_mb: SUPRA emails for the subject_ids above, one calendar year at a time (an
-- email_sent_date filter is required or the join times out). Run by .cache/supra_pull.py
------------------------------------------------------------------------------------------
select e.mailbox_id, e.subject_id, min(e.email_sent_date) first_date, count(*) n
from share_niq.srs.supra_quality_merchant_emails e
where e.email_sent_date between '{y}-01-01' and '{y}-12-31'
  and e.subject_id in (/* 4,656 subject_ids from q_supra_subj */)
group by 1,2;
