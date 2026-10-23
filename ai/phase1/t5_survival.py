"""Task 5: survival (Kaplan-Meier) on the reliable subset, churn dated when known, monthly churn, and index back-test.

Subscription = uid x provider, channels pooled (renewing channels only; ChatGPT direct sends sign-up receipts only and is
left to the modelled line). A new subscription starts when the gap from the previous paid receipt exceeds W of the
channel that billed it (W = p99 continuing gap in the reliable subset, t2b). Plan = plan of the first receipt.

Churn dated WHEN KNOWN: known = last payment + W (no payment from the provider on any channel by then).
Reliable subset (time-local, reference senders only to keep censoring independent of AI churn): a subscription enters R
if a reference sender (iCloud+/Google One storage/YouTube Premium/Spotify) has a paid receipt in its start month; it is
followed while the reference has a receipt every month; the first month without one censors it (start of that month).
A churn counts only if the reference is present in every month up to the month churn becomes known. Open subscriptions
are censored at the data end (no settled month). EU: also censored when the user stops sending receipts.

Back-test: S (churn) and G (reference-loss censoring) are re-estimated on data truncated 6 months before the end, then
model(t) = sum_s adds(s) x S(t-s) x G(t-s) is compared with the observed R actives over the 6 hold-out months.
Outputs: out/t5_km.csv, out/t5_monthly_churn.csv, out/t5_backtest.csv, data/subs_{region}.parquet
"""
import numpy as np
import pandas as pd
from common import *
from t2_mailbox import ref_charges

H = 1500
PLAN_MIN = 300  # plans with fewer R subscriptions are pooled into '<prov>_other'


def build(region, T):
    """Subscriptions as of data end T (inputs truncated at T)."""
    W = windows()
    x = load(region)
    c = charges(x)
    c = c[c["renews"] & (c["dt"] <= T)].sort_values(["uid", "prov", "dt"]).reset_index(drop=True)
    c["W"] = [W(region, p, ch) for p, ch in zip(c["prov"], c["channel"])]
    c.loc[c["cadence"] == "A", "W"] = 400
    c.loc[c["cadence"] == "Q", "W"] = 135
    g = c.groupby(["uid", "prov"], sort=False)
    prev, prevW = g["dt"].shift(), g["W"].shift()
    c["new"] = prev.isna() | ((c["dt"] - prev).dt.days > prevW)
    c["sid"] = c["new"].cumsum()
    s = c.groupby("sid").agg(uid=("uid", "first"), prov=("prov", "first"), plan=("plan", "first"), cad=("cadence", "first"),
                             channel=("channel", "first"), start=("dt", "min"), last=("dt", "max"), n=("dt", "size"),
                             W=("W", "last"))
    s["known"] = s["last"] + pd.to_timedelta(s["W"], unit="D")
    s["event"] = s["known"] <= T
    # reference presence by month
    r = ref_charges(region)
    r = r[r["dt"] <= T]
    rmon = set(zip(r["uid"], r["dt"].dt.year * 12 + r["dt"].dt.month))
    # Gemini plans replace Google One storage (upgrade ends the storage plan): storage is not a valid reference for Gemini
    r2 = r[r["prov"] != "gone_storage"]
    rmon_g = set(zip(r2["uid"], r2["dt"].dt.year * 12 + r2["dt"].dt.month))
    ymT = T.year * 12 + T.month
    ym0 = (s["start"].dt.year * 12 + s["start"].dt.month).to_numpy()
    isg = (s["prov"] == "gemini").to_numpy()
    s["in_R"] = [(u, m) in (rmon_g if gm else rmon) for u, m, gm in zip(s["uid"], ym0, isg)]
    # follow: first month after start without a reference receipt (month of T counts as present)
    endym = np.where(s["event"], s["known"].dt.year * 12 + s["known"].dt.month, ymT)
    cens_ym = np.full(len(s), 0)
    R = s["in_R"].to_numpy()
    uids = s["uid"].to_numpy()
    for i in np.where(R)[0]:
        m = ym0[i] + 1
        while m <= min(endym[i], ymT - 1):
            if (uids[i], m) not in (rmon_g if isg[i] else rmon):
                cens_ym[i] = m
                break
            m += 1
    s["ref_lost_ym"] = cens_ym
    lost = cens_ym > 0
    s["ref_lost"] = pd.NaT
    if lost.any():
        s.loc[lost, "ref_lost"] = pd.to_datetime(pd.DataFrame({"year": (cens_ym[lost] - 1) // 12,
                                                               "month": (cens_ym[lost] - 1) % 12 + 1, "day": 1})).to_numpy()
    s["ref_lost"] = pd.to_datetime(s["ref_lost"])
    if region == "eu":
        la = s["uid"].map(eu_last_active())
        quiet = (la + pd.Timedelta(days=90) < T) & (la < s["known"])
        s["exit"] = la.where(quiet)
    else:
        s["exit"] = pd.NaT
    s["exit"] = pd.to_datetime(s["exit"])
    cens = s[["ref_lost", "exit"]].min(axis=1)
    s["R_event"] = s["in_R"] & s["event"] & (cens.isna() | (cens > s["known"]))
    s["R_end"] = s["known"].where(s["R_event"], cens.fillna(T).clip(upper=T))
    s["age_end"] = (s["R_end"] - s["start"]).dt.days.clip(lower=0)
    s["censor_kind"] = np.select([s["R_event"], s["ref_lost"].notna() & (s["ref_lost"] == s["R_end"]),
                                  s["exit"].notna() & (s["exit"] == s["R_end"])], ["churn", "ref_lost", "exit"], "open")
    s["region"] = region
    s["country"] = s["uid"].map(x.drop_duplicates("uid").set_index("uid")["country"]) if region == "eu" else "us"
    return s


def km(age, event, horizon=H):
    age = np.asarray(age).clip(max=horizon - 1)
    event = np.asarray(event, bool)
    at_risk = np.bincount(age, minlength=horizon)[::-1].cumsum()[::-1].astype(float)
    d = np.bincount(age[event], minlength=horizon)
    h = np.divide(d, at_risk, out=np.zeros(horizon), where=at_risk > 0)
    return np.cumprod(1 - h)


def km_window(start, age_end, event, w0, w1, horizon=H):
    """Period KM: hazards by age from exposure and events falling in calendar window [w0, w1] only."""
    e = ((w0 - start).dt.days).clip(lower=0).to_numpy()
    x = np.minimum(age_end.to_numpy(), (w1 - start).dt.days.to_numpy())
    ok = x >= e
    e, x, ev = e[ok].clip(max=horizon - 1), x[ok].clip(max=horizon - 1), np.asarray(event)[ok]
    diff = np.zeros(horizon + 1)
    np.add.at(diff, e, 1)
    np.add.at(diff, x + 1, -1)
    at_risk = np.cumsum(diff)[:horizon]
    d = np.bincount(x[ev & (age_end.to_numpy()[ok] == x)], minlength=horizon)[:horizon]
    h = np.divide(d, at_risk, out=np.zeros(horizon), where=at_risk > 0)
    return np.cumprod(1 - h)


def curves_recent(s, T, days=365):
    out = {}
    r = s[s["in_R"]]
    w0 = T - pd.Timedelta(days=days)
    for (p, pl), y in r.groupby(["prov", "pk"]):
        lost = y["censor_kind"].isin(["ref_lost", "exit"])
        out[(p, pl)] = (km_window(y["start"], y["age_end"], y["R_event"].to_numpy(), w0, T),
                        km_window(y["start"], y["age_end"], lost.to_numpy(), w0, T))
    return out


def haz(age, event, horizon=H):
    age = np.asarray(age).clip(max=horizon - 1)
    event = np.asarray(event, bool)
    at_risk = np.bincount(age, minlength=horizon)[::-1].cumsum()[::-1].astype(float)
    d = np.bincount(age[event], minlength=horizon)
    return np.divide(d, at_risk, out=np.zeros(horizon), where=at_risk > 0), at_risk


def curves_cohort(s, min_risk=200):
    """S and G per provider x plan x start half-year: the cohort's own hazards where >= min_risk at risk, pooled beyond."""
    out = {}
    r = s[s["in_R"]].assign(coh=lambda d: d["start"].dt.year.astype(str) + "H" + ((d["start"].dt.month > 6) + 1).astype(str))
    lost = r["censor_kind"].isin(["ref_lost", "exit"])
    for (p, pl), y in r.groupby(["prov", "pk"]):
        hp, _ = haz(y["age_end"], y["R_event"])
        gp, _ = haz(y["age_end"], lost[y.index])
        for coh, z in y.groupby("coh"):
            hc, ar = haz(z["age_end"], z["R_event"])
            gc, _ = haz(z["age_end"], lost[z.index])
            use = ar >= min_risk
            out[(p, pl, coh)] = (np.cumprod(1 - np.where(use, hc, hp)), np.cumprod(1 - np.where(use, gc, gp)))
        out[(p, pl, "latest")] = out[(p, pl, sorted(y["coh"].unique())[-1])]
    return out


def model_vs_obs_cohort(s, cv, months, T0):
    rows = []
    r = s[s["in_R"]].assign(coh=lambda d: d["start"].dt.year.astype(str) + "H" + ((d["start"].dt.month > 6) + 1).astype(str))
    for (p, pl), y in r.groupby(["prov", "pk"]):
        for t in months:
            started = y[y["start"] <= t]
            model = 0.0
            for coh, z in started.groupby("coh"):
                key = (p, pl, coh) if (p, pl, coh) in cv and z["start"].max() <= T0 else (p, pl, "latest")
                if key not in cv:
                    continue
                S, G = cv[key]
                age = (t - z["start"]).dt.days.clip(upper=H - 1).to_numpy()
                model += (S[age] * G[age]).sum()
            obs = ((started["R_end"] > t) | ((started["censor_kind"] == "open") & (started["R_end"] >= t))).sum()
            rows.append(dict(prov=p, pk=pl, month=t, model=model, obs=obs))
    return pd.DataFrame(rows)


def calib(s, st, T0, T):
    """Hold-out hazard calibration: observed vs expected churn and reference-loss events in (T0, T] among R subs at risk,
    expected from the training-period hazards (provider x plan)."""
    rows = []
    r = s[s["in_R"] & (s["R_end"] > T0)]
    tr = st[st["in_R"]]
    for (p, pl), y in r.groupby(["prov", "pk"]):
        z = tr[(tr["prov"] == p) & (tr["pk"] == pl)]
        if len(z) < 100:
            continue
        hc, _ = haz(z["age_end"], z["R_event"])
        hg, _ = haz(z["age_end"], z["censor_kind"].isin(["ref_lost", "exit"]))
        Lc, Lg = np.r_[0, np.cumsum(hc)], np.r_[0, np.cumsum(hg)]
        a0 = (T0 - y["start"]).dt.days.clip(lower=0).clip(upper=H - 1).to_numpy()
        a1 = y["age_end"].clip(upper=H - 1).to_numpy()
        rows.append(dict(prov=p, pk=pl, at_risk=len(y),
                         churn_obs=int((y["R_event"] & (y["R_end"] > T0)).sum()), churn_exp=(Lc[a1 + 1] - Lc[a0]).sum(),
                         lost_obs=int((y["censor_kind"].isin(["ref_lost", "exit"]) & (y["R_end"] > T0)).sum()),
                         lost_exp=(Lg[a1 + 1] - Lg[a0]).sum()))
    return pd.DataFrame(rows)


def plan_key(s):
    n = s[s["in_R"]].groupby(["prov", "plan"]).size()
    big = set(n[n >= PLAN_MIN].index)
    return np.where([(p, q) in big for p, q in zip(s["prov"], s["plan"])], s["plan"], s["prov"] + "_other")


def curves(s):
    out = {}
    r = s[s["in_R"]]
    for (p, pl), y in r.groupby(["prov", "pk"]):
        out[(p, pl)] = (km(y["age_end"], y["R_event"]), km(y["age_end"], y["censor_kind"].isin(["ref_lost", "exit"])))
    return out


def model_vs_obs(s, cv, months, T0=None):
    if T0 is not None:  # split holdout into subscriptions started before / after the training end
        return pd.concat([model_vs_obs(s[s["start"] <= T0], cv, months).assign(cohort="started<=T0"),
                          model_vs_obs(s[s["start"] > T0], cv, months).assign(cohort="started>T0")])
    rows = []
    r = s[s["in_R"]]
    for (p, pl), y in r.groupby(["prov", "pk"]):
        if (p, pl) not in cv:
            continue
        S, G = cv[(p, pl)]
        for t in months:
            started = y[y["start"] <= t]
            age = (t - started["start"]).dt.days.clip(upper=H - 1).to_numpy()
            model = (S[age] * G[age]).sum()
            obs = ((started["R_end"] > t) | ((started["censor_kind"] == "open") & (started["R_end"] >= t))).sum()
            rows.append(dict(prov=p, pk=pl, month=t, model=model, obs=obs))
    return pd.DataFrame(rows)


def run(region):
    x_end = load(region)["dt"].max()
    s = build(region, x_end)
    s["pk"] = plan_key(s)
    s.to_parquet(D / f"subs_{region}.parquet")
    # KM by provider x plan (and EU country where n allows)
    rows = []
    groups = [("region", s)] + ([(cc, s[s["country"] == cc]) for cc in ["uk", "de", "fr", "es", "it"]] if region == "eu" else [])
    for gname, ss in groups:
        r = ss[ss["in_R"]]
        for (p, pl), y in list(r.groupby(["prov", "pk"])) + [((p, "ALL"), y) for p, y in r.groupby("prov")]:
            if len(y) < 100:
                continue
            S = km(y["age_end"], y["R_event"])
            rows.append(dict(region=region, geo=gname, prov=p, plan=pl, subs_R=len(y), churn_events=int(y["R_event"].sum()),
                             ref_lost=int((y["censor_kind"] == "ref_lost").sum()), open=int((y["censor_kind"] == "open").sum()),
                             S30=S[30], S60=S[60], S90=S[90], S120=S[120], S180=S[180], S365=S[365],
                             at_risk_365=int((y["age_end"] >= 365).sum())))
    kmt = pd.DataFrame(rows)
    # monthly churn dated when known (R): events in month / R actives at start of month
    r = s[s["in_R"]]
    mrows = []
    for m in pd.period_range("2024-07", x_end.to_period("M"), freq="M"):
        t0, t1 = m.start_time, m.end_time.normalize()
        for p, y in r.groupby("prov"):
            act = ((y["start"] < t0) & (y["R_end"] >= t0)).sum()
            ev = (y["R_event"] & (y["R_end"] >= t0) & (y["R_end"] <= t1)).sum()
            adds = ((y["start"] >= t0) & (y["start"] <= t1)).sum()
            mrows.append(dict(region=region, prov=p, month=str(m), R_active_start=act, R_adds=adds, R_churn=ev,
                              churn_rate=ev / act if act else np.nan))
    mc = pd.DataFrame(mrows)
    # back-test: train on data truncated at T0
    T0 = x_end - pd.Timedelta(days=182)
    st = build(region, T0)
    st["pk"] = plan_key(st)
    st["pk"] = np.where(st["pk"].isin(set(s["pk"])), st["pk"], st["prov"] + "_other")
    cv_tr = curves(st)
    cv_full = curves(s)
    s_months = list(pd.date_range("2024-07-01", x_end, freq="MS")) + [x_end]
    bt_in = model_vs_obs(s, cv_full, s_months).assign(fit="in_sample")
    ho_months = [m for m in s_months if m > T0]
    bt_ho = model_vs_obs(s, cv_tr, ho_months, T0).assign(fit="holdout_trained_to_T0")
    bt_hr = model_vs_obs(s, curves_recent(st, T0), ho_months, T0).assign(fit="holdout_trailing12m_hazards")
    bt_co = model_vs_obs_cohort(s, curves_cohort(st), ho_months, T0).assign(fit="holdout_cohort_S")
    bt = pd.concat([bt_in, bt_ho, bt_hr, bt_co]).assign(region=region)
    cal = calib(s, st, T0, x_end).assign(region=region)
    return kmt, mc, bt, cal


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 600)
    out = [run(r) for r in ["us", "eu"]]
    kmt, mc, bt, cal = (pd.concat(z) for z in zip(*out))
    cal.round(1).to_csv(OUTD / "t5_holdout_calibration.csv", index=False)
    cp = cal.groupby(["region", "prov"])[["at_risk", "churn_obs", "churn_exp", "lost_obs", "lost_exp"]].sum()
    cp["churn_ratio"] = cp["churn_obs"] / cp["churn_exp"]
    cp["lost_ratio"] = cp["lost_obs"] / cp["lost_exp"]
    print(cp.round(2).to_string())
    print(cal.round(2).to_string(index=False))
    kmt.round(4).to_csv(OUTD / "t5_km.csv", index=False)
    mc.round(4).to_csv(OUTD / "t5_monthly_churn.csv", index=False)
    bt.round(2).to_csv(OUTD / "t5_backtest.csv", index=False)
    print(kmt[kmt["geo"] == "region"].round(3).to_string(index=False))
    agg = bt.groupby(["region", "prov", "fit", "month"])[["model", "obs"]].sum().reset_index()
    agg["err"] = agg["model"] / agg["obs"] - 1
    agg["month"] = agg["month"].astype(str)
    print(agg[agg["fit"] != "in_sample"].pivot_table(index=["region", "prov", "fit"], columns="month", values="err").round(3).to_string())
    ins = agg[agg["fit"] == "in_sample"]
    c = bt[bt["fit"] == "holdout_trained_to_T0"].groupby(["region", "prov", "cohort", "month"])[["model", "obs"]].sum()
    c = c.groupby(level=[0, 1, 2]).last()
    c["err"] = c["model"] / c["obs"] - 1
    print(c.round(3).to_string())
    print(ins.pivot_table(index=["region", "prov"], columns="month", values="err").round(3).iloc[:, ::3].to_string())
