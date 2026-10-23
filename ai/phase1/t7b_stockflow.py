"""Task 7b: stock-flow back-test with channel-specific churn-rate sources (user decision 2026-10-20).

Churn-rate source per provider x region x channel (first billing channel of the subscription):
  FULL PANEL where all-user renewal capture >= 98% (t2b 'all' capture, out/recommended_windows.csv), else the reliable
  subset R (always Apple). Rates per month x plan x tenure band within each provider x channel, pooled upward within the
  channel (plan -> cadence x band -> cadence), then to the channel-pooled t7 R rate as a last resort.
The cohort model runs per channel, so the provider x plan x tenure rate is the channel rates weighted by each channel's
share of the modelled stock. Everything else as t7 (rules in RESULTS.md section 7; one-month reference-gap tolerance).
Comparisons: full panel non-Apple (now partly in-sample: cells on full-panel rates reproduce their own churn), full panel
non-Apple on R-sourced cells only (the out-of-sample check), full panel all channels.
Usage: python t7b_stockflow.py [capture threshold, default 0.98]  (non-default thresholds write *_cap{x}.csv)
Outputs: out/t7b_sources.csv, out/t7b_backtest.csv, out/t7b_drift.csv, out/t7b_shares.csv
"""
import numpy as np
import pandas as pd
from common import *
from t7_stockflow import build, rates as rates_R, Rate, band, observed, ymlab, MIN_ACT

import sys
CAPTURE_MIN = float(sys.argv[1]) if len(sys.argv) > 1 else 0.98
SUF = "" if CAPTURE_MIN == 0.98 else f"_cap{int(round(CAPTURE_MIN * 1000))}"


def rates_ch(s, H, first_ym, use_R):
    """Churn / active at month start per (prov, channel, plan, cad, band); R (with censoring) or full panel."""
    base = s[s["in_R"]] if use_R else s
    rows = []
    for t in range(first_ym, H + 1):
        cond = (base["start_ym"] < t) & ((base["known_ym"] == 0) | (base["known_ym"] >= t))
        if use_R:
            cond &= (base["cens_ym"] == 0) | (base["cens_ym"] >= t)
        act = base[cond]
        if not len(act):
            continue
        churn = act["known_ym"] == t
        if use_R:
            churn &= (act["cens_ym"] == 0) | (act["cens_ym"] > t)
        a = act.assign(band=band(t - act["start_ym"].to_numpy()), churn=churn)
        rows.append(a.groupby(["prov", "channel", "plan", "cad", "band"]).agg(active=("churn", "size"), churn=("churn", "sum"))
                    .reset_index().assign(ym=t))
    return pd.concat(rows, ignore_index=True)


class ChRate:
    def __init__(self, rt, fallback):
        self.levels = []
        for keys in (["prov", "channel", "plan", "band"], ["prov", "channel", "plan"], ["prov", "channel", "cad", "band"],
                     ["prov", "channel", "cad"]):
            g = rt.groupby(["ym", *keys])[["active", "churn"]].sum()
            g = g[g["active"] >= MIN_ACT]
            self.levels.append((keys, (g["churn"] / g["active"]).to_dict()))
        self.fb = fallback

    def get(self, ym, prov, ch, plan, cad, bnd):
        vals = {"prov": prov, "channel": ch, "plan": plan, "cad": cad, "band": bnd}
        for keys, d in self.levels:
            k = (ym, *[vals[k] for k in keys])
            if k in d:
                return d[k]
        return self.fb.get(ym, prov, plan, cad, bnd)


def run_model(s, start_ym, end_ym, rate):
    init = observed(s, start_ym - 1)
    key = ["prov", "channel", "plan", "cad", "start_ym"]
    coh = init.groupby(key).size().astype(float).rename("n").reset_index()
    adds = s.groupby(key).size().astype(float).rename("n").reset_index()
    out = []
    for t in range(start_ym, end_ym + 1):
        if len(coh):
            b = band(t - coh["start_ym"].to_numpy())
            h = np.array([rate.get(t, p, ch, pl, cd, bb) for p, ch, pl, cd, bb in
                          zip(coh["prov"], coh["channel"], coh["plan"], coh["cad"], b)])
            coh["n"] = coh["n"] * (1 - np.clip(h, 0, 1))
        coh = pd.concat([coh, adds[adds["start_ym"] == t]], ignore_index=True).groupby(key, as_index=False)["n"].sum()
        out.append(coh.groupby("prov")["n"].sum().rename("model").reset_index().assign(ym=t))
    return pd.concat(out)


def obs_series(s, start_ym, end_ym):
    return pd.concat([observed(s, t).groupby("prov").size().rename("obs").reset_index().assign(ym=t)
                      for t in range(start_ym, end_ym + 1)])


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 500)
    cap = pd.read_csv(OUTD / "recommended_windows.csv").set_index(["region", "prov", "channel"])["capture_all"]
    allbt, shares, srcs = [], [], []
    for region in ["us", "eu"]:
        s, held, H, T = build(region)
        first = 2024 * 12 + 1
        fb = Rate(rates_R(s, H, first), "churn")
        rt_full = rates_ch(s, H, first, use_R=False)
        rt_R = rates_ch(s, H, first, use_R=True)
        src = {}
        for (p, ch) in s[["prov", "channel"]].drop_duplicates().itertuples(index=False):
            c_ = cap.get((region, p, ch), np.nan)
            src[(p, ch)] = "full" if (ch != "apple" and c_ >= CAPTURE_MIN) else "R"
            n = int((s["prov"].eq(p) & s["channel"].eq(ch)).sum())
            srcs.append(dict(region=region, prov=p, channel=ch, capture_all=c_, source=src[(p, ch)], subs=n))
        full_keys = {k for k, v in src.items() if v == "full"}
        sel = lambda rt, want: rt[[((p, ch) in full_keys) == want for p, ch in zip(rt["prov"], rt["channel"])]]
        rate = ChRate(pd.concat([sel(rt_full, True), sel(rt_R, False)]), fb)
        s["src"] = [src[(p, ch)] for p, ch in zip(s["prov"], s["channel"])]
        for start in (2024 * 12 + 1, 2025 * 12 + 7):
            for comp, ss in [("full_nonapple", s[s["channel"] != "apple"]),
                             ("full_nonapple_Rcells", s[(s["channel"] != "apple") & (s["src"] == "R")]),
                             ("full_all", s)]:
                m = run_model(ss, start, H, rate)
                o = obs_series(ss, start, H)
                bt = m.merge(o, on=["prov", "ym"], how="outer").assign(region=region, start=ymlab(start), comparison=comp)
                bt["month_n"] = bt["ym"] - start + 1
                allbt.append(bt)
        m = run_model(s, first, H, rate)
        m = m[m["ym"] == H].set_index("prov")["model"]
        o = observed(s, H).groupby("prov").size().rename("obs_full")
        sh = m.to_frame().join(o)
        for col in ["model", "obs_full"]:
            sh[f"share_{col}"] = sh[col] / sh[col].sum()
        shares.append(sh.reset_index().assign(region=region, month=ymlab(H)))
        print(region, "done", ymlab(H), flush=True)
    pd.DataFrame(srcs).round(4).to_csv(OUTD / f"t7b_sources{SUF}.csv", index=False)
    bt = pd.concat(allbt)
    bt["month"] = bt["ym"].map(ymlab)
    bt["err"] = bt["model"] / bt["obs"] - 1
    bt.round(3).to_csv(OUTD / f"t7b_backtest{SUF}.csv", index=False)
    d = bt[bt["month_n"].isin([6, 12])].pivot_table(index=["region", "start", "comparison", "prov"], columns="month_n", values="err")
    last = bt.sort_values("ym").groupby(["region", "start", "comparison", "prov"]).last()[["month", "obs", "model", "err"]]
    drift = d.join(last).reset_index()
    drift.columns = [f"err_m{c}" if isinstance(c, (int, np.integer)) else c for c in drift.columns]
    drift.round(3).to_csv(OUTD / f"t7b_drift{SUF}.csv", index=False)
    sh = pd.concat(shares)
    sh.round(4).to_csv(OUTD / f"t7b_shares{SUF}.csv", index=False)
    print(pd.DataFrame(srcs).sort_values(["region", "prov", "channel"]).round(3).to_string(index=False))
    print(drift.round(3).to_string(index=False))
    print(sh.round(3).to_string(index=False))
