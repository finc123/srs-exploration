"""Receipt subscriber engine: classified charges + cancellation emails -> subscriptions, daily index and flows.

Rules (agreed 2026-10-19):
- Pre-join history is used (both receipt panels backfill each mailbox's history); no tenure rule. Signals revise
  slightly as new mailboxes bring their history.
- A subscription is a run of paid receipts for one key (plan or provider). It continues while the next paid receipt
  arrives within 75 days of a monthly charge (tolerates one missed renewal email) or 365 + 35 days of an annual one,
  and no cancellation email arrived in between.
- Churn = the earlier signal: a cancellation email (dated on the email day), or renewals stopping (dated at the end of
  the paid period, last payment + 31 / 365 days).
- Channels that send no renewal receipts (ChatGPT direct: sign-up only) stay active until a cancellation email
  (`raw`), or follow the survival curve of the same provider's renewing channels in that panel (`modelled`).
- Panel exit: US mailboxes that are now inactive are not in the extract (removed). EU: a subscription that lapses
  after the user stopped sending any receipts (activity spell, 90-day gap) is a panel exit and removed retroactively;
  so is an open non-renewing subscription whose user has gone quiet.
- Gross add = first paid receipt of a subscription; reactivation = gross add after an earlier churn of the same key.
"""
import numpy as np
import pandas as pd

from subs import _daily_count

CYCLE = {"M": 31, "Q": 92, "A": 365}
WINDOW = {"M": 75, "Q": 135, "A": 400}  # Q: e.g. Apple SuperGrok $30 for 3 months
EU_QUIET = 90
FAR = pd.Timestamp("2100-01-01")


def subscriptions(pay: pd.DataFrame, cancels: pd.DataFrame, key: str, data_end: pd.Timestamp,
                  spells: pd.DataFrame | None = None, by=()) -> pd.DataFrame:
    """pay: uid, dt, cadence, plan, provider, channel, renews. cancels: uid, dt, provider, plan.
    A cancel applies at provider level, or at plan level when its plan is known (else to whatever plan is live)."""
    grp = [*by, "uid", key]
    ch = pay.assign(ev=0).sort_values([*grp, "dt"]).drop_duplicates([*grp, "dt", "plan"])
    ch["cover"] = np.where(ch["renews"], ch["dt"] + pd.to_timedelta(ch["cadence"].map(WINDOW), unit="D"), FAR)
    cx = cancels.copy()
    if key == "plan":  # unknown-plan cancels attach to the member's live plan(s) for that provider
        lk = list(dict.fromkeys([*by, "uid", "provider"]))
        live = ch.groupby(lk)["plan"].unique().explode().reset_index()
        unk = cx["plan"].isna() | cx["plan"].astype(str).str.startswith("unknown")
        cx = pd.concat([cx[~unk], cx[unk].drop(columns="plan").merge(live, on=lk)])
    cx = cx.assign(ev=1)[[*grp, "dt", "ev"]]
    e = pd.concat([ch, cx], ignore_index=True).sort_values([*grp, "dt", "ev"]).reset_index(drop=True)
    g = e.groupby(grp, sort=False)
    e["n_cancel"] = g["ev"].cumsum()
    is_ch = e["ev"] == 0
    c = e[is_ch].copy()
    cg = c.groupby(grp, sort=False)
    prev_cover = cg["cover"].shift()
    cancel_between = c["n_cancel"] - cg["n_cancel"].shift()
    c["new"] = prev_cover.isna() | (c["dt"] > prev_cover) | (cancel_between > 0)
    c["sub_n"] = c.groupby(grp, sort=False)["new"].cumsum()
    e.loc[is_ch, "sub_n"] = c["sub_n"]
    e["sub_n"] = e.groupby(grp, sort=False)["sub_n"].ffill()
    first_cancel = (e[(e["ev"] == 1) & e["sub_n"].notna()].groupby([*grp, "sub_n"])["dt"].min().rename("cancel_dt"))

    # A subscription renews if any of its charges comes from a renewing channel (e.g. an EU ChatGPT direct sign-up
    # receipt followed by PayPal renewals); then only the renewing charges set the lapse.
    c["paid_through"] = (c["dt"] + pd.to_timedelta(c["cadence"].map(CYCLE), unit="D")).where(c["renews"])
    c["cover_r"] = c["cover"].where(c["renews"])
    s = (c.groupby([*grp, "sub_n"])
          .agg(start=("dt", "min"), last_pay=("dt", "max"), paid_through=("paid_through", "max"),
               renew_by=("cover_r", "max"), renews=("renews", "any"), n_pay=("dt", "size"),
               first_plan=("plan", "first"), channel=("channel", "first"))
          .join(first_cancel).reset_index())
    s["renew_by"] = s["renew_by"].fillna(FAR)
    lapse_known = s["renews"] & (s["renew_by"] <= data_end)
    s["end"] = pd.NaT
    s.loc[lapse_known, "end"] = s.loc[lapse_known, "paid_through"]
    s["end"] = s[["end", "cancel_dt"]].min(axis=1)  # earlier signal
    s["outcome"] = np.where(s["end"].notna(), np.where(s["cancel_dt"].notna() & (s["end"] == s["cancel_dt"]), "cancel", "lapse"), "open")

    if spells is not None:  # EU exit rule
        sp = spells.astype({"spell_start": "datetime64[ns]", "spell_end": "datetime64[ns]"}).sort_values("spell_start")
        s["last_pay"] = s["last_pay"].astype("datetime64[ns]")
        s = pd.merge_asof(s.sort_values("last_pay"), sp[["uid", "spell_start", "spell_end"]],
                          left_on="last_pay", right_on="spell_start", by="uid", direction="backward")
        quiet_at_lapse = (s["outcome"] == "lapse") & (s["spell_end"] < s["paid_through"])
        quiet_open = (s["outcome"] == "open") & ~s["renews"] & (s["spell_end"] + pd.Timedelta(days=EU_QUIET) < data_end)
        s.loc[quiet_at_lapse | quiet_open, "outcome"] = "exit"
        s = s.drop(columns=["spell_start", "spell_end"])
    s["kept"] = s["outcome"] != "exit"
    s["end"] = s["end"].fillna(data_end)
    s = s.sort_values([*grp, "start"])
    churned = s["kept"] & s["outcome"].isin(["cancel", "lapse"])
    prior = churned.astype(int).groupby([s[c] for c in grp]).cumsum() - churned.astype(int)
    s["reactivation"] = s["kept"] & (prior > 0)
    return s.reset_index(drop=True)


def survival(s: pd.DataFrame, data_end: pd.Timestamp, horizon: int = 900) -> np.ndarray:
    """Kaplan-Meier-style daily survival S[k] from kept renewing subscriptions (churn = cancel or lapse)."""
    r = s[s["kept"] & s["renews"]]
    dur = (r["end"] - r["start"]).dt.days.clip(lower=0).to_numpy()
    event = r["outcome"].isin(["cancel", "lapse"]).to_numpy()
    at_risk = np.array([(dur >= k).sum() for k in range(horizon)], dtype=float)
    deaths = np.bincount(dur[event].clip(max=horizon - 1), minlength=horizon)[:horizon]
    h = np.divide(deaths, at_risk, out=np.zeros(horizon), where=at_risk > 0)
    return np.cumprod(1 - h)


def daily(s: pd.DataFrame, key: str, days: pd.DatetimeIndex, by=(), modelled: dict | None = None) -> pd.DataFrame:
    """Daily subs and flows per key. `modelled` maps provider -> survival array: non-renewing subscriptions of that
    provider are replaced by their expected survivors (fractional), and their churn by the expected decrements."""
    out = []
    k = s[s["kept"]]
    for gkey, x in k.groupby([*by, key]):
        gkey = gkey if isinstance(gkey, tuple) else (gkey,)
        row = dict(zip([*by, key], gkey))
        prov = x["provider"].iloc[0] if "provider" in x else row.get("provider", gkey[-1])
        f = pd.DataFrame(index=days)
        surv = (modelled or {}).get(prov)
        obs = x if surv is None else x[x["renews"]]
        f["subs"] = _daily_count(obs["start"], obs["end"], days).astype(float)
        f["gross_adds"] = x.groupby("start").size().reindex(days, fill_value=0)
        f["reactivations"] = x[x["reactivation"]].groupby("start").size().reindex(days, fill_value=0)
        f["churn"] = obs[obs["outcome"].isin(["cancel", "lapse"])].groupby("end").size().reindex(days, fill_value=0).astype(float)
        if surv is not None:
            # Expected survivors and decrements = sign-ups by day convolved with S (and with its daily drop).
            adds = x[~x["renews"]].groupby("start").size().reindex(days, fill_value=0).to_numpy(float)
            S = np.r_[surv, np.full(max(0, len(days) - len(surv)), surv[-1])][:len(days)]
            exp = np.convolve(adds, S)[:len(days)]
            dec = np.convolve(adds, np.r_[0, -np.diff(S)])[:len(days)]
            f["subs"] += exp
            f["churn"] += dec
            f["modelled_subs"] = exp
        out.append(f.assign(**row).rename_axis("date").reset_index())
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()
