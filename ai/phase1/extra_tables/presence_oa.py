"""Presence of OpenAI lifecycle emails (SUPRA, openai.com) around confirmed ChatGPT lapses (t6 definitions)."""
import pandas as pd, numpy as np
L = pd.read_parquet("L_us.parquet")
ev = pd.read_parquet("supra_openai_events.parquet"); ev["uid"] = ev["uid"].astype(str); ev["dt"] = pd.to_datetime(ev["dt"])
cov = pd.read_parquet("supra_mbx_month.parquet"); cov["uid"] = cov["uid"].astype(str); cov["m"] = pd.to_datetime(cov["m"]).dt.to_period("M")
covset = set(zip(cov["uid"], cov["m"]))
L = L[(L["prov"] == "chatgpt") & (L["month"] >= pd.Period("2025-08", "M")) & (L["month"] <= pd.Period("2026-08", "M"))].copy()
L["covered"] = [((u, m) in covset) and ((u, m - 1) in covset) for u, m in zip(L["uid"], L["month"])]
END = ["will_not_renew", "cancel_feedback", "access_end_soon", "final_reminder", "update_payment", "payment_failed", "dont_lose_access"]
j = L[["uid", "pt"]].reset_index().merge(ev[ev["k"].isin(END)][["uid", "dt", "k"]], on="uid")
j = j[(j["dt"] - j["pt"]).dt.days.abs() <= 45]
for k in END + ["access_any"]:
    ks = ["access_end_soon", "final_reminder"] if k == "access_any" else [k]
    L[k] = L.index.isin(j.loc[j["k"].isin(ks), "index"].unique())
L["oa_any"] = L.index.isin(j["index"].unique())
L["union"] = L["present"] | L["oa_any"]
rows = []
for (ch, cv), g in L.groupby(["channel", "covered"]):
    rows.append(dict(channel=ch, supra_covered=cv, lapses=len(g), ie_cancel=g.present.mean(), **{k: g[k].mean() for k in ["will_not_renew","access_any","update_payment","oa_any"]}, union=g["union"].mean(),
                     union_R=g.loc[g.reliable, "union"].mean(), ie_R=g.loc[g.reliable, "present"].mean()))
out = pd.DataFrame(rows); print(out.round(3).to_string())
m = L[L.covered].groupby(["channel", "month"]).agg(n=("uid", "size"), ie=("present", "mean"), union=("union", "mean")).round(3)
print(m.unstack(0).to_string())
out.to_csv("presence_oa_summary.csv", index=False); m.to_csv("presence_oa_monthly.csv")
