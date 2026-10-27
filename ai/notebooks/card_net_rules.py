"""Engine for card_net_adds.ipynb: billing cycles, lapse churn and net adds on card data (Omega 2022 panel), and the
matching Google Play e-receipt flows (NIQ items_v) for the card vs e-receipt comparison.

Card payments come from card_core_rules (same pull, same classification as card_gross_adds.ipynb).

cycle_gaps()    -> one row per payment with the days to the same member's next payment for the same key
cycle_table()   -> p50 / p90 / p95 / p99 of in-subscription gaps per group (monthly plans, gaps up to CAP days)
series()        -> one row per subscription spell: start (gross add), last payment, churn date, censored flag
monthly()       -> gross adds, churn, start-of-month subscribers, churn rate and net adds per month
gp_receipts()   -> Google Play paid receipts and cancellation emails per provider (filters from direct_v_channel_comparison)
"""
from pathlib import Path

import numpy as np
import pandas as pd

import channel_rules

CACHE = Path(__file__).resolve().parent.parent / ".cache" / "card_net"
RECEIPTS = Path(__file__).resolve().parent.parent / ".cache" / "channel_cmp" / "raw.parquet"
CAP = 75          # a monthly gap above this starts a new subscription under the old gross-add rule, so it is not a billing cycle
ANNUAL_THR = 400  # annual plans: 365 + 35 days (earlier decision), too few annual renewals to estimate a percentile
CARD_LAG = 10     # card transactions are still posting for about 10 days
RECEIPT_LAG = 3   # e-receipts load within a few days


def cycle_gaps(pay: pd.DataFrame, key: list) -> pd.DataFrame:
    """pay: uid, dt, cadence + key columns. Same-day payments are one payment. Adds `gap` = days to the next payment
    for the same uid and key (NaN for the last one)."""
    y = pay.drop_duplicates(["uid", *key, "dt"]).sort_values(["uid", *key, "dt"]).reset_index(drop=True)
    y["gap"] = (y.groupby(["uid", *key]).dt.shift(-1) - y.dt).dt.days
    return y


def cycle_table(g: pd.DataFrame, by: list, cap=CAP) -> pd.DataFrame:
    """Percentiles of in-subscription gaps (monthly plans, 0 < gap <= cap) per group, plus how regular they are."""
    m = g[g.cadence.eq("M") & g.gap.between(1, cap)]
    q = m.groupby(by).gap.quantile([0.5, 0.9, 0.95, 0.99]).unstack()
    q.columns = ["p50", "p90", "p95", "p99"]
    t = m.groupby(by).agg(gaps=("gap", "size"), members=("uid", "nunique"),
                          pct_26_35=("gap", lambda s: s.between(26, 35).mean()),
                          pct_under_20=("gap", lambda s: (s < 20).mean()))
    # share of all monthly gaps (any length) above CAP: these are stop-and-restart, not a billing cycle
    allm = g[g.cadence.eq("M") & g.gap.gt(0)].groupby(by).gap
    t["pct_gaps_over_cap"] = allm.apply(lambda s: (s > cap).mean())
    return q.join(t)


def regularity(g: pd.DataFrame, by: list, p95: pd.Series, p99: pd.Series, cap=CAP) -> pd.DataFrame:
    """Does a member's cycle stay put? For members with 3+ consecutive in-subscription gaps:
    - pct_steady: all their gaps within 3 days of their own median gap
    - late_then_normal: share of gaps above p95 (but <= cap) that are followed by a normal gap (<= p95) - a 30 / 40 / 30 pattern
    - false_churn_p99: share of in-subscription gaps above p99 (but <= cap). The p99 rule reads these as churn + re-add."""
    m = g[g.cadence.eq("M")].copy()
    m["thr95"] = m.set_index(by).index.map(p95).values
    m["thr99"] = m.set_index(by).index.map(p99).values
    m["in_sub"] = m.gap.between(1, cap)
    m["next_gap"] = m.groupby(["uid", *by]).gap.shift(-1)
    s = m[m.in_sub]
    per = s.groupby([*by, "uid"]).gap.agg(n="size", med="median", lo="min", hi="max")
    per = per[per.n >= 3]
    per["steady"] = (per.hi - per.med <= 3) & (per.med - per.lo <= 3)
    late = s[s.gap > s.thr95]
    out = pd.DataFrame({
        "members_3plus_gaps": per.groupby(level=by).size(),
        "pct_steady": per.groupby(level=by).steady.mean(),
        "median_member_range_days": (per.hi - per.lo).groupby(level=by).median(),
        "late_then_normal": late.assign(ok=late.next_gap.between(1, 1e9) & (late.next_gap <= late.thr95)).groupby(by).ok.mean(),
        "false_churn_p99": s.assign(f=s.gap > s.thr99).groupby(by).f.mean(),
    })
    return out


def streak_table(g: pd.DataFrame, by: list, runs=(0, 1, 3, 6), cap=CAP) -> pd.DataFrame:
    """p95 / p99 of in-subscription gaps, restricted to gaps preceded by at least r consecutive normal (26-35 day) gaps
    for the same uid and key. r = 1 is "paid the prior month"; larger r keeps members with a steady history."""
    key = ["uid", "provider", "channel", "plan"]
    m = g[g.cadence.eq("M")].copy()
    m["norm"] = m.gap.between(26, 35).astype(int)
    m["prev_norm"] = m.groupby(key).norm.shift(1).fillna(0).astype(int)
    m["blk"] = (m.prev_norm == 0).astype(int).groupby([m[k] for k in key]).cumsum()
    m["run"] = m.groupby(key + ["blk"]).prev_norm.cumsum()
    s = m[m.gap.between(1, cap)]
    out = {r: s[s.run >= r].groupby(by).gap.agg(p95=lambda x: x.quantile(0.95), p99=lambda x: x.quantile(0.99),
                                                 pct_over_35=lambda x: (x > 35).mean(), gaps="size") for r in runs}
    return pd.concat(out, names=["prior_normal_months"]).unstack(0).swaplevel(axis=1).sort_index(axis=1, level=0, sort_remaining=False)


def user_steadiness(g: pd.DataFrame, by: list, cap=CAP) -> pd.DataFrame:
    """Per member (3+ in-subscription gaps for one plan): are all gaps 26-35 days, all within 3 days of their own median,
    their range (longest - shortest), and whether they ever had a gap above 35 days."""
    key = ["uid", "provider", "channel", "plan"]
    s = g[g.cadence.eq("M") & g.gap.between(1, cap)]
    u = s.groupby(key).gap.agg(n="size", med="median", lo="min", hi="max")
    u = u[u.n >= 3]
    u["all_26_35"] = (u.lo >= 26) & (u.hi <= 35)
    u["within_3d"] = (u.hi - u.med <= 3) & (u.med - u.lo <= 3)
    u["range"] = u.hi - u.lo
    u["any_over_35"] = u.hi > 35
    return u.groupby(by).agg(members=("n", "size"), pct_all_26_35=("all_26_35", "mean"), pct_within_3d=("within_3d", "mean"),
                             median_range=("range", "median"), p90_range=("range", lambda x: x.quantile(0.9)),
                             pct_any_over_35=("any_over_35", "mean"))


def anchor_share(g: pd.DataFrame, by: list, cap=CAP) -> pd.Series:
    """Of 40-75 day gaps, the share within 2 days of twice the member's own normal cycle. Such a gap keeps the billing
    day-of-month: one charge is missing (failed payment, or not recorded) rather than a cancel and later re-subscribe,
    which would restart billing on a random day."""
    key = ["uid", "provider", "channel", "plan"]
    s = g[g.cadence.eq("M") & g.gap.between(1, cap)]
    own = s[s.gap.between(26, 35)].groupby(key).gap.median().rename("own")
    x = s[s.gap.between(40, cap)].join(own, on=key).dropna(subset=["own"])
    return x.assign(hit=(x.gap - 2 * x.own).abs() <= 2).groupby(by).hit.mean()


def series(pay: pd.DataFrame, key: list, thr: pd.Series, cycle: pd.Series, end: pd.Timestamp, lag=0,
           thr_by=("provider", "channel")) -> pd.DataFrame:
    """Subscription spells. A payment starts a new spell when the previous payment for the same uid and key is more than
    the threshold earlier (thr and cycle: indexed by thr_by, monthly plans; ANNUAL_THR after an annual payment).
    churn_dt = last payment + the key's median cycle (the date the next charge was due). The spell's status is known
    only once last payment + threshold + lag <= end; otherwise it is censored (still active or not yet known)."""
    y = pay.drop_duplicates(["uid", *key, "dt"]).sort_values(["uid", *key, "dt"]).reset_index(drop=True)
    k = y.set_index(list(thr_by)).index
    t = np.where(y.cadence.eq("A"), ANNUAL_THR, k.map(thr).values.astype(float))
    c = np.where(y.cadence.eq("A"), 365, k.map(cycle).values.astype(float))
    grp = y.groupby(["uid", *key])
    prev_dt, prev_t = grp.dt.shift(1), pd.Series(t).groupby([y.uid, *[y[c_] for c_ in key]]).shift(1)
    new = prev_dt.isna() | ((y.dt - prev_dt).dt.days > prev_t)
    y["sid"] = new.cumsum()
    y["thr"], y["cyc"] = t, c
    s = y.groupby("sid").agg(uid=("uid", "first"), **{k_: (k_, "first") for k_ in key}, start=("dt", "min"),
                             last=("dt", "max"), n_pay=("dt", "size"), thr=("thr", "last"), cyc=("cyc", "last"))
    s["known_at"] = s["last"] + pd.to_timedelta(s.thr + lag, unit="D")
    s["censored"] = s.known_at > end
    s["churn_dt"] = (s["last"] + pd.to_timedelta(s.cyc, unit="D")).where(~s.censored)
    return s.reset_index(drop=True)


def monthly(s: pd.DataFrame, by: list, start="2024-01", end=None) -> pd.DataFrame:
    """Gross adds (spell starts), churn (by churn month), subscribers at the start of each month (spells started before
    the month and not churned before it), churn rate = churn / start-of-month subscribers, net adds = adds - churn."""
    months = pd.period_range(start, end or s.start.max(), freq="M")
    out = []
    for keys, d in s.groupby(by):
        keys = keys if isinstance(keys, tuple) else (keys,)
        adds = d.groupby(d.start.dt.to_period("M")).size()
        churn = d.churn_dt.dropna().dt.to_period("M").value_counts()
        first = months.to_timestamp()
        subs = [((d.start < f) & ~(d.churn_dt < f)).sum() for f in first]
        t = pd.DataFrame({"gross_adds": adds.reindex(months, fill_value=0), "churn": churn.reindex(months, fill_value=0),
                          "subs_start": subs}, index=months)
        out.append(t.assign(**dict(zip(by, keys))))
    t = pd.concat(out).rename_axis("month").reset_index()
    t["churn_rate"] = t.churn / t.subs_start.where(t.subs_start > 0)
    t["net_adds"] = t.gross_adds - t.churn
    return t


def churn_complete_through(end: pd.Timestamp, thr: float, cycle: float, lag=0) -> pd.Period:
    """Last month whose churn is fully known: every spell churning in it (last payment + cycle in the month) has
    last payment + thr + lag <= end, i.e. month end + (thr - cycle) + lag <= end."""
    m = (end - pd.Timedelta(days=thr - cycle + lag)).to_period("M")
    return m if (m + 1).to_timestamp() - pd.Timedelta(days=1) + pd.Timedelta(days=thr - cycle + lag) <= end else m - 1


# ---- e-receipts: Google Play, same filters as direct_v_channel_comparison.ipynb -------------------------------------
GP_RX = {  # provider: (paid receipt regex, cancellation regex), on the lower-cased description
    "chatgpt": (r"\(chatgpt\) auto-renewing subscription", r"chatgpt"),
    "claude": (r"\(claude by anthropic\) auto-renewing subscription", r"claude by anthropic"),
    "perplexity": (r"perplexity (pro|max) \(perplexity.*auto-renewing subscription", r"perplexity"),
}


def gp_receipts() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Google Play paid receipts (priced, auto-renewing, not trial notices) and Google Play Cancellation emails, per provider.
    Cancellations are de-duplicated with the channel notebook's 45-day rule (channel_rules.churn_events)."""
    r = pd.read_parquet(RECEIPTS, filters=[("merchant_id", "in", [1493, 3452])])
    r["d"] = r.description.str.lower().fillna("")
    r["dt"] = pd.to_datetime(r.order_date)
    gp_pay = r.merchant_id.eq(1493) & (r.item_price.fillna(0) > 0) & r.d.str.contains("auto-renewing subscription") \
        & ~r.d.str.startswith("your trial")
    pays, cans = [], []
    for p, (prx, crx) in GP_RX.items():
        pm = gp_pay & r.d.str.contains(prx, regex=True)
        cm = r.merchant_id.eq(3452) & r.d.str.contains(crx, regex=True)
        sig = r.loc[pm, ["mailbox_id", "dt"]]
        can = channel_rules.churn_events(r.loc[cm, ["mailbox_id", "dt"]], sig)
        pays.append(sig.assign(provider=p))
        cans.append(can.assign(provider=p))
    pays = pd.concat(pays).rename(columns={"mailbox_id": "uid"}).assign(channel="google_play", cadence="M")
    cans = pd.concat(cans).rename(columns={"mailbox_id": "uid"}).assign(channel="google_play")
    return pays.reset_index(drop=True), cans.reset_index(drop=True)


def cancels_in_spells(cans: pd.DataFrame, s: pd.DataFrame, key: list) -> pd.DataFrame:
    """Cancellation emails that fall inside a receipt spell (start <= cancel <= last payment + threshold): the mailbox's
    sign-up was seen. Adds the spell's start, last payment and expected next charge (last + cycle)."""
    sp = s[["uid", *key, "start", "last", "thr", "cyc"]].sort_values("start")
    j = pd.merge_asof(cans.sort_values("dt"), sp, left_on="dt", right_on="start", by=["uid", *key], direction="backward")
    j = j[j.start.notna() & (j.dt <= j["last"] + pd.to_timedelta(j.thr, unit="D"))].copy()
    j["next_due"] = j["last"] + pd.to_timedelta(j.cyc, unit="D")
    return j.drop_duplicates(["uid", *key, "start"])  # one cancellation per spell, the first

