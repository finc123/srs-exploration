-- Rockstar Games / Take-Two parsing in Slice items + SUPRA email headers
-- Written 2026-10-27. All read-only (no tables created; the SUPRA join uses a literal IN list).
-- Run through the local connector: snowflake.connector.connect(connection_name="default", warehouse="ANALYST_L").
-- Classification and pivots were done in pandas on the pulled rows (rules are given as comments below).

------------------------------------------------------------------------------------------
-- A1. Inventory: quality / issue / SUPRA tables in SHARE_NIQ.SRS
------------------------------------------------------------------------------------------
select table_name from SHARE_NIQ.INFORMATION_SCHEMA.TABLES
where table_schema = 'SRS'
  and (table_name ilike '%supra%' or table_name ilike '%quality%' or table_name ilike '%merchant%')
order by 1;

------------------------------------------------------------------------------------------
-- A2. Rockstar / Take-Two merchant ids in Slice items (base table; ~50s)
--     Result: only merchant_id 3325 'Rockstar Games' has rows. 2K (1783) has none since 2023.
--     Zynga (20224) is Take-Two too but is mobile, not relevant here.
------------------------------------------------------------------------------------------
select merchant_name, merchant_id, count(*) rows_, count(distinct order_id) orders,
       count(distinct user_id) users, min(order_date) mn, max(order_date) mx
from share_niq.srs.items_extended
where order_date >= '2023-01-01'
  and (merchant_name ilike '%rockstar%' or merchant_name ilike '%take%two%' or merchant_name ilike '%take-two%'
       or merchant_name ilike '%2k%' or merchant_name ilike '%social club%')
group by 1, 2 order by 3 desc;

select * from share_niq.srs.merchant_ticker_mappings
where merchant_name ilike '%rockstar%' or merchant_name ilike '%take%two%' or ticker ilike 'TTWO%';

------------------------------------------------------------------------------------------
-- A3. Quality list, known issues, order-total-only list
------------------------------------------------------------------------------------------
select * from share_niq.srs.quality_merchants          where merchant_id = 3325;  -- present, NOTE null
select * from share_niq.srs.merchants_with_issues      where merchant_id = 3325;  -- Jun-2025 layout issue, 'Fixed' 2025-08-28
select * from share_niq.srs.order_total_only_merchants where merchant_id = 3325;  -- empty

------------------------------------------------------------------------------------------
-- A4. Pull every Rockstar row since 2024 (45k rows) -> pandas
------------------------------------------------------------------------------------------
select * from share_niq.srs.items_extended
where merchant_id = 3325 and order_date >= '2024-01-01';
-- pandas classification on DESCRIPTION:
--   startswith 'Welcome'                         -> Welcome/account ('Welcome to Rockstar Games', '...Social Club'); price NULL
--   'GTA+' and ('Payment' or 'Subscription')     -> GTA+ subscription ($7.99; B2G1 offer $15.98)
--   'Shark' (not Starter Pack / Bundle)          -> Shark Cards (GTA Online currency, PC)
--   'Gold Bars'                                  -> RDO Gold Bars
--   'Grand Theft Auto VI' / 'GTA VI'             -> GTA VI (none found)
--   else                                         -> PC game / bundle (GTA V $29.99, RDR2, GTA IV, Trilogy, ...)

------------------------------------------------------------------------------------------
-- A5. Rockstar-branded items at OTHER merchants since 2025 (context: PSN / Xbox / Steam; ~50s)
--     Used to test whether the Oct-2025 collapse in Rockstar Store Shark Card / PC game rows is
--     demand (should show at Steam too) or parsing (Rockstar only). Steam stays flat -> parsing.
------------------------------------------------------------------------------------------
select merchant_name, order_date, description, item_price, item_quantity, user_id
from share_niq.srs.items_extended
where order_date >= '2025-01-01' and merchant_id <> 3325
  and (description ilike '%rockstar games%' or description ilike '%shark card%' or description ilike '%shark cash%'
       or description ilike '%gta+%' or description ilike '%gta online%' or description ilike '%rockstar store%');

------------------------------------------------------------------------------------------
-- B1. SUPRA domains (header tables have no date; ~400M subject rows, 23 domains)
------------------------------------------------------------------------------------------
select domain || '.' || top_level_domain d, count(*) n
from share_niq.srs.supra_quality_merchant_email_header group by 1 order by 2 desc;
select domain || '.' || top_level_domain d, count(*) n
from share_niq.srs.supra_non_quality_merchant_email_header group by 1 order by 2 desc;

-- Is Rockstar a SUPRA domain? (No. Only false positives: rockstargo.com under netflix, teamrockstars.nl under google.)
select domain, top_level_domain, count(*) n_subj, count(distinct from_addr) n_from, min(from_addr)
from share_niq.srs.supra_quality_merchant_email_header
where domain ilike '%rockstar%' or domain ilike '%take2%' or domain ilike '%taketwo%' or domain ilike '%take-two%'
   or domain ilike '%socialclub%' or from_addr ilike '%rockstar%'
group by 1, 2;

------------------------------------------------------------------------------------------
-- B2. Subject search across all SUPRA domains (header only, ~90s) -> pandas
------------------------------------------------------------------------------------------
select domain, from_addr, subject_id, subject
from share_niq.srs.supra_quality_merchant_email_header
where subject ilike '%rockstar%' or subject ilike '%grand theft%' or regexp_like(subject, '.*\\bGTA\\b.*', 'is')
   or subject ilike '%gta vi%' or subject ilike '%gta 6%' or subject ilike '%gta6%' or subject ilike '%take-two%'
   or subject ilike '%red dead%' or subject ilike '%shark card%';
-- pandas groups (GTA VI regex: 'grand theft auto (vi|6)\b|gta ?(vi|6)\b', case-insensitive):
--   netflix + VI       -> 'Grand Theft Auto VI: An Extended Look' (Netflix title marketing / viewing nudges)
--   openai  + VI       -> ChatGPT scheduled-task updates tracking GTA VI news / pre-orders
--   google  + 'rockstar games' / 'Grand Theft Auto ... installed' -> Android installs, Google sign-in
--   google/spotify/roblox + VI -> misc (Google Forms, Calendar, Family Link, Google News)

------------------------------------------------------------------------------------------
-- B3. Email counts for those subject_ids (literal IN list of ~1,500 ids; ~60s with the date filter)
------------------------------------------------------------------------------------------
select subject_id, email_sent_date, mailbox_id, user_id, email_type
from share_niq.srs.supra_quality_merchant_emails
where email_sent_date >= '2024-01-01'
  and subject_id in ( /* ids from B2 */ );

select max(email_sent_date) from share_niq.srs.supra_quality_merchant_emails
where email_sent_date >= '2026-10-01';   -- 2026-10-20

------------------------------------------------------------------------------------------
-- B4. Other raw-email feed: US_MERCHANT_EMAILS PROMOTIONAL_EMAILS (DATA has domain, ticker, subject,
--     from_addr, email_sent_date). 12B rows; even a 0.5% row sample is slow (>10 min).
------------------------------------------------------------------------------------------
select feed_description, count(*) from share_niq.srs.us_merchant_emails group by 1 order by 2 desc;
select data:domain::string dom, data:ticker::string tk, count(*) n
from share_niq.srs.us_merchant_emails sample (0.5)
where feed_description = 'PROMOTIONAL_EMAILS'
  and (data:ticker::string in ('TTWO','SONY','MSFT','GME','EA') or data:domain::string ilike '%rockstar%'
       or data:domain::string ilike '%playstation%' or data:domain::string ilike '%xbox%')
group by 1, 2 order by 3 desc;
