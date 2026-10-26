"""Rebuild app/ai_consumer.json from the live sources, read-only, with the production exporter.

Runs srs workflows/jobs/ai/consumer's export_dashboard_json with each srs_mcp.ai_consumer.* table swapped for its
load SELECT (so nothing is written to Snowflake), email_flows and email_adds_daily built in-process by
engine/email_flows.py (the daily table inlined as VALUES), and the S3
put redirected to the local file (the previous one is kept as ai_consumer.json.bak). Snowflake connection "default".
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
SUBS["email_adds_daily"] = ("SELECT column1 AS region, column2 AS provider, column3::DATE AS date, column4 AS gross_adds, "
                            f"{panel} AS panel FROM VALUES " + ",".join(
    f"('{r.region}','{r.provider}','{r.date.date()}',{r.gross_adds})" for r in daily.itertuples()))
flows_sec = pd.DataFrame({
    "MONTH": flows.month.dt.strftime("%Y-%m-%d"), "PROVIDER": flows.provider, "CHANNEL": flows.channel,
    "PLAN": flows.plan, "GROSS_ADDS": flows.gross_adds, "CHURN": flows.churn, "SWITCH_IN": flows.switch_in,
    "SWITCH_OUT": flows.switch_out, "NET_ADDS": flows.net_adds, "IN_COMBINED": flows.in_combined,
    "PARTIAL": flows.partial}).sort_values(["PROVIDER", "CHANNEL", "PLAN", "MONTH"]).reset_index(drop=True)


def query(sql, warehouse):
    if "ai_consumer.email_flows" in sql:
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
OUT.write_text(json.dumps(j, separators=(",", ":"), allow_nan=False, default=str))
print(json.dumps({k: res[k] for k in ("status", "sections", "bytes")}, default=str))
