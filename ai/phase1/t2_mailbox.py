"""Task 2: is a missed renewal email a mailbox trait? + reliable-subset candidates.

Reference recurring senders (pulled by pull.py, monthly paid only): iCloud+ (Apple), YouTube Premium (Apple / Google Play /
direct / PayPal), Google One storage (Google Play), Spotify (direct).

Tests
 a) month level: for each AI renewal month (captured, or a high-purity missed month = skipped month inside a gap that
    lands within +-1 day of the billing anchor), is the user's reference sender present that month (where the reference
    subscription is running either side), and did the mailbox send any receipt at all?
 b) user level: does a missed reference renewal predict a missed AI renewal (and AI provider vs other AI provider)?
Subset candidates are scored by the AI renewal capture (chance-corrected, as in t1) within vs outside the subset.

Outputs: out/t2_month_level.csv, out/t2_user_level.csv, out/t2_subset_eval.csv, data/reliable_{region}.parquet
"""
import numpy as np
import pandas as pd
from common import *
from t1_gaps import continuing_dist

REF_EXCLUDE = set()  # reference senders to drop (t7c sets {"gone_storage"})
ANNUAL = r"annual|yearly|year\)|jährlich|annuel|anual|annuale|\(yearly\)"


def ref_charges(region):
    r = pd.read_parquet(D / f"{region}_ref_raw.parquet")
    r["uid"] = r["uid"].astype(str)
    r["dt"] = pd.to_datetime(r["dt"]).astype("datetime64[ns]")
    t = r["descr"].fillna("").str.lower()
    m = r["merchant_name"].fillna("").str.lower()
    if region == "us":
        ref = np.select([m.eq("itunes") & t.str.contains("icloud"), m.eq("itunes") & t.str.contains("youtube"),
                         m.eq("google play") & t.str.contains("google one"), m.eq("google play") & t.str.contains("youtube"),
                         m.eq("spotify") & ~t.str.contains("trial"), m.eq("youtube premium")],
                        ["icloud", "youtube", "gone_storage", "youtube", "spotify", "youtube"], "")
        ch = np.select([m.eq("itunes"), m.eq("google play")], ["apple", "google_play"], "direct")
        monthly = (m.eq("itunes") & t.str.contains(r"\(monthly\)")) | (m.eq("google play") & (r["price"] < 12)) | \
                  (m.isin(["spotify", "youtube premium"]) & (r["price"] < 40))
    else:
        ref = np.select([m.eq("apple") & t.str.contains("icloud"), t.str.contains("youtube premium"),
                         m.eq("google play") & t.str.contains("google one"), m.eq("spotify")],
                        ["icloud", "youtube", "gone_storage", "spotify"], "")
        ch = np.select([m.eq("apple"), m.eq("google play"), m.eq("paypal")], ["apple", "google_play", "paypal"], "direct")
        monthly = ~t.str.contains(ANNUAL) & (r["price"] < 35)
    r = r.assign(prov=ref, channel=ch)[(ref != "") & monthly & (r["price"] > 0)]
    r = r.assign(cadence="M", renews=True, plan=r["prov"], country="", region=region)
    r = r[~r["prov"].isin(REF_EXCLUDE)]
    return r.sort_values(["uid", "prov", "channel", "dt"]).drop_duplicates(["uid", "prov", "channel", "dt"])


def month_rows(g):
    """AI/ref continuing gaps -> one row per expected renewal month: missed (skipped month) or captured (d1 month)."""
    g = g[g["kind"] != "break"]
    ym0 = g["d0"].dt.year * 12 + g["d0"].dt.month
    rep = g.loc[g.index.repeat(g["k"])].copy()
    j = rep.groupby(level=0).cumcount() + 1
    rep["ym"] = ym0.loc[rep.index].to_numpy() + j.to_numpy()
    rep["missed"] = j.to_numpy() < rep["k"].to_numpy()
    rep["pure"] = ~rep["missed"] | (rep["off"].abs() <= 1)  # high-purity missed months only
    return rep


def capture_adj(g):
    if len(g) < 30:
        return np.nan
    cd = continuing_dist(g)
    kk = (cd["gap"] / CYC["M"]).round().clip(lower=1)
    return cd["w"].sum() / (cd["w"] * kk).sum()


def run(region):
    ai = pd.read_parquet(D / f"gaps_{region}.parquet")
    ai = ai[ai["cad"] == "M"].reset_index(drop=True)
    rc = ref_charges(region)
    rg = gaps(rc).reset_index(drop=True)
    rg = rg[rg["k"] <= 13]
    act = pd.read_parquet(D / f"{region}_activity.parquet")
    act["uid"] = act["uid"].astype(str)
    act["ym"] = pd.to_datetime(act["month"]).dt.year * 12 + pd.to_datetime(act["month"]).dt.month
    actset = pd.Series(1, index=pd.MultiIndex.from_frame(act[["uid", "ym"]])).groupby(level=[0, 1]).first()

    # --- a) month level
    am = month_rows(ai[ai["k"] <= 13])
    am = am[am["pure"]]
    rm = month_rows(rg)  # reference months inside running ref episodes (renew or missed gaps)
    rpres = rm.groupby(["uid", "ym"])["missed"].min().rename("ref_missed")  # any ref captured that month -> not missed
    am = am.join(rpres, on=["uid", "ym"])
    am["mbx_any"] = actset.reindex(pd.MultiIndex.from_frame(am[["uid", "ym"]])).notna().to_numpy()
    # other AI provider (different provider) running that month
    oth = am[["uid", "prov", "ym", "missed"]].rename(columns={"prov": "p2", "missed": "oth_missed"})
    ao = am[["uid", "prov", "channel", "ym", "missed"]].merge(oth, on=["uid", "ym"])
    ao = ao[ao["prov"] != ao["p2"]].groupby(["uid", "prov", "channel", "ym", "missed"])["oth_missed"].min().reset_index()
    ml = []
    for (p, ch), x in am.groupby(["prov", "channel"]):
        if len(x) < 500:
            continue
        for mis, y in x.groupby("missed"):
            yr = y[y["ref_missed"].notna()]
            o = ao[(ao["prov"] == p) & (ao["channel"] == ch) & (ao["missed"] == mis)]
            ml.append(dict(region=region, prov=p, channel=ch, ai_month="missed" if mis else "captured", n=len(y),
                           mbx_no_receipt=1 - y["mbx_any"].mean(), n_with_ref=len(yr),
                           ref_missed=yr["ref_missed"].mean() if len(yr) else np.nan,
                           n_with_other_ai=len(o), other_ai_missed=o["oth_missed"].mean() if len(o) else np.nan))
    ml = pd.DataFrame(ml)

    # --- b) user level: per uid, does any ref subscription show a missed renewal; per uid x prov, any AI miss
    def per_user(g, keys):
        g = g[g["kind"] != "break"]
        return g.groupby(keys).agg(n_gaps=("k", "size"), n_exp=("k", "sum"),
                                   n_missed=("kind", lambda s: (s == "missed").sum()))
    ru = per_user(rg, ["uid"])
    ru = ru[ru["n_gaps"] >= 2]
    ru["ref_capture"] = ru["n_gaps"] / ru["n_exp"]
    au = per_user(ai, ["uid", "prov", "channel"]).reset_index()
    au = au[au["n_gaps"] >= 2]
    au["ai_miss"] = au["n_missed"] > 0
    ul = au.merge(ru[["ref_capture", "n_missed"]].rename(columns={"n_missed": "ref_n_missed"}), on="uid")
    ul["ref_miss"] = ul["ref_n_missed"] > 0
    ulr = ul.groupby(["prov", "channel", "ref_miss"]).agg(users=("uid", "size"), p_ai_miss=("ai_miss", "mean")).reset_index()
    ulr["region"] = region
    # AI vs other AI provider
    au2 = au.merge(au[["uid", "prov", "ai_miss"]].rename(columns={"prov": "p2", "ai_miss": "oth_miss"}), on="uid")
    au2 = au2[au2["prov"] != au2["p2"]].groupby(["uid", "prov", "channel", "ai_miss"])["oth_miss"].max().reset_index()
    u2 = au2.groupby(["prov", "channel", "oth_miss"]).agg(users=("uid", "size"), p_ai_miss=("ai_miss", "mean")).reset_index()
    u2["region"] = region
    u2 = u2.rename(columns={"oth_miss": "ref_miss"}).assign(ref="other_ai")
    ulr = pd.concat([ulr.assign(ref="ref_sender"), u2])

    # --- subset candidates (user level; none uses the AI subscription's own ending)
    au_all = per_user(ai, ["uid", "prov"]).reset_index()
    oth_ok = au_all.merge(au_all[["uid", "prov", "n_gaps", "n_missed"]].rename(
        columns={"prov": "p2", "n_gaps": "g2", "n_missed": "m2"}), on="uid")
    oth_ok = oth_ok[(oth_ok["prov"] != oth_ok["p2"]) & (oth_ok["g2"] >= 2)]
    oth_ok = oth_ok.groupby(["uid", "prov"]).agg(oth_gaps=("g2", "sum"), oth_missed=("m2", "sum")).reset_index()
    users = ai[["uid", "prov", "channel"]].drop_duplicates()
    # include users with a single AI charge (no gap) too
    ch1 = pd.read_parquet(D / f"episodes_{region}.parquet")[["uid", "prov", "channel"]].drop_duplicates()
    users = pd.concat([users, ch1]).drop_duplicates()
    users = users.merge(ru[["n_gaps", "n_missed", "ref_capture"]].rename(columns={"n_gaps": "ref_gaps", "n_missed": "ref_missed"}),
                        left_on="uid", right_index=True, how="left")
    users = users.merge(oth_ok, on=["uid", "prov"], how="left")
    act_last = act.groupby("uid")["ym"].max()
    users["last_active_ym"] = users["uid"].map(act_last)
    users["has_ref"] = users["ref_gaps"].fillna(0) >= 2
    users["has_oth"] = users["oth_gaps"].fillna(0) >= 2
    users["ref_clean"] = users["has_ref"] & (users["ref_missed"] == 0)
    users["ref_90"] = users["has_ref"] & (users["ref_capture"] >= 0.9)
    users["oth_clean"] = users["has_oth"] & (users["oth_missed"] == 0)
    users["S_ref_or_oth_clean"] = users["ref_clean"] | users["oth_clean"]
    users["S_ref3_clean"] = (users["ref_gaps"].fillna(0) >= 3) & (users["ref_missed"] == 0)
    users["S_any_other"] = users["has_ref"] | users["has_oth"]
    users.to_parquet(D / f"reliable_{region}.parquet", index=False)

    cands = ["has_ref", "ref_clean", "ref_90", "S_ref3_clean", "oth_clean", "S_ref_or_oth_clean", "S_any_other"]
    ev = []
    aim = ai.merge(users[["uid", "prov", "channel", *cands]], on=["uid", "prov", "channel"], how="left")
    for (p, ch), x in aim.groupby(["prov", "channel"]):
        if len(x) < 300:
            continue
        nu = users[(users["prov"] == p) & (users["channel"] == ch)]
        row = dict(region=region, prov=p, channel=ch, users=len(nu), capture_all=capture_adj(x))
        for cnd in cands:
            ins = x[x[cnd].fillna(False).astype(bool)]
            row[f"{cnd}_share"] = nu[cnd].mean()
            row[f"{cnd}_capture"] = capture_adj(ins)
            row[f"{cnd}_capture_out"] = capture_adj(x[~x[cnd].fillna(False).astype(bool)])
        ev.append(row)
    return ml, ulr, pd.DataFrame(ev)


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 500)
    pd.set_option("display.max_columns", 50)
    out = [run(r) for r in ["us", "eu"]]
    ml, ul, ev = (pd.concat(z) for z in zip(*out))
    ml.round(4).to_csv(OUTD / "t2_month_level.csv", index=False)
    ul.round(4).to_csv(OUTD / "t2_user_level.csv", index=False)
    ev.round(4).to_csv(OUTD / "t2_subset_eval.csv", index=False)
    print(ml.round(3).to_string(index=False))
    print(ul.round(3).to_string(index=False))
    print(ev.round(3).T.to_string())
