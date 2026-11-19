"""Daily Steam spend and total spend on card panels, for a Steam share-of-card-spend check against the e-receipt page.
US: Earnest Omega CS2022 panel, same denominator as ai/notebooks/card_ereceipt_rules.PANEL_SPEND_SQL (USD debits at
brand-tagged merchants), Steam = Earnest brand 12648. EU5: Fable consumer accounts, by transaction type, Steam by descriptor.
US (vetted): Consumer Edge MU daily signal, Steam brand / all-industry total spend.
EU5 (vetted): fable.common.machine_data_daily_enhanced_srs_agg, steam games tag / all merchant tags.
Run: python pull_card_steam.py us|eu|mu|fable_agg  (writes ../data/card_steam_<us|eu|us_mu|eu_agg>.parquet)"""
import sys
from pathlib import Path
import polars as pl
import snowflake.connector

OMEGA = "SHARE_CE_PRIME_ENRICHED_OMEGA_2822.PRIME_OMEGA"
PANEL = "aggregate_consistent_shopper_2022_v2"
STEAM_BRAND = 12648
START, STOP = "2020-01-01", "2026-11-19"   # raw US pull (us) keeps its own 2023+ year list
FABLE = {"UK": "UK_V2_TXN", "DE": "DE_V2_TXN", "FR": "FR_V3_TXN", "ES": "ES_V2_TXN", "IT": "IT_V2_TXN"}
# Steam card descriptors seen in Fable (no backslashes: passes through to Snowflake unchanged)
FABLE_STEAM = "STEAMGAMES|STEAM ?PURC|STEAM GAMES?|KLARNA.{0,2}STEAM|WL .?STEAM|VALVE CORP|^STEAM$"
OUT = Path(__file__).resolve().parent.parent / "data"

US_SQL = f"""
with panel as (
    select cardlinkid from {OMEGA}.CARDLINK_PANEL_V1_0 p
    where panel = '{PANEL}'
      and not exists (select 1 from {OMEGA}_STATIC.AFFECTED_ACCOUNTS_092026 a where a.cardlinkid = p.cardlinkid))
select t.trans_date as date, sum(t.trans_amount) as total, sum(iff(m.main_brand_id = {STEAM_BRAND}, t.trans_amount, 0)) as steam
from {OMEGA}.TRANS_V1_0 t
join panel p on p.cardlinkid = t.cardlinkid
join {OMEGA}.MID_MATCH_V1_0 m on m.merchid = t.merchid and m.main_brand_id is not null
where t.filedate >= dateadd(day, -7, '{{start}}'::date) and t.filedate < dateadd(day, 60, '{{stop}}'::date)
  and t.trans_date >= '{{start}}' and t.trans_date < '{{stop}}'
  and t.transtype = 'debit' and t.currency = 'USD' and t.trans_amount > 0
group by 1
"""

EU_SQL = " union all ".join(f"""
select '{c}' as country, txndate as date, txntype, sum(-spendout) as total,
       sum(iff(regexp_instr(upper(description), '{FABLE_STEAM}') > 0, -spendout, 0)) as steam
from share_fable.fable_signal.{t}
where txndate >= '{START}' and txndate < '{STOP}' and usertype = 'C' and spendout < 0 and -spendout <= 10000
group by all""" for c, t in FABLE.items())

# Consumer Edge MU aggregate (cwang's recommendation for spend share): projected US spend, Steam brand vs all-industry total,
# summed over every CBSA, DISTRIBUTION channel dropped (a delivery-app overlay, never a main brand; the ALL rows have none)
MU = "CER.CER_1415_MU_DAILY_SIGNAL"
MU_SQL = f"""
with s as (
    select trans_date as date, sum(spend_amount) as steam from {MU}.DAY_SYM_BRAND_CHANNEL_ALL
    where brand_id = {STEAM_BRAND} and channel <> 'DISTRIBUTION' group by 1),
t as (
    select trans_date as date, sum(spend_amount_usd) as total from {MU}.TOTAL_GEOGRAPHY_CHANNEL_DAY
    where subindustry_id = 'NA' and industry_name = 'ALL' and channel <> 'DISTRIBUTION' group by 1)
select t.date, t.total, coalesce(s.steam, 0) as steam from t left join s using (date) where t.date >= '{START}' order by 1
"""

# Fable's vetted aggregate (fable.common, srs job `fable`): one row per merchant tag x day x source type x channel, both panels.
# No panel-total row, so the total is the sum over every merchant tag (payment-processor rows left out: they overlap merchants)
FABLE_AGG_SQL = """
select panel, country, date, txn_source_type, channel,
       sum(sales_net::float) as total, sum(iff(tag = 'steam games', sales_net::float, 0)) as steam,
       count(*) as n_rows, count(distinct tag) as n_tags
from fable.common.machine_data_daily_enhanced_srs_agg
where aggregate_type = 'merchant' and date >= '2023-01-01'
  and country in ('United Kingdom', 'Germany', 'France', 'Italy', 'Spain')
group by all
"""

def run(sql):
    con = snowflake.connector.connect(connection_name="default", warehouse="ANALYST_XL", network_timeout=7200)
    cur = con.cursor(); cur.execute(sql)
    return pl.from_arrow(cur.fetch_arrow_all()).rename(str.lower)

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    if sys.argv[1] == "eu":
        run(EU_SQL).write_parquet(OUT / "card_steam_eu.parquet"); print("eu done")
    elif sys.argv[1] == "mu":
        run(MU_SQL).write_parquet(OUT / "card_steam_us_mu.parquet"); print("mu done")
    elif sys.argv[1] == "fable_agg":
        run(FABLE_AGG_SQL).write_parquet(OUT / "card_steam_eu_agg.parquet"); print("fable_agg done")
    else:
        path, parts = OUT / "card_steam_us.parquet", []
        years = [("2023-01-01", "2024-01-01"), ("2024-01-01", "2025-01-01"), ("2025-01-01", "2026-01-01"), ("2026-01-01", STOP)]
        for a, b in years:   # older dates scan all of TRANS_V1_0, so one year per query
            parts.append(run(US_SQL.format(start=a, stop=b)))
            pl.concat(parts).write_parquet(path); print("us", a, "done", flush=True)
