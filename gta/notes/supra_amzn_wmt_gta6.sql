-- GTA VI pre-orders at Amazon / Walmart in NIQ email-header feeds
-- Written 2026-10-27. All read-only. Run through the local connector (connection_name="default").
-- Summary: supra_amzn_wmt_gta6.md

------------------------------------------------------------------------------------------
-- 1. Inventory: every SUPRA-named object in the account
------------------------------------------------------------------------------------------
show views  like '%SUPRA%' in account;   -- 4 in SHARE_NIQ.SRS + 2 in SHARE_NIQ."TRIAL-THROUGH-2025-12-31"
show tables like '%SUPRA%' in account;   -- only SRS_SLICE.{ALGN,RIVN,ROKU}.*_SUPRA derived tables

select table_name, column_name, data_type
from share_niq.information_schema.columns
where table_name ilike '%SUPRA%'
order by table_schema, table_name, ordinal_position;

------------------------------------------------------------------------------------------
-- 2. Domain coverage: Amazon and Walmart are NOT in the production SUPRA feed
------------------------------------------------------------------------------------------
-- Production quality feed: 23 domains (google, etsy, netflix, airbnb, ... roblox, openai ...)
select domain, top_level_domain, count(*) n_subjects
from share_niq.srs.supra_quality_merchant_email_header
group by 1, 2 order by n_subjects desc;

-- No amazon/walmart by domain or sender address (0 rows)
select domain, count(*) from share_niq.srs.supra_quality_merchant_email_header
where domain ilike any ('%amazon%', '%walmart%') or from_addr ilike any ('%amazon%', '%walmart%')
group by 1;

-- Non-quality feed: 3 domains only (currentbody, 360incentives, invisalign)
select domain, count(*) from share_niq.srs.supra_non_quality_merchant_email_header group by 1;

-- The trial schema does carry amazon (940M subjects) and walmart (58M) but ends 2025-12-31
select domain, count(*) n
from share_niq."TRIAL-THROUGH-2025-12-31".supra_quality_merchant_email_header
group by 1 order by n desc;
select min(email_sent_date), max(email_sent_date)
from share_niq."TRIAL-THROUGH-2025-12-31".supra_quality_merchant_emails
where email_sent_date >= '2025-01-01';                       -- 2025-01-01 .. 2025-12-31

-- Production SUPRA freshness (max 2026-10-20)
select min(email_sent_date), max(email_sent_date) from share_niq.srs.supra_quality_merchant_emails;

-- GTA subjects in production SUPRA exist only for unrelated domains (google/netflix/... = noise)
select domain, count(*) n
from share_niq.srs.supra_quality_merchant_email_header
where subject ilike any ('%grand theft%', '%gta%', '%theft auto%', '%rockstar%')
group by 1 order by n desc;

------------------------------------------------------------------------------------------
-- 3. Alternative: SHARE_NIQ.SRS.EMAIL_HEADER (Slice receipt email headers, linked by ORDER_ID)
--    Columns: EXTRACT_ID, MESSAGE_ORDER_ID, MESSAGE_ID, ORDER_ID, MERCHANT_ID, MERCHANT_NAME,
--    ORDER_DATE, EMAIL_SENT_DATE, SEQUENCE, SUBJECT, SUBJECT_KEYWORDS, LOCAL_PART, DOMAIN,
--    TOP_LEVEL_DOMAIN, AUX_DATA, STATUS. ~36s per day scanned; pull month by month.
------------------------------------------------------------------------------------------
-- Coverage on launch day
select merchant_name, domain, count(*) n, count(subject) n_subj,
       sum(iff(subject ilike '%grand theft%', 1, 0)) gta
from share_niq.srs.email_header
where email_sent_date = '2026-06-25' and domain in ('amazon', 'walmart')
group by all order by n desc;

-- Discovery pull (run per month, 2026-05 .. 2026-10)
select h.*,
       regexp_like(h.subject, '.*(GRAND THEFT|THEFT AUTO|\\bGTA|ROCKSTAR).*', 'is') is_gta
from share_niq.srs.email_header h
where h.email_sent_date between :month_start and :month_end
  and (regexp_like(h.subject, '.*(GRAND THEFT|THEFT AUTO|\\bGTA|ROCKSTAR).*', 'is')
       or (h.domain = 'walmart' and regexp_like(h.subject, '.*(PRE-?ORDER).*', 'is')));

-- Weekly Amazon / Walmart header volume and share of rows with a non-null subject (2026)
select date_trunc('week', email_sent_date) wk, domain, count(*) n, count(subject) n_with_subject
from share_niq.srs.email_header
where email_sent_date >= '2026-01-01' and domain in ('amazon', 'walmart')
group by 1, 2 order by 1, 2;

-- Freshness (rows to 2026-10-26; subjects back-fill over ~5-7 days)
select email_sent_date, domain, count(*) n, count(subject) n_subj
from share_niq.srs.email_header
where email_sent_date >= '2026-10-14' and domain in ('amazon', 'walmart')
group by 1, 2 order by 1, 2;

------------------------------------------------------------------------------------------
-- 4. RECOMMENDED FILTER: GTA VI game subjects at Amazon / Walmart (email_header)
------------------------------------------------------------------------------------------
select h.email_sent_date, h.merchant_name, h.order_id, h.local_part, h.subject,
       case when h.subject ilike 'Ordered:%'  then 'order confirmation'
            when h.subject ilike 'Canceled:%' then 'cancellation'
            when h.subject ilike 'Shipped:%'  then 'shipped'
            when h.subject ilike 'Delivered:%' then 'delivered' else 'other' end as template,
       regexp_substr(h.subject, 'Grand Theft Auto VI, ([PX])', 1, 1, 'e') as wmt_platform  -- P=PS5, X=Xbox
from share_niq.srs.email_header h
where h.email_sent_date >= '2026-06-24'
  and h.domain in ('amazon', 'walmart')
  and h.subject like '%Grand Theft Auto VI%'
  and regexp_like(h.subject, '.*Grand Theft Auto VI( __|,).*', 's')   -- 'VI:' = the soundtrack album
  ;

------------------------------------------------------------------------------------------
-- 5. Overlap with Slice items (join key = ORDER_ID; email_header has no user/mailbox column)
------------------------------------------------------------------------------------------
-- 5a. Items behind every header order with a GTA VI subject (literal ORDER_ID list from step 4)
select * from share_niq.srs.items_extended
where order_date >= '2026-06-01' and order_id in (/* 243 order_ids from step 4 */);

-- 5b. All header rows for the Slice Amazon / Walmart GTA VI orders (literal ORDER_ID list
--     from slice_items_gta6.sql recommended filter, merchants Amazon + Walmart Cancellation)
select * from share_niq.srs.email_header
where email_sent_date >= '2026-06-20' and order_id in (/* 309 Slice order_ids */);

------------------------------------------------------------------------------------------
-- 6. US_MERCHANT_EMAILS_FLATTEN (non-SUPRA, has user/mailbox ids) - launch-week check
--    Result: 0 rows (no walmart domain; amazon rows are NOT_A_RECEIPT marketing mail). ~42 min.
------------------------------------------------------------------------------------------
select * from share_niq.srs.us_merchant_emails_flatten
where email_sent_date between '2026-06-24' and '2026-07-01'
  and (domain ilike '%walmart%' or (domain = 'amazon' and subject ilike '%grand theft%'));
