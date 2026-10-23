"""Task 3: cancellation-email reliability per provider x channel, and what follows a cancellation.

Confirmed lapse: last paid receipt of an episode (uid x provider x channel, renewing channels) with no paid receipt from the
same provider on ANY channel within W days (p99 window from t2b, reliable subset), W already elapsed by the data end, and
the mailbox still active at last+W (US: any receipt in that month or later; EU: user still sending receipts).
'reliable' flag: a different recurring sender (reference sender or other AI provider) captured in every month from the
last payment's month+1 to the month of last+W (the live_any rule).

Cancel -> next payment: for each cancellation email, the next paid receipt of the same provider; whether it lands within
W of the cancel; same channel / same plan / on the old billing anchor (= looks like a continuing renewal); and whether a
sign-up marker (gross-add email) sits within +-7 days of that payment.

Sign-up markers (gross-add emails) by channel:
  US apple       unpriced iTunes 'App Plan $X /month' subscription confirmation
  US google_play unpriced Google Play '(Google One)' / plan confirmation rows (not 'trial will end')
  US direct      ChatGPT direct paid receipt (sign-up only); Anthropic 'Pro/Max subscription' unpriced welcome;
                 Google One 'Welcome (back) to Google One/AI Pro'; Perplexity 'Welcome to Perplexity Pro'
  EU             unpriced non-cancel Fox rows on Apple/Google Play/direct/Stripe/PayPal (not trials); ChatGPT direct paid
Outputs: out/t3_lapse_cancel.csv, out/t3_cancel_then_pay.csv, out/t3_signup_marker.csv
"""
import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.compute as pc
from common import *
from t2_mailbox import ref_charges, month_rows

PRX = [("chatgpt", r"chat ?gpt|openai"), ("claude", r"claude|anthropic"),
       ("grok", r"super ?grok|(?<![a-z])grok(?![a-z])|x\.ai|(?<![a-z])xai(?![a-z])|x premium plus|premium\+|premium plus \(x\)"),
       ("perplexity", r"perplexity"), ("muse", r"muse from meta|^\s*(?:power|maximum) plan"),
       ("gemini", r"google ai (?:pro|plus|ultra)|ai premium|gemini|google one ai|ai pro")]
NOTP = r"sora|roblox|accuweather|grok ?bot|ngrok|itvx|hellofresh|codeway"


def prov_of(t):
    out = pd.Series(None, index=t.index, dtype=object)
    for p, rx in PRX:
        out[out.isna() & t.str.contains(rx)] = p
    out[t.str.contains(NOTP)] = None
    return out


def signup_markers(region, x):
    f = (pc.field("item_price").is_null()) | (pc.field("item_price") <= 0)
    if region == "us":
        r = ds.dataset(C / "us_ai_items.parquet").to_table(columns=["uid", "dt", "merchant_name", "descr"], filter=f).to_pandas()
        m, t = r["merchant_name"].fillna("").str.lower(), r["descr"].fillna("").str.lower()
        ch = np.select([m.eq("itunes"), m.eq("google play"), m.isin(["anthropic", "google one", "perplexity ai", "openai"])],
                       ["apple", "google_play", "direct"], "")
        ok = ((m.eq("itunes") & t.str.contains(r"/ ?(?:month|year|week)") & ~t.str.contains("trial"))
              | (m.eq("google play") & ~t.str.contains(r"trial|will end|automatically charged"))
              | (m.eq("anthropic") & t.str.match(r"^(?:pro|max) subscription"))
              | (m.eq("google one") & t.str.contains(r"welcome") & t.str.contains(r"ai (?:pro|plus|premium|ultra)|gemini"))
              | (m.eq("perplexity ai") & t.str.match(r"^welcome to perplexity (?:pro|max)\b")))
        p = prov_of(np.where(m.eq("anthropic"), "anthropic ", "") + t)
    else:
        r = ds.dataset(C / "eu_ai_items.parquet").to_table(
            columns=["uid", "dt", "merchant_name", "product_name", "descr", "email_type", "order_attributes"], filter=f).to_pandas()
        r = r[~r["order_attributes"].fillna("").str.contains(r"order_is_spam\W+1")]
        m = r["merchant_name"].fillna("").str.lower()
        t = (r["product_name"].fillna("") + " " + r["descr"].fillna("")).str.lower()
        ch = np.select([m.eq("apple"), m.eq("google play"), m.eq("paypal"), m.eq("stripe"),
                        m.isin(["chatgpt", "anthropic", "perplexity", "x", "grok"])],
                       ["apple", "google_play", "paypal", "stripe", "direct"], "")
        ok = ~r["email_type"].fillna("").str.lower().eq("cancel") & ~t.str.contains(r"trial|probeabo|essai|prueba|prova")
        p = prov_of(m + " " + t)
    r = r.assign(prov=p, channel=ch)[ok & (ch != "") & p.notna()]
    r["uid"] = r["uid"].astype(str)
    r["dt"] = pd.to_datetime(r["dt"]).astype("datetime64[ns]")
    cg = x[(x["kind"] == "charge") & (x["prov"] == "chatgpt") & (x["channel"] == "direct")]
    return pd.concat([r[["uid", "dt", "prov", "channel"]], cg[["uid", "dt", "prov", "channel"]]]).drop_duplicates()


def near(a, b, lo, hi, on=("uid", "prov")):
    """For rows of a (index preserved), True if b has a row with same keys and b.dt - a.dt in [lo, hi]."""
    on = list(on)
    j = a[[*on, "dt"]].reset_index().merge(b[[*on, "dt"]].rename(columns={"dt": "d2"}), on=on)
    dd = (j["d2"] - j["dt"]).dt.days
    hit = j.loc[(dd >= lo) & (dd <= hi), "index"].unique()
    return a.index.isin(hit)


def run(region):
    W = windows()
    x = load(region)
    data_end = x["dt"].max()
    c = charges(x)
    allpay = c[["uid", "prov", "channel", "dt", "plan"]]
    cn = x[x["kind"] == "cancel"].drop_duplicates(["uid", "prov", "channel", "dt"]).reset_index(drop=True)
    su = signup_markers(region, x)
    ep = pd.read_parquet(D / f"episodes_{region}.parquet").reset_index()
    ep = ep[ep["cad"] == "M"].copy()
    ep["W"] = [W(region, p, ch) for p, ch in zip(ep["prov"], ep["channel"])]
    ep["pt"] = ep["last"] + pd.Timedelta(days=31)
    ep["known"] = ep["last"] + pd.to_timedelta(ep["W"], unit="D")
    ep = ep[ep["known"] <= data_end]
    # no same-provider payment (any channel) within W after last
    tmp = ep[["uid", "prov", "last"]].rename(columns={"last": "dt"})
    ep["paid_after"] = near(tmp, allpay, 1, 10_000)
    nxt = tmp.reset_index().merge(allpay[["uid", "prov", "dt"]].rename(columns={"dt": "d2"}), on=["uid", "prov"])
    nxt = nxt[nxt["d2"] > nxt["dt"]].groupby("index")["d2"].min()
    ep["next_pay"] = nxt.reindex(ep.index)
    ep["lapse"] = ep["next_pay"].isna() | ((ep["next_pay"] - ep["last"]).dt.days > ep["W"])
    if region == "us":
        a = pd.read_parquet(D / "us_activity.parquet")
        a["uid"] = a["uid"].astype(str)
        lastym = (pd.to_datetime(a["month"]).dt.year * 12 + pd.to_datetime(a["month"]).dt.month).groupby(a["uid"]).max()
        ep["active"] = ep["uid"].map(lastym) >= ep["known"].dt.year * 12 + ep["known"].dt.month
    else:
        ep["active"] = ep["uid"].map(eu_last_active()) >= ep["known"]
    # live_any after last payment
    rg = gaps(ref_charges(region))
    rm = month_rows(rg[rg["k"] <= 13])
    ai = pd.read_parquet(D / f"gaps_{region}.parquet")
    am = month_rows(ai[(ai["cad"] == "M") & (ai["k"] <= 13)])
    live = pd.concat([rm.loc[~rm["missed"], ["uid", "ym"]].assign(prov="_ref"),
                      am.loc[~am["missed"], ["uid", "ym", "prov"]]]).drop_duplicates()
    L = ep[ep["lapse"] & ep["active"]].copy()
    ym0 = L["last"].dt.year * 12 + L["last"].dt.month
    nmon = (L["known"].dt.year * 12 + L["known"].dt.month - ym0).clip(lower=1)
    rep = L.loc[L.index.repeat(nmon), ["uid", "prov"]]
    rep["ym"] = ym0.loc[rep.index].to_numpy() + rep.groupby(level=0).cumcount().to_numpy() + 1
    rep["i"] = rep.index
    o = rep.merge(live.rename(columns={"prov": "p2"}), on=["uid", "ym"])
    o = o[o["p2"] != o["prov"]].groupby("i")["ym"].nunique()
    L["reliable"] = o.reindex(L.index).fillna(0).to_numpy() >= nmon.to_numpy()
    # cancellation email near paid-through end
    tmp = L[["uid", "prov", "channel", "pt"]].rename(columns={"pt": "dt"})
    L["cancel_same"] = near(tmp, cn, -45, 45, on=("uid", "prov", "channel"))
    L["cancel_any"] = near(tmp, cn, -45, 45)
    j = L[["uid", "prov", "channel", "pt", "last"]].reset_index().merge(cn[["uid", "prov", "channel", "dt"]], on=["uid", "prov", "channel"])
    j = j[(j["dt"] - j["pt"]).dt.days.abs() <= 45].groupby("index")["dt"].min()
    L["cancel_lag"] = (j.reindex(L.index) - L["last"]).dt.days
    rows = []
    for (p, ch), y in L.groupby(["prov", "channel"]):
        if len(y) < 30:
            continue
        yr = y[y["reliable"]]
        rows.append(dict(region=region, prov=p, channel=ch, W=int(y["W"].iloc[0]), lapses=len(y), cancel_same=y["cancel_same"].mean(),
                         cancel_any=y["cancel_any"].mean(), lapses_reliable=len(yr),
                         cancel_same_reliable=yr["cancel_same"].mean() if len(yr) else np.nan,
                         lapses_last12m=int((y["last"] >= data_end - pd.Timedelta(days=365)).sum()),
                         lag_last_to_cancel_p25=y["cancel_lag"].quantile(.25), lag_last_to_cancel_p50=y["cancel_lag"].median(),
                         lag_last_to_cancel_p75=y["cancel_lag"].quantile(.75),
                         cancel_same_last12m=y.loc[y["last"] >= data_end - pd.Timedelta(days=365), "cancel_same"].mean()))
    lc = pd.DataFrame(rows)

    # cancel -> next payment
    cn2 = cn[cn["dt"] <= data_end - pd.Timedelta(days=62)].copy()
    prev = cn2[["uid", "prov", "dt"]].reset_index().merge(allpay.rename(columns={"dt": "d0", "channel": "ch0", "plan": "plan0"}),
                                                           on=["uid", "prov"])
    prev = prev[(prev["d0"] <= prev["dt"]) & (prev["d0"] >= prev["dt"] - pd.Timedelta(days=62))].sort_values("d0").groupby("index").last()
    nx = cn2[["uid", "prov", "dt"]].reset_index().merge(allpay.rename(columns={"dt": "d1", "channel": "ch1", "plan": "plan1"}),
                                                         on=["uid", "prov"])
    nx = nx[nx["d1"] > nx["dt"]].sort_values("d1").groupby("index").first()
    cn2 = cn2.join(prev[["d0", "ch0", "plan0"]]).join(nx[["d1", "ch1", "plan1"]])
    cn2["W"] = [W(region, p, ch) for p, ch in zip(cn2["prov"], cn2["channel"])]
    cn2["days_to_pay"] = (cn2["d1"] - cn2["dt"]).dt.days
    cn2["pay_in_W"] = cn2["days_to_pay"] <= cn2["W"]
    k = np.maximum(1, np.round((cn2["d1"] - cn2["d0"]).dt.days / 30.44)).fillna(1)
    ok = cn2["d0"].notna() & cn2["d1"].notna()
    cn2["anchored"] = False
    cn2.loc[ok, "anchored"] = (cn2.loc[ok, "d1"] - add_months(cn2.loc[ok, "d0"], k[ok])).dt.days.abs() <= TOL["M"]
    cn2["same_ch_plan"] = (cn2["ch1"] == cn2["channel"]) & (cn2["plan1"] == cn2["plan0"])
    pay = cn2[["uid", "prov", "d1"]].dropna().rename(columns={"d1": "dt"})
    cn2["signup_near_pay"] = False
    cn2.loc[pay.index, "signup_near_pay"] = near(pay, su, -7, 7)
    rows = []
    for (p, ch), y in cn2.groupby(["prov", "channel"]):
        if len(y) < 30:
            continue
        z = y[y["pay_in_W"]]
        cont = z[z["anchored"] & z["same_ch_plan"] & ~z["signup_near_pay"]]
        rows.append(dict(region=region, prov=p, channel=ch, cancels=len(y), had_pay_before=y["d0"].notna().mean(),
                         pay_within_W=y["pay_in_W"].mean(), pay_within_W_n=len(z),
                         of_which_signup_email=z["signup_near_pay"].mean() if len(z) else np.nan,
                         of_which_continuing_renewal=len(cont) / len(z) if len(z) else np.nan,
                         share_cancels_continuing_no_signup=len(cont) / len(y),
                         days_to_pay_p25=z["days_to_pay"].quantile(.25), days_to_pay_p50=z["days_to_pay"].median(),
                         days_to_pay_p75=z["days_to_pay"].quantile(.75)))
    cp = pd.DataFrame(rows)

    # sign-up marker presence: episode starts vs renewal receipts
    starts = c[c["renews"] | (c["prov"] == "chatgpt")].copy()
    starts = starts.sort_values(["uid", "prov", "dt"])
    gprev = starts.groupby(["uid", "prov"])["dt"].shift()
    starts["is_start"] = gprev.isna() | ((starts["dt"] - gprev).dt.days > 62)
    starts = starts[starts["dt"] >= pd.Timestamp("2024-01-01")]
    smp = pd.concat([d.sample(min(len(d), 400_000), random_state=0) for _, d in starts.groupby("is_start")])
    smp["marker"] = near(smp[["uid", "prov", "dt"]], su[["uid", "prov", "dt"]], -7, 7)
    smp["marker_same_ch"] = near(smp[["uid", "prov", "channel", "dt"]], su, -7, 7, on=("uid", "prov", "channel"))
    sm = smp.groupby(["prov", "channel", "is_start"]).agg(n=("dt", "size"), marker=("marker", "mean"),
                                                         marker_same_ch=("marker_same_ch", "mean")).reset_index()
    sm = sm[sm["n"] >= 30].assign(region=region)
    return lc, cp, sm


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 500)
    out = [run(r) for r in ["us", "eu"]]
    lc, cp, sm = (pd.concat(z) for z in zip(*out))
    lc.round(4).to_csv(OUTD / "t3_lapse_cancel.csv", index=False)
    cp.round(4).to_csv(OUTD / "t3_cancel_then_pay.csv", index=False)
    sm.round(4).to_csv(OUTD / "t3_signup_marker.csv", index=False)
    print(lc.round(3).to_string(index=False))
    print(cp.round(3).to_string(index=False))
    print(sm.round(3).to_string(index=False))
