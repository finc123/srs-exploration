"""Subscriber engine: classified payments + panel activity spells -> subscriptions, daily index and flows.

Rules (agreed 2026-10-19, same as the Muse tracker):
- A subscription is a run of payments for one key (plan = tier x cadence, or provider) where each payment arrives
  within the renewal window of the previous one: 45 days after a monthly payment (user rule, 2026-10-19), 365 + 35
  days after an annual one. A lapse is dated at the end of the paid period (one month after the last monthly payment).
- Paid-through = last payment + cycle (31 monthly, 365 annual). The subscriber is active from the first payment to
  paid-through, or to the data end while the renewal window has not yet passed (open / provisional).
- Gross add: the member's activity spell containing the first payment started more than TENURE days earlier.
  Otherwise the subscription is new-to-panel and excluded at both ends (not added, not churned, not in the index).
- Lapse at paid-through: churn if the member transacted in the CHURN_WINDOW days up to the lapse; otherwise a panel
  exit, and the whole subscription is removed retroactively (gross add and index), per the user's option (a).
- A gross add by a member with an earlier churned subscription to the same key is also a reactivation.
- Active panel members on day d: a transaction in the trailing GRACE days (d within [spell_start, spell_end + GRACE]).
- No end-of-data cutoff: all data is used; the latest weeks are provisional.
"""
import numpy as np
import pandas as pd

GRACE, TENURE, CHURN_WINDOW = 35, 35, 30
CYCLE = {"M": 31, "A": 365}
WINDOW = {"M": 45, "A": 365 + GRACE}  # monthly: user rule 2026-10-19 (35 days gave ~3-6pp false churn)


def subscriptions(pay: pd.DataFrame, spells: pd.DataFrame, key: str, data_end: pd.Timestamp) -> pd.DataFrame:
    """pay: uid, dt, cadence (M/A), plan, provider (+ any grouping cols in `pay.attrs['by']`).
    spells: uid, spell_start, spell_end.  key: 'plan' or 'provider'."""
    by = pay.attrs.get("by", [])
    p = (pay.sort_values([*by, "uid", key, "dt"])
            .drop_duplicates([*by, "uid", key, "dt"])
            .reset_index(drop=True))
    p["paid_through"] = p["dt"] + pd.to_timedelta(p["cadence"].map(CYCLE), unit="D")
    p["renew_by"] = p["dt"] + pd.to_timedelta(p["cadence"].map(WINDOW), unit="D")
    grp = [*by, "uid", key]
    prev_cover = p.groupby(grp)["renew_by"].shift()
    p["sub_n"] = (prev_cover.isna() | (p["dt"] > prev_cover)).groupby([p[c] for c in grp]).cumsum()

    s = (p.groupby([*grp, "sub_n"])
          .agg(start=("dt", "min"), last_pay=("dt", "max"), paid_through=("paid_through", "max"), renew_by=("renew_by", "max"),
               n_pay=("dt", "size"), first_plan=("plan", "first"), last_plan=("plan", "last"),
               first_cadence=("cadence", "first"))
          .reset_index())

    sp = spells.sort_values("spell_start")
    # Spell containing the first payment -> tenure.
    s = pd.merge_asof(s.sort_values("start"), sp[["uid", "spell_start"]].rename(columns={"spell_start": "start_spell"}),
                      left_on="start", right_on="start_spell", by="uid", direction="backward")
    s["tenure_days"] = (s["start"] - s["start_spell"]).dt.days
    s["gross_add"] = s["tenure_days"] > TENURE

    # Activity up to the lapse -> churn vs panel exit.
    s = pd.merge_asof(s.sort_values("paid_through"), sp[["uid", "spell_start", "spell_end"]],
                      left_on="paid_through", right_on="spell_start", by="uid", direction="backward")
    s["open"] = s["renew_by"] > data_end
    active_at_lapse = s["spell_end"] >= s["paid_through"] - pd.Timedelta(days=CHURN_WINDOW)
    s["outcome"] = np.select([s["open"], active_at_lapse], ["open", "churn"], "exit")
    s["end"] = np.where(s["open"], data_end, s["paid_through"])
    s["kept"] = s["gross_add"] & (s["outcome"] != "exit")

    s = s.sort_values([*grp, "start"]).drop(columns=["spell_start", "spell_end"])
    prior_churn = s.assign(c=(s["kept"] & (s["outcome"] == "churn")).astype(int)).groupby(grp)["c"].cumsum() - \
        (s["kept"] & (s["outcome"] == "churn")).astype(int)
    s["reactivation"] = s["kept"] & (prior_churn > 0)
    return s.reset_index(drop=True)


def _daily_count(start: pd.Series, end: pd.Series, days: pd.DatetimeIndex) -> np.ndarray:
    """Number of [start, end] intervals covering each day (difference array)."""
    i0 = np.searchsorted(days.values, start.values.astype("datetime64[ns]"))
    i1 = np.searchsorted(days.values, end.values.astype("datetime64[ns]"), side="right")
    d = np.zeros(len(days) + 1, dtype=np.int64)
    np.add.at(d, i0, 1)
    np.add.at(d, i1, -1)
    return np.cumsum(d)[:-1]


def daily(subs: pd.DataFrame, key: str, days: pd.DatetimeIndex, by=()) -> pd.DataFrame:
    """Daily subscribers and flows per key from kept subscriptions."""
    out = []
    k = subs[subs["kept"]]
    for g, x in k.groupby([*by, key]):
        g = g if isinstance(g, tuple) else (g,)
        row = dict(zip([*by, key], g))
        f = pd.DataFrame(index=days)
        f["subs"] = _daily_count(x["start"], x["end"], days)
        f["gross_adds"] = x.groupby("start").size().reindex(days, fill_value=0)
        f["reactivations"] = x[x["reactivation"]].groupby("start").size().reindex(days, fill_value=0)
        f["churn"] = x[x["outcome"] == "churn"].groupby("end").size().reindex(days, fill_value=0)
        out.append(f.assign(**row).rename_axis("date").reset_index())
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def removed_adds(subs: pd.DataFrame, key: str, by=()) -> pd.DataFrame:
    """Gross adds later removed because the member exited the panel, by start month (revision size)."""
    x = subs[subs["gross_add"]].assign(month=lambda d: d["start"].dt.to_period("M"))
    return (x.groupby([*by, key, "month"])
             .agg(gross_adds_raw=("gross_add", "size"), removed_exit=("outcome", lambda o: (o == "exit").sum()))
             .reset_index())


def active_members(spells: pd.DataFrame, days: pd.DatetimeIndex) -> pd.Series:
    """Panel members with a transaction in the trailing GRACE days, per day."""
    return pd.Series(_daily_count(spells["spell_start"], spells["spell_end"] + pd.Timedelta(days=GRACE), days),
                     index=days, name="active_members")
