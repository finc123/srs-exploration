"""Interim subscriber sections for the local page, from the exploration engine (observed subs, 75-day lapse,
ChatGPT direct excluded). Replaced by the srs engine output once model.py lands."""
import json, pandas as pd, numpy as np
M = ".cache/receipts/metrics/"
EU = ["uk", "de", "fr", "es", "it"]
END = {"us": pd.Timestamp("2026-10-18"), **{c: pd.Timestamp("2026-10-13") for c in EU}}

def prep(f, plan_col):
    s = pd.read_parquet(M + f)
    s = s[s.kept & (s.channel != "direct") | (s.kept & (s.provider != "chatgpt") & (s.channel == "direct"))]
    s = s[s.provider.isin(["chatgpt", "claude", "gemini", "grok", "grok_x", "perplexity", "muse"])].copy()
    s["provider"] = s.provider.replace({"grok_x": "grok"})
    s["plan"] = s[plan_col]
    s["end"] = pd.to_datetime(s["end"]); s["start"] = pd.to_datetime(s["start"])
    return s

def monthly(s, by):
    rows = []
    for panel, g in s.groupby("panel"):
        months = pd.period_range("2024-01", END[panel].to_period("M"), freq="M")
        for key, h in g.groupby(by):
            for m in months:
                me = min(m.end_time.normalize(), END[panel])
                subs = ((h.start <= me) & ((h.outcome == "open") | (h.end > me))).sum()
                adds = ((h.start.dt.to_period("M") == m) & ~h.reactivation).sum()
                react = ((h.start.dt.to_period("M") == m) & h.reactivation).sum()
                churn = ((h.outcome != "open") & (h.end.dt.to_period("M") == m)).sum()
                rows.append(dict(zip(by, key if isinstance(key, tuple) else (key,)), COUNTRY=panel, MONTH=str(m),
                                 SUBS=float(subs), GROSS_ADDS=int(adds + react), CHURN=float(churn)))
    d = pd.DataFrame(rows)
    eu = d[d.COUNTRY.isin(EU)].groupby([*by, "MONTH"], as_index=False)[["SUBS", "GROSS_ADDS", "CHURN"]].sum().assign(COUNTRY="eu")
    return pd.concat([d, eu], ignore_index=True)

sp = prep("subs_provider.parquet", "first_plan")
d = monthly(sp, ["provider"]).rename(columns={"provider": "PROVIDER"}).sort_values(["COUNTRY", "PROVIDER", "MONTH"])
d["prev"] = d.groupby(["COUNTRY", "PROVIDER"]).SUBS.shift()
d["CHURN_RATE"] = (d.CHURN / d.prev).replace([np.inf], np.nan).round(4)
d["NET_ADDS"] = d.SUBS - d.prev
d["SHARE"] = (d.SUBS / d.groupby(["COUNTRY", "MONTH"]).SUBS.transform("sum")).round(4)
act = pd.read_parquet(M + "active.parquet"); act["MONTH"] = pd.to_datetime(act.date).dt.to_period("M").astype(str)
act = act.groupby(["panel", "MONTH"]).active_members.last().reset_index().rename(columns={"panel": "COUNTRY", "active_members": "ACTIVE_MEMBERS"})
act = pd.concat([act, act[act.COUNTRY.isin(EU)].groupby("MONTH", as_index=False).ACTIVE_MEMBERS.sum().assign(COUNTRY="eu")])
d = d.merge(act, on=["COUNTRY", "MONTH"], how="left")
d["SUBS_PER_1000"] = (d.SUBS / d.ACTIVE_MEMBERS * 1000).round(3)
d["SUBS_OBSERVED"] = d.SUBS; d["REGION"] = np.where(d.COUNTRY == "us", "us", "eu"); d["HELD"] = d.MONTH == "2026-10"
d = d.drop(columns="prev")

spl = prep("subs_plan.parquet", "plan")
p = monthly(spl, ["provider", "plan"]).rename(columns={"provider": "PROVIDER", "plan": "PLAN"})
p["HELD"] = p.MONTH == "2026-10"

dp = pd.read_parquet(M + "daily_provider.parquet")
dp = dp[dp.provider.isin(["chatgpt", "claude", "gemini", "grok", "grok_x", "perplexity", "muse"])].copy()
dp["provider"] = dp.provider.replace({"grok_x": "grok"})
dp["DATE"] = pd.to_datetime(dp.date).dt.strftime("%Y-%m-%d")
dp = dp.groupby(["panel", "provider", "DATE"], as_index=False).gross_adds.sum()
dp = pd.concat([dp, dp[dp.panel.isin(EU)].groupby(["provider", "DATE"], as_index=False).gross_adds.sum().assign(panel="eu")])
dp = dp.rename(columns={"panel": "COUNTRY", "provider": "PROVIDER", "gross_adds": "GROSS_ADDS"}).sort_values(["COUNTRY", "PROVIDER", "DATE"])
dp["GROSS_ADDS_TR7D"] = dp.groupby(["COUNTRY", "PROVIDER"]).GROSS_ADDS.transform(lambda x: x.rolling(7).mean()).round(2)
dp = dp[dp.DATE >= "2025-01-01"]

j = json.load(open("app/ai_consumer.json"))
clean = lambda df: json.loads(df.replace({np.nan: None}).to_json(orient="records"))
j["sections"]["subs_monthly"] = clean(d)
j["sections"]["plan_mix"] = clean(p)
j["sections"]["subs_daily_adds"] = clean(dp)
j["interim_note"] = "INTERIM: observed subscribers from the exploration engine (75-day lapse, ChatGPT direct excluded); model pending."
json.dump(j, open("app/ai_consumer.json", "w"), allow_nan=False)
print(d[d.MONTH == "2026-09"][["COUNTRY", "PROVIDER", "SUBS", "SHARE", "GROSS_ADDS", "CHURN_RATE"]].query("COUNTRY in ['us','eu']").to_string())
