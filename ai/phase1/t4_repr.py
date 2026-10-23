"""Task 4: representativeness of the reliable subset (R, time-local reference rule from t5) vs the rest.

Uses data/subs_{region}.parquet (built by t5_survival.py). Compares subscriptions entering R at start vs the rest:
plan mix, first-channel mix, start-cohort mix, receipts per subscription, first-renewal rate (a 2nd paid receipt within
70 days, starts >= 100 days before the data end: lenient enough that one missed email rarely flips it), and a naive
KM for the rest (same W, no reference censoring; inflated by missed-email false churn, so an upper bound on churn).
Outputs: out/t4_mix.csv, out/t4_early.csv
"""
import numpy as np
import pandas as pd
from common import *
from t5_survival import km

rows, early = [], []
for region in ["us", "eu"]:
    s = pd.read_parquet(D / f"subs_{region}.parquet")
    T = s["last"].max()
    s["grp"] = np.where(s["in_R"], "R", "rest")
    s["cohort"] = s["start"].dt.to_period("Q").astype(str)
    s = s[s["start"] >= "2024-01-01"]
    for p, x in s.groupby("prov"):
        for dim in ["pk", "channel", "cohort"]:
            t = pd.crosstab(x[dim], x["grp"], normalize="columns")
            for k, r in t.iterrows():
                rows.append(dict(region=region, prov=p, dim=dim, value=k, R=r.get("R", np.nan), rest=r.get("rest", np.nan)))
        for g, y in x.groupby("grp"):
            m = y[y["start"] <= T - pd.Timedelta(days=100)]
            # 2nd receipt within 70 days: subs with n>=2 and (n==1 -> no). Approximate with episode n and duration.
            first_renew = ((m["n"] >= 2) & ((m["last"] - m["start"]).dt.days >= 20)).mean()
            ev = y["event"] & (y["known"] <= T)
            age = ((y["known"].where(ev, T)) - y["start"]).dt.days.clip(lower=0)
            S = km(age, ev)
            early.append(dict(region=region, prov=p, grp=g, subs=len(y), share=len(y) / len(x), first_renewal_rate=first_renew,
                              receipts_per_sub=y["n"].mean(), naive_S90=S[90], naive_S180=S[180],
                              share_apple=(y["channel"] == "apple").mean()))
    # R KM for comparison (from t5 censoring)
    for p, y in s[s["in_R"]].groupby("prov"):
        S = km(y["age_end"], y["R_event"])
        early.append(dict(region=region, prov=p, grp="R_censored_KM", subs=len(y), naive_S90=S[90], naive_S180=S[180]))

mix = pd.DataFrame(rows)
mix["diff_pp"] = (mix["R"] - mix["rest"]) * 100
mix.round(4).to_csv(OUTD / "t4_mix.csv", index=False)
e = pd.DataFrame(early)
e.round(4).to_csv(OUTD / "t4_early.csv", index=False)
pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 500)
print(e.round(3).to_string(index=False))
big = mix[(mix["dim"] != "cohort") & ((mix["R"] > 0.03) | (mix["rest"] > 0.03))]
print(big.round(3).to_string(index=False))
c = mix[mix["dim"] == "cohort"].pivot_table(index=["region", "prov"], columns="value", values="diff_pp")
print(c.round(1).to_string())

# first-renewal rate within channel (capture is ~equal for R and rest on Google Play / direct / Stripe / PayPal, so the gap
# there is the selection effect; on Apple it is mostly missed Apple emails in the rest)
fr = []
for region in ["us", "eu"]:
    s = pd.read_parquet(D / f"subs_{region}.parquet")
    T = s["last"].max()
    m = s[(s["start"] >= "2024-01-01") & (s["start"] <= T - pd.Timedelta(days=100))]
    m = m.assign(fr=m["n"] >= 2, grp=np.where(m["in_R"], "R", "rest"))
    t = m.groupby(["prov", "channel", "grp"]).agg(n=("fr", "size"), fr=("fr", "mean")).unstack("grp")
    t.columns = [f"{a}_{b}" for a, b in t.columns]
    t = t[(t["n_R"] >= 200) & (t["n_rest"] >= 200)].assign(region=region, diff_pp=lambda d: (d["fr_R"] - d["fr_rest"]) * 100)
    fr.append(t.reset_index())
fr = pd.concat(fr)
fr.round(4).to_csv(OUTD / "t4_first_renewal_by_channel.csv", index=False)
print(fr.round(3).to_string(index=False))
