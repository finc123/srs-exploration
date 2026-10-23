"""ChatGPT direct (web) sign-up cohorts: what openai.com lifecycle emails follow (SUPRA), and renewal-email capture."""
import pandas as pd, numpy as np
c = pd.read_parquet("charges_us.parquet"); c["uid"] = c["uid"].astype(str)
d = c[(c.prov == "chatgpt") & (c.channel == "direct")].copy()
other = c[(c.prov == "chatgpt") & (c.channel != "direct")]
ev = pd.read_parquet("supra_openai_events.parquet"); ev["uid"] = ev["uid"].astype(str); ev["dt"] = pd.to_datetime(ev["dt"])
cov = pd.read_parquet("supra_mbx_month.parquet"); cov["uid"] = cov["uid"].astype(str); cov["m"] = pd.to_datetime(cov["m"]).dt.to_period("M")
last_cov = cov.groupby("uid")["m"].max()
# cohort: direct sign-ups Aug 2025 - Mar 2026, mailbox in SUPRA through Sep 2026, no app-store ChatGPT charge within +-60d
d = d[(d.dt >= "2025-08-01") & (d.dt < "2026-04-01")]
d = d[d.uid.map(last_cov) >= pd.Period("2026-09", "M")]
x = d[["uid", "dt"]].reset_index().merge(other[["uid", "dt"]].rename(columns={"dt": "d2"}), on="uid")
d = d[~d.index.isin(x.loc[(x.d2 - x.dt).dt.days.abs() <= 60, "index"])]
d = d.sort_values("dt").drop_duplicates("uid")
print("cohort sign-ups:", len(d))
kinds = ["signup", "will_not_renew", "cancel_feedback", "access_end_soon", "final_reminder", "update_payment", "payment_failed", "dont_lose_access", "updated_plan"]
j = d[["uid", "dt"]].merge(ev[["uid", "dt", "k"]].rename(columns={"dt": "e"}), on="uid")
j["lag"] = (j.e - j.dt).dt.days
j = j[(j.lag > 3) & (j.lag <= 240)]
res = {k: j.loc[j.k == k, "uid"].nunique() / len(d) for k in kinds}
end = j[j.k.isin(["will_not_renew", "access_end_soon", "final_reminder"])]
res["any_end_signal"] = end.uid.nunique() / len(d)
res["any_end_or_dunning"] = j[j.k.isin(["will_not_renew", "access_end_soon", "final_reminder", "update_payment", "payment_failed"])].uid.nunique() / len(d)
print(pd.Series(res).round(3).to_string())
f = end.sort_values("lag").drop_duplicates("uid")
print("first end-signal lag (days) quantiles:", f.lag.quantile([.1, .25, .5, .75, .9]).to_dict())
# share of will_not_renew followed by access_end within 45d; and access_end without will_not_renew
w = j[j.k == "will_not_renew"].groupby("uid").e.min(); a = j[j.k.isin(["access_end_soon","final_reminder"])].groupby("uid").e.min()
both = pd.concat([w.rename("w"), a.rename("a")], axis=1)
print("uids with will_not_renew:", both.w.notna().sum(), " also access_end:", (both.w.notna() & both.a.notna()).sum(),
      " access_end only (no will_not_renew):", (both.w.isna() & both.a.notna()).sum())
# months observed after sign-up: monthly renewal emails? count openai events per uid-month after signup, by kind
cn = pd.read_parquet("cn_us.parquet"); cn["uid"]=cn.uid.astype(str); cn = cn[(cn.prov=="chatgpt")]
ao = both[both.w.isna() & both.a.notna()].reset_index().rename(columns={"index":"uid"})
k = ao.merge(cn[["uid","dt","channel"]], on="uid"); k = k[(k.dt - k.a).dt.days.abs() <= 60]
print("access_end-only uids with an IE ChatGPT cancel within 60d:", k.uid.nunique(), "of", len(ao), k.drop_duplicates("uid").channel.value_counts().to_dict())
# dunning preceded access-end?
dn = j[j.k=="update_payment"].groupby("uid").e.min()
print("access_end-only uids with prior 'update payment method' email:", ao.uid.map(dn).notna().mean().round(3))
# IE direct cancels for the cohort vs SUPRA will_not_renew
ci = d[["uid","dt"]].merge(cn[cn.channel=="direct"][["uid","dt"]].rename(columns={"dt":"e"}), on="uid"); ci = ci[((ci.e-ci.dt).dt.days>3)&((ci.e-ci.dt).dt.days<=240)]
print("cohort share with IE direct cancel:", round(ci.uid.nunique()/len(d),3), " IE cancel OR SUPRA end/dunning:", round(len(set(ci.uid)|set(j[j.k.isin(['will_not_renew','access_end_soon','final_reminder','update_payment'])].uid))/len(d),3))
