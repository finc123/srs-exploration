"""Builds card_gross_adds.ipynb (run: python _make_card_gross_adds.py, then execute with nbconvert on the exploration kernel)."""
import nbformat as nbf

from _card_gross_adds_text import FINDINGS

nb = nbf.v4.new_notebook()
C = []
md = lambda s: C.append(nbf.v4.new_markdown_cell(s.strip()))
code = lambda s: C.append(nbf.v4.new_code_cell(s.strip()))
note = lambda k: md(FINDINGS[k]) if FINDINGS.get(k) else None

md("""
# AI subscription payments and gross adds on card data (US, Omega 2022 panel)

Plan: `../plans/23rd_october_2026.txt`. Engine: `card_core_rules.py`. Cache: `../.cache/card_core/` (delete `raw.parquet` to re-pull; about 15 minutes on `ANALYST_XL`).

**Source.** `EARNEST.COMMON.TXNS_CORE_V`, `BRAND_ID IN (29847 ANTHROPIC, 27440 OPENAI, 32111 GOOGLE ONE, 29069 PERPLEXITY, 11021 FACEBOOK)`, 2022 consistent-shopper panel (`WEIGHT_AGG_CS2022 IS NOT NULL`), from 2023-01-01 (Google One from 2024-01-01 and above $3.50; Facebook from 2026-06-01).

**Brand gaps, patched by descriptor.** Several subscription merchants have no main brand in Omega's `MID_MATCH_V1_0`, so `TXNS_CORE` never picks them up. The notebook adds the panel's rows for these unbranded merchants from the Omega share, using `TXNS_CORE`'s row logic (same panel join, affected accounts excluded). Longer term, these merchants need mapping to the brands.
- **ChatGPT subscriptions are not under brand 27440.** Neither `OPENAI *CHATGPT SUBSCR ...` nor Play's `GOOGLE *CHATGPT` is branded, so they come from the patch: about 96% of ChatGPT rows. Brand 27440 itself holds `OPENAI OPENAI.COM`-style rows, mostly API credits.
- **Muse direct web (`METAPAY META.COM`) and Play (`GOOGLE MUSE FROM META`) are not under FACEBOOK.** Brand 11021 is mostly Facebook ad spend (`FACEBK *____`).
- **Older Claude web descriptors and Google Play:** `CLAUDEAI SUBSCRIPTION ...` (no dot; 2024 to early 2025, about 40% of Claude payments then) and `GOOGLE *CLAUDE BY ANTH...` are unbranded, as is most of Perplexity's Google Play (`GOOGLE *PERPLEXITY ...`).
- **Truncated ChatGPT descriptor:** some issuers cut the descriptor to 15 characters and drop the final T (`GOOGLE *CHATGP MOUNTAIN VIE CA`, `PAYPAL *OPENAI *CHATGP`). The Google Play form grows from Oct 2025 and reaches about 3.8k rows a month in Aug 2026. It is matched since 2026-10-26; before that, those subscribers looked like churn followed by a re-add.
- The patch takes every unbranded merchant matching `CHATGP` (covers `CHATGPT` and the truncated form), `OPENAI`, `CLAUDEAI` / `CLAUDE.AI` / `CLAUDE BY` / `ANTHROPIC`, `PERPLEX`, `METAPAY META.COM`, `MUSE FROM META` or Google One SKU codes. The classification rules then reject look-alikes and API rows, exactly as for branded rows.
- **Descriptor changes:** Perplexity's brandless Stripe descriptor (`PRO WWW.PERPLEX...`, 2026-06-08 to 10-04) and Google One's SKU-code descriptors (`GOOGLE G1SK003M`, `G1AI101M`, from 2026-09-15) are unbranded. Without them, Perplexity loses about 90% of its payments in Jun-Sep 2026, and Gemini about half from mid-September.

Grok and Cursor are not in the brand list and are out of scope.
""")

code("""
import sys, warnings, pandas as pd, numpy as np, matplotlib.pyplot as plt, matplotlib.dates as mdates
from matplotlib.ticker import PercentFormatter, FuncFormatter
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message="This pattern is interpreted")
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)
pd.set_option("display.width", 220); pd.set_option("display.max_colwidth", 70); pd.set_option("display.max_rows", 200)
import card_core_rules as R

if not (R.CACHE / "raw.parquet").exists():
    R.pull()
raw = pd.read_parquet(R.CACHE / "raw.parquet")
panel = pd.read_parquet(R.CACHE / "panel.parquet").iloc[0]
N, W = panel.members, panel.weight_sum
END = raw.dt.max()
NAMES = {"chatgpt": "ChatGPT", "claude": "Claude", "gemini": "Gemini", "perplexity": "Perplexity", "muse": "Muse"}
COLORS = {"chatgpt": "#2a78d6", "claude": "#eb6834", "gemini": "#1baf7a", "perplexity": "#eda100", "muse": "#e87ba4"}
ORDER = list(NAMES)
PLANS = {"plus_M": "Plus", "go_M": "Go", "pro100_M": "Pro $100", "pro200_M": "Pro $200", "pro500_M": "Pro $500",
         "pro_M": "Pro (monthly)", "pro_A": "Pro (annual)", "max5_M": "Max 5x", "max20_M": "Max 20x",
         "ai_pro_M": "AI Pro (monthly)", "ai_pro_A": "AI Pro (annual)", "ai_plus_M": "AI Plus (monthly)",
         "ai_plus_A": "AI Plus (annual)", "ai_plus_2tb_M": "2TB incl. AI Plus (monthly)",
         "ai_plus_2tb_A": "2TB incl. AI Plus (annual)", "ultra_M": "Ultra", "ultra_5x_M": "Ultra 5x",
         "pro_disc_M": "Pro (discounted)", "max_M": "Max (monthly)", "max_A": "Max (annual)",
         "power_M": "Power"}
print(f"panel members {N:,.0f}, weight sum {W:,.0f}, data end {END.date()}")
(raw.assign(provider=raw.provider.map(NAMES))
    .groupby(["provider", "source"]).agg(rows=("transid", "size"), members=("memid", "nunique"),
                                         first=("dt", "min"), last=("dt", "max")))
""")

md("""
## 1. Is the 2022 consistent-shopper panel fixed?

`CARDLINK_PANEL_V1_0` holds one row per member for `aggregate_consistent_shopper_2022_v2`. If every member has the same start date and one static weight, membership is fixed: nobody joins after the panel is drawn, so gross adds can be read as a share of a constant base.
""")

code("""
import snowflake.connector as sc
cur = sc.connect(connection_name="default", warehouse="ANALYST_L").cursor()
cur.execute(f\"\"\"SELECT COUNT(*) AS rows_, COUNT(DISTINCT cardlinkid) AS members, COUNT(DISTINCT panel_start_date) AS start_dates,
        MIN(panel_start_date) AS first_start, MAX(panel_start_date) AS last_start,
        COUNT(*) - COUNT(DISTINCT cardlinkid, weight) AS members_with_2plus_weights,
        COUNT_IF(EXISTS (SELECT 1 FROM {R.OMEGA}_STATIC.AFFECTED_ACCOUNTS_092026 a WHERE a.cardlinkid = p.cardlinkid)) AS affected_excluded
    FROM {R.OMEGA}.CARDLINK_PANEL_V1_0 p WHERE panel = '{R.PANEL}'\"\"\")
pd.DataFrame(cur.fetchall(), columns=[d[0].lower() for d in cur.description]).T.rename(columns={0: "value"})
""")

md("""
A fixed list is not the same as a fixed **active** base: members can stop transacting. As a check, the chart below uses activity spells built earlier on the same panel (`../.cache/omega_spells.parquet`, a member is active while they have a transaction in the trailing 35 days).
""")

code("""
sp = pd.read_parquet(R.CACHE.parent / "omega_spells.parquet")
sp[["spell_start", "spell_end"]] = sp[["spell_start", "spell_end"]].apply(pd.to_datetime)
ids = pd.read_parquet(R.CACHE.parent / "omega_panel.parquet", columns=["cardlinkid"]).cardlinkid  # panel list as of 2026-10-19
sp = sp[sp.uid.isin(ids)]
NP = ids.nunique()
months = pd.date_range("2023-01-31", sp.spell_end.max(), freq="ME")
act = pd.Series([sp.uid[(sp.spell_start <= m) & (sp.spell_end + pd.Timedelta(days=35) >= m)].nunique() for m in months],
                index=months)
ax = (act / NP).plot(figsize=(9, 3), color="#2a78d6", lw=2, title="Panel members active (transaction in trailing 35 days), share of fixed panel")
ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=1)); ax.set_ylim(0.9, 1.0); ax.grid(alpha=0.3); plt.show()
print(f"active at {months[-1].date()}: {act.iloc[-1]:,.0f} of {NP:,.0f} ({act.iloc[-1] / NP:.1%}); "
      f"lowest month-end since 2023: {(act / NP).min():.1%}")
""")
note("panel")

md("""
## 2. Billing descriptions x pricing, by provider

For each provider, descriptors are grouped into families. For each family (debits only):
- **pct_on_price**: share of payments on a US consumer list price valid that day (from `../plans/{provider}_prices.csv`, list price to +12% sales tax).
- **pct_recurring**: share of payments where the same member pays again in the same family 26-35 days before or after (a monthly billing rhythm).
- **pct_both**: on price and recurring.

A subscription family should score high on both. A family that is off-price and on random dates (for example API credits or ad spend) is excluded, so it cannot create false gross adds.
""")

code("""
RES = {}
def show(p):
    t, x = R.research(raw, p)
    RES[p] = x
    fmt = {c: "{:.0%}" for c in ["pct_on_price", "pct_recurring", "pct_both"]} | {"rows": "{:,}", "members": "{:,}", "median_amt": "${:,.2f}"}
    display(t.style.format(fmt))
    top = x.groupby("family").size().nlargest(4).index
    fig, axes = plt.subplots(1, len(top), figsize=(4 * len(top), 2.6), squeeze=False)
    for ax, f in zip(axes[0], top):
        a = x.loc[x.family == f, "amount"]
        ax.hist(a.clip(upper=a.quantile(0.99)), bins=60, color=COLORS[p])
        ax.set_title(f, fontsize=9); ax.tick_params(labelsize=8); ax.grid(alpha=0.3)
    fig.suptitle(f"{NAMES[p]}: amount distribution by descriptor family (clipped at p99)", fontsize=10); plt.tight_layout(); plt.show()
""")

for p, title in [("claude", "Claude (brand 29847 ANTHROPIC)"), ("chatgpt", "ChatGPT (brand 27440 OPENAI + unbranded CHATGPT)"),
                 ("gemini", "Gemini (brand 32111 GOOGLE ONE)"), ("perplexity", "Perplexity (brand 29069)"),
                 ("muse", "Muse (brand 11021 FACEBOOK + unbranded METAPAY)")]:
    md(f"### {title}")
    code(f'show("{p}")')
    if p == "claude":
        md("""
**Hypothesis: bare `ANTHROPIC` is not a plan.** Compare the day-of-month regularity and amounts of bare `ANTHROPIC` rows with the Claude subscription descriptors for the same members.
""")
        code("""
x = RES["claude"]
sub = x.family.isin(["CLAUDE.AI SUBSCRIPTION", "ANTHROPIC* CLAUDE SUB", "ANTHROPIC* CLAUDE"])
bare = x.family.eq("bare ANTHROPIC")
both_m = set(x.loc[sub, "memid"]) & set(x.loc[bare, "memid"])
def stats(m):
    g = x[m].sort_values(["memid", "dt"]).groupby("memid").dt.diff().dt.days
    return pd.Series({"rows": m.sum(), "members": x.loc[m, "memid"].nunique(),
                      "payments per member-month": x[m].groupby(["memid", x.dt.dt.to_period("M")]).size().mean(),
                      "median gap (days)": g.median(), "gap 26-35d": g.between(26, 35).mean(),
                      "amount on $20/$100/$200 (+tax)": x.loc[m, "on_price"].mean(),
                      "top amounts": ", ".join(f"${a:g}" for a in x.loc[m, "amount"].round(0).value_counts().head(6).index)})
pd.DataFrame({"subscription descriptors": stats(sub), "bare ANTHROPIC": stats(bare),
              "bare ANTHROPIC, members who also pay a sub": stats(bare & x.memid.isin(both_m))})
""")
    note(p)

md("""
## 3. Classification rules

The families above line up with the descriptor rules researched on the same panel on 2026-10-19 (`../filters/{provider}.py`, reports in `../filters/*_report.md`). The rows here have the same descriptors (Omega `MERCHDESC` = `BILLING_DESCRIPTION`), so those rules are applied unchanged:

| Provider | Kept as a plan payment | Excluded |
|---|---|---|
| Claude | `CLAUDE.AI SUBSCRIPTION`, `ANTHROPIC* CLAUDE (SUB)`, Google Play `GOOGLE *CLAUDE`, on Pro $20 / Max $100 / $200 bands (+tax; $200 = Max 20x if repeated 25-40 days apart, else Pro annual) | bare `ANTHROPIC` (API credits) unless on a list price and repeated 26-35 days apart; Team; refunds; duplicates |
| ChatGPT | `CHATGPT SUBSCR`, Google Play `GOOGLE *CHATGPT`, on Go $8 / Plus $20 / Pro $100 / $200 / $500 bands | bare `OPENAI` (API) unless on a plan price and repeated 25-35 days apart; Team/Business seat multiples; credit packs |
| Gemini | Google One at AI-tier prices: AI Pro $19.99, AI Plus, Ultra; 2TB from 2026-01-27 (`ai_plus_2tb`, now includes AI Plus) | storage-only prices; $19.99 / $99.99 / $199.99 one-offs read as annual storage where the collision applies |
| Perplexity | `WWW.PERPLEXITY.AI`, `PERPLEXITY PRO`, Google Play, on Pro $20 / $200 annual, Max $200 / $2,000 | Enterprise seats, API / Computer credits, merch |
| Muse | `METAPAY META.COM` at Power $16 / Max $80 (+tax), Google Play `GOOGLE *MUSE FROM META` at $20 / $100, from 2026-09-07 | pre-Muse Meta One look-alikes on `METAPAY`; Facebook ads; `GOOGLE *FACEBOOK` (in-app purchases, not identifiable as Muse) |
""")

code("""
cls = R.classify(raw)
cls["provider_name"] = cls.provider.map(NAMES)
print("kept vs excluded rows by provider and reason")
cls.pivot_table(index="reason", columns="provider_name", values="dt", aggfunc="size", fill_value=0).sort_values("Claude", ascending=False)
""")

code("""
# how each research family was treated: share of rows kept
fam = pd.concat([RES[p][["transid", "family"]].assign(provider=p) for p in ORDER])
k = raw[["transid", "memid", "dt", "amount"]].merge(fam, on="transid").assign(amount=lambda d: d.amount.round(2))
kept = cls.loc[cls.keep, ["memid", "dt", "amount", "provider", "keep"]].assign(amount=lambda d: d.amount.round(2))
k = k.merge(kept.drop_duplicates(["memid", "dt", "amount", "provider"]), on=["memid", "dt", "amount", "provider"],
            how="left").fillna({"keep": False})
(k.groupby(["provider", "family"]).agg(rows=("transid", "size"), pct_kept=("keep", "mean"))
   .sort_values(["provider", "rows"], ascending=[True, False]).style.format({"rows": "{:,}", "pct_kept": "{:.0%}"}))
""")

code("""
pay = cls[cls.keep].copy()
pay = pay.merge(raw.drop_duplicates("memid")[["memid", "weight"]], on="memid", how="left")
pay["plan_name"] = pay.provider.map(NAMES) + " " + pay.plan.astype(str).map(lambda c: PLANS.get(c, c))
print(f"{len(pay):,} plan payments, {pay.memid.nunique():,} members")
pay.pivot_table(index="plan_name", columns="channel", values="dt", aggfunc="size", fill_value=0)
""")

md("""
**Cross-check against the earlier keyword extract.** The Oct-19 card tracker found candidates by keyword across all Omega merchants (`../.cache/metrics_omega/payments.parquet`, data to 2026-10-17). Comparing monthly kept payments shows whether the brand filter misses merchants.
""")

code("""
old = pd.read_parquet(R.CACHE.parent / "metrics_omega" / "payments.parquet")
old = old[old.keep & old.provider.isin(ORDER) & (old.dt < "2026-10-01")]
new = pay[pay.dt < "2026-10-01"]
cmp = pd.concat({"keyword extract (Oct-19)": old.groupby(["provider", pd.to_datetime(old.dt).dt.to_period("M")]).size(),
                 "TXNS_CORE + patch": new.groupby(["provider", new.dt.dt.to_period("M")]).size()}, axis=1).fillna(0)
cmp["ratio"] = cmp.iloc[:, 1] / cmp.iloc[:, 0]
r = cmp.reset_index().pivot(index="dt", columns="provider", values="ratio").loc["2024-01":]
r.columns = [NAMES[c] for c in r.columns]
r.iloc[::3].style.format("{:.2f}")
""")
note("crosscheck")

md("""
## 4. Daily and TR30 subscriber payments and gross adds

- **Subscriber payments (daily):** distinct members with a plan payment that day.
- **TR30 subscribers:** distinct members with a plan payment in the trailing 30 days (day d-29 to d).
- **Gross add:** a member's plan payment with no payment for the same provider (or plan) in the previous 75 days (400 days after an annual payment). Reactivations count. Reported from 2024-01-01, so every add has at least a year of lookback. At plan level, a plan switch is an add for the new plan.
- **% of panel:** count / fixed panel members (unweighted), and weighted count / sum of panel weights.

Caveats:
- TR30 counts payers, so annual-plan subscribers only appear in the month they pay. Annual plans are a small share (see the plan table at the end).
- The last ~10 days are still filling (late-posting transactions); they are shaded grey.
- Cards only see web and Google Play billing. Apple App Store subscriptions are invisible.
""")

code("""
P = R.daily(pay, "provider")
PW = R.daily(pay, "provider", weight="weight")
L = R.daily(pay, "plan_name")
tr = P["tr30_subs"][ORDER]
last = tr.index[-1]
summary = pd.DataFrame({
    "TR30 subscribers": tr.iloc[-1], "% of panel": tr.iloc[-1] / N, "% of panel (weighted)": PW["tr30_subs"][ORDER].iloc[-1] / W,
    "TR30 gross adds": P["tr30_adds"][ORDER].iloc[-1], "gross adds % of panel": P["tr30_adds"][ORDER].iloc[-1] / N,
    "share of TR30 subs": tr.iloc[-1] / tr.iloc[-1].sum(),
    "TR30 subs 1y ago": tr.loc[last - pd.Timedelta(days=364)]}).rename(index=NAMES)
print(f"as of {last.date()} (latest days still filling; see charts)")
summary.style.format({"TR30 subscribers": "{:,.0f}", "TR30 gross adds": "{:,.0f}", "TR30 subs 1y ago": "{:,.0f}",
                      "% of panel": "{:.2%}", "% of panel (weighted)": "{:.2%}", "gross adds % of panel": "{:.3%}", "share of TR30 subs": "{:.1%}"})
""")

code("""
def style(ax, title, pct=False, dec=1):
    ax.set_title(title, fontsize=11, loc="left")
    ax.axvspan(END - pd.Timedelta(days=10), END, color="#999", alpha=0.15, lw=0)
    ax.grid(alpha=0.3); ax.spines[["top", "right"]].set_visible(False)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b-%y"))
    ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=dec) if pct else FuncFormatter(lambda v, _: f"{v:,.0f}"))

def lines(df, title, pct=False, dec=1, ax=None):
    ax = ax or plt.subplots(figsize=(11, 4))[1]
    top = df.iloc[-1].max()
    for p in [c for c in ORDER if c in df]:
        ax.plot(df.index, df[p], color=COLORS[p], lw=2, label=NAMES[p])
        if df[p].iloc[-1] > 0.05 * top:  # direct-label the visible lines; the legend covers the rest
            ax.annotate(NAMES[p], (df.index[-1], df[p].iloc[-1]), xytext=(4, 0), textcoords="offset points", fontsize=8, va="center")
    style(ax, title, pct, dec); ax.legend(loc="upper left", frameon=False, fontsize=9)
    return ax

lines(tr, "TR30 subscribers by provider (panel members with a plan payment in the trailing 30 days)"); plt.show()
lines(tr / N, "TR30 subscribers by provider, % of fixed panel", pct=True, dec=1); plt.show()
""")

code("""
share = tr.div(tr.sum(axis=1), axis=0)
fig, ax = plt.subplots(figsize=(11, 4))
ax.stackplot(share.index, *[share[p] for p in ORDER], colors=[COLORS[p] for p in ORDER], labels=[NAMES[p] for p in ORDER],
             edgecolor="white", linewidth=0.5)
style(ax, "Share of TR30 subscribers between providers", pct=True, dec=0); ax.set_ylim(0, 1); ax.margins(x=0)
ax.legend(loc="upper left", bbox_to_anchor=(1, 1), frameon=False, fontsize=9); plt.show()
share.resample("QE").last().rename(columns=NAMES, index=lambda d: d.date()).style.format("{:.1%}")
""")

code("""
# the 2TB plan counts as Gemini AI Plus from 2026-01-27 (earlier decision); without it Gemini's share is much smaller
g2 = R.tr_distinct(pay[pay.provider.ne("gemini") | ~pay.plan.astype(str).str.startswith("ai_plus_2tb")], "provider", tr.index)[ORDER]
sh2 = g2.div(g2.sum(axis=1), axis=0)
fig, ax = plt.subplots(figsize=(11, 4))
ax.stackplot(sh2.index, *[sh2[p] for p in ORDER], colors=[COLORS[p] for p in ORDER], labels=[NAMES[p] for p in ORDER],
             edgecolor="white", linewidth=0.5)
style(ax, "Share of TR30 subscribers between providers, Gemini excluding the 2TB plan", pct=True, dec=0); ax.set_ylim(0, 1); ax.margins(x=0)
ax.legend(loc="upper left", bbox_to_anchor=(1, 1), frameon=False, fontsize=9); plt.show()
""")

code("""
lines(P["tr30_adds"][ORDER], "TR30 gross adds by provider (members starting or restarting a plan in the trailing 30 days)"); plt.show()
lines(P["tr30_adds"][ORDER] / N, "TR30 gross adds by provider, % of fixed panel", pct=True, dec=2); plt.show()
""")

code("""
fig, ax = plt.subplots(figsize=(11, 3.5))
d = P["payments"][ORDER].loc["2026-01-01":]
for p in ORDER:
    ax.plot(d.index, d[p], color=COLORS[p], lw=1, label=NAMES[p])
style(ax, "Daily subscriber payments by provider (2026)"); ax.legend(loc="upper left", frameon=False, fontsize=9, ncol=5); plt.show()
""")
note("provider")

md("## 5. TR30 subscribers by plan")

code("""
fig, axes = plt.subplots(len(ORDER), 1, figsize=(11, 3.2 * len(ORDER)))
for ax, p in zip(axes, ORDER):
    cols = [c for c in L["tr30_subs"].columns if c.startswith(NAMES[p] + " ")]
    d = L["tr30_subs"][cols]
    d = d[d.iloc[-1].sort_values(ascending=False).index]
    for i, c in enumerate(d.columns):
        ax.plot(d.index, d[c], lw=2, color=plt.cm.tab10(i), label=c.split(" ", 1)[1])
    style(ax, f"{NAMES[p]}: TR30 subscribers by plan"); ax.legend(loc="upper left", frameon=False, fontsize=8, ncol=4)
plt.tight_layout(); plt.show()
""")

code("""
pl = pd.DataFrame({"TR30 subscribers": L["tr30_subs"].iloc[-1], "% of panel": L["tr30_subs"].iloc[-1] / N,
                   "TR30 gross adds": L["tr30_adds"].iloc[-1], "gross adds % of panel": L["tr30_adds"].iloc[-1] / N})
pl = pl[pl["TR30 subscribers"] > 0].sort_values("TR30 subscribers", ascending=False)
pl.style.format({"TR30 subscribers": "{:,.0f}", "TR30 gross adds": "{:,.0f}", "% of panel": "{:.3%}", "gross adds % of panel": "{:.3%}"})
""")
note("plan")

code("""
# export for later comparison with the e-receipt panel
out = {f"{k}_{lvl}": v for lvl, D in [("provider", P), ("plan", L)] for k, v in D.items()}
pd.concat(out, axis=1).to_parquet(R.CACHE / "daily_metrics.parquet")
print("saved", R.CACHE / "daily_metrics.parquet")
""")

nb["cells"] = C
nb["metadata"]["kernelspec"] = {"name": "exploration", "display_name": "exploration", "language": "python"}
nbf.write(nb, "card_gross_adds.ipynb")
print("wrote card_gross_adds.ipynb")
