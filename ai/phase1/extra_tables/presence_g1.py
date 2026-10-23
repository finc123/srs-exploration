"""Presence of Google One 'AI plan ended / canceled' emails (SUPRA) around confirmed Gemini lapses."""
import pandas as pd
L = pd.read_parquet("L_us.parquet"); L = L[(L.prov == "gemini") & (L.month >= pd.Period("2025-08","M")) & (L.month <= pd.Period("2026-08","M"))].copy()
ev = pd.read_parquet("supra_googleone_end.parquet"); ev["uid"]=ev.uid.astype(str); ev["dt"]=pd.to_datetime(ev.dt)
ev = ev[ev.subject.str.contains(r"AI (?:Pro|Plus|Premium|Ultra)|Gemini", case=False)]
cov = pd.read_parquet("supra_mbx_month.parquet"); cov["uid"]=cov.uid.astype(str); cov["m"]=pd.to_datetime(cov.m).dt.to_period("M")
cs = set(zip(cov.uid, cov.m)); L["covered"] = [((u,m) in cs) and ((u,m-1) in cs) for u,m in zip(L.uid, L.month)]
j = L[["uid","pt"]].reset_index().merge(ev[["uid","dt"]], on="uid"); j = j[(j.dt-j.pt).dt.days.abs() <= 45]
L["g1"] = L.index.isin(j["index"].unique()); L["union"] = L.present | L.g1
print(L.groupby(["channel","covered"]).agg(n=("uid","size"), ie=("present","mean"), g1=("g1","mean"), union=("union","mean")).round(3).to_string())
print(L[L.covered & L.reliable].groupby("channel").agg(n=("uid","size"), ie=("present","mean"), union=("union","mean")).round(3).to_string())
print(L[L.covered].groupby(["channel","month"]).agg(ie=("present","mean"), union=("union","mean")).round(3).unstack(0).to_string())
