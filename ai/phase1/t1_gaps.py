"""Task 1: renewal consistency by provider x region x channel x cadence.

Gap = days between consecutive paid receipts of one uid x provider x channel. Each gap is
  renew  : <= 1.5 cycles
  missed : longer and within +-TOL days of the billing anchor (d0 + k cycles) -> continued, k-1 renewal emails missed
  break  : longer and off-anchor -> lapse + resubscribe (or billing-retry re-anchor)
Off-anchor gaps land uniformly over the month, so some breaks fall on the anchor by chance. The estimated true
missed-email count at k cycles = aligned_k - background_k, background = off-anchor density (7<=|off|<=14) x window.
Episodes split at breaks; 'subscription' = episode with >= 3 charges (as specified).

Outputs (out/): t1_gap_dist.csv, t1_window.csv (p99 continuing gap per provider x region x channel), t1_missed_k.csv,
t1_by_quarter.csv, t1_by_tenure.csv, t1_by_mbx_age.csv, and data/gaps_{region}.parquet for later tasks.
"""
import numpy as np
import pandas as pd
from common import *

OUTD.mkdir(exist_ok=True)


def wq(values, weights, p):
    o = np.argsort(values)
    v, w = np.asarray(values)[o], np.asarray(weights, float)[o]
    cw = np.cumsum(w) / w.sum()
    return v[np.searchsorted(cw, p)]


def continuing_dist(g: pd.DataFrame) -> pd.DataFrame:
    """Weighted distribution of continuing gaps: every renew gap (weight 1) plus, per k>=2, aligned gaps weighted by
    the excess share over the off-anchor background."""
    cad = g["cad"].iloc[0]
    tol = TOL[cad]
    parts = [g.loc[g["kind"] == "renew", ["gap"]].assign(w=1.0)]
    lg = g[g["kind"] != "renew"]
    for k, x in lg.groupby("k"):
        al = x[x["aligned"]]
        bg = ((x["off"].abs() >= tol + 3) & (x["off"].abs() <= tol + 10)).sum() / 16 * (2 * tol + 1)
        if len(al):
            parts.append(al[["gap"]].assign(w=max(0.0, 1 - bg / len(al))))
    return pd.concat(parts)


def summarise(g: pd.DataFrame, ep: pd.DataFrame) -> dict:
    cad = g["cad"].iloc[0]
    d = {"n_eps3": int((ep["n"] >= 3).sum()), "n_gaps": len(g)}
    e3 = set(ep.index[ep["n"] >= 3])
    gi = g[g["ep"].isin(e3)]
    d |= {f"gap_{k}": v for k, v in q(gi["gap"]).items()}  # within >=3-charge subscriptions (breaks excluded)
    cd = continuing_dist(g)
    for p in (0.5, 0.9, 0.95, 0.99, 0.995):
        d[f"cont_p{p * 100:g}"] = wq(cd["gap"], cd["w"], p) if len(cd) else np.nan
    est_missed = cd.loc[cd["gap"] > 1.5 * CYC[cad], "w"]
    d["share_renew"] = (g["kind"] == "renew").mean()
    d["share_missed_aligned"] = (g["kind"] == "missed").mean()
    d["share_break"] = (g["kind"] == "break").mean()
    d["est_missed_gaps"] = est_missed.sum()
    # capture: observed renewals / expected renewals within >=3-charge subscriptions (before the final receipt)
    d["capture"] = (len(gi) / gi["k"].sum()) if len(gi) else np.nan
    # bias-corrected capture: chance-aligned breaks excluded from the expected count
    cont_k = (cd["gap"] / CYC[cad]).round().clip(lower=1)
    d["capture_adj"] = cd["w"].sum() / (cd["w"] * cont_k).sum() if len(cd) else np.nan
    e = ep[ep["n"] >= 3]
    d["share_subs_full_capture"] = (e["n_missed"] == 0).mean() if len(e) else np.nan
    d["share_months_with_receipt"] = (e["n"] / e["exp"]).mean() if len(e) else np.nan
    return d


def run(region):
    x = load(region)
    c = charges(x)
    c = c[c["renews"]]
    g = gaps(c)
    c = episodes(c, g)
    epi = c.set_index(["uid", "prov", "channel", "dt"])["ep"]
    g["ep"] = epi.reindex(pd.MultiIndex.from_frame(g[["uid", "prov", "channel", "d0"]])).to_numpy()
    g.loc[g["kind"] == "break", "ep"] = np.nan  # a break closes the episode
    # episode table
    gg = g[g["ep"].notna()]
    ep = c.groupby("ep").agg(uid=("uid", "first"), prov=("prov", "first"), channel=("channel", "first"),
                             country=("country", "first"), cad=("cadence", "first"), plan=("plan", "first"),
                             start=("dt", "min"), last=("dt", "max"), n=("dt", "size"))
    ep["exp"] = 1 + gg.groupby("ep")["k"].sum().reindex(ep.index).fillna(0)
    ep["n_missed"] = (gg["kind"] == "missed").groupby(gg["ep"]).sum().reindex(ep.index).fillna(0)
    ep.to_parquet(D / f"episodes_{region}.parquet")
    g.to_parquet(D / f"gaps_{region}.parquet", index=False)

    rows, kr = [], []
    levels = [("region", "all")] + ([("country", None)] if region == "eu" else [])
    for lvl, _ in levels:
        gcol = "region" if lvl == "region" else "country"
        g["_r"] = g[gcol]
        ep["_r"] = region if lvl == "region" else ep["country"]
        for (r, p, ch, cad), x in g.groupby(["_r", "prov", "channel", "cad"]):
            if len(x) < 50:
                continue
            e = ep[(ep["_r"] == r) & (ep["prov"] == p) & (ep["channel"] == ch) & (ep["cad"] == cad)]
            rows.append({"region": r, "prov": p, "channel": ch, "cad": cad} | summarise(x, e))
            if lvl == "region" and cad == "M":
                for k, y in x[x["k"].between(2, 13)].groupby("k"):
                    tol = TOL[cad]
                    bg = ((y["off"].abs() >= tol + 3) & (y["off"].abs() <= tol + 10)).sum() / 16 * (2 * tol + 1)
                    kr.append(dict(region=r, prov=p, channel=ch, k=k, n=len(y), aligned=int(y["aligned"].sum()),
                                   chance=round(bg, 1), est_missed=max(0, y["aligned"].sum() - bg)))
    res = pd.DataFrame(rows)

    # stability (monthly): raw capture = observed / expected renewals over continuing gaps; adj = chance-aligned
    # resubscribes removed using each cell's own off-anchor background
    m = g[g["cad"] == "M"].copy()
    m["quarter"] = m["d1"].dt.to_period("Q").astype(str)
    c["pos"] = c.groupby("ep").cumcount() + 1
    m["pos"] = c.set_index(["uid", "prov", "channel", "dt"])["pos"].reindex(
        pd.MultiIndex.from_frame(m[["uid", "prov", "channel", "d0"]])).to_numpy()
    m["tenure"] = pd.cut(m["pos"], [0, 1, 3, 6, 12, 24, 999], labels=["1st renewal", "2-3", "4-6", "7-12", "13-24", "25+"])
    born = us_mailboxes() if region == "us" else eu_users()
    age = (m["d1"] - m["uid"].map(born)).dt.days / 30.44
    m["mbx_age"] = pd.cut(age, [-999, 0, 6, 12, 24, 999], labels=["pre-join (backfill)", "0-6m", "6-12m", "12-24m", "24m+"])
    stab = {}
    for dim in ["quarter", "tenure", "mbx_age"]:
        out = []
        for key, y in m.groupby(["region", "prov", "channel", dim], observed=True):
            if len(y) < 100:
                continue
            cont = y[y["kind"] != "break"]
            cd = continuing_dist(y)
            kk = (cd["gap"] / CYC["M"]).round().clip(lower=1)
            out.append(dict(zip(["region", "prov", "channel", dim], key)) | dict(
                gaps=len(y), capture_raw=len(cont) / cont["k"].sum(), capture_adj=cd["w"].sum() / (cd["w"] * kk).sum(),
                share_break=(y["kind"] == "break").mean()))
        stab[dim] = pd.DataFrame(out)
    return res, pd.DataFrame(kr), stab


if __name__ == "__main__":
    allr, allk, st = [], [], {}
    for r in ["us", "eu"]:
        res, kr, stab = run(r)
        allr.append(res)
        allk.append(kr)
        for k, v in stab.items():
            st.setdefault(k, []).append(v)
        print(r, "done", flush=True)
    res = pd.concat(allr)
    res.round(4).to_csv(OUTD / "t1_gap_dist.csv", index=False)
    pd.concat(allk).round(1).to_csv(OUTD / "t1_missed_k.csv", index=False)
    for k, v in st.items():
        pd.concat(v).round(4).to_csv(OUTD / f"t1_by_{k}.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 500)
    cols = ["region", "prov", "channel", "cad", "n_eps3", "n_gaps", "gap_p50", "gap_p90", "gap_p95", "gap_p99", "gap_p99.5",
            "gap_max", "cont_p95", "cont_p99", "cont_p99.5", "share_break", "share_missed_aligned", "capture", "capture_adj",
            "share_subs_full_capture", "share_months_with_receipt"]
    print(res[cols].round(3).to_string(index=False))
