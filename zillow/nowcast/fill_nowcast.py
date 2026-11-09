"""Zillow origination nowcast from Cotality fill rates.

Monthly: % filled at day d after month-end = volume as of that day (interpolated between weekly
captures) / the month's estimated final volume, where final = latest x the portal's chain-ladder
tail factor at the month's current age (so a reference month that is still filling isn't treated
as complete). A month d days past month-end is projected as latest / fill, using the fill at day d
of months m-4..m-2: mean -> central, lowest -> upper bound, highest -> lower bound (m-1 is added
only when fewer than two of m-4..m-2 have a fill at that day). Months > 120 days old are final.
A month is first estimated from its first capture no more than 7 days before month-end (MIN_DAY);
estimates before month-end are flagged provisional.

Revisions: each projected month's y/y re-estimated at every earlier weekly capture in the vintages
(build_monthly on the data as it stood then), charted for the last REVISION_MONTHS months and listed
under each month in the summary.

Quarterly: the portal's model, run unchanged from the vendored `portal_model.py` (chain-ladder
gross-up of months >= 21 days past month-end, partial quarters at quarter-to-date growth, / trailing
4-quarter capture rate, y/y vs reported). The range scales each ready month by its monthly bounds.
A quarter gets no estimate until one of its months is 21 days past month-end.

Hiring: Zillow mortgage job postings per month (Revelio Indeed), charted only on the first weekly
run after a new Revelio load (BATCH_ID timestamp within HIRING_NEW_DAYS before the run), so each
load posts once.

Inputs are either live Snowflake (local, via common.q) or the JSON saved from the SRS MCP snowflake
tool (cloud routine): `--monthly monthly.json --vintages vintages.json --backtest backtest.json [--hiring hiring.json]`.
Outputs to --out: monthly.png, quarterly.png, revisions.png, monthly.csv, quarterly.csv, revisions.csv,
summary.md, and hiring.png when there is a new Revelio load.
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import portal_model as pm  # noqa: E402

MAX_DAY = 120
MIN_DAY = -7              # first estimate: a capture no more than 7 days before month-end
SHOW_MONTHS = 24
SHOW_QUARTERS = 8
REFS = (4, 3, 2)          # m-4..m-2
FALLBACK = 1              # m-1, only when fewer than two of m-4..m-2 have a fill at that day
QUERIES = ("monthly", "vintages", "backtest")
HIRING_MONTHS = 24
HIRING_NEW_DAYS = 7       # routine runs weekly
REVISION_MONTHS = 4       # projected months on the revisions chart

BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e6e5e0", "#fcfcfb"


# ---- load -------------------------------------------------------------------------------------

def _records(df):
    """Portal-payload rows: upper-case keys, ISO timestamp strings, floats."""
    df = df.copy()
    df.columns = [c.upper() for c in df.columns]
    if "CAPTURE_TIMESTAMP" in df:
        df["CAPTURE_TIMESTAMP"] = pd.to_datetime(df.CAPTURE_TIMESTAMP).dt.strftime("%Y-%m-%dT%H:%M:%S")
    df = df.astype(object).where(df.notna(), None)
    return df.to_dict("records")


def load(args):
    if args.monthly:
        out = {}
        for k in QUERIES:
            raw = json.loads(Path(getattr(args, k)).read_text())
            out[k] = _records(pd.DataFrame(raw["rows"] if isinstance(raw, dict) else raw))
        if args.hiring:
            raw = json.loads(Path(args.hiring).read_text())
            out["hiring"] = _records(pd.DataFrame(raw["rows"] if isinstance(raw, dict) else raw))
        return out
    sys.path.insert(0, str(HERE.parent))
    from common import q
    return {k: _records(q((HERE / f"{k}.sql").read_text())) for k in QUERIES + ("hiring",)}


# ---- hiring -----------------------------------------------------------------------------------

def build_hiring(data, asof):
    """Last HIRING_MONTHS months of postings, or None if the Revelio load isn't new this week."""
    if not data.get("hiring"):
        return None
    h = pd.DataFrame(data["hiring"])
    loaded = datetime.strptime(max(h.BATCH_ID)[:19], "%Y-%m-%d-%H-%M-%S")       # BATCH_ID is the UTC load time
    run = datetime.combine(asof, datetime.now(timezone.utc).time())
    if not timedelta(0) <= run - loaded < timedelta(days=HIRING_NEW_DAYS):    # a load after last week's run, by the clock
        return None
    loaded = loaded.date()
    s = h.set_index(pd.PeriodIndex(h.POST_MONTH, freq="M")).JOB_COUNT.astype(int)
    s = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"), fill_value=0)
    s.attrs["loaded"] = loaded
    s.attrs["ly"] = s.shift(12)
    return s.iloc[-HIRING_MONTHS:]


# ---- monthly fill-rate projection -------------------------------------------------------------

def _and(items):
    return ", ".join(items[:-1]) + " and " + items[-1] if len(items) > 1 else items[0]


def build_monthly(data, asof):
    fill = pm.build_fill(data["vintages"])

    def tail(age):                        # latest x tail = estimated final volume
        f = pm.fill_factor(fill, "Z", age)
        return f if f is not None else np.nan

    lat = pd.DataFrame(data["monthly"])
    lat["m"] = pd.PeriodIndex(lat.MONTH, freq="M")
    lat = lat[lat.m.dt.start_time.dt.date < asof].set_index("m").sort_index()
    lat["age"] = [pm.day_age(t, m) for t, m in zip(lat.CAPTURE_TIMESTAMP, lat.MONTH)]
    lat = lat[lat.age >= MIN_DAY]
    lat["vol"] = lat.TOTAL_LOANS_VOLUME.astype(float)

    vin = pd.DataFrame(data["vintages"])
    vin["day"] = vin.CAPTURE_TIMESTAMP.str[:10]
    vin = vin.sort_values("CAPTURE_TIMESTAMP").groupby(["MONTH", "day"]).last().reset_index()   # 2026-08-07 loaded twice
    curves = {}
    for mo, g in vin.groupby("MONTH"):
        m = pd.Period(mo, freq="M")
        if m not in lat.index:
            continue
        ages = np.array([pm.day_age(d, mo) for d in g.day])
        final = lat.at[m, "vol"] * tail(lat.at[m, "age"])
        curves[m] = (ages, g.TOTAL_LOANS_VOLUME.astype(float).to_numpy() / final)

    def fill_at(m, d):
        if m not in curves:
            return np.nan
        a, f = curves[m]
        return float(np.interp(d, a, f, left=np.nan, right=np.nan))

    out = []
    for m, r in lat.iloc[-SHOW_MONTHS - 12:].iterrows():
        d, vol = int(r.age), r.vol
        row = dict(month=m, capture=r.CAPTURE_TIMESTAMP[:10], day=d, latest=vol)
        if d > MAX_DAY:
            row.update(proj=vol, lo=vol, hi=vol, refs="final", n_refs=0)
        else:
            refs = {m - k: fill_at(m - k, d) for k in REFS}
            refs = {k: v for k, v in refs.items() if not np.isnan(v)}
            if len(refs) < 2 and not np.isnan(fill_at(m - FALLBACK, d)):
                refs[m - FALLBACK] = fill_at(m - FALLBACK, d)
            if refs:
                f = np.array(list(refs.values()))
                row.update(proj=vol / f.mean(), lo=vol / f.max(), hi=vol / f.min(), n_refs=len(refs),
                           refs=", ".join(f"{k.strftime('%b-%y')} {v:.1%}" for k, v in sorted(refs.items())),
                           refs_text=_and([f"{k.strftime('%B')} ({v:.1%})" for k, v in sorted(refs.items())]))
            else:
                row.update(proj=np.nan, lo=np.nan, hi=np.nan, refs="none", n_refs=0)
        out.append(row)
    mo = pd.DataFrame(out).set_index("month")
    mo["ly"] = lat.vol.reindex(mo.index - 12).to_numpy()
    for c in ("proj", "lo", "hi"):
        mo[f"yoy_{c}"] = mo[c] / mo.ly - 1
    mo["projected"] = mo.day <= MAX_DAY
    return mo.iloc[-SHOW_MONTHS:]


def build_revisions(data, mo):
    """Each projected month's y/y as it would have been published at every earlier weekly capture:
    build_monthly rerun on the vintages up to that capture (a month's volume = its last vintage then).
    Only months already past month-end at that capture are estimated, as in the weekly post."""
    vin = pd.DataFrame(data["vintages"])
    vin["day"] = vin.CAPTURE_TIMESTAMP.str[:10]
    first = vin.MONTH.min()
    out = []
    for cut in sorted(vin.day.unique()):
        v = vin[vin.day <= cut]
        last = v.sort_values("CAPTURE_TIMESTAMP").groupby("MONTH").last()
        monthly = []
        for r in data["monthly"]:
            if r["MONTH"] in last.index:
                r = dict(r, TOTAL_LOANS_VOLUME=last.at[r["MONTH"], "TOTAL_LOANS_VOLUME"],
                         CAPTURE_TIMESTAMP=last.at[r["MONTH"], "CAPTURE_TIMESTAMP"])
            elif r["MONTH"] >= first:                       # no vintage yet at this capture
                continue
            monthly.append(r)
        m = build_monthly({"monthly": monthly, "vintages": v.drop(columns="day").to_dict("records")},
                          date.fromisoformat(cut) + timedelta(days=1))
        m = m[m.projected & m.index.isin(mo.index[mo.projected])]
        out.append(m.assign(cap=cut)[["cap", "day", "yoy_proj", "yoy_lo", "yoy_hi"]])
    rv = pd.concat(out).reset_index().dropna(subset=["yoy_proj"])
    return rv.sort_values(["month", "cap"])


# ---- quarterly: the portal model --------------------------------------------------------------

def build_quarterly(data, mo, asof):
    payload = {"generated_at": asof.isoformat(), "monthly": data["monthly"],
               "vintages": data["vintages"], "backtest": data["backtest"]}
    rows, MA = pm.build_model(payload)
    ma = MA.get("Z", {})
    qt = pd.DataFrame(rows["Z"])
    qt = qt[qt.MONTHS_DONE > 0].tail(SHOW_QUARTERS).copy()

    lo, hi = [], []
    for _, r in qt.iterrows():
        if r.G_SIGNAL is None or r.ESTCAP is None:
            lo.append(np.nan), hi.append(np.nan)
            continue
        sl = sh = 0.0
        for m in r.QMONTHS:
            p = pd.Period(m, freq="M")
            if m in ma:
                base = ma[m]
                ok = p in mo.index and mo.at[p, "projected"] and not np.isnan(mo.at[p, "proj"])
                sl += base * (mo.at[p, "lo"] / mo.at[p, "proj"] if ok else 1)
                sh += base * (mo.at[p, "hi"] / mo.at[p, "proj"] if ok else 1)
            else:                                            # not ready: last year x (1 + qtd/trailing growth)
                v = ma[pm.add_m(m, -12)] * (1 + r.G_GROWTH)
                sl += v
                sh += v
        lo.append(sl), hi.append(sh)
    qt["G_LO"], qt["G_HI"] = lo, hi
    # No estimate until at least one of the quarter's months is FILL_MIN_AGE days past month-end
    # (the portal would otherwise carry trailing 3-month growth forward).
    qt["FIRST_READY"] = [str(pm.month_end(q[0]) + timedelta(days=pm.FILL_MIN_AGE)) for q in qt.QMONTHS]
    qt.loc[qt.READY_N == 0, ["EST", "EST_YOY", "G_LO", "G_HI"]] = None
    pyrep = {r["PERIOD"]: r["REPORTED"] for r in rows["Z"]}
    prev = [pyrep.get(f"{int(p[:4]) - 1}{p[4:]}") for p in qt.PERIOD]
    qt["EST_YOY_LO"] = [l / c / py - 1 if py and c else np.nan for l, c, py in zip(qt.G_LO, qt.ESTCAP, prev)]
    qt["EST_YOY_HI"] = [h / c / py - 1 if py and c else np.nan for h, c, py in zip(qt.G_HI, qt.ESTCAP, prev)]
    qt["READY_MONTHS"] = [", ".join(pd.Period(m, freq="M").strftime("%b") for m, ok in zip(q, rd) if ok)
                          for q, rd in zip(qt.QMONTHS, qt.READY)]
    keep = ["PERIOD", "READY_N", "READY_MONTHS", "FIRST_READY", "G_GROWTH", "G_GROWTH_SRC", "G_SIGNAL", "ESTCAP", "EST",
            "REPORTED", "CONSENSUS", "EST_YOY", "EST_YOY_LO", "EST_YOY_HI", "ACT_YOY", "CONS_YOY"]
    qt = qt[keep].set_index("PERIOD")
    num = [c for c in keep[1:] if c not in ("READY_MONTHS", "FIRST_READY", "G_GROWTH_SRC")]
    qt[num] = qt[num].astype(float)
    return qt


# ---- charts -----------------------------------------------------------------------------------

def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def pct(ax):
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:+.0%}"))


def chart_monthly(s, path, asof):
    x = np.arange(len(s))
    lab = [m.strftime("%b\n%y") if m.month == 1 or i == 0 else m.strftime("%b") for i, m in enumerate(s.index)]
    pr = s.projected.to_numpy()

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True, gridspec_kw=dict(height_ratios=[3, 2], hspace=0.12))
    fig.patch.set_facecolor(SURFACE)
    for a in (a1, a2):
        _style(a)

    a1.axhline(0, color=MUTED, lw=1)
    a1.plot(x, s.yoy_proj, color=BLUE, lw=2, zorder=3)
    a1.scatter(x[~pr], s.yoy_proj[~pr], s=36, color=BLUE, zorder=4, label="Final (>120 days after month-end)")
    a1.scatter(x[pr], s.yoy_proj[pr], s=44, facecolor=SURFACE, edgecolor=BLUE, lw=2, zorder=4, label="Projected from fill rates")
    a1.errorbar(x[pr], s.yoy_proj[pr], yerr=[s.yoy_proj[pr] - s.yoy_lo[pr], s.yoy_hi[pr] - s.yoy_proj[pr]],
                fmt="none", ecolor=BLUE, capsize=4, lw=1.5, zorder=3)
    for i in np.where(pr)[0][-3:]:
        a1.annotate(f"{s.yoy_proj.iloc[i]:+.0%}", (x[i], s.yoy_proj.iloc[i]), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=9, color=INK)
    pct(a1)
    a1.set_ylabel("Volume y/y (Cotality basis)", color=INK2)
    a1.legend(frameon=False, fontsize=9, loc="upper left")
    a1.set_title(f"Zillow Home Loans monthly origination volume (Cotality), as of {asof}", loc="left", color=INK, fontsize=12)

    a2.bar(x, s.latest / 1e6, width=0.7, color=BLUE, edgecolor=SURFACE, lw=2, label="Volume recorded so far")
    rest = (s.proj - s.latest).clip(lower=0) / 1e6
    a2.bar(x[pr], rest[pr], bottom=s.latest[pr] / 1e6, width=0.7, color=BLUE, alpha=0.3, hatch="///",
           edgecolor=SURFACE, lw=2, label="Projected remaining fill")
    a2.errorbar(x[pr], s.proj[pr] / 1e6, yerr=[(s.proj - s.lo)[pr] / 1e6, (s.hi - s.proj)[pr] / 1e6],
                fmt="none", ecolor=INK2, capsize=4, lw=1.2, label="Projection range (m-4..m-2 fill)")
    a2.set_ylim(0, s.hi.max() / 1e6 * 1.3)
    a2.set_ylabel("$M", color=INK2)
    a2.legend(frameon=False, fontsize=9, loc="upper left", ncol=3)
    a2.set_xticks(x, lab)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def chart_quarterly(qt, path, asof):
    x = np.arange(len(qt))
    lab = [f"{p[-2:]}\n{p[2:4]}" for p in qt.index]
    fig, ax = plt.subplots(figsize=(11, 5))
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    ax.axhline(0, color=MUTED, lw=1)

    est = qt.EST_YOY.to_numpy(float)
    ax.plot(x, est, color=BLUE, lw=2, marker="o", ms=6, label="Cotality estimate (portal model, out-of-sample)")
    live = np.isnan(qt.ACT_YOY.to_numpy(float)) & ~np.isnan(est)
    ax.errorbar(x[live], est[live], yerr=[est[live] - qt.EST_YOY_LO[live], qt.EST_YOY_HI[live] - est[live]],
                fmt="none", ecolor=BLUE, capsize=5, lw=1.5)
    rep = qt.ACT_YOY.to_numpy(float)
    ax.plot(x, rep, color=ORANGE, lw=2, marker="o", ms=6, label="Reported")

    have = np.where(~np.isnan(rep))[0]
    if len(have):
        i0 = have[-1]
        cons = [i for i in range(i0 + 1, len(qt)) if not np.isnan(qt.CONS_YOY.iloc[i])]
        if cons:
            xs, ys = [i0] + cons, [rep[i0]] + [qt.CONS_YOY.iloc[i] for i in cons]
            ax.plot(xs, ys, color=ORANGE, lw=2, ls="--", marker="o", ms=6, mfc=SURFACE, label="Consensus")
            ax.annotate(f"cons {ys[-1]:+.0%}", (xs[-1], ys[-1]), xytext=(8, 8), textcoords="offset points", fontsize=9, color=INK)
    for i in np.where(live)[0]:
        r = qt.iloc[i]
        note = f"{r.EST_YOY:+.0%}"
        if r.READY_N < 3:
            note += f"\n({r.READY_MONTHS} only)" if r.READY_N else "\n(trailing 3-mo growth)"
        ax.annotate(note, (x[i], r.EST_YOY), xytext=(12, 0), textcoords="offset points", va="center", fontsize=9, color=INK)
    ax.set_xlim(-0.4, len(qt) - 0.2)
    pct(ax)
    ax.set_xticks(x, lab)
    ax.set_ylabel("Origination volume y/y", color=INK2)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    ax.set_title(f"Zillow total loan origination volume y/y: Cotality vs reported and consensus, as of {asof}",
                 loc="left", color=INK, fontsize=12)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def chart_revisions(rv, path, asof):
    months = sorted(rv.month.unique())[-REVISION_MONTHS:]
    cols = [YELLOW, AQUA, ORANGE, BLUE][-len(months):]
    fig, ax = plt.subplots(figsize=(11, 5))
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    for m, c in zip(months, cols):
        g = rv[rv.month == m]
        x = pd.to_datetime(g.cap)
        ax.fill_between(x, g.yoy_lo, g.yoy_hi, color=c, alpha=0.15, lw=0)
        ax.plot(x, g.yoy_proj, color=c, lw=2, marker="o", ms=5, label=m.strftime("%b-%y"))
        pre = (g.day < 0).to_numpy()
        ax.scatter(x[pre], g.yoy_proj[pre], s=30, facecolor=SURFACE, edgecolor=c, lw=1.5, zorder=4)
        ax.annotate(f"{g.yoy_proj.iloc[-1]:+.1%}", (x.iloc[-1], g.yoy_proj.iloc[-1]), xytext=(8, 0),
                    textcoords="offset points", va="center", fontsize=9, color=INK)
    pct(ax)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%d %b"))
    ax.set_ylabel("Projected volume y/y at each capture\n(open points: before month-end)", color=INK2)
    ax.legend(frameon=False, fontsize=9, loc="upper left", ncol=len(months))
    ax.set_title(f"Zillow monthly y/y estimate revisions by weekly Cotality capture, as of {asof}",
                 loc="left", color=INK, fontsize=12)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def chart_hiring(h, path):
    x = np.arange(len(h))
    lab = [m.strftime("%b\n%y") if m.month == 1 or i == 0 else m.strftime("%b") for i, m in enumerate(h.index)]
    fig, ax = plt.subplots(figsize=(11, 4))
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    ax.bar(x, h, width=0.7, color=BLUE, edgecolor=SURFACE, lw=2)
    for i, v in enumerate(h):
        ax.annotate(f"{v}", (x[i], v), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=9, color=INK)
    ax.set_xticks(x, lab)
    ax.set_ylabel("Job postings", color=INK2)
    ax.set_title(f"Zillow New Indeed Job Postings for Mortgage Roles (load as of {h.attrs['loaded']})",
                 loc="left", color=INK, fontsize=12)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


# ---- summary ----------------------------------------------------------------------------------

def summary(mo, qt, asof, h=None, rv=None):
    cap = max(mo.capture)
    stale = (asof - date.fromisoformat(cap)).days > 8
    lines = ["*Zillow Cotality nowcast*"]
    if stale:
        lines.append(":warning: No new Cotality capture in the last 8 days.")
    lines.append("")
    for p, r in qt[qt.ACT_YOY.isna()].iterrows():
        cons = f" vs consensus {r.CONS_YOY:+.1%}" if not np.isnan(r.CONS_YOY) else ""
        if r.READY_N == 0:
            lines.append(f"*{p}*: no estimate until {r.FIRST_READY} (first month 21 days past month-end){cons}")
            continue
        basis = "all 3 months" if r.READY_N == 3 else f"{r.READY_MONTHS} only"
        lines.append(f"*{p}* ({basis}): {r.EST_YOY:+.1%} y/y (range {r.EST_YOY_LO:+.1%} to {r.EST_YOY_HI:+.1%}){cons}")
    lines.append("")
    for m, r in mo[mo.projected & mo.proj.notna()].iterrows():
        d = abs(r.day)
        when = "at month-end" if r.day == 0 else f"{d} day{'s' if d != 1 else ''} {'after' if r.day > 0 else 'before'} month-end"
        if r.day < 0:
            when += ", provisional"
        lines.append(f"• *{m.strftime('%b-%y')}*: ${r.proj/1e6:,.0f}M (${r.lo/1e6:,.0f}–{r.hi/1e6:,.0f}M), "
                     f"*{r.yoy_proj:+.1%} y/y* ({when}; uses {r.refs_text} for fill rates)")
        g = rv[rv.month == m] if rv is not None else []
        if len(g) > 1:
            path = " → ".join(f"{date.fromisoformat(c):%d %b} {y:+.1%}" for c, y in zip(g.cap, g.yoy_proj))
            lines.append(f"    Revisions: {path}")
    if h is not None:
        m, ly = h.index[-1], h.attrs["ly"].get(h.index[-1])
        lines += ["", f"New Indeed postings load ({h.attrs['loaded']}): {h.iloc[-1]} new Zillow mortgage job postings in "
                      f"{m.strftime('%b-%y')} (prior month {h.iloc[-2]}"
                      + (f", year ago {int(ly)})" if pd.notna(ly) else ")")]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    for k in QUERIES + ("hiring",):
        ap.add_argument(f"--{k}")
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--asof", default=str(date.today()))
    args = ap.parse_args()
    asof = date.fromisoformat(args.asof)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    data = load(args)
    mo = build_monthly(data, asof)
    qt = build_quarterly(data, mo, asof)
    chart_monthly(mo, out / "monthly.png", asof)
    chart_quarterly(qt, out / "quarterly.png", asof)
    rv = build_revisions(data, mo)
    chart_revisions(rv, out / "revisions.png", asof)
    mo.to_csv(out / "monthly.csv")
    qt.to_csv(out / "quarterly.csv")
    rv.to_csv(out / "revisions.csv", index=False)
    h = build_hiring(data, asof)
    if h is not None:
        chart_hiring(h, out / "hiring.png")
    text = summary(mo, qt, asof, h, rv)
    (out / "summary.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
