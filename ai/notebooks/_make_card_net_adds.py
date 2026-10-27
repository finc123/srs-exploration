"""Builds card_net_adds.ipynb (run: python _make_card_net_adds.py, then execute with nbconvert on the exploration kernel)."""
import nbformat as nbf

from _card_net_adds_text import FINDINGS

nb = nbf.v4.new_notebook()
C = []
md = lambda s: C.append(nbf.v4.new_markdown_cell(s.strip()))
code = lambda s: C.append(nbf.v4.new_code_cell(s.strip()))
note = lambda k: md(FINDINGS[k]) if FINDINGS.get(k) else None

md("""
# AI subscription net adds on card data, and card vs e-receipt churn on Google Play (US)

Engine: `card_net_rules.py` (on top of `card_core_rules.py`). Card payments use the same pull, descriptor families and classification as `card_gross_adds.ipynb`: Omega 2022 consistent-shopper panel via `EARNEST.COMMON.TXNS_CORE_V` plus the unbranded-descriptor patch, rules from `../filters/{provider}.py`. E-receipts use the Google Play filters from `direct_v_channel_comparison.ipynb` (cache `../.cache/channel_cmp/raw.parquet`, NIQ `srs_slice.common.items_v`).

**Steps**
1. **Billing cycle.** For each provider x channel x descriptor family (each way a gross add is identified), the days between a member's consecutive payments for the same provider x channel x plan. p95 and p99 are taken over in-subscription gaps: monthly plans, 1 to 75 days (a gap above 75 days is a new subscription under the gross-add rule, so it is not a billing cycle).
2. **Churn rule.** A subscription churns when the member has no further payment for the same provider x channel x plan within a fixed **45-day cutoff** (both card and e-receipts; the p99 analysis below put the cutoff at about 60 days, which delays churn by a further cycle). Churn is dated at the expected next charge (last payment + median cycle). A payment after a longer gap starts a new subscription (a gross add), so adds and churn reconcile: net adds = the change in subscribers.
3. **Comparison.** Card vs e-receipt churn, gross adds and net adds for the provider x channels where the e-receipts miss under 5% of sign-ups and cancellations and the card data sees the same channel: **ChatGPT, Claude and Perplexity on Google Play**. Rates are used (per start-of-month subscriber), because the two panels differ in size.

Out of scope here: Grok (not in the card brand pull), Muse (about 90 card subscribers), Gemini (card descriptors can't separate Google Play from other Google One billing), and Apple (invisible on cards).
""")

code("""
import warnings, pandas as pd, numpy as np, matplotlib.pyplot as plt, matplotlib.dates as mdates
from matplotlib.ticker import PercentFormatter, FuncFormatter
from IPython.display import display
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message="This pattern is interpreted")
pd.set_option("display.width", 220); pd.set_option("display.max_colwidth", 70); pd.set_option("display.max_rows", 200)
import card_core_rules as CR, card_net_rules as N

raw = pd.read_parquet(CR.CACHE / "raw.parquet")
END = raw.dt.max()
cls = CR.classify(raw)
pay = cls[cls.keep & cls.provider.ne("muse")].rename(columns={"memid": "uid"}).copy()  # Muse: ~90 members, too few to read
pay["plan"] = pay.plan.astype(str)
pay["family"] = ""
for p in pay.provider.unique():
    m = pay.provider.eq(p)
    pay.loc[m, "family"] = CR.family(pay.loc[m, "descr"], p).values
rp, rc = N.gp_receipts()
REND = rp.dt.max()
NAMES = {"chatgpt": "ChatGPT", "claude": "Claude", "gemini": "Gemini", "perplexity": "Perplexity"}
CH = {"web": "web", "google_play": "Google Play"}
lab = lambda i: f"{NAMES[i[0]]} {CH[i[1]]}"
GP = ["chatgpt", "claude", "perplexity"]
print(f"card: {len(pay):,} plan payments, {pay.uid.nunique():,} members, data end {END.date()}")
print(f"e-receipts (Google Play): {len(rp):,} paid receipts, {len(rc):,} cancellations, data end {REND.date()}")
pay.groupby(["provider", "channel"]).agg(payments=("dt", "size"), members=("uid", "nunique"), first=("dt", "min"))
""")

md("""
## 1. Billing cycle by provider x channel x descriptor family (card)

- **p50 / p90 / p95 / p99:** percentiles of in-subscription gaps (monthly plans, 1 to 75 days).
- **pct_26_35:** share of those gaps 26 to 35 days apart (one normal monthly cycle).
- **pct_under_20:** gaps under 20 days (double charges, retries, upgrades mid-cycle).
- **pct_gaps_over_cap:** share of all monthly gaps longer than 75 days (stop and restart).

Families with fewer than 200 gaps are hidden.
""")

code("""
g = N.cycle_gaps(pay, ["provider", "channel", "plan"])
rg = N.cycle_gaps(rp, ["provider", "channel"])
FMT = {"p50": "{:.0f}", "p90": "{:.0f}", "p95": "{:.0f}", "p99": "{:.0f}", "gaps": "{:,}", "members": "{:,}",
       "pct_26_35": "{:.1%}", "pct_under_20": "{:.1%}", "pct_gaps_over_cap": "{:.1%}"}
fam = N.cycle_table(g, ["provider", "channel", "family"])
fam[fam.gaps >= 200].style.format(FMT)
""")

code("""
pc = N.cycle_table(g, ["provider", "channel"])
print("Pooled by provider x channel (the churn rule uses a fixed CUTOFF instead; see section 4)")
pc.style.format(FMT)
""")

code("""
pl = N.cycle_table(g, ["provider", "channel", "plan"])
print("By plan (200+ gaps)")
pl[pl.gaps >= 200].style.format(FMT)
""")

code("""
keys = list(pc.index)
fig, axes = plt.subplots(2, 4, figsize=(16, 6), sharex=True)
for ax, k in zip(axes.flat, keys):
    s = g[(g.provider == k[0]) & (g.channel == k[1]) & g.cadence.eq("M") & g.gap.between(1, 120)].gap
    h = s.value_counts(normalize=True).sort_index()
    ax.bar(h.index, h.values, width=1, color="#2a78d6")
    for q, c in [("p95", "#eda100"), ("p99", "#eb6834")]:
        ax.axvline(pc.loc[k, q], color=c, ls="--", lw=1.2, label=f"{q} = {pc.loc[k, q]:.0f}d")
    ax.set_yscale("log"); ax.set_title(lab(k), fontsize=10, loc="left"); ax.legend(frameon=False, fontsize=8)
    ax.grid(alpha=0.3); ax.spines[["top", "right"]].set_visible(False)
for ax in axes.flat[len(keys):]: ax.axis("off")
fig.suptitle("Card: days between a member's consecutive payments (same provider x channel x plan), share of gaps, log scale", fontsize=11)
plt.tight_layout(); plt.show()
""")
note("cycles")

md("""
## 2. Is a member's billing cycle consistent?

For members with 3+ consecutive in-subscription gaps:
- **pct_steady:** every gap within 3 days of the member's own median gap.
- **median_member_range_days:** the member's longest gap minus their shortest.
- **late_then_normal:** of gaps above p95, the share followed by a normal gap (<= p95). This is the "t+30, t+40, t+30" pattern.
- **false_churn_p99:** share of in-subscription gaps above p99. The p99 rule reads each as a churn followed by a re-add.
""")

code("""
reg = N.regularity(g, ["provider", "channel"], pc.p95, pc.p99)
reg.style.format({"members_3plus_gaps": "{:,}", "pct_steady": "{:.1%}", "median_member_range_days": "{:.0f}",
                  "late_then_normal": "{:.1%}", "false_churn_p99": "{:.2%}"})
""")

md("""
### 2a. Member-level steadiness, and p99 for members with a steady history

Hypothesis: p99 is high because it includes members who churned and re-subscribed. Three checks:
1. **Per member** (3+ gaps on one plan): share whose gaps are all 26-35 days, all within 3 days of their own median, the range of their gaps, and the share who ever had a gap above 35 days.
2. **p99 restricted to steady histories:** only gaps preceded by at least r consecutive normal (26-35 day) gaps for the same plan. r = 1 is "paid the prior month".
3. **Anchor test:** of 40-75 day gaps, the share within 2 days of twice the member's own cycle. A re-subscription restarts billing on a random day; a missing charge keeps the billing day.
""")

code("""
us = N.user_steadiness(g, ["provider", "channel"])
display(us.style.format({"members": "{:,}", "pct_all_26_35": "{:.1%}", "pct_within_3d": "{:.1%}", "median_range": "{:.0f}",
                         "p90_range": "{:.0f}", "pct_any_over_35": "{:.1%}"}))
stk = N.streak_table(g, ["provider", "channel"])
stk.style.format({c: ("{:,}" if c[1] == "gaps" else "{:.1%}" if c[1] == "pct_over_35" else "{:.0f}") for c in stk.columns})
""")

code("""
anc = pd.DataFrame({"card": N.anchor_share(g, ["provider", "channel"]),
                    "e-receipt": N.anchor_share(rg.assign(plan="all"), ["provider", "channel"])})
anc.set_axis([lab(k) for k in anc.index]).style.format("{:.0%}", na_rep="")
""")
note("steady")

md("""
**Where do the ~60-day gaps come from?** A 56 to 66 day gap means one monthly charge is missing between two normal ones. The chart shows, by the month of the missing charge, the share of continuing payments whose next payment skips a month: card vs Google Play e-receipts. If the skip shows on cards but not in receipts, the charge happened but the card panel didn't record it.
""")

code("""
def skipped(gg, by):
    m = gg[gg.cadence.eq("M") & gg.gap.between(1, 120)]
    miss = (m.dt + pd.Timedelta(days=31)).dt.to_period("M")
    num = m[m.gap.between(56, 66)].groupby(by).apply(lambda d: miss[d.index].value_counts())
    den = m.groupby(by).apply(lambda d: d.dt.dt.to_period("M").value_counts())
    return (num / den).unstack(by) if isinstance(num, pd.Series) else (num / den).T

sk_card = skipped(g, ["provider", "channel"])
sk_rec = skipped(rg, ["provider", "channel"])
fig, ax = plt.subplots(figsize=(11, 4))
for k, c in [(("chatgpt", "google_play"), "#2a78d6"), (("claude", "google_play"), "#eb6834"), (("gemini", "web"), "#1baf7a"), (("chatgpt", "web"), "#8b5cc8")]:
    s = sk_card[k].loc["2025-01":"2026-09"]
    ax.plot(s.index.to_timestamp(), s.values, color=c, lw=2, label=f"card: {lab(k)}")
for k, c in [(("chatgpt", "google_play"), "#2a78d6"), (("claude", "google_play"), "#eb6834")]:
    s = sk_rec[k].loc["2025-01":"2026-09"]
    ax.plot(s.index.to_timestamp(), s.values, color=c, lw=1.5, ls="--", label=f"e-receipt: {lab(k)}")
ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0)); ax.grid(alpha=0.3); ax.spines[["top", "right"]].set_visible(False)
ax.set_title("Share of continuing payments that skip one month, by month of the missing charge", fontsize=11, loc="left")
ax.legend(frameon=False, fontsize=8, ncol=2); plt.show()
print("card, share skipping a month:"); display(sk_card.loc["2026-03":"2026-09"].pipe(lambda d: d.set_axis([lab(k) for k in d.columns], axis=1)).style.format("{:.1%}"))
""")
note("regularity")

md("""
## 3. Billing cycle on Google Play e-receipts

Google Play sends a priced receipt for each renewal, so the same percentiles can be read from the e-receipts.
""")

code("""
rt = N.cycle_table(rg, ["provider", "channel"])
cmp = pd.concat({"card": pc.loc[[(p, "google_play") for p in GP], ["p50", "p95", "p99", "pct_26_35", "gaps"]],
                 "e-receipt": rt[["p50", "p95", "p99", "pct_26_35", "gaps"]]}, axis=1)
cmp.style.format({c: FMT[c[1]] for c in cmp.columns})
""")
note("receipt_cycles")

md("""
## 4. Card gross adds, churn and net adds by provider x channel

Threshold: a fixed **45-day cutoff** for every provider x channel (`CUTOFF`), annual plans 400 days. Churn is shown only for complete months: a month is complete when every subscription that could churn in it has had 45 days plus 10 days of card posting lag to show a further payment. Later months are censored (hollow markers mark the last complete month).

At **plan level** (the rule as specified), a switch between plans in the same provider x channel is a churn of the old plan plus an add of the new one. The charts use **provider x channel level** (any plan), which matches the e-receipt flows. The table after the charts shows the difference.
""")

code("""
CUTOFF = 45  # days between payments: continuing if the next payment comes within CUTOFF, otherwise churn (p99 was ~60)
THR, CYC = pd.Series(float(CUTOFF), index=pc.index), pc.p50
sp = N.series(pay, ["provider", "channel"], THR, CYC, END, lag=N.CARD_LAG)
sp_plan = N.series(pay, ["provider", "channel", "plan"], THR, CYC, END, lag=N.CARD_LAG)
cm = N.monthly(sp, ["provider", "channel"], start="2024-01", end=END)
cm_plan = N.monthly(sp_plan, ["provider", "channel", "plan"], start="2024-01", end=END)
DONE = {k: N.churn_complete_through(END, THR[k], CYC[k], N.CARD_LAG) for k in THR.index}
cm["complete"] = [m <= DONE[(p, c)] for m, p, c in zip(cm.month, cm.provider, cm.channel)]
for c in ["churn", "churn_rate", "net_adds"]:
    cm.loc[~cm.complete, c] = np.nan
print("last complete churn month:", {lab(k): str(v) for k, v in DONE.items()})

fig, axes = plt.subplots(4, 2, figsize=(15, 13))
for ax, k in zip(axes.flat, keys):
    d = cm[(cm.provider == k[0]) & (cm.channel == k[1])].set_index("month")
    x = d.index.to_timestamp()
    ax.bar(x, d.gross_adds, width=20, color="#2a78d6", alpha=0.35, label="gross adds")
    ax.bar(x, -d.churn, width=20, color="#eb6834", alpha=0.35, label="churn")
    ax.plot(x, d.net_adds, color="#3d3d3a", lw=2, marker="o", ms=3, label="net adds")
    ax.axhline(0, color="#999", lw=0.8); ax.set_title(lab(k), fontsize=10, loc="left")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}")); ax.grid(alpha=0.3); ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
axes.flat[-1].axis("off")
fig.suptitle("Card (Omega 2022 panel): monthly gross adds, churn (45-day lapse) and net adds, members", fontsize=11)
plt.tight_layout(); plt.show()
""")

code("""
# plan level vs provider x channel level: plan-level churn includes plan switches within the provider x channel
done = cm[cm.complete & (cm.month >= pd.Period("2025-01"))]
pcl = cm_plan.merge(done[["month", "provider", "channel"]], on=["month", "provider", "channel"])
t = pd.DataFrame({"churn, provider x channel": done.groupby(["provider", "channel"]).churn.sum(),
                  "churn, plan level": pcl.groupby(["provider", "channel"]).churn.sum(),
                  "gross adds, provider x channel": done.groupby(["provider", "channel"]).gross_adds.sum(),
                  "gross adds, plan level": pcl.groupby(["provider", "channel"]).gross_adds.sum()})
t["plan switches (approx.)"] = t["churn, plan level"] - t["churn, provider x channel"]
t["switches % of plan churn"] = t["plan switches (approx.)"] / t["churn, plan level"]
print("2025-01 to each provider x channel's last complete month")
t.set_axis([lab(k) for k in t.index]).style.format({c: "{:,.0f}" for c in t.columns} | {"switches % of plan churn": "{:.1%}"})
""")

code("""
# monthly churn rate by plan (complete months, plans with 1,000+ subscribers at the start of the month)
cp = cm_plan.merge(cm[["month", "provider", "channel", "complete"]], on=["month", "provider", "channel"])
cp = cp[cp.complete & (cp.subs_start >= 1000) & (cp.month >= pd.Period("2025-01"))]
cp.assign(line=cp.provider.map(NAMES) + " " + cp.channel.map(CH) + " " + cp.plan).pivot_table(
    index="month", columns="line", values="churn_rate").style.format("{:.1%}")
""")
note("card_flows")

md("""
## 5. Card vs e-receipt on Google Play: ChatGPT, Claude, Perplexity

Three churn measures, each per start-of-month subscriber in its own panel:
- **Card (lapse):** no further Google Play payment for the provider within 45 days; dated at the expected next charge. Complete months only.
- **E-receipt (cancellation email):** Google Play cancellation emails (45-day de-duplication), counted only for mailboxes whose subscription was seen in the receipts (the cancellation falls inside a receipt spell: after its first paid receipt and before last receipt + 45 days). Dated at the email.
- **E-receipt (lapse):** the card method applied to Google Play renewal receipts (same 45-day cutoff). This separates a difference between panels from a difference between methods.

E-receipt subscribers = mailboxes in a receipt spell at the start of the month (same spell rule as the cards). Gross adds = spell starts. Comparison from 2025-01 (receipts start 2024-07, so earlier spells are left-censored).
""")

code("""
RTHR, RCYC = pd.Series(float(CUTOFF), index=rt.index), rt.p50
csp = sp[sp.provider.isin(GP) & sp.channel.eq("google_play")]
card = cm[cm.provider.isin(GP) & cm.channel.eq("google_play") & (cm.month >= pd.Period("2025-01"))].drop(columns="channel")
rsp = N.series(rp, ["provider", "channel"], RTHR, RCYC, REND, lag=N.RECEIPT_LAG)
rec = N.monthly(rsp, ["provider"], start="2025-01", end=REND)
RDONE = {p: N.churn_complete_through(REND, RTHR[(p, "google_play")], RCYC[(p, "google_play")], N.RECEIPT_LAG) for p in GP}
rec.loc[[m > RDONE[p] for m, p in zip(rec.month, rec.provider)], ["churn", "churn_rate"]] = np.nan
inside = N.cancels_in_spells(rc, rsp, ["provider", "channel"])
cn = inside.groupby(["provider", inside.dt.dt.to_period("M")]).size().rename("cancels")
rec = rec.merge(cn.rename_axis(["provider", "month"]).reset_index(), on=["provider", "month"], how="left").fillna({"cancels": 0})
LAST_FULL = (REND + pd.Timedelta(days=1)).to_period("M") - 1
rec = rec[rec.month <= LAST_FULL]
rec["cancel_rate"] = rec.cancels / rec.subs_start
rec["add_rate"] = rec.gross_adds / rec.subs_start
rec["net_rate_cancel"] = (rec.gross_adds - rec.cancels) / rec.subs_start
card["add_rate"] = card.gross_adds / card.subs_start
card["net_rate"] = card.net_adds / card.subs_start
cov = rc[rc.dt >= "2025-01-01"].merge(inside[["uid", "provider", "dt"]].assign(seen=True), on=["uid", "provider", "dt"], how="left")
print("share of e-receipt cancellations (2025+) inside a receipt spell, i.e. kept:")
print(cov.groupby("provider").seen.apply(lambda s: s.notna().mean()).map("{:.1%}".format).to_string())
""")

code("""
C3 = {"card": "#2a78d6", "cancel": "#eb6834", "rlapse": "#1baf7a"}
fig, axes = plt.subplots(len(GP), 3, figsize=(17, 4 * len(GP)))
for row, p in zip(axes, GP):
    c = card[card.provider == p].set_index("month"); r = rec[rec.provider == p].set_index("month")
    xc, xr = c.index.to_timestamp(), r.index.to_timestamp()
    ax = row[0]
    ax.plot(xc, c.churn_rate, color=C3["card"], lw=2.2, marker="o", ms=3, label="card (lapse)")
    ax.plot(xr, r.cancel_rate, color=C3["cancel"], lw=2.2, marker="o", ms=3, label="e-receipt (cancellation email)")
    ax.plot(xr, r.churn_rate, color=C3["rlapse"], lw=1.5, ls="--", label="e-receipt (lapse)")
    ax.set_title(f"{NAMES[p]} Google Play: monthly churn, % of start-of-month subscribers", fontsize=10, loc="left")
    ax = row[1]
    ax.plot(xc, c.add_rate, color=C3["card"], lw=2.2, marker="o", ms=3, label="card")
    ax.plot(xr, r.add_rate, color=C3["cancel"], lw=2.2, marker="o", ms=3, label="e-receipt")
    ax.set_title(f"{NAMES[p]} Google Play: gross adds, % of start-of-month subscribers", fontsize=10, loc="left")
    ax = row[2]
    ax.plot(xc, c.net_rate, color=C3["card"], lw=2.2, marker="o", ms=3, label="card (adds - lapse churn)")
    ax.plot(xr, r.net_rate_cancel, color=C3["cancel"], lw=2.2, marker="o", ms=3, label="e-receipt (adds - cancellations)")
    ax.axhline(0, color="#999", lw=0.8)
    ax.set_title(f"{NAMES[p]} Google Play: net adds, % of start-of-month subscribers", fontsize=10, loc="left")
    for ax in row:
        ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0)); ax.grid(alpha=0.3); ax.spines[["top", "right"]].set_visible(False)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b-%y")); ax.legend(frameon=False, fontsize=8, loc="upper left")
plt.tight_layout(); plt.show()
""")

code("""
# Jul-Aug 2026: Claude and Perplexity Google Play (and Gemini) card charges skip a month for 10-21% of subscribers (section 2),
# not seen in the receipts; a 45-day cutoff reads each as churn. ChatGPT's equivalent (the truncated "GOOGLE *CHATGP"
# descriptor, Nov 2025 and Jul-Aug 2026) is fixed in the pull, so these months are clean for ChatGPT.
GAP_MONTHS = pd.PeriodIndex(["2026-07", "2026-08"], freq="M")

def stats(p, excl=None):
    j = card[card.provider == p].set_index("month")[["churn_rate", "add_rate", "net_rate", "subs_start"]].join(
        rec[rec.provider == p].set_index("month")[["cancel_rate", "churn_rate", "add_rate", "net_rate_cancel", "subs_start"]],
        rsuffix="_r", how="inner").dropna(subset=["churn_rate", "cancel_rate"])
    if excl is not None: j = j[~j.index.isin(excl)]
    ratio = j.churn_rate / j.cancel_rate
    ratio_l = j.churn_rate / j.churn_rate_r
    return pd.Series({
        "months": len(j), "card subs (median)": j.subs_start.median(), "receipt subs (median)": j.subs_start_r.median(),
        "card churn rate (mean)": j.churn_rate.mean(), "receipt cancel rate (mean)": j.cancel_rate.mean(),
        "receipt lapse rate (mean)": j.churn_rate_r.mean(),
        "corr churn: card vs cancel": j.churn_rate.corr(j.cancel_rate),
        "corr churn MoM change: card vs cancel": j.churn_rate.diff().corr(j.cancel_rate.diff()),
        "ratio card / cancel (mean)": ratio.mean(), "ratio card / cancel (CV)": ratio.std() / ratio.mean(),
        "corr churn: card vs receipt lapse": j.churn_rate.corr(j.churn_rate_r),
        "ratio card / receipt lapse (mean)": ratio_l.mean(), "ratio card / receipt lapse (CV)": ratio_l.std() / ratio_l.mean(),
        "corr gross add rate": j.add_rate.corr(j.add_rate_r), "corr net add rate": j.net_rate.corr(j.net_rate_cancel)})

ST = pd.DataFrame({**{NAMES[p]: stats(p) for p in GP}, **{f"{NAMES[p]} ex gap months": stats(p, GAP_MONTHS) for p in GP}})
pct = [i for i in ST.index if "rate (mean)" in i]
ST.style.format(lambda v: f"{v:,.2f}").format(lambda v: f"{v:.1%}", subset=pd.IndexSlice[pct, :]).format(
    lambda v: f"{v:,.0f}", subset=pd.IndexSlice[["months", "card subs (median)", "receipt subs (median)"], :])
""")

code("""
# monthly detail, for reading the charts
D = card[["provider", "month", "subs_start", "churn_rate"]].merge(
    rec[["provider", "month", "subs_start", "cancel_rate", "churn_rate"]], on=["provider", "month"], suffixes=("_card", "_rec"))
D["ratio card / cancel"] = D.churn_rate_card / D.cancel_rate
D.assign(provider=D.provider.map(NAMES)).set_index(["provider", "month"]).style.format(
    {"subs_start_card": "{:,.0f}", "subs_start_rec": "{:,.0f}", "churn_rate_card": "{:.1%}", "cancel_rate": "{:.1%}",
     "churn_rate_rec": "{:.1%}", "ratio card / cancel": "{:.2f}"}, na_rep="")
""")
note("comparison")

md("""
## 6. How much earlier do cancellation emails arrive?

For e-receipt cancellations inside a spell:
- **days before the next charge:** expected next charge (last paid receipt + median cycle) minus the cancellation email date. Google Play sends the email when the user cancels, which can be any time in the paid month.
- **days before the card rule knows:** last paid receipt + 45-day cutoff + 10 days posting lag, minus the email date. This is how much earlier the e-receipts flag the churn than the card lapse rule can confirm it.
""")

code("""
x = inside[inside.dt >= "2025-01-01"].copy()
x["thr_card"] = [THR[(p, "google_play")] for p in x.provider]
x["before_due"] = (x.next_due - x.dt).dt.days
x["before_card"] = (x["last"] + pd.to_timedelta(x.thr_card + N.CARD_LAG, unit="D") - x.dt).dt.days
q = x.groupby("provider")[["before_due", "before_card"]].quantile([0.1, 0.25, 0.5, 0.75, 0.9]).unstack()
q.index = q.index.map(NAMES)
q.style.format("{:.0f}")
""")
note("timing")

md("""
## 7. Nowcasting card churn from e-receipt cancellations: backtest

Card churn for a month is complete only about 24 days after it ends (45-day cutoff - 31-day cycle + 10 days lag), and the gap months are unusable. E-receipt cancellations are complete at month end. The test: at the end of month m, predict the card churn rate for m as **e-receipt cancel rate (m) x mean card/receipt ratio** over the 6 latest months whose card churn was complete at that point (m-7 to m-2). The baseline is the naive forecast: the last complete card churn rate (m-2). Scored on all months and with the card gap months excluded (neither used in the ratio nor scored).
""")

code("""
def backtest(p, win=6, gap=2, excl=None):
    j = card[card.provider == p].set_index("month")[["churn_rate"]].join(
        rec[rec.provider == p].set_index("month")[["cancel_rate"]], how="outer")
    if excl is not None: j.loc[j.index.isin(excl), "churn_rate"] = np.nan  # unusable card months: not used in ratios or scored
    out = []
    for i, m in enumerate(j.index):
        hist = j.loc[:m - gap].dropna().tail(win)
        if len(hist) < 3: continue
        ratio = (hist.churn_rate / hist.cancel_rate).mean()
        out.append({"month": m, "actual": j.churn_rate.get(m), "nowcast": j.cancel_rate.get(m) * ratio,
                    "naive": hist.churn_rate.iloc[-1], "ratio_used": ratio})
    return pd.DataFrame(out).set_index("month")

BT = {p: backtest(p) for p in GP}
BTX = {p: backtest(p, excl=GAP_MONTHS) for p in GP}
rows = {}
for name, b in [*[(NAMES[p], BT[p]) for p in GP], *[(f"{NAMES[p]} ex gap months", BTX[p]) for p in GP]]:
    e = b.dropna(subset=["actual"])
    rows[name] = {"months tested": len(e), "MAE nowcast (pp)": (e.nowcast - e.actual).abs().mean() * 100,
                      "MAE naive (pp)": (e.naive - e.actual).abs().mean() * 100,
                      "mean error nowcast (pp)": (e.nowcast - e.actual).mean() * 100,
                      "corr nowcast vs actual": e.nowcast.corr(e.actual), "corr naive vs actual": e.naive.corr(e.actual)}
display(pd.DataFrame(rows).style.format("{:.2f}").format("{:.0f}", subset=pd.IndexSlice[["months tested"], :]))

fig, axes = plt.subplots(1, len(GP), figsize=(17, 3.8))
for ax, p in zip(axes, GP):
    b = BTX[p]; x = b.index.to_timestamp()  # gap months excluded
    ax.plot(x, b.actual, color=C3["card"], lw=2.2, marker="o", ms=3, label="card churn rate (actual)")
    ax.plot(x, b.nowcast, color=C3["cancel"], lw=2, marker="o", ms=3, label="nowcast from e-receipts")
    ax.plot(x, b.naive, color="#999", lw=1.2, ls="--", label="naive (last complete card month)")
    ax.set_title(f"{NAMES[p]} Google Play (card gap months excluded)", fontsize=10, loc="left"); ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b-%y")); ax.grid(alpha=0.3); ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
plt.tight_layout(); plt.show()
print("nowcasts for months whose card churn is not complete yet:")
pd.concat({NAMES[p]: b[b.index > DONE[(p, "google_play")]][["nowcast", "ratio_used"]] for p, b in BTX.items()}).style.format({"nowcast": "{:.1%}", "ratio_used": "{:.2f}"})
""")
note("backtest")

code("""
# exports for the app / later work
N.CACHE.mkdir(parents=True, exist_ok=True)
pd.concat([t.reset_index().assign(table=n) for n, t in {"card_family": fam, "card_provider_channel": pc, "card_plan": pl, "receipt_gp": rt}.items()]).to_parquet(N.CACHE / "cycles.parquet", index=False)
cm.to_parquet(N.CACHE / "card_monthly.parquet", index=False)
cm_plan.to_parquet(N.CACHE / "card_monthly_plan.parquet", index=False)
D.to_parquet(N.CACHE / "gp_comparison_monthly.parquet", index=False)
print("saved to", N.CACHE)
""")
note("summary")

md("""
## 8. ChatGPT Google Play: monthly churn counts, card vs e-receipt

Top: the number of churns each month from each source, on one axis (the card and receipt panels have similar numbers of ChatGPT Google Play subscribers: about 2-24k on cards, 3-14k on receipts). Card churn uses the 45-day lapse rule and is shown for complete months only; e-receipt cancellations are counted to the last full month. Bottom: the same as a share of start-of-month subscribers, with the card / cancellation ratio. Grey bands are Jul-Aug 2026, the card gap months for the other Google Play providers (ChatGPT is clean since the `CHATGP` descriptor fix).
""")

code("""
c = card[card.provider == "chatgpt"].set_index("month")
r = rec[rec.provider == "chatgpt"].set_index("month")
months = c.index.union(r.index)
x = months.to_timestamp()
fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
for m in GAP_MONTHS:
    for ax in (a1, a2):
        ax.axvspan(m.to_timestamp(), (m + 1).to_timestamp(), color="#999", alpha=0.15, lw=0)
a1.plot(x, c.churn.reindex(months), color=C3["card"], lw=2.4, marker="o", ms=4, label="card: 45-day lapse")
a1.plot(x, r.cancels.reindex(months), color=C3["cancel"], lw=2.4, marker="o", ms=4, label="e-receipt: cancellation emails")
a1.plot(x, r.churn.reindex(months), color=C3["rlapse"], lw=1.5, ls="--", marker="o", ms=3, label="e-receipt: 45-day lapse")
a1.set_title("ChatGPT Google Play: churns per month", fontsize=11, loc="left")
a1.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
a2.plot(x, c.churn_rate.reindex(months), color=C3["card"], lw=2.4, marker="o", ms=4, label="card: 45-day lapse")
a2.plot(x, r.cancel_rate.reindex(months), color=C3["cancel"], lw=2.4, marker="o", ms=4, label="e-receipt: cancellation emails")
a2.plot(x, r.churn_rate.reindex(months), color=C3["rlapse"], lw=1.5, ls="--", marker="o", ms=3, label="e-receipt: 45-day lapse")
a2.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
a2.set_title("Churn, % of start-of-month subscribers (right axis: card / cancellation ratio)", fontsize=11, loc="left")
a3 = a2.twinx()
a3.plot(x, (c.churn_rate / r.cancel_rate).reindex(months), color="#3d3d3a", lw=1, ls=":", marker="s", ms=3, label="card / cancellation ratio")
a3.set_ylabel("ratio", fontsize=9); a3.spines[["top"]].set_visible(False)
for ax in (a1, a2):
    ax.grid(alpha=0.3); ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
a3.legend(frameon=False, fontsize=9, loc="upper right")
a2.xaxis.set_major_formatter(mdates.DateFormatter("%b-%y"))
plt.tight_layout(); plt.show()

T = pd.DataFrame({"card subs (start)": c.subs_start, "card churn": c.churn, "receipt subs (start)": r.subs_start,
                  "receipt cancellations": r.cancels, "receipt lapse churn": r.churn,
                  "card churn rate": c.churn_rate, "receipt cancel rate": r.cancel_rate}).reindex(months)
T["card / cancel ratio"] = T["card churn rate"] / T["receipt cancel rate"]
T["card gap month"] = T.index.isin(GAP_MONTHS)
T.style.format({**{k: "{:,.0f}" for k in ["card subs (start)", "card churn", "receipt subs (start)", "receipt cancellations", "receipt lapse churn"]},
                "card churn rate": "{:.1%}", "receipt cancel rate": "{:.1%}", "card / cancel ratio": "{:.2f}"}, na_rep="")
""")
note("gpt_counts")

nb["cells"] = C
nb["metadata"]["kernelspec"] = {"name": "exploration", "display_name": "exploration", "language": "python"}
nbf.write(nb, "card_net_adds.ipynb")
print("wrote card_net_adds.ipynb")
