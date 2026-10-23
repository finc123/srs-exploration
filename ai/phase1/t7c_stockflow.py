"""Task 7c: final Phase 1 re-run (rules in RESULTS.md 7c and FINAL_SPEC.md).

Changes vs t7b:
- Reference senders: iCloud+, YouTube Premium, Spotify, and a different AI provider's paid receipt. Google One storage is
  removed (its receipts fell by a third in May-June 2026 and it is replaced by Gemini plans).
- Lapse windows re-derived with that reference set (t2b logic -> out/t2c_windows.csv -> out/final_windows.csv).
- Full-panel churn rates where all-user renewal capture >= 97.5%; reliable subset R elsewhere (always Apple).
- Held months and the one-month reference-gap tolerance as t7 (held months measured on iCloud+/YouTube/Spotify).
Outputs: out/t2c_windows.csv, out/final_windows.csv, out/t7c_sources.csv, out/t7c_held.csv, out/t7c_backtest.csv,
out/t7c_drift.csv, out/t7c_shares.csv
"""
import numpy as np
import pandas as pd
import common
from common import *
import t2_mailbox
t2_mailbox.REF_EXCLUDE = {"gone_storage"}
from t2_mailbox import ref_charges
import t2b_windows
from t7_stockflow import held_months, rates as rates_R, Rate, band, observed, ymlab, ymi
from t7b_stockflow import rates_ch, ChRate, run_model, obs_series

CAPTURE_MIN = 0.975
FIRST = 2024 * 12 + 1


def final_windows():
    w = pd.concat([t2b_windows.run("us"), t2b_windows.run("eu")])
    w.round(4).to_csv(OUTD / "t2c_windows.csv", index=False)
    common.WINDOWS_FILE = "t2c_windows.csv"
    get = windows()
    a = w[(w["subset"] == "all") & (w["prov"] != "ALL") & (w["channel"] != "ALL")].set_index(["region", "prov", "channel"])
    r = w[(w["subset"] == "live_any") & (w["prov"] != "ALL") & (w["channel"] != "ALL")].set_index(["region", "prov", "channel"])
    idx = a.index.union(r.index)
    out = pd.DataFrame({"gaps_all": a["n_gaps"], "capture_all": a["capture"], "p99_all": a["p99"], "gaps_R": r["n_gaps"],
                        "capture_R": r["capture"], "p99_R": r["p99"]}, index=idx).reset_index()
    out["W_monthly"] = [get(*k) for k in zip(out["region"], out["prov"], out["channel"])]
    out["W_source"] = np.where(out["gaps_R"].fillna(0) >= 2000, "own cell", "pooled (provider, else channel)")
    out["W_quarterly"], out["W_annual"] = 135, 400
    out["rate_source"] = np.where((out["channel"] != "apple") & (out["capture_all"] >= CAPTURE_MIN), "full_panel", "reliable_subset")
    out.round(4).to_csv(OUTD / "final_windows.csv", index=False)
    return out


def build(region):
    """As t7_stockflow.build, with the final reference set (incl. other AI providers)."""
    W = windows()
    x = load(region)
    T = x["dt"].max()
    c = charges(x)
    other_ai = c[["uid", "prov", "dt"]].copy()  # any paid AI receipt (incl. ChatGPT direct sign-ups) as reference evidence
    c = c[c["renews"] & ~((c["prov"] == "chatgpt") & (c["channel"] == "direct"))].sort_values(["uid", "prov", "dt"]).reset_index(drop=True)
    c["W"] = [W(region, p, ch) for p, ch in zip(c["prov"], c["channel"])]
    c.loc[c["cadence"] == "A", "W"] = 400
    c.loc[c["cadence"] == "Q", "W"] = 135
    cn = x[(x["kind"] == "cancel") & ~((x["prov"] == "chatgpt") & (x["channel"] == "direct"))]
    cn = cn.drop_duplicates(["uid", "prov", "channel", "dt"]).sort_values(["uid", "prov", "channel", "dt"])
    cn = cn[~cn.groupby(["uid", "prov", "channel"])["dt"].diff().dt.days.le(45)]
    lc = pd.merge_asof(c[["uid", "prov", "dt"]].reset_index().sort_values("dt"),
                       cn[["uid", "prov", "dt"]].rename(columns={"dt": "cdt"}).sort_values("cdt"),
                       left_on="dt", right_on="cdt", by=["uid", "prov"], direction="backward")
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
    s = s.sort_values(["uid", "prov", "start"])
    nxt_start = s.groupby(["uid", "prov"])["start"].shift(-1)
    nxt_split = s.groupby(["uid", "prov"])["split_start"].shift(-1).fillna(False).astype(bool)
    s["known"] = (s["last"] + pd.to_timedelta(s["W"], unit="D")).where(~nxt_split, nxt_start)
    s["end_kind"] = np.where(nxt_split, "cancel_split", "lapse")
    s["event"] = s["known"] <= T
    if region == "eu":
        la = s["uid"].map(eu_last_active())
        s = s[~((la + pd.Timedelta(days=90) < T) & (la < s["known"]) & (s["end_kind"] == "lapse"))].copy()
    r = ref_charges(region)
    r = r[r["dt"] <= T]
    held = held_months(r, T)
    H = int(held.loc[~held["held"], "ym"].max())
    rmon = set(zip(r["uid"], ymi(r["dt"])))
    am = other_ai.assign(ym=ymi(other_ai["dt"])).drop_duplicates(["uid", "ym", "prov"])
    aimon = am.groupby(["uid", "ym"])["prov"].agg(frozenset).to_dict()

    def present(u, m, p):
        return (u, m) in rmon or len(aimon.get((u, m), frozenset()) - {p}) > 0

    ym0 = ymi(s["start"]).to_numpy()
    uids, provs = s["uid"].to_numpy(), s["prov"].to_numpy()
    s["in_R"] = [present(u, m, p) for u, m, p in zip(uids, ym0, provs)]
    endym = np.where(s["event"], ymi(s["known"]), 10**6)
    cens = np.zeros(len(s), dtype=int)
    for i in np.where(s["in_R"].to_numpy())[0]:
        u, p = uids[i], provs[i]
        m = ym0[i] + 1
        while m <= min(endym[i], H):
            if not present(u, m, p) and not (m + 1 <= H and present(u, m - 1, p) and present(u, m + 1, p)):
                cens[i] = m
                break
            m += 1
    s["cens_ym"] = cens
    s["known_ym"] = np.where(s["event"], ymi(s["known"]), 0)
    s["start_ym"] = ym0
    s["region"] = region
    return s, held, H, T


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 500)
    fw = final_windows()
    src_map = fw.set_index(["region", "prov", "channel"])["rate_source"]
    allbt, shares, srcs, helds = [], [], [], []
    for region in ["us", "eu"]:
        s, held, H, T = build(region)
        helds.append(held.assign(region=region))
        fb = Rate(rates_R(s, H, FIRST), "churn")
        rt_full, rt_R = rates_ch(s, H, FIRST, use_R=False), rates_ch(s, H, FIRST, use_R=True)
        src = {}
        for p, ch in s[["prov", "channel"]].drop_duplicates().itertuples(index=False):
            src[(p, ch)] = "full" if src_map.get((region, p, ch), "reliable_subset") == "full_panel" else "R"
            srcs.append(dict(region=region, prov=p, channel=ch, source=src[(p, ch)], subs=int((s["prov"].eq(p) & s["channel"].eq(ch)).sum()),
                             subs_in_R=int((s["prov"].eq(p) & s["channel"].eq(ch) & s["in_R"]).sum())))
        fk = {k for k, v in src.items() if v == "full"}
        sel = lambda rt, want: rt[[((p, ch) in fk) == want for p, ch in zip(rt["prov"], rt["channel"])]]
        rate = ChRate(pd.concat([sel(rt_full, True), sel(rt_R, False)]), fb)
        s["src"] = [src[(p, ch)] for p, ch in zip(s["prov"], s["channel"])]
        for start in (FIRST, 2025 * 12 + 7):
            for comp, ss in [("full_nonapple", s[s["channel"] != "apple"]),
                             ("full_nonapple_Rcells", s[(s["channel"] != "apple") & (s["src"] == "R")]),
                             ("full_all", s)]:
                m = run_model(ss, start, H, rate)
                o = obs_series(ss, start, H)
                bt = m.merge(o, on=["prov", "ym"], how="outer").assign(region=region, start=ymlab(start), comparison=comp)
                bt["month_n"] = bt["ym"] - start + 1
                allbt.append(bt)
        m = run_model(s, FIRST, H, rate)
        m = m[m["ym"] == H].set_index("prov")["model"]
        sh = m.to_frame().join(observed(s, H).groupby("prov").size().rename("obs_full"))
        for col in ["model", "obs_full"]:
            sh[f"share_{col}"] = sh[col] / sh[col].sum()
        shares.append(sh.reset_index().assign(region=region, month=ymlab(H)))
        print(region, "last non-held month", ymlab(H), "R share of subs", round(s["in_R"].mean(), 3), flush=True)
    pd.DataFrame(srcs).to_csv(OUTD / "t7c_sources.csv", index=False)
    pd.concat(helds).round(4).to_csv(OUTD / "t7c_held.csv", index=False)
    bt = pd.concat(allbt)
    bt["month"] = bt["ym"].map(ymlab)
    bt["err"] = bt["model"] / bt["obs"] - 1
    bt.round(3).to_csv(OUTD / "t7c_backtest.csv", index=False)
    d = bt[bt["month_n"].isin([6, 12])].pivot_table(index=["region", "start", "comparison", "prov"], columns="month_n", values="err")
    last = bt.sort_values("ym").groupby(["region", "start", "comparison", "prov"]).last()[["month", "obs", "model", "err"]]
    drift = d.join(last).reset_index()
    drift.columns = [f"err_m{c}" if isinstance(c, (int, np.integer)) else c for c in drift.columns]
    drift.round(3).to_csv(OUTD / "t7c_drift.csv", index=False)
    sh = pd.concat(shares)
    sh.round(4).to_csv(OUTD / "t7c_shares.csv", index=False)
    print(fw.round(3).to_string(index=False))
    print(pd.concat(helds).tail(20).round(3).to_string(index=False))
    print(pd.DataFrame(srcs).to_string(index=False))
    print(drift.round(3).to_string(index=False))
    print(sh.round(3).to_string(index=False))
