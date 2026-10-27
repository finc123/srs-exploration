"""Rebuild app/ai_consumer.json from the live sources, read-only, with the production exporter.

Runs srs workflows/jobs/ai/consumer's export_dashboard_json with each srs_mcp.ai_consumer.* table swapped for its
load SELECT (so nothing is written to Snowflake), email_flows and email_flows_daily built in-process by
engine/email_flows.py (the daily table inlined as VALUES), and the S3
put redirected to the local file (the previous one is kept as ai_consumer.json.bak). Snowflake connection "default".
Local only (not in the srs job yet): sections card_spend_daily (observable AI-plan spend on the card panel) and
card_panel_spend_daily (total panel spend at tagged merchants), built by notebooks/card_ereceipt_rules.py: a fresh
Omega pull on ANALYST_XL (about 15 minutes) and the panel total, cached in .cache/card_ereceipt/panel_spend_daily.parquet
with its last 45 days re-pulled each run.
Run from exploration/ai: python app/refresh_local.py [srs checkout; default ../../srs]."""
import json, os, re, shutil, sys
from pathlib import Path
import pandas as pd
import snowflake.connector as sc

SRS = Path(sys.argv[1] if len(sys.argv) > 1 else "../../srs").resolve()
JOB = SRS / "workflows/jobs/ai/consumer/artifacts"
OUT = Path(__file__).resolve().parent / "ai_consumer.json"
sys.path[:0] = [str(JOB / "engine"), str(JOB / "export"), str(SRS / "packages/srs-core")]
os.environ["_SRS_TAG_WORKFLOW"] = "ai_consumer"
import email_flows as F  # noqa: E402
import export_dashboard_json as E  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))
import card_ereceipt_rules as C  # noqa: E402


def bodies(path):
    """{table: SELECT body} from a load file's CREATE OR REPLACE TABLE ... AS <select>; statements."""
    out = {}
    for chunk in re.split(r"CREATE OR REPLACE TABLE ", path.read_text())[1:]:
        name = chunk.split()[0].split(".")[-1].split("(")[0]
        out[name] = re.split(r"^;\s*$", chunk.split("\nAS\n", 1)[1], maxsplit=1, flags=re.M)[0]
    return out


SUBS = {**bodies(JOB / "load/app_web.sql"), **bodies(JOB / "load/receipts_us.sql")}
cur = sc.connect(connection_name="default").cursor()


def fetch(sql):
    for name, body in SUBS.items():
        sql = re.sub(rf"srs_mcp\.ai_consumer\.{name}\b", f"(\n{body}\n)", sql, flags=re.I)
    cur.execute(sql)
    return cur.fetch_pandas_all()


print("email flows: reading receipts ...", flush=True)
flows, daily, end = F.build(fetch(F.READ_SQL.format(schema="srs_mcp.ai_consumer")))
panel = int(fetch(F.PANEL_SQL).iloc[0, 0])
print(f"email flows built, data end {end.date()}, panel {panel:,}", flush=True)
SUBS["email_flows_daily"] = ("SELECT column1 AS region, column2 AS provider, column3::DATE AS date, column4 AS gross_adds, "
                             f"column5 AS churn, column6 AS net_adds, {panel} AS panel FROM VALUES " + ",".join(
    f"('{r.region}','{r.provider}','{r.date.date()}',{r.gross_adds},{r.churn},{r.net_adds})" for r in daily.itertuples()))
flows_sec = pd.DataFrame({
    "MONTH": flows.month.dt.strftime("%Y-%m-%d"), "PROVIDER": flows.provider, "CHANNEL": flows.channel,
    "PLAN": flows.plan, "GROSS_ADDS": flows.gross_adds, "CHURN": flows.churn, "SWITCH_IN": flows.switch_in,
    "SWITCH_OUT": flows.switch_out, "NET_ADDS": flows.net_adds, "IN_COMBINED": flows.in_combined,
    "PARTIAL": flows.partial}).sort_values(["PROVIDER", "CHANNEL", "PLAN", "MONTH"]).reset_index(drop=True)


print("card spend: pulling the card panel ...", flush=True)
card = C.pull_card(save=False)
card_end = card.dt.max()
spend = C.card_spend_daily(C.card_payments(card, C.SPEND_PROVIDERS), card_end)
panel_spend = C.panel_spend_daily(spend.date.max())
d0 = fetch("SELECT DISTINCT LOWER(app) AS provider, day0 FROM srs_mcp.ai_consumer.app_usage WHERE country = 'US'")
spend = spend.merge(d0.rename(columns=str.lower), on="provider", how="left")
spend["day_n"] = (spend.date - pd.to_datetime(spend.day0)).dt.days
spend_sec = [dict(PROVIDER=r.provider, DATE=str(r.date.date()), DAY_N=None if pd.isna(r.day_n) else int(r.day_n),
                  SPEND=round(float(r.spend), 2), ACCOUNTS=int(r.accounts))
             for r in spend.sort_values(["provider", "date"]).itertuples()]
panel_sec = [dict(DATE=str(r.date.date()), SPEND=round(float(r.spend), 0)) for r in panel_spend.itertuples()]
print(f"card spend built, data end {card_end.date()} (shown to {spend.date.max().date()}), "
      f"panel spend {panel_spend.date.min().date()} to {panel_spend.date.max().date()}", flush=True)


def query(sql, warehouse):
    if re.search(r"ai_consumer\.email_flows\b", sql, flags=re.I):
        return flows_sec.copy()
    df = fetch(sql)
    df.columns = [c.upper() for c in df.columns]
    for c in df.columns:  # dates as ISO strings, as execute_sql returns them
        if df[c].map(lambda v: hasattr(v, "isoformat")).any():
            df[c] = df[c].map(lambda v: v.isoformat() if hasattr(v, "isoformat") else v)
    return df


class _LocalS3:
    def put_object(self, Body, **_):
        if OUT.exists():
            shutil.copy(OUT, OUT.with_suffix(".json.bak"))
        OUT.write_bytes(Body)


E._query = query
E.boto3.client = lambda *_a, **_k: _LocalS3()
res = E._export({})
# Local preview shows the e-receipt data end, not the month the exporter reports.
j = json.loads(OUT.read_text())
j["freshness"][0] = dict(DATASET="E-receipt emails (to date)", MAX_DATE=str(end.date()))
j["freshness"].append(dict(DATASET="Card panel spend (to date)", MAX_DATE=str(spend.date.max().date())))
j["sections"]["card_spend_daily"] = spend_sec
j["sections"]["card_panel_spend_daily"] = panel_sec
j["methodology"].append(dict(
    KEY="card_spend_daily", TITLE="Provider market share: daily spend on consumer AI plans from the card panel (US)",
    SOURCE="Consumer Edge Omega card panel (2022 consistent-shopper panel, affected accounts excluded): tagged rows from "
           "EARNEST.COMMON.TXNS_CORE_V plus untagged AI merchids from PRIME_OMEGA TRANS_V1_0, classified by "
           "exploration/ai/filters/{provider}.py (notebooks/card_ereceipt_rules.py). Built locally, not yet in the job.",
    FILTERS=[
        dict(RULE="Kept consumer AI-plan payments only: web and Google Play billing (Apple App Store charges carry no "
                  "provider and are not visible)",
             WHY="The same payments the card gross adds and churn use. Providers billed mostly through Apple (Grok, "
                 "ChatGPT) are understated, and a move from iTunes to the web reads as spend growth."),
        dict(RULE="Gemini = Google One AI plans, including 2 TB from 2026-01-27 (it includes AI Plus); Grok = SuperGrok "
                  "+ X Premium+; Muse = Muse Power / Max from 2026-09-07",
             WHY="The current card methodology. About 6% of Gemini accounts appear only under the generic "
                 "'GOOGLE *GOOGLE MOUNTAIN VIE' descriptor at AI prices."),
        dict(RULE="Annual plans count on the day charged", WHY="Observable spend, not a monthly equivalent."),
    ],
    DEDUPE="One row per transaction; spend is summed per provider and day.",
    MEASURE="SPEND = the sum of charged amounts (USD, incl. sales tax) per provider and day; ACCOUNTS = distinct paying "
            "card accounts. Share = a provider's spend over the six-provider total. % of Panel = a provider's spend over "
            "card_panel_spend_daily: all panel USD debits at merchants tagged to a brand (MID_MATCH main_brand_id), "
            "which leaves out bank transfers, rent and bill payments (untagged, about 80% of all debits by value). Most "
            "AI charges are untagged, so they are not in the denominator. TR7D = 7-day sums over 7-day sums; Monthly = "
            "monthly sums. Unweighted panel totals, not scaled to the US.",
    LAG=f"Card transactions post over about {C.CARD_LAG} days, so the last {C.CARD_LAG} days before the data end are "
        "dropped.",
))
OUT.write_text(json.dumps(j, separators=(",", ":"), allow_nan=False, default=str))
print(json.dumps({k: res[k] for k in ("status", "sections", "bytes")}, default=str))
