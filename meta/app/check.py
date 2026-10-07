"""Reconcile meta_muse.json against the findings recorded in the investigation notebooks."""

import json
from pathlib import Path

import pandas as pd

p = json.loads((Path(__file__).parent / "meta_muse.json").read_text(encoding="utf-8"))
S = {k: pd.DataFrame(v) for k, v in p["sections"].items()}


def weekly(df: pd.DataFrame, cols: list[str], by: list[str] | None = None) -> pd.DataFrame:
    d = df.assign(WEEK=pd.to_datetime(df.DATE).dt.to_period("W-SUN").dt.start_time.dt.date)
    return d.groupby(["WEEK", *(by or [])])[cols].sum().unstack(by or []).fillna(0) if by else d.groupby("WEEK")[cols].sum()


print("freshness:", p["freshness"])
print("\nsummary:")
print(pd.DataFrame(p["summary"]).to_string(index=False))

print("\nagentic weekly (notebook, Yodlee: 08-31 16 | 09-07 89 | 09-14 153 | 09-21 295):")
ag = S["agentic_daily"]
w = weekly(ag, ["TXNS", "SHOPIFY_TXNS", "PANEL_TXNS"])
w["PER_MILLION"] = (w.TXNS / w.PANEL_TXNS * 1e6).round(2)
print(w.tail(8).to_string())

print("\nmuse web weekly members by plan (notebook: first charge 09-17; weekly 1, 20, 21):")
web = S["muse_web_daily"]
print(weekly(web, ["MEMBERS"], ["PLAN"]).tail(6).to_string())
print("first charge:", web[web.MEMBERS > 0].DATE.min())

print("\nmuse in-app totals by store/plan (notebook: Apple Power ~179 charges, Google Play Power ~75):")
ia = S["muse_inapp_daily"]
print(ia.groupby(["STORE", "PLAN"])[["CHARGES", "CANCELS", "TRIALS"]].sum().to_string())
print(weekly(ia, ["CHARGES"], ["STORE"]).tail(6).to_string())

print("\napp usage, last TR7D per app/country:")
au = S["app_usage_daily"]
last = au.dropna(subset=["DAU_TR7D"]).sort_values("DATE").groupby(["APP", "COUNTRY"]).tail(1)
print(last[["APP", "COUNTRY", "DATE", "DOWNLOADS_TR7D", "DAU_TR7D"]].to_string(index=False))

print("\nAI assistant share of US / WW DAU TR7D (latest full day), share set:", p.get("share_apps"))
sa = au[au.APP.isin(p.get("share_apps", []))].dropna(subset=["DAU_TR7D"])
for c in ("US", "WW"):
    x = sa[sa.COUNTRY == c]
    for d in sorted(x.DATE.unique())[-1:] + ["2026-09-01"]:
        y = x[x.DATE == d].set_index("APP").DAU_TR7D
        print(f"  {c} {d}:", ", ".join(f"{a} {v / y.sum():.1%} ({v / 1e6:.2f}M)" for a, v in y.sort_values(ascending=False).items()))

print("\ntop merchants:")
print(S["agentic_merchants"].head(10).to_string(index=False))
