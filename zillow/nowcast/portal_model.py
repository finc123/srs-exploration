# Vendored verbatim from SRSfund/srs workflows/jobs/cotality/artifacts/loan_volume_weekly/post_run/insight_template.py @ 454e8c2d.
# The portal's quarterly model (chain-ladder county-fill gross-up + trailing capture). Re-copy when the portal changes.
"""Cotality loan-volume takeaway: the dashboard's top-note insight, built from the export payload.

A Python port of the page's model (``internet/cotality_loan_volume_backtest/index.html``, the
``FILL-MODEL`` block and ``takeaway()``), so the workflow writes the same read the page shows on
its default settings (RKT capture rule ``last``, Z ``avg``, no growth override):

* county-fill gross-up: chain-ladder development factors from the weekly vintages, per entity,
  steps across a vendor restatement left out; a month is used once it is ``FILL_MIN_AGE`` days
  past month-end, else projected as last year's month x (1 + growth);
* estimate = grossed-up signal / capture rate (grossed-up signal / reported) from up to 4 reported
  quarters before it in the same regime;
* the takeaway: the quarter the nowcast covers (unreported, 2+ of its months over), else a recap of
  the last reported quarter; then the recent monthly trend with the 30-yr PMMS move.

Everything here is pure (no I/O): ``build_insights(payload)`` takes the dict
``export_dashboard_json.py`` writes and returns insights in the shared format
(``workflows.jobs._shared.data_insights``). Change the page and this module together; bump
``TEMPLATE_VERSION`` when the wording or the math changes, so a new version writes even on
data already written.
"""

from __future__ import annotations

import calendar
import math
from datetime import date

TEMPLATE_ID = "cotality_loan_volume_takeaway"
TEMPLATE_VERSION = "1"
ENTITIES = ("Z", "RKT")          # Total (the market) is not published

FILL_STEP, FILL_MIN_AGE, FILL_MATURE_AGE = 7, 21, 84
FILL_BREAK_LO, FILL_BREAK_HI = 0.995, 1.015
CAP_RULE = {"RKT": "last"}       # everyone else: avg
CAP_RULE_LABEL = {"avg": "average", "last": "last quarter", "trend": "trend"}
TK_NEUTRAL, TK_SHARP, TK_RATE_MOVE, TK_RATE_SHARP = 0.02, 0.15, 0.25, 0.5
MIN_YEAR = "2023"


# ---- dates and formatting -------------------------------------------------------------------
def _ym(m: str) -> tuple[int, int]:
    return int(m[:4]), int(m[5:7])


def add_m(m: str, k: int) -> str:
    y, mo = _ym(m)
    i = y * 12 + mo - 1 + k
    return f"{i // 12}-{i % 12 + 1:02d}"


def month_end(m: str) -> date:
    y, mo = _ym(m)
    return date(y, mo, calendar.monthrange(y, mo)[1])


def day_age(ts: str, m: str) -> int:
    return (date.fromisoformat(ts[:10]) - month_end(m)).days


def q_months(p: str) -> list[str]:
    y, q = p[:4], int(p[-1])
    return [f"{y}-{3 * q - 2 + i:02d}" for i in range(3)]


def mon_short(m: str) -> str:
    return calendar.month_abbr[_ym(m)[1]]


def fmt_date(d: date) -> str:
    return f"{calendar.month_abbr[d.month]} {d.day}, {d.year}"


def f_pct(v):        # +51.9%
    return "n/a" if v is None else f"{'+' if v >= 0 else '-'}{abs(v) * 100:.1f}%"


def f_usd(v):        # $1.95B (the page's toLocaleString, max 2 decimals)
    if v is None:
        return "n/a"
    s = f"{v / 1e9:,.2f}".rstrip("0").rstrip(".")
    return f"${s}B"


def _round_half_up(x: float) -> int:   # JS Math.round
    return math.floor(x + 0.5)


# ---- county-fill gross-up -------------------------------------------------------------------
def _interp(pts, a):
    for p, q in zip(pts, pts[1:]):
        if p["a"] <= a <= q["a"]:
            return p["v"] + (q["v"] - p["v"]) * (a - p["a"]) / max(q["a"] - p["a"], 1)
    return None


def build_fill(vintages):
    by_e: dict = {}
    for v in vintages or []:
        day = v["CAPTURE_TIMESTAMP"][:10]
        mm = by_e.setdefault(v["ENTITY"], {}).setdefault(v["MONTH"], {})
        if day not in mm or v["CAPTURE_TIMESTAMP"] > mm[day]["ts"]:
            mm[day] = {"ts": v["CAPTURE_TIMESTAMP"], "v": v["TOTAL_LOANS_VOLUME"]}
    out = {}
    for e, months in by_e.items():
        ms = sorted(months)
        days = sorted({d for m in ms for d in months[m]})
        breaks = []
        for i in range(1, len(days)):
            rs = []
            for m in ms:
                a, b = months[m].get(days[i - 1]), months[m].get(days[i])
                if a and b and a["v"] > 0 and day_age(days[i - 1], m) >= FILL_MATURE_AGE:
                    rs.append(b["v"] / a["v"])
            if len(rs) >= 2:
                rs.sort()
                n = len(rs)
                med = rs[(n - 1) // 2] if n % 2 else (rs[n // 2 - 1] + rs[n // 2]) / 2
                if med < FILL_BREAK_LO or med > FILL_BREAK_HI:
                    breaks.append(days[i])
        seg = lambda d: sum(1 for b in breaks if b <= d)  # noqa: E731
        num: dict = {}
        den: dict = {}
        for m in ms:
            pts = [{"a": day_age(d, m), "v": months[m][d]["v"], "s": seg(d)} for d in sorted(months[m])]
            m_max = max(p["a"] for p in pts)
            for s in dict.fromkeys(p["s"] for p in pts):
                sp = [p for p in pts if p["s"] == s]
                g = FILL_STEP
                while g + FILL_STEP <= m_max:
                    x0, x1 = _interp(sp, g), _interp(sp, g + FILL_STEP)
                    if x0 and x1:
                        num[g] = num.get(g, 0) + x1
                        den[g] = den.get(g, 0) + x0
                    g += FILL_STEP
        f = {g: num[g] / den[g] for g in den}
        cum, c = {}, 1.0
        for g in sorted(f, reverse=True):          # oldest age first
            c *= f[g]
            cum[g] = c
        out[e] = cum
    return out


def fill_factor(fill, e, age):
    if age is None or age < FILL_MIN_AGE:
        return None
    cum = fill.get(e)
    if cum is None:
        return 1.0
    g = max(FILL_STEP, _round_half_up(age / FILL_STEP) * FILL_STEP)
    return cum.get(g, 1.0)


# ---- capture rate ---------------------------------------------------------------------------
def regime_of(e, p):
    if e != "RKT":
        return "all"
    if p <= "2025 Q3":
        return "pre"
    if p >= "2026 Q1":
        return "post"
    return "transition"


def trailing_cap(e, arr, i, rule="avg"):
    t = arr[i]
    reg = regime_of(e, t["PERIOD"])
    if reg == "transition":
        return None, []
    el = [r for r in arr if r["idx"] < t["idx"] and r["MONTHS"] == 3 and r["REPORTED"] is not None
          and r["G_CAPTURE"] is not None and regime_of(e, r["PERIOD"]) == reg][-4:]
    if not el:
        return None, []
    src = [(r["PERIOD"], r["G_CAPTURE"]) for r in el]
    if rule == "last" or (rule == "trend" and len(el) < 2):
        return el[-1]["G_CAPTURE"], src
    if rule == "trend":
        n = len(el)
        mx = sum(r["idx"] for r in el) / n
        my = sum(r["G_CAPTURE"] for r in el) / n
        b = (sum((r["idx"] - mx) * (r["G_CAPTURE"] - my) for r in el)
             / sum((r["idx"] - mx) ** 2 for r in el))
        return my + b * (t["idx"] - mx), src
    return sum(r["G_CAPTURE"] for r in el) / len(el), src


# ---- quarterly model ------------------------------------------------------------------------
def build_model(payload):
    """{entity: [quarter rows, oldest first]}, {entity: {month: grossed-up volume}} (ready only)."""
    fill = build_fill(payload.get("vintages"))
    cur_m = (payload.get("generated_at") or "")[:7]
    Q: dict = {}
    MA: dict = {}
    for m in payload["monthly"]:
        e, mo = m["ENTITY"], m["MONTH"]
        y, mn = _ym(mo)
        qq = (mn + 2) // 3
        per, idx = f"{y} Q{qq}", y * 4 + qq - 1
        r = Q.setdefault(e, {}).setdefault(per, {"sig": 0.0, "n": 0, "ne": 0, "idx": idx, "months": []})
        age = day_age(m["CAPTURE_TIMESTAMP"], mo) if m.get("CAPTURE_TIMESTAMP") else None
        g = fill_factor(fill, e, age)
        r["sig"] += m["TOTAL_LOANS_VOLUME"]
        r["n"] += 1
        if mo < cur_m:
            r["ne"] += 1
        r["months"].append({"MONTH": mo, "RAW": m["TOTAL_LOANS_VOLUME"], "CAP": m.get("CAPTURE_TIMESTAMP")})
        if g is not None:
            MA.setdefault(e, {})[mo] = m["TOTAL_LOANS_VOLUME"] * g
    bt = {(b["ENTITY"], b["PERIOD"]): b for b in payload["backtest"]}
    rows = {}
    for e in Q:
        ma = MA.get(e, {})
        last3 = sorted(ma)[-3:]
        t3py = [ma.get(add_m(m, -12)) for m in last3]
        trail = (sum(ma[m] for m in last3) / sum(t3py) - 1
                 if len(last3) == 3 and None not in t3py and sum(t3py) > 0 else None)
        arr = []
        for p in sorted(Q[e], key=lambda k: Q[e][k]["idx"]):
            q, b = Q[e][p], bt.get((e, p), {})
            rep = b.get("REPORTED_VOLUME")
            qm = q_months(p)
            rdy = [m for m in qm if m in ma]
            py = lambda m: ma.get(add_m(m, -12))  # noqa: E731
            py_r = [py(m) for m in rdy]
            g_qtd = (sum(ma[m] for m in rdy) / sum(py_r) - 1
                     if rdy and None not in py_r and sum(py_r) > 0 else None)
            g_def = None if len(rdy) == 3 else (g_qtd if g_qtd is not None else trail)
            src = "" if len(rdy) == 3 else ("qtd" if g_qtd is not None else ("trail" if trail is not None else ""))
            used = []
            for m in qm:
                if m in ma:
                    used.append(ma[m])
                elif py(m) is not None and g_def is not None:
                    used.append(py(m) * (1 + g_def))
                else:
                    used.append(None)
            gsig = sum(used) if None not in used else None
            arr.append({
                "PERIOD": p, "idx": q["idx"], "MONTHS": q["n"], "MONTHS_DONE": q["ne"],
                "QMONTHS": qm, "READY": [m in ma for m in qm], "READY_N": len(rdy),
                "G_GROWTH": g_def, "G_GROWTH_SRC": src,
                "REPORTED": rep, "CONSENSUS": b.get("CONSENSUS_VOLUME"),
                "IS_CURRENT": b["IS_CURRENT"] if b.get("IS_CURRENT") is not None else q["ne"] < 3,
                "R_SIGNAL": q["sig"], "G_SIGNAL": gsig,
                "G_CAPTURE": gsig / rep if rep and gsig is not None and len(rdy) == 3 else None,
                "CAPTURE_TS": max((x["CAP"] for x in q["months"] if x["CAP"]), default=None),
            })
        rule = CAP_RULE.get(e, "avg")
        for i, r in enumerate(arr):
            cap, src = trailing_cap(e, arr, i, rule)
            r["CAP_RULE"], r["ESTCAP"], r["CAPSRC"] = rule, cap, src
            r["EST"] = r["G_SIGNAL"] / cap if cap and r["G_SIGNAL"] is not None else None
            r["ERROR"] = r["EST"] / r["REPORTED"] - 1 if r["EST"] is not None and r["REPORTED"] else None
            r["NC_OK"] = r["G_SIGNAL"] is not None
        by_idx = {r["idx"]: r for r in arr}
        for r in arr:
            py = by_idx.get(r["idx"] - 4)
            pyr = py["REPORTED"] if py else None
            r["ACT_YOY"] = r["REPORTED"] / pyr - 1 if r["REPORTED"] is not None and pyr is not None else None
            r["CONS_YOY"] = r["CONSENSUS"] / pyr - 1 if r["CONSENSUS"] is not None and pyr is not None else None
            r["EST_YOY"] = r["EST"] / pyr - 1 if r["EST"] is not None and pyr is not None else None
        rows[e] = arr
    return rows, MA


# ---- the takeaway ---------------------------------------------------------------------------
class _Figs:
    """Collects key_figures: every number the text quotes (workflows.jobs._shared.data_insights checks this)."""

    def __init__(self):
        self.items = []

    def add(self, label, value, unit, compare_label=None, compare_value=None):
        if value is None:
            return
        # Unrounded: the text formats this same value, so the writer's number check matches exactly.
        f = {"label": label, "value": float(value), "unit": unit}
        if compare_label is not None and compare_value is not None:
            f["compare_label"], f["compare_value"] = compare_label, float(compare_value)
        self.items.append(f)


def _stance(v):
    if v is None:
        return "neutral"
    return "positive" if v > TK_NEUTRAL else "negative" if v < -TK_NEUTRAL else "neutral"


def _monthly_trend(e, ma, pmms, cur_m, figs):
    ms = sorted(ma)[-3:]
    if len(ms) < 3:
        return None
    ys = [ma[m] / ma[add_m(m, -12)] - 1 if ma.get(add_m(m, -12)) else None for m in ms]
    if None in ys:
        return None
    (y3, y2, y1), (m3, m2, m1) = ys, ms
    dec, acc, sharp = y1 < y2 < y3, y1 > y2 > y3, abs(y1 - y3) >= TK_SHARP
    if dec:
        trend = f"{'sharp ' if sharp else ''}deceleration"
    elif acc:
        trend = f"{'sharp ' if sharp else ''}acceleration"
    else:
        trend = f"growth {'slowed' if y1 < y2 else 'picked up'} in {mon_short(m1)}"
    pm = {p["MONTH"]: p["PMMS30"] for p in pmms or [] if p.get("PMMS30") is not None}
    last = max(pm) if pm else None
    if m3 in pm and last and last > m3:
        r0, r1 = pm[m3], pm[last]
        dr = r1 - r0
        lbl = f"{mon_short(last)} {'to date' if last >= cur_m else 'avg'}"
        figs.add(f"30-yr fixed rate, {mon_short(m3)} avg", r0, "rate_pct")
        figs.add(f"30-yr fixed rate, {lbl}", r1, "rate_pct")
        if abs(dr) < TK_RATE_MOVE:
            trend += (f", with the 30-yr fixed rate little changed ({r0:.1f}% in {mon_short(m3)}, "
                      f"{r1:.1f}% {lbl})")
        else:
            up = dr > 0
            link = "as" if (up and y1 < y2) or (not up and y1 > y2) else "while"
            trend += (f" {link} the 30-yr fixed rate has {'risen' if up else 'fallen'}"
                      f"{' sharply' if abs(dr) >= TK_RATE_SHARP else ''} from {r0:.1f}% "
                      f"({mon_short(m3)} avg) to {r1:.1f}% ({lbl})")
    for m, y in zip(ms, ys):
        figs.add(f"{mon_short(m)} {m[:4]} YoY (grossed-up Cotality volume)", y, "pct")
    return (f"Recent Cotality data trend ({e} volume in Cotality vs the same month last year, grossed "
            f"up for late county reporting; not the company's reported figures): {trend}. "
            f"{mon_short(m1)} is trending at {f_pct(y1)} YoY vs {mon_short(m2)} {f_pct(y2)} and "
            f"{mon_short(m3)} {f_pct(y3)}.")


def entity_insight(e, rows, ma, payload):
    """The takeaway for one entity in the shared insight format, or None with nothing to say."""
    rows = [r for r in rows if r["PERIOD"][:4] >= MIN_YEAR]
    figs = _Figs()
    cur_m = (payload.get("generated_at") or "")[:7]
    caps = [m.get("CAPTURE_TIMESTAMP") for m in payload["monthly"]
            if m["ENTITY"] == e and m.get("CAPTURE_TIMESTAMP")]
    as_of = fmt_date(date.fromisoformat(max(caps)[:10])) if caps else None
    tgt = next((r for r in rows if r["IS_CURRENT"] and r["NC_OK"] and r["MONTHS_DONE"] >= 2), None)
    bullets, headline, stance, period = [], None, "neutral", None
    if tgt:
        q, period = tgt["PERIOD"][5:], tgt["PERIOD"]
        fill = tgt["R_SIGNAL"] / tgt["G_SIGNAL"] if tgt["G_SIGNAL"] else None
        proj = [mon_short(m) for m, ok in zip(tgt["QMONTHS"], tgt["READY"]) if not ok]
        if as_of and fill is not None:
            figs.add(f"Share of {q} volume captured (raw / grossed-up)", fill, "pct")
            s = (f"Data as of the {as_of} capture; about {fill * 100:.0f}% of {e}'s {q} volume is in "
                 f"(the rest is the county-fill gross-up{' and the projected months' if proj else ''}).")
            if proj:
                figs.add("Growth assumed for months not ready", tgt["G_GROWTH"], "pct")
                s += (f" {tgt['READY_N']} of 3 months ready; {' and '.join(proj)} projected at "
                      f"{f_pct(tgt['G_GROWTH'])} YoY "
                      f"({'quarter to date' if tgt['G_GROWTH_SRC'] == 'qtd' else 'latest 3 months'}).")
            bullets.append(s)
        if tgt["EST_YOY"] is None:
            return None
        vc = tgt["EST"] / tgt["CONSENSUS"] - 1 if tgt["CONSENSUS"] else None
        stance = _stance(vc)
        figs.add(f"{q} estimate YoY", tgt["EST_YOY"], "pct", "VA consensus YoY", tgt["CONS_YOY"])
        figs.add("VA consensus YoY", tgt["CONS_YOY"], "pct")
        figs.add("Estimate vs consensus", vc, "pct")
        headline = (f"{e} {q} is trending towards {f_pct(tgt['EST_YOY'])} growth"
                    + (f" vs. VA cons of {f_pct(tgt['CONS_YOY'])}" if tgt["CONS_YOY"] is not None else "")
                    + (f", or {abs(vc) * 100:.1f}% {'above' if vc >= 0 else 'below'} consensus"
                       if vc is not None else ""))
        figs.add(f"{q} estimate", tgt["EST"], "usd", "VA consensus", tgt["CONSENSUS"])
        figs.add(f"{q} VA consensus", tgt["CONSENSUS"], "usd")
        rule = (f" RKT capture rate: {CAP_RULE_LABEL[tgt['CAP_RULE']]}." if e == "RKT" else "")
        bullets.insert(0, f"Estimate {f_usd(tgt['EST'])} vs VA consensus {f_usd(tgt['CONSENSUS'])}.{rule}")
    else:
        rep = next((r for r in reversed(rows) if r["REPORTED"] is not None), None)
        nxt = next((r for r in rows if r["IS_CURRENT"]), None)
        if as_of:
            bullets.append(f"Data as of the {as_of} capture.")
        if rep:
            period = rep["PERIOD"]
            vc = rep["REPORTED"] / rep["CONSENSUS"] - 1 if rep["CONSENSUS"] else None
            stance = _stance(vc)
            figs.add(f"{rep['PERIOD'][5:]} reported", rep["REPORTED"], "usd")
            figs.add(f"{rep['PERIOD'][5:]} reported YoY", rep["ACT_YOY"], "pct")
            figs.add("Reported vs consensus", vc, "pct")
            figs.add(f"{rep['PERIOD'][5:]} VA consensus", rep["CONSENSUS"], "usd")
            headline = (f"{e} {rep['PERIOD'][5:]} reported {f_usd(rep['REPORTED'])} "
                        f"({f_pct(rep['ACT_YOY'])} YoY)"
                        + (f", {abs(vc) * 100:.1f}% {'above' if vc >= 0 else 'below'} VA cons of "
                           f"{f_usd(rep['CONSENSUS'])}" if vc is not None else ""))
            if rep["EST"] is not None:
                figs.add("Our estimate", rep["EST"], "usd")
                figs.add("Our estimate YoY", rep["EST_YOY"], "pct")
                figs.add("Estimate error", rep["ERROR"], "pct")
                bullets.append(f"Our estimate was {f_usd(rep['EST'])} ({f_pct(rep['EST_YOY'])}, "
                               f"error {f_pct(rep['ERROR'])}).")
        if nxt:
            start = month_end(nxt["QMONTHS"][1]).toordinal() + 1
            d = date.fromordinal(start)
            figs.add(f"{nxt['PERIOD'][5:]} VA consensus YoY", nxt["CONS_YOY"], "pct")
            bullets.append(f"{nxt['PERIOD'][5:]} commentary starts {calendar.month_abbr[d.month]} {d.day}, "
                           f"once 2 of its months are over"
                           + (f"; VA cons is {f_pct(nxt['CONS_YOY'])} YoY" if nxt["CONS_YOY"] is not None else "")
                           + ".")
    mo = _monthly_trend(e, ma, payload.get("pmms"), cur_m, figs)
    if mo:
        bullets.append(mo)
    if not headline:
        return None
    ready = sorted(ma)
    return {
        "tickers": [e],
        "headline": headline,
        "bullets": bullets,
        "stance": stance,
        "stance_vs": "consensus",
        "period": period,
        "data_through": month_end(ready[-1]).isoformat() if ready else None,
        "key_figures": figs.items,
        "assumptions": {"cap_rule": CAP_RULE.get(e, "avg"), "growth_override": None,
                        "fill_min_age_days": FILL_MIN_AGE},
    }


def data_as_of(payload):
    """The newest Z/RKT capture in the payload (ISO string), or None: the same value as the job
    YAML's ``data_as_of.sql``, but from the read the insights are built from."""
    caps = [r["CAPTURE_TIMESTAMP"] for r in payload.get("monthly") or []
            if r.get("ENTITY") in ENTITIES and r.get("CAPTURE_TIMESTAMP")]
    return max(caps) if caps else None


def build_insights(payload):
    """Insights for ``ENTITIES`` from the export payload (the dashboard JSON)."""
    rows, MA = build_model(payload)
    out = []
    for e in ENTITIES:
        if e in rows:
            ins = entity_insight(e, rows[e], MA.get(e, {}), payload)
            if ins:
                out.append(ins)
    return out
