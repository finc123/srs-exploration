"""Local preview of the ai_consumer page with the email-based flows, in the shape the production exporter writes
(srs workflows/jobs/ai/consumer: engine/email_flows.py -> email_flows table -> export/). It runs the production
module on the notebook's cached rows (.cache/channel_cmp/raw.parquet), then uses the exporter's own section list,
tiles, methodology and coverage notes; the app and web sections are kept from the existing app/ai_consumer.json.
Run from exploration/ai: python app/channel_flows.py [srs worktree; default ../../srs-ai-consumer]."""
import json, sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

SRS = Path(sys.argv[1] if len(sys.argv) > 1 else "../../srs-ai-consumer")
JOB = SRS / "workflows/jobs/ai/consumer/artifacts"
sys.path[:0] = [str(JOB / "engine"), str(JOB / "export"), str(SRS / "packages/srs-core")]
import email_flows as F  # noqa: E402
import consumer_sections as S  # noqa: E402
import export_dashboard_json as E  # noqa: E402

out, end = F.build(pd.read_parquet(".cache/channel_cmp/raw.parquet"))
out.to_parquet(".cache/channel_cmp/srs_email_flows.parquet", index=False)
flows = out.assign(month=out.month.dt.strftime("%Y-%m-%d")).drop(columns="region")
flows.columns = [c.upper() for c in flows.columns]

j = json.load(open("app/ai_consumer.json"))
frames = {"channel_flows": flows}
for s in S.SECTIONS:
    if s["key"] != "channel_flows":
        frames[s["key"]] = pd.DataFrame(j["sections"].get(s["key"], []))
j["sections"] = {k: json.loads(v.to_json(orient="records")) for k, v in frames.items()}
j["summary"] = E._summary_rows(frames)
j["methodology"] = E._methodology()
j["providers"] = [dict(ID=k, NAME=v["name"], COVERAGE=v["coverage"]) for k, v in S.PROVIDERS.items()]
j["freshness"] = [f for f in j["freshness"] if not f["DATASET"].startswith("E-receipt")]
j["freshness"].insert(0, dict(DATASET="E-receipt emails (to date)", MAX_DATE=str(end.date())))
j["generated_at"] = datetime.now(timezone.utc).isoformat()
j.pop("interim_note", None)
json.dump(j, open("app/ai_consumer.json", "w"), allow_nan=False, default=str)
print(f"channel_flows: {len(flows)} rows, {flows.MONTH.min()} to {flows.MONTH.max()} (data end {end.date()}); "
      f"sections {list(j['sections'])}")
