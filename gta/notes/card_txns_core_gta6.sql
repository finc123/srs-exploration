-- GTA VI pre-purchase detectability in EARNEST.COMMON.TXNS_CORE_V (2022 Consistent Shopper panel)
-- Read-only. Run 2026-10-27 via SRS MCP snowflake. Data through trans_date 2026-10-25 (BUILT_AT 2026-10-26).
-- Panel filter: WEIGHT_AGG_CS2022 IS NOT NULL (PANEL_START_DATE_AGG_CS2022 = 2022-01-01 for all such rows; static weight, 26 distinct values).

-- 0. Schema and selection
describe view EARNEST.COMMON.TXNS_CORE_V;
select * from EARNEST.COMMON.TXNS_CORE_SELECTION order by 1,2;  -- no Sony/MSFT/Valve/Epic/GameStop/TTWO/BBY/TGT selectors

-- 1. Brands present, panel check
select brand_id, brand_name, brand_symbol, count(*) n, sum(iff(weight_agg_cs2022 is not null,1,0)) n22, max(trans_date) maxd
from EARNEST.COMMON.TXNS_CORE_V where trans_date >= '2026-10-01' group by 1,2,3 order by n desc;

select min(panel_start_date_agg_cs2022), max(panel_start_date_agg_cs2022), count(distinct memid),
       count(distinct weight_agg_cs2022), sum(iff(weight_agg_cs2022 is null,1,0)), max(built_at)
from EARNEST.COMMON.TXNS_CORE_V where trans_date between '2026-09-01' and '2026-09-07';

-- 2. Descriptor search (GTA / publisher / console-store keywords) since 2026-05-01
select brand_name, distribution_brand_name, payment_brand_name, count(*) n, any_value(billing_description) ex
from EARNEST.COMMON.TXNS_CORE_V
where trans_date >= '2026-05-01'
  and (upper(billing_description) like '%GTA%' or upper(billing_description) like '%GRAND THEFT%' or upper(billing_description) like '%ROCKSTAR%'
       or upper(billing_description) like '%TAKE TWO%' or upper(billing_description) like '%TAKE-TWO%' or upper(billing_description) like '%TAKETWO%'
       or upper(billing_description) like '%PLAYSTATION%' or upper(billing_description) like '%SONY%' or upper(billing_description) like '%XBOX%'
       or upper(billing_description) like '%MICROSOFT%' or upper(billing_description) like '%STEAM%' or upper(billing_description) like '%VALVE%'
       or upper(billing_description) like '%EPIC GAMES%' or upper(billing_description) like '%GAMESTOP%' or upper(billing_description) like '%NINTENDO%'
       or upper(billing_description) like '%PSN%')
group by 1,2,3 order by n desc;

-- 3a. Price-bucket daily averages by retailer, windows around 25 Jun, 2026 vs 2025
with b as (
select trans_date d,
 case when brand_id=10127 then 'AMZN_COM' when brand_id=23513 then 'AMZN_MKT'
      when brand_id=93718 and channel='ONLINE' then 'WMT_ON' when brand_id=93718 then 'WMT_OFF'
      when brand_id=10315 then 'BBY' when brand_id=12734 then 'TGT' end grp,
 case when trans_amount=69.99 then 'X69.99' when trans_amount=79.99 then 'X79.99' when trans_amount=99.99 then 'X99.99'
      when trans_amount=129.99 then 'X129.99' when trans_amount between 74 and 87.99 then 'T74-88'
      when trans_amount between 105 and 142 then 'T105-142' else 'other' end bkt,
 weight_agg_cs2022 w, memid
from EARNEST.COMMON.TXNS_CORE_V
where weight_agg_cs2022 is not null and transtype='debit'
  and brand_id in (10127,23513,93718,10315,12734)
  and ((trans_date between '2026-05-01' and '2026-10-25') or (trans_date between '2025-05-01' and '2025-10-25'))
)
select year(d) yr, grp, bkt,
 sum(iff(dayofyear(d) between dayofyear(date_from_parts(year(d),6,4)) and dayofyear(date_from_parts(year(d),6,24)),1,0))/21 pre3w_daily,
 sum(iff(dayofyear(d) = dayofyear(date_from_parts(year(d),6,25)),1,0)) d0,
 sum(iff(dayofyear(d) between dayofyear(date_from_parts(year(d),6,25)) and dayofyear(date_from_parts(year(d),7,1)),1,0))/7 wk1_daily,
 sum(iff(dayofyear(d) between dayofyear(date_from_parts(year(d),7,2)) and dayofyear(date_from_parts(year(d),7,22)),1,0))/21 wk2_4_daily,
 sum(iff(dayofyear(d) between dayofyear(date_from_parts(year(d),9,1)) and dayofyear(date_from_parts(year(d),10,25)),1,0))/55 sepoct_daily
from b group by 1,2,3 order by 2,3,1;

-- 3b. Daily around launch (2026)
select trans_date d,
 sum(iff(brand_id in (10127,23513) and trans_amount in (69.99,79.99),1,0)) amzn_x6979,
 sum(iff(brand_id in (10127,23513) and trans_amount in (99.99,129.99),1,0)) amzn_x99129,
 sum(iff(brand_id in (10127,23513) and trans_amount between 74 and 87.99,1,0)) amzn_t74,
 sum(iff(brand_id in (10127,23513),1,0)) amzn_all,
 sum(iff(brand_id=93718 and trans_amount in (69.99,79.99),1,0)) wmt_x6979,
 sum(iff(brand_id=93718 and channel='ONLINE' and trans_amount between 74 and 87.99,1,0)) wmton_t74,
 sum(iff(brand_id=93718 and channel='ONLINE',1,0)) wmton_all
from EARNEST.COMMON.TXNS_CORE_V
where weight_agg_cs2022 is not null and transtype='debit' and brand_id in (10127,23513,93718)
  and trans_date between '2026-06-15' and '2026-07-10'
group by 1 order by 1;

-- 3c. Prime Day 2025 mix check (tax-inclusive bucket share of Amazon debits)
select trans_date d, sum(iff(trans_amount in (69.99,79.99),1,0)) amzn_x6979,
 sum(iff(trans_amount between 74 and 87.99,1,0)) amzn_t74, count(*) amzn_all, round(100*amzn_t74/amzn_all,2) t74_share
from EARNEST.COMMON.TXNS_CORE_V
where weight_agg_cs2022 is not null and transtype='debit' and brand_id in (10127,23513)
  and trans_date between '2025-07-01' and '2025-07-15'
group by 1 order by 1;

-- 3d. Weekly exact-price counts (week 0 = 25 Jun-1 Jul), raw / weighted / unique members, 2026 vs 2025
with b as (
select year(trans_date) yr,
 floor(datediff(day, date_from_parts(year(trans_date),6,25), trans_date)/7) wk,
 iff(brand_id=93718,'WMT','AMZN') grp, trans_amount a, weight_agg_cs2022 w, memid
from EARNEST.COMMON.TXNS_CORE_V
where weight_agg_cs2022 is not null and transtype='debit' and brand_id in (10127,23513,93718)
  and ((trans_date between '2026-05-07' and '2026-10-21') or (trans_date between '2025-05-07' and '2025-10-21'))
  and trans_amount in (69.99,79.99,99.99,129.99)
)
select grp, wk,
 sum(iff(yr=2026,1,0)) n26, round(sum(iff(yr=2026,w,0))) wn26, count(distinct iff(yr=2026,memid,null)) mem26,
 sum(iff(yr=2026 and a in (69.99,79.99),1,0)) n26_std,
 sum(iff(yr=2025,1,0)) n25, sum(iff(yr=2025 and a in (69.99,79.99),1,0)) n25_std
from b group by 1,2 order by 1,2;

-- 3e. Best Buy / Target rows are delivery-app only
select brand_name, distribution_brand_name, payment_brand_name, count(*) n, any_value(billing_description) ex
from EARNEST.COMMON.TXNS_CORE_V where trans_date between '2026-09-01' and '2026-09-30' and brand_id in (10315,12734)
group by 1,2,3 order by n desc;
