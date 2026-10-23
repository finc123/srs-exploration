"""Task 6 (US): can churn be read from cancellation emails scaled by 1 / presence rate?

Definitions (as t3):
  confirmed lapse : last paid receipt of an episode (uid x provider x channel), no payment from the provider on any channel
                    within W, W elapsed, mailbox active at last+W. Dated at paid-through (last + 31) for the monthly series.
  presence        : the lapse has a same-provider, same-channel cancel email within +-45 days of paid-through.
  cancel event    : first cancel email per uid x provider x channel within 45 days (repeat emails dropped).
  re-enabled      : a cancel email followed by a same-provider payment (any channel) within W of the email.
  reliable (R)    : live_any rule. Lapses: a different recurring sender is captured in every month from last payment to
                    last+W. Cancels: one is captured in the cancel month and the month after.
Scaling factors, trailing window of k = 6 or 12 months, lagged 2 months (only data known when the month is published):
  (a) predicted lapses(m) = cancels(m) x (1 - reenable rate) / presence
  (b) predicted lapses(m) = cancels(m) x sum(lapses) / sum(cancels)
  (c) as (a) but only cancels with a same-provider payment in the prior 62 days (paying subscribers; drops trial and
      non-subscriber cancels that never become a lapse)
  compared with observed lapses(m) over the last 12 complete months (paid-through month <= data end - W).
ChatGPT direct: no renewals, so presence cannot be measured. Scaled churn = direct cancels x (1 - direct re-enable) /
presence borrowed from ChatGPT Apple+Google Play, compared with the modelled curve (direct sign-ups x survival of
ChatGPT renewing channels, the current engine's approach).
Outputs: out/t6_presence_monthly.csv, out/t6_presence_summary.csv, out/t6_presence_by_plan_tenure.csv,
out/t6_reenable_monthly.csv, out/t6_backtest.csv, out/t6_backtest_summary.csv, out/t6_timeliness.csv, out/t6_chatgpt_direct.csv
"""
import numpy as np
import pandas as pd
from common import *
from t2_mailbox import ref_charges, month_rows
from t3_cancel import near
from t5_survival import km

REGION = "us"
CHS = [("chatgpt", "apple"), ("chatgpt", "google_play"), ("claude", "apple"), ("claude", "direct"), ("claude", "google_play"),
       ("gemini", "apple"), ("gemini", "google_play"), ("grok", "apple"), ("grok", "google_play"), ("perplexity", "apple"),
       ("perplexity", "google_play")]


def ym(d):
    return d.dt.year * 12 + d.dt.month


def build():
    W = windows()
    x = load(REGION)
    data_end = x["dt"].max()
    c = charges(x)
    allpay = c[["uid", "prov", "channel", "dt", "plan"]]
    cn = x[x["kind"] == "cancel"].drop_duplicates(["uid", "prov", "channel", "dt"]).sort_values(["uid", "prov", "channel", "dt"])
    # one cancellation event per uid x provider x channel per 45 days (Google Play sends 'will be canceled' + 'has ended':
    # 30-40% of GP cancel emails repeat within 45 days; Apple/direct 3-8%)
    rep_ = cn.groupby(["uid", "prov", "channel"])["dt"].diff().dt.days.le(45)
    cn = cn[~rep_].reset_index(drop=True)
    ep = pd.read_parquet(D / f"episodes_{REGION}.parquet").reset_index()
    ep = ep[ep["cad"] == "M"].copy()
    ep["W"] = [W(REGION, p, ch) for p, ch in zip(ep["prov"], ep["channel"])]
    ep["pt"] = ep["last"] + pd.Timedelta(days=31)
    ep["known"] = ep["last"] + pd.to_timedelta(ep["W"], unit="D")
    ep = ep[ep["known"] <= data_end]
    tmp = ep[["uid", "prov", "last"]].rename(columns={"last": "dt"})
    nxt = tmp.reset_index().merge(allpay[["uid", "prov", "dt"]].rename(columns={"dt": "d2"}), on=["uid", "prov"])
    nxt = nxt[nxt["d2"] > nxt["dt"]].groupby("index")["d2"].min()
    ep["next_pay"] = nxt.reindex(ep.index)
    ep["lapse"] = ep["next_pay"].isna() | ((ep["next_pay"] - ep["last"]).dt.days > ep["W"])
    a = pd.read_parquet(D / "us_activity.parquet", columns=["uid", "month"])
    a["uid"] = a["uid"].astype(str)
    lastym = ym(pd.to_datetime(a["month"])).groupby(a["uid"]).max()
    ep["active"] = ep["uid"].map(lastym) >= ym(ep["known"])
    # live_any months
    rg = gaps(ref_charges(REGION))
    rm = month_rows(rg[rg["k"] <= 13])
    ai = pd.read_parquet(D / f"gaps_{REGION}.parquet")
    am = month_rows(ai[(ai["cad"] == "M") & (ai["k"] <= 13)])
    live = pd.concat([rm.loc[~rm["missed"], ["uid", "ym"]].assign(prov="_ref"),
                      am.loc[~am["missed"], ["uid", "ym", "prov"]]]).drop_duplicates()
    L = ep[ep["lapse"] & ep["active"]].copy()
    m0 = ym(L["last"])
    nmon = (ym(L["known"]) - m0).clip(lower=1)
    rep = L.loc[L.index.repeat(nmon), ["uid", "prov"]]
    rep["ym"] = m0.loc[rep.index].to_numpy() + rep.groupby(level=0).cumcount().to_numpy() + 1
    rep["i"] = rep.index
    o = rep.merge(live.rename(columns={"prov": "p2"}), on=["uid", "ym"])
    o = o[o["p2"] != o["prov"]].groupby("i")["ym"].nunique()
    L["reliable"] = o.reindex(L.index).fillna(0).to_numpy() >= nmon.to_numpy()
    j = L[["uid", "prov", "channel", "pt"]].reset_index().merge(cn[["uid", "prov", "channel", "dt"]], on=["uid", "prov", "channel"])
    j = j[(j["dt"] - j["pt"]).dt.days.abs() <= 45].groupby("index")["dt"].min()
    L["cancel_dt"] = j.reindex(L.index)
    L["present"] = L["cancel_dt"].notna()
    L["month"] = L["pt"].dt.to_period("M")
    L["tenure"] = pd.cut(L["n"], [0, 1, 3, 6, 9999], labels=["1 receipt", "2-3", "4-6", "7+"])
    # cancels: re-enabled? reliable?
    cn["W"] = [W(REGION, p, ch) for p, ch in zip(cn["prov"], cn["channel"])]
    nx = cn[["uid", "prov", "dt"]].reset_index().merge(allpay[["uid", "prov", "dt"]].rename(columns={"dt": "d1"}), on=["uid", "prov"])
    nx = nx[nx["d1"] > nx["dt"]].groupby("index")["d1"].min()
    cn["next_pay"] = nx.reindex(cn.index)
    cn["reenabled"] = (cn["next_pay"] - cn["dt"]).dt.days <= cn["W"]
    cn["matured"] = cn["dt"] + pd.to_timedelta(cn["W"], unit="D") <= data_end
    pv = cn[["uid", "prov", "dt"]].reset_index().merge(allpay[["uid", "prov", "channel", "dt"]].rename(columns={"dt": "d0", "channel": "ch0"}), on=["uid", "prov"])
    pv = pv[pv["d0"] <= pv["dt"]]
    cn["paid_before_62d"] = cn.index.isin(pv.loc[(pv["dt"] - pv["d0"]).dt.days <= 62, "index"].unique())
    cn["paid_ever"] = cn.index.isin(pv["index"].unique())
    cn["direct_signup_ever"] = cn.index.isin(pv.loc[pv["ch0"] == "direct", "index"].unique())
    cm = ym(cn["dt"])
    lv = live[["uid", "ym", "prov"]].rename(columns={"prov": "p2"})
    for k_, col in [(0, "l0"), (1, "l1")]:
        t = cn[["uid", "prov"]].assign(ym=cm + k_).reset_index().merge(lv, on=["uid", "ym"])
        cn[col] = cn.index.isin(t.loc[t["p2"] != t["prov"], "index"].unique())
    cn["reliable"] = cn["l0"] & cn["l1"]
    cn["month"] = cn["dt"].dt.to_period("M")
    return L, cn, allpay, data_end, c


def series(L, cn, data_end, months, subset):
    rows = []
    for p, ch in CHS:
        l = L[(L["prov"] == p) & (L["channel"] == ch)]
        k = cn[(cn["prov"] == p) & (cn["channel"] == ch)]
        if subset == "R":
            l, k = l[l["reliable"]], k[k["reliable"]]
        W = int(l["W"].iloc[0]) if len(l) else 45
        for m in months:
            lm, km_ = l[l["month"] == m], k[k["month"] == m]
            rows.append(dict(subset=subset, prov=p, channel=ch, W=W, month=m, lapses=len(lm), lapses_with_cancel=int(lm["present"].sum()),
                             presence=lm["present"].mean() if len(lm) else np.nan, cancels=len(km_),
                             cancels_matured=int(km_["matured"].sum()), cancels_paid=int(km_["paid_before_62d"].sum()),
                             cancels_paid_matured=int((km_["paid_before_62d"] & km_["matured"]).sum()),
                             reenable_paid=km_.loc[km_["matured"] & km_["paid_before_62d"], "reenabled"].mean()
                             if (km_["matured"] & km_["paid_before_62d"]).any() else np.nan,
                             reenable=km_.loc[km_["matured"], "reenabled"].mean() if km_["matured"].any() else np.nan,
                             complete=(m.end_time + pd.Timedelta(days=max(W - 31, 45))) <= data_end))
    return pd.DataFrame(rows)


def backtest(s):
    out = []
    for (sub, p, ch), y in s.groupby(["subset", "prov", "channel"]):
        y = y.sort_values("month").reset_index(drop=True)
        comp = y[y["complete"]]
        test = comp.tail(12)
        for k in (6, 12):
            for i, r in test.iterrows():
                tr = y.iloc[max(0, i - 2 - k + 1): i - 1]  # lag 2: months i-k-1 .. i-2
                tr = tr[tr["complete"]]
                if len(tr) < k // 2 or tr["lapses_with_cancel"].sum() == 0 or tr["cancels"].sum() == 0:
                    continue
                pres = tr["lapses_with_cancel"].sum() / tr["lapses"].sum()
                re = (tr["reenable"] * tr["cancels_matured"]).sum() / tr["cancels_matured"].sum()
                pa = r["cancels"] * (1 - re) / pres
                pb = r["cancels"] * tr["lapses"].sum() / tr["cancels"].sum()
                rep_ = (tr["reenable_paid"] * tr["cancels_paid_matured"]).sum() / max(tr["cancels_paid_matured"].sum(), 1)
                pc = r["cancels_paid"] * (1 - rep_) / pres
                out.append(dict(subset=sub, prov=p, channel=ch, k=k, month=r["month"], obs=r["lapses"], pred_a=pa, pred_b=pb, pred_c=pc))
    return pd.DataFrame(out)


def summarize_bt(b, keys):
    g = b.groupby(keys + ["month"])[["obs", "pred_a", "pred_b", "pred_c"]].sum().reset_index()
    rows = []
    for key, y in g.groupby(keys):
        d = dict(zip(keys, key if isinstance(key, tuple) else (key,)))
        for f in ("a", "b", "c"):
            e = y[f"pred_{f}"] / y["obs"] - 1
            d[f"mape_{f}"] = e.abs().mean()
            d[f"bias_{f}"] = e.mean()
        d["months"] = len(y)
        d["obs_per_month"] = y["obs"].mean()
        rows.append(d)
    return pd.DataFrame(rows)


def chatgpt_direct(L, cn, c, s_full, data_end, months):
    """Scaled ChatGPT direct cancels vs the modelled curve (direct sign-ups x survival of ChatGPT renewing channels)."""
    pool = s_full[(s_full["prov"] == "chatgpt") & s_full["channel"].isin(["apple", "google_play"]) & (s_full["subset"] == "all")]
    pm = pool.groupby("month")[["lapses", "lapses_with_cancel"]].sum()
    d = cn[(cn["prov"] == "chatgpt") & (cn["channel"] == "direct")]
    su = c[(c["prov"] == "chatgpt") & (c["channel"] == "direct")].sort_values(["uid", "dt"])
    # direct re-enable: another direct sign-up (or any ChatGPT payment) within 45 days of the cancel
    s5 = pd.read_parquet(D / "subs_us.parquet")
    r = s5[(s5["prov"] == "chatgpt") & s5["in_R"]]  # reliable-subset survival, churn dated when known (t5)
    S = km(r["age_end"], r["R_event"], 1500)
    adds = su.groupby(su["dt"].dt.to_period("M")).size()
    rows = []
    for i, m in enumerate(months):
        tr = pm.loc[[mm for mm in months[max(0, i - 13): max(0, i - 1)] if mm in pm.index]]
        pres = tr["lapses_with_cancel"].sum() / tr["lapses"].sum() if len(tr) else np.nan
        dm = d[d["month"] == m]
        re = dm.loc[dm["matured"], "reenabled"].mean() if dm["matured"].any() else np.nan
        # modelled churn in month m = sum over sign-up months s of adds(s) x (S(age at start of m) - S(age at end of m))
        mod = 0.0
        for sm, n in adds.items():
            a0 = (m.start_time - sm.start_time).days + 15
            a1 = (m.end_time - sm.start_time).days + 15
            if a1 <= 0:
                continue
            mod += n * (S[min(max(a0, 0), 1499)] - S[min(a1, 1499)])
        rows.append(dict(month=m, direct_cancels=len(dm), share_with_any_prior_chatgpt_payment=dm["paid_ever"].mean(),
                         share_with_prior_direct_signup=dm["direct_signup_ever"].mean(), direct_reenable=re, borrowed_presence=pres,
                         scaled_direct_churn=len(dm) * (1 - (re if re == re else 0)) / pres if pres else np.nan,
                         modelled_direct_churn=mod, direct_signups=int(adds.get(m, 0))))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    pd.set_option("display.width", 260)
    pd.set_option("display.max_rows", 500)
    L, cn, allpay, data_end, c = build()
    months = list(pd.period_range(data_end.to_period("M") - 25, data_end.to_period("M") - 1, freq="M"))
    s = pd.concat([series(L, cn, data_end, months, "all"), series(L, cn, data_end, months, "R")])
    s.to_csv(OUTD / "t6_presence_monthly.csv", index=False)
    # 1. presence stability over last 24 complete months
    summ = []
    for (sub, p, ch), y in s[s["complete"]].groupby(["subset", "prov", "channel"]):
        y = y.tail(24)
        pr = y["presence"]
        t = np.arange(len(y))
        slope = np.polyfit(t, pr.fillna(pr.mean()), 1)[0] * 12 if len(y) > 3 else np.nan
        h1, h2 = pr.iloc[: len(pr) // 2].mean(), pr.iloc[len(pr) // 2:].mean()
        re = y["reenable"]
        p12 = pr.tail(12)
        summ.append(dict(presence_mean_last12=p12.mean(), presence_cv_last12=p12.std() / p12.mean(),
                         trend_pp_per_year_last12=np.polyfit(np.arange(len(p12)), p12.fillna(p12.mean()), 1)[0] * 1200 if len(p12) > 3 else np.nan,
                         **dict(subset=sub, prov=p, channel=ch, months=len(y), lapses_per_month=y["lapses"].mean(),
                         presence_mean=pr.mean(), presence_sd=pr.std(), presence_cv=pr.std() / pr.mean(),
                         trend_pp_per_year=slope * 100, first_half=h1, second_half=h2,
                         reenable_mean=re.mean(), reenable_cv=re.std() / re.mean(),
                         ratio_lapses_per_cancel=y["lapses"].sum() / y["cancels"].sum(),
                         ratio_cv=(y["lapses"] / y["cancels"]).std() / (y["lapses"] / y["cancels"]).mean())))
    summ = pd.DataFrame(summ)
    summ.round(4).to_csv(OUTD / "t6_presence_summary.csv", index=False)
    # by plan and tenure (last 24 months)
    Lw = L[L["month"].isin(months)]
    pt = []
    for dim in ["plan", "tenure"]:
        for sub, Z in [("all", Lw), ("R", Lw[Lw["reliable"]])]:
            g = Z.groupby(["prov", "channel", dim], observed=True).agg(lapses=("present", "size"), presence=("present", "mean")).reset_index()
            pt.append(g[g["lapses"] >= 200].rename(columns={dim: "value"}).assign(dim=dim, subset=sub))
    pt = pd.concat(pt)
    pt = pt[pt.set_index(["prov", "channel"]).index.isin(CHS)]
    pt.round(4).to_csv(OUTD / "t6_presence_by_plan_tenure.csv", index=False)
    # 2. re-enable by month
    s[["subset", "prov", "channel", "month", "cancels", "cancels_matured", "reenable"]].to_csv(OUTD / "t6_reenable_monthly.csv", index=False)
    # 3. back-test
    b = backtest(s)
    b.to_csv(OUTD / "t6_backtest.csv", index=False)
    bs = pd.concat([summarize_bt(b, ["subset", "k", "prov", "channel"]),
                    summarize_bt(b, ["subset", "k", "prov"]).assign(channel="ALL")])
    bs.round(4).to_csv(OUTD / "t6_backtest_summary.csv", index=False)
    # 4. timeliness
    Lt = L[L["month"].isin(months)]
    tl = []
    for (p, ch), y in Lt.groupby(["prov", "channel"]):
        if (p, ch) not in CHS:
            continue
        lag = (y["cancel_dt"] - y["last"]).dt.days.dropna()
        tl.append(dict(prov=p, channel=ch, W_lapse_detection_days=int(y["W"].iloc[0]),
                       cancel_lag_p10=lag.quantile(.1), cancel_lag_p25=lag.quantile(.25), cancel_lag_p50=lag.median(),
                       cancel_lag_p75=lag.quantile(.75), cancel_lag_p90=lag.quantile(.9),
                       median_days_earlier=int(y["W"].iloc[0]) - lag.median()))
    tl = pd.DataFrame(tl)
    tl.round(1).to_csv(OUTD / "t6_timeliness.csv", index=False)
    # 5. ChatGPT direct
    cd = chatgpt_direct(L, cn, c, s, data_end, months)
    cd.round(3).to_csv(OUTD / "t6_chatgpt_direct.csv", index=False)
    print(summ.round(3).to_string(index=False))
    print(s[s["complete"]].pivot_table(index=["subset", "prov", "channel"], columns="month", values="presence").round(2).iloc[:, -24:].to_string())
    print(pt.pivot_table(index=["subset", "prov", "channel"], columns=["dim", "value"], values="presence").round(2).to_string())
    print(bs.round(3).to_string(index=False))
    print(tl.round(1).to_string(index=False))
    print(cd.round(3).to_string(index=False))
