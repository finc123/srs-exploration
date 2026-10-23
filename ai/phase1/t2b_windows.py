"""Task 2b: renewal capture and lapse windows (p99 continuing gap) under each reliable-subset candidate.

Candidates
  all            : every AI subscriber
  has_ref        : mailbox has a monthly reference subscription (iCloud+/Google One/YouTube/Spotify, >=3 receipts)
  ref_clean      : ... and it never shows a missed renewal (user level, whole history)
  S_ref_or_oth   : ref_clean, or another AI provider with >=3 receipts and no missed renewal
  live_any       : ref_live, where a different AI provider's captured renewal also counts as the live reference.
  ref_live       : TIME-LOCAL. The AI gap is scored only if a reference subscription was captured in every calendar month the
                   gap spans (i.e. the mailbox demonstrably still delivers recurring receipts at that time). For lapses the
                   same check applies to the months after the last AI payment, so churners are not excluded by construction.
Outputs: out/t2b_windows.csv (capture, continuing-gap p95/p99/p99.5, false-lapse rate at 45/62/92 days, coverage).
"""
import numpy as np
import pandas as pd
from common import *
from t1_gaps import continuing_dist, wq
from t2_mailbox import ref_charges, month_rows


def stats(g):
    if len(g) < 200:
        return {}
    cd = continuing_dist(g)
    kk = (cd["gap"] / CYC["M"]).round().clip(lower=1)
    d = dict(n_gaps=len(g), capture=cd["w"].sum() / (cd["w"] * kk).sum())
    for p in (0.95, 0.99, 0.995):
        d[f"p{p * 100:g}"] = wq(cd["gap"], cd["w"], p)
    for w in (45, 62, 92):
        d[f"false_lapse_{w}"] = cd.loc[cd["gap"] > w, "w"].sum() / cd["w"].sum()
    return d


def run(region):
    ai = pd.read_parquet(D / f"gaps_{region}.parquet")
    ai = ai[(ai["cad"] == "M") & (ai["k"] <= 24)].reset_index(drop=True)
    rel = pd.read_parquet(D / f"reliable_{region}.parquet")
    ai = ai.merge(rel[["uid", "prov", "channel", "has_ref", "ref_clean", "S_ref_or_oth_clean"]], on=["uid", "prov", "channel"], how="left")
    # time-local reference coverage
    rg = gaps(ref_charges(region))
    rg = rg[rg["k"] <= 13]
    rm = month_rows(rg)
    rcap = rm.loc[~rm["missed"], ["uid", "ym"]].drop_duplicates().assign(rc=1).set_index(["uid", "ym"])["rc"]
    ai["gid"] = np.arange(len(ai))
    ym0 = ai["d0"].dt.year * 12 + ai["d0"].dt.month
    rep = ai.loc[ai.index.repeat(ai["k"]), ["gid", "uid"]]
    rep["ym"] = ym0.loc[rep.index].to_numpy() + rep.groupby(level=0).cumcount().to_numpy() + 1
    rep["rc"] = rcap.reindex(pd.MultiIndex.from_frame(rep[["uid", "ym"]])).notna().to_numpy()
    ai["ref_live"] = rep.groupby("gid")["rc"].all().reindex(ai["gid"]).to_numpy()
    # live_any: reference sender OR a different AI provider captured in each month the gap spans
    am = month_rows(ai.drop(columns=["gid"]))
    acap = am.loc[~am["missed"], ["uid", "ym", "prov"]].drop_duplicates()
    rep["prov"] = ai["prov"].to_numpy()[rep["gid"].to_numpy()]
    o = rep[["gid", "uid", "ym", "prov"]].merge(acap.rename(columns={"prov": "p2"}), on=["uid", "ym"])
    o = o[o["prov"] != o["p2"]][["gid", "ym"]].drop_duplicates().assign(oc=True)
    rep = rep.merge(o, on=["gid", "ym"], how="left")
    rep["any"] = rep["rc"] | rep["oc"].fillna(False).astype(bool)
    ai["live_any"] = rep.groupby("gid")["any"].all().reindex(ai["gid"]).to_numpy()
    rows = []
    for (p, ch), x in ai.groupby(["prov", "channel"]):
        for cnd in ["all", "has_ref", "ref_clean", "S_ref_or_oth_clean", "ref_live", "live_any"]:
            y = x if cnd == "all" else x[x[cnd].fillna(False).astype(bool)]
            s = stats(y)
            if s:
                rows.append(dict(region=region, prov=p, channel=ch, subset=cnd, share_of_gaps=len(y) / len(x)) | s)
        # pooled across providers for the channel (stable windows for small cells)
    for p, x in ai.groupby("prov"):  # provider pooled across channels (fallback for small cells)
        for cnd in ["all", "live_any"]:
            y = x if cnd == "all" else x[x[cnd].fillna(False).astype(bool)]
            s = stats(y)
            if s:
                rows.append(dict(region=region, prov=p, channel="ALL", subset=cnd, share_of_gaps=len(y) / len(x)) | s)
    for ch, x in ai.groupby("channel"):
        for cnd in ["all", "ref_clean", "ref_live", "live_any"]:
            y = x if cnd == "all" else x[x[cnd].fillna(False).astype(bool)]
            s = stats(y)
            if s:
                rows.append(dict(region=region, prov="ALL", channel=ch, subset=cnd, share_of_gaps=len(y) / len(x)) | s)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 500)
    r = pd.concat([run("us"), run("eu")])
    r.round(4).to_csv(OUTD / "t2b_windows.csv", index=False)
    print(r.round(3).to_string(index=False))
