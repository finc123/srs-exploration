"""Shared filters and the gross-add / churn engine for direct_v_channel_comparison.ipynb.

Each provider x channel is reduced to three kinds of e-receipt rows from srs_slice.common.items_v:
  signup  - an email sent when a subscription starts (welcome / confirmation), unpriced
  pay     - a priced subscription receipt (first payment and, where the channel sends them, each renewal)
  cancel  - a cancellation email
Gross add = the first signup/pay row in a consecutive series for a mailbox. A new series starts when the previous
signup/pay row is more than WINDOW days earlier (ANNUAL_WINDOW if that row was an annual plan), or when a
cancellation email arrived since it. Churn = cancellation emails, one per cancellation (emails for the same
mailbox within CANCEL_CLUSTER days and with no signup/pay row between them are one cancellation, dated at the first).
Both are counted as distinct mailboxes per order_date month.
"""
import pandas as pd, numpy as np

WINDOW, ANNUAL_WINDOW, CANCEL_CLUSTER = 75, 400, 45


def gross_adds(sig: pd.DataFrame, cancels: pd.DataFrame) -> pd.DataFrame:
    """sig: mailbox_id, dt, annual (bool). cancels: mailbox_id, dt. Returns the signal rows that start a series."""
    s = sig.sort_values(["mailbox_id", "dt"]).reset_index(drop=True)
    same = s.mailbox_id.eq(s.mailbox_id.shift())
    prev_dt, prev_annual = s.dt.shift(), s.annual.shift(fill_value=False).astype(bool)
    gap = (s.dt - prev_dt).dt.days
    new = ~same | (gap > np.where(prev_annual, ANNUAL_WINDOW, WINDOW))
    # a cancellation email dated in [previous signal, this signal) also starts a new series
    if len(cancels):
        c = cancels[["mailbox_id", "dt"]].rename(columns={"dt": "cdt"}).sort_values("cdt")
        t = s.assign(prev_dt=prev_dt.where(same)).reset_index().sort_values("dt")
        t = pd.merge_asof(t, c, left_on="dt", right_on="cdt", by="mailbox_id", allow_exact_matches=False, direction="backward")
        hit = t.set_index("index").sort_index()
        new |= same & hit.cdt.notna() & (hit.cdt >= hit.prev_dt)
    return s[new]


def churn_events(cancels: pd.DataFrame, sig: pd.DataFrame) -> pd.DataFrame:
    c = cancels.sort_values(["mailbox_id", "dt"]).reset_index(drop=True)
    same = c.mailbox_id.eq(c.mailbox_id.shift())
    gap = (c.dt - c.dt.shift()).dt.days
    new = ~same | (gap > CANCEL_CLUSTER)
    if len(sig):  # a signup/pay row between two cancellation emails means two separate cancellations
        s = sig[["mailbox_id", "dt"]].rename(columns={"dt": "sdt"}).sort_values("sdt")
        t = c.assign(prev_dt=c.dt.shift().where(same)).reset_index().sort_values("dt")
        t = pd.merge_asof(t, s, left_on="dt", right_on="sdt", by="mailbox_id", allow_exact_matches=True, direction="backward")
        hit = t.set_index("index").sort_index()
        new |= same & hit.sdt.notna() & (hit.sdt > hit.prev_dt)
    return c[new]


def monthly(adds: pd.DataFrame, churn: pd.DataFrame, start="2025-01") -> pd.DataFrame:
    f = lambda x, n: x.assign(month=x.dt.dt.to_period("M")).groupby("month").mailbox_id.nunique().rename(n)
    out = pd.concat([f(adds, "gross_adds"), f(churn, "churn")], axis=1).fillna(0).astype(int)
    out = out[out.index >= pd.Period(start)]
    full = pd.period_range(start, max(out.index.max(), pd.Period(start)), freq="M") if len(out) else []
    return out.reindex(full, fill_value=0).rename_axis("month")


def run(rows: pd.DataFrame, signup, pay, cancel, annual=None, start="2025-01"):
    """rows: tagged items for one provider x channel; signup/pay/cancel/annual: boolean masks over rows."""
    m = signup | pay
    # `row` keeps each event's source row (index into the full frame), so labels such as plan can be looked up later
    sig = rows.loc[m, ["mailbox_id", "dt"]].assign(annual=annual[m].values if annual is not None else False, row=rows.index[m])
    can = rows[cancel][["mailbox_id", "dt"]].assign(row=rows.index[cancel])
    adds, churn = gross_adds(sig, can), churn_events(can, sig)
    return monthly(adds, churn, start), adds, churn, sig
