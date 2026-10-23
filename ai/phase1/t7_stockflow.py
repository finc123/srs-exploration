"""Task 7: stock-flow back-test under the agreed rules (RESULTS.md section 7).

Rules applied
- Subscription = uid x provider, channels pooled; ChatGPT direct excluded entirely. A new subscription (gross add) starts at
  the first paid receipt after a gap > W of the billing channel (out/recommended_windows.csv via common.windows; annual
  plans W = 400, quarterly 135), or at the first paid receipt after a same-provider cancel event (cancel followed by any
  later payment = churn + gross add; the churn is dated at that payment, when it is detected).
- Churn otherwise = lapse, dated at detection (last payment + W).
- Reliable subset R: a reference-sender receipt in the start month, then in every month; censored at the first month
  without one. Months whose reference receipts have not fully landed are HELD (no churn rate).
- EU: subscriptions that lapse after the user stopped sending receipts are panel exits (removed, as the engine does).
Model:  subs(t) = subs(t-1) + adds(t) - churn_rate(t, plan, tenure band) x subs(t-1), run as cohorts so tenure is tracked;
        churn_rate = R churn / R active at month start in that cell; sparse cells pool upward:
        (plan, band) -> (plan) -> (cadence, band) -> (cadence) -> provider (all within provider x region).
Comparisons (month-end stocks): full panel on non-Apple first channels (capture ~98-99%, observed reliable), full panel
all channels (Apple observed understated by missed emails), and R's own stock (model also removes R's censoring rate).
Starts 2024-01 and 2025-07; initial stock = observed stock at the previous month end.
Outputs: out/t7_rates.csv, out/t7_held.csv, out/t7_backtest.csv, out/t7_drift.csv, out/t7_shares.csv
"""
import numpy as np
import pandas as pd
from common import *
from t2_mailbox import ref_charges

MIN_ACT = 100
BANDS = [(0, 1, "m1"), (2, 3, "m2-3"), (4, 6, "m4-6"), (7, 12, "m7-12"), (13, 9999, "m13+")]


def band(age):
    age = np.asarray(age)
    out = np.empty(len(age), dtype=object)
    for lo, hi, lab in BANDS:
        out[(age >= lo) & (age <= hi)] = lab
    return out


def ymi(d):
    return d.dt.year * 12 + d.dt.month


def held_months(r, T):
    """Months whose reference receipts have not landed: landing share (ref users of m-1 and m-2 with a ref receipt in m)
    below 95% of the median of the prior 6 months; the partial data-end month is always held."""
    m = set(zip(r["uid"], ymi(r["dt"])))
    df = pd.DataFrame(list(m), columns=["uid", "ym"])
    s = set(m)
    yms = sorted(df["ym"].unique())
    rows = []
    for y in yms[-15:]:
        base = df[df["ym"] == y - 1]["uid"]
        base = base[[(u, y - 2) in s for u in base]]
        land = np.mean([(u, y) in s for u in base]) if len(base) else np.nan
        rows.append(dict(ym=y, base=len(base), landing=land))
    h = pd.DataFrame(rows)
    h["ref"] = h["landing"].shift(1).rolling(6).median()
    ymT = T.year * 12 + T.month
    h["fail"] = (h["landing"] < 0.95 * h["ref"]) | (h["ym"] >= ymT)
    # held = the trailing run of failing months (receipts still landing); an isolated failing month followed by landed
    # months is a capture dip, not lag (flagged 'dip', bridged in the follow rule)
    held, run = [], True
    for f in h["fail"][::-1]:
        run = run and bool(f)
        held.append(run)
    h["held"] = held[::-1]
    h["dip"] = h["fail"] & ~h["held"]
    h["month"] = [f"{(y - 1) // 12}-{(y - 1) % 12 + 1:02d}" for y in h["ym"]]
    return h


def build(region):
    W = windows()
    x = load(region)
    T = x["dt"].max()
    c = charges(x)
    c = c[c["renews"] & ~((c["prov"] == "chatgpt") & (c["channel"] == "direct"))].sort_values(["uid", "prov", "dt"]).reset_index(drop=True)
    c["W"] = [W(region, p, ch) for p, ch in zip(c["prov"], c["channel"])]
    c.loc[c["cadence"] == "A", "W"] = 400
    c.loc[c["cadence"] == "Q", "W"] = 135
    # cancel events (first per uid x provider x channel within 45 days), any channel except ChatGPT direct
    cn = x[(x["kind"] == "cancel") & ~((x["prov"] == "chatgpt") & (x["channel"] == "direct"))]
    cn = cn.drop_duplicates(["uid", "prov", "channel", "dt"]).sort_values(["uid", "prov", "channel", "dt"])
    cn = cn[~cn.groupby(["uid", "prov", "channel"])["dt"].diff().dt.days.le(45)]
    lc = pd.merge_asof(c[["uid", "prov", "dt"]].reset_index().sort_values("dt"),
                       cn[["uid", "prov", "dt"]].rename(columns={"dt": "cdt"}).sort_values("cdt"),
                       left_on="dt", right_on="cdt", by=["uid", "prov"], direction="backward", allow_exact_matches=True)
    c["last_cancel"] = lc.set_index("index")["cdt"].reindex(c.index)
    g = c.groupby(["uid", "prov"], sort=False)
    prev, prevW = g["dt"].shift(), g["W"].shift()
    lapse_new = prev.isna() | ((c["dt"] - prev).dt.days > prevW)
    cancel_new = ~lapse_new & c["last_cancel"].notna() & (c["last_cancel"] > prev)
    c["new"] = lapse_new | cancel_new
    c["split"] = cancel_new
    c["sid"] = c["new"].cumsum()
    s = c.groupby("sid").agg(uid=("uid", "first"), prov=("prov", "first"), plan=("plan", "first"), cad=("cadence", "first"),
                             channel=("channel", "first"), start=("dt", "min"), last=("dt", "max"), n=("dt", "size"),
                             W=("W", "last"), split_start=("split", "first"))
    # end: next subscription started by a cancel split -> churn at that payment; else lapse at last + W
    s = s.sort_values(["uid", "prov", "start"])
    nxt_start = s.groupby(["uid", "prov"])["start"].shift(-1)
    nxt_split = s.groupby(["uid", "prov"])["split_start"].shift(-1).fillna(False).astype(bool)
    s["known"] = (s["last"] + pd.to_timedelta(s["W"], unit="D")).where(~nxt_split, nxt_start)
    s["end_kind"] = np.where(nxt_split, "cancel_split", "lapse")
    s["event"] = s["known"] <= T
    if region == "eu":
        la = s["uid"].map(eu_last_active())
        s["exit"] = (la + pd.Timedelta(days=90) < T) & (la < s["known"]) & (s["end_kind"] == "lapse")
    else:
        s["exit"] = False
    s = s[~s["exit"]].copy()
    # reliable subset
    r = ref_charges(region)
    r = r[r["dt"] <= T]
    held = held_months(r, T)
    H = int(held.loc[~held["held"], "ym"].max())  # last landed month
    rmon = set(zip(r["uid"], ymi(r["dt"])))
    r2 = r[r["prov"] != "gone_storage"]
    rmon_g = set(zip(r2["uid"], ymi(r2["dt"])))
    ym0 = ymi(s["start"]).to_numpy()
    isg = (s["prov"] == "gemini").to_numpy()
    uids = s["uid"].to_numpy()
    s["in_R"] = [(u, m) in (rmon_g if gm else rmon) for u, m, gm in zip(uids, ym0, isg)]
    endym = np.where(s["event"], ymi(s["known"]), 10**6)
    cens = np.zeros(len(s), dtype=int)
    for i in np.where(s["in_R"].to_numpy())[0]:
        m = ym0[i] + 1
        ref = rmon_g if isg[i] else rmon
        while m <= min(endym[i], H):
            # a single missing month bridged by receipts either side (m+1 must be landed) counts as present
            if (uids[i], m) not in ref and not (m + 1 <= H and (uids[i], m - 1) in ref and (uids[i], m + 1) in ref):
                cens[i] = m
                break
            m += 1
    s["cens_ym"] = cens
    s["known_ym"] = np.where(s["event"], ymi(s["known"]), 0)
    s["start_ym"] = ym0
    s["region"] = region
    return s, held, H, T


def rates(s, H, first_ym):
    """R churn and censoring rates per month x (prov, plan, band) with pooling."""
    R = s[s["in_R"]]
    rows = []
    for t in range(first_ym, H + 1):
        act = R[(R["start_ym"] < t) & ((R["known_ym"] == 0) | (R["known_ym"] >= t)) & ((R["cens_ym"] == 0) | (R["cens_ym"] >= t))]
        if not len(act):
            continue
        a = act.assign(band=band(t - act["start_ym"].to_numpy()),
                       churn=(act["known_ym"] == t) & ((act["cens_ym"] == 0) | (act["cens_ym"] > t)),
                       cens=act["cens_ym"] == t)
        rows.append(a.groupby(["prov", "plan", "cad", "band"]).agg(active=("churn", "size"), churn=("churn", "sum"),
                                                                    cens=("cens", "sum")).reset_index().assign(ym=t))
    return pd.concat(rows, ignore_index=True)


class Rate:
    def __init__(self, rt, col):
        self.levels = []
        # (no provider-only level: annual plans must only take annual rates; t7/t7b outputs predate this change)
        for keys in (["prov", "plan", "band"], ["prov", "plan"], ["prov", "cad", "band"], ["prov", "cad"]):
            g = rt.groupby(["ym", *keys])[["active", col]].sum()
            g = g[g["active"] >= MIN_ACT]
            self.levels.append((keys, (g[col] / g["active"]).to_dict()))
        # last resort for small providers: provider x cadence pooled over the trailing 6 months
        g = rt.groupby(["prov", "cad", "ym"])[["active", col]].sum().sort_index()
        roll = g.groupby(level=[0, 1]).rolling(6, min_periods=1).sum().droplevel([0, 1])
        self.levels.append((["prov", "cad"], (roll[col] / roll["active"].clip(lower=1)).swaplevel(0, 2).swaplevel(1, 2).to_dict()))

    def get(self, ym, prov, plan, cad, bnd):
        vals = {"prov": prov, "plan": plan, "cad": cad, "band": bnd}
        for keys, d in self.levels:
            k = (ym, *[vals[k] for k in keys])
            if k in d:
                return d[k]
        return 0.0


def observed(s, ym):
    """Active at end of month ym: started by then, churn not yet detected."""
    return s[(s["start_ym"] <= ym) & ((s["known_ym"] == 0) | (s["known_ym"] > ym))]


def run_model(s, start_ym, end_ym, churn, cens=None, R_only=False):
    """Cohort stock-flow. Initial stock = observed at start_ym - 1 by (start month, plan, cad, prov)."""
    base = s[s["in_R"]] if R_only else s
    if R_only:
        init = base[(base["start_ym"] <= start_ym - 1) & ((base["known_ym"] == 0) | (base["known_ym"] > start_ym - 1))
                    & ((base["cens_ym"] == 0) | (base["cens_ym"] > start_ym - 1))]
    else:
        init = observed(base, start_ym - 1)
    coh = init.groupby(["prov", "plan", "cad", "start_ym"]).size().astype(float).rename("n").reset_index()
    adds = base.groupby(["prov", "plan", "cad", "start_ym"]).size().astype(float).rename("n").reset_index()
    out = []
    for t in range(start_ym, end_ym + 1):
        if len(coh):
            age = t - coh["start_ym"].to_numpy()
            b = band(age)
            h = np.array([churn.get(t, p, pl, cd, bb) for p, pl, cd, bb in zip(coh["prov"], coh["plan"], coh["cad"], b)])
            if cens is not None:
                h = h + np.array([cens.get(t, p, pl, cd, bb) for p, pl, cd, bb in zip(coh["prov"], coh["plan"], coh["cad"], b)])
            coh["n"] = coh["n"] * (1 - np.clip(h, 0, 1))
        coh = pd.concat([coh, adds[adds["start_ym"] == t]], ignore_index=True)
        coh = coh.groupby(["prov", "plan", "cad", "start_ym"], as_index=False)["n"].sum()
        out.append(coh.groupby("prov")["n"].sum().rename("model").reset_index().assign(ym=t))
    return pd.concat(out)


def obs_series(s, start_ym, end_ym, R_only=False):
    rows = []
    for t in range(start_ym, end_ym + 1):
        if R_only:
            a = s[s["in_R"] & (s["start_ym"] <= t) & ((s["known_ym"] == 0) | (s["known_ym"] > t)) & ((s["cens_ym"] == 0) | (s["cens_ym"] > t))]
        else:
            a = observed(s, t)
        rows.append(a.groupby("prov").size().rename("obs").reset_index().assign(ym=t))
    return pd.concat(rows)


def ymlab(y):
    return f"{(y - 1) // 12}-{(y - 1) % 12 + 1:02d}"


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 500)
    allbt, allrt, allheld, shares = [], [], [], []
    for region in ["us", "eu"]:
        s, held, H, T = build(region)
        allheld.append(held.assign(region=region))
        rt = rates(s, H, 2024 * 12 + 1)
        allrt.append(rt.assign(region=region))
        churn, cens = Rate(rt, "churn"), Rate(rt, "cens")
        # diagnostic: rates from R's non-Apple subscriptions only (is the US gap channel mix / R optimism?)
        churn_na = Rate(rates(s[s["channel"] != "apple"], H, 2024 * 12 + 1), "churn")
        for start in (2024 * 12 + 1, 2025 * 12 + 7):
            for comp, ss, R_only, use_cens, ch_ in [("full_nonapple", s[s["channel"] != "apple"], False, False, churn),
                                                    ("full_nonapple_ratesRnonapple", s[s["channel"] != "apple"], False, False, churn_na),
                                                    ("full_all", s, False, False, churn), ("R_own", s, True, True, churn)]:
                m = run_model(ss, start, H, ch_, cens if use_cens else None, R_only)
                o = obs_series(ss, start, H, R_only)
                bt = m.merge(o, on=["prov", "ym"], how="outer").assign(region=region, start=ymlab(start), comparison=comp)
                bt["month_n"] = bt["ym"] - start + 1
                allbt.append(bt)
        # shares at latest non-held month (model on all included channels, run from 2024-01)
        m = run_model(s, 2024 * 12 + 1, H, churn)
        m = m[m["ym"] == H]
        o = observed(s, H).groupby("prov").size().rename("obs_full")
        oR = s[s["in_R"] & (s["start_ym"] <= H) & ((s["known_ym"] == 0) | (s["known_ym"] > H)) & ((s["cens_ym"] == 0) | (s["cens_ym"] > H))].groupby("prov").size().rename("obs_R")
        sh = m.set_index("prov")["model"].to_frame().join(o).join(oR)
        for col in ["model", "obs_full", "obs_R"]:
            sh[f"share_{col}"] = sh[col] / sh[col].sum()
        shares.append(sh.reset_index().assign(region=region, month=ymlab(H)))
        print(region, "last landed month", ymlab(H), flush=True)
    bt = pd.concat(allbt)
    bt["month"] = bt["ym"].map(ymlab)
    bt["err"] = bt["model"] / bt["obs"] - 1
    bt.round(3).to_csv(OUTD / "t7_backtest.csv", index=False)
    pd.concat(allrt).to_csv(OUTD / "t7_rates.csv", index=False)
    pd.concat(allheld).round(4).to_csv(OUTD / "t7_held.csv", index=False)
    sh = pd.concat(shares)
    sh.round(4).to_csv(OUTD / "t7_shares.csv", index=False)
    # drift at month 6, 12 and latest
    d = bt[bt["month_n"].isin([6, 12])].pivot_table(index=["region", "start", "comparison", "prov"], columns="month_n", values="err")
    last = bt.sort_values("ym").groupby(["region", "start", "comparison", "prov"]).last()[["month", "obs", "model", "err"]]
    drift = d.join(last).reset_index()
    drift.columns = [f"err_m{c}" if isinstance(c, (int, np.integer)) else c for c in drift.columns]
    drift.round(3).to_csv(OUTD / "t7_drift.csv", index=False)
    print(pd.concat(allheld).round(3).to_string(index=False))
    print(drift.round(3).to_string(index=False))
    print(sh.round(3).to_string(index=False))
