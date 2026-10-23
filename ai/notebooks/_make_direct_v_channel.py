"""Builds direct_v_channel_comparison.ipynb (run: python _make_direct_v_channel.py, then execute with nbconvert)."""
import nbformat as nbf

nb = nbf.v4.new_notebook()
C = []
md = lambda s: C.append(nbf.v4.new_markdown_cell(s.strip()))
code = lambda s: C.append(nbf.v4.new_code_cell(s.strip()))

md("""
# Direct vs app-store channels: AI subscription gross adds and churn on e-receipts

For each AI provider, this notebook builds monthly gross adds and churn from three receipt channels in `srs_slice.common.items_v` (NIQ / Slice, US) and compares them:

1. **Direct:** the provider's own sender, e.g. `Chat GPT` / `Chat GPT Cancellation`.
2. **Google Play:** `Google Play` / `Google Play Cancellation`.
3. **App Store:** `iTunes` / `iTunes Cancellation`.

Each comparison chart also shows the **modelled** gross adds and churn from the `ai_consumer` job (`srs_mcp.ai_consumer.subs_monthly`, US, all plans). These are from yesterday's method:
- **Modelled gross adds:** the first paid receipt of a subscription, pooled across every channel the model reads.
- **Modelled churn:** churn rates from the reliable subset, applied to modelled subscribers. Churn is dated when a subscription lapses (last payment plus the lapse window), not when a cancellation email arrives. The two measures cover different mailboxes, so a consistent one-month lag isn't visible in the charts.

Each chart also shows a **combined, deduped** line (purple, thicker): gross adds and churn across direct, Google Play and iTunes. Each channel is first built with its own rules (below). An add or cancellation for a mailbox within 45 days of an add or cancellation for the same mailbox in a different channel counts once, at the first date (for example, a Google One welcome email plus a Google Play receipt for the same Gemini sign-up). Mailboxes are distinct per month.

The modelled and combined numbers are one total per provider, not extra channels, so they are left out of the channel shares. The table under each chart gives the combined total as a share of the summed channels; one minus that share is the cross-channel overlap. See the per-provider notes for which channels the model covers.

**Common rules (all sections)**
- **Unit:** distinct `mailbox_id` per `order_date` month. All mailboxes are included, with no panel-status filter. Counts are at provider level: any tier counts, and a tier switch is not a new add.
- **Gross add:** the first sign-up or paid subscription email in a consecutive series for a mailbox in that channel. A new series starts when the previous sign-up/paid email is more than **75 days** earlier, or **400 days** if that email was for an annual plan, or when a cancellation email arrived in between. The 75-day window comes from renewal gaps: store renewals are a median 31 days apart, and 4–12% of gaps are 36–75 days (one missed email). How each channel's emails map to "sign-up" and "paid" is set per channel below, after looking at the structure.
- **Churn:** cancellation emails only. Several emails about the same cancellation (e.g. Google Play's "will be canceled on…" followed by "…will end on…") count once: emails for one mailbox within 45 days, with no sign-up/paid email between them, are one cancellation, dated at the first.
- Paid rows exclude credits, tokens and other one-off purchases. Free-trial notices are not adds; a trial that converts shows up as an add at its first paid receipt.
- Data runs to the latest `order_date` loaded. **The last month is partial.** Charts stop at the last complete month.

The filter and engine code is in `channel_rules.py`. The raw candidate rows are cached in `../.cache/channel_cmp/raw.parquet`. Delete that file to re-pull it (about 5 minutes on `ANALYST_L`).
""")

code("""
import re, sys, warnings, pandas as pd, numpy as np, matplotlib.pyplot as plt, matplotlib.dates as mdates
warnings.filterwarnings("ignore", message="This pattern is interpreted")
warnings.filterwarnings("ignore", category=FutureWarning)
from pathlib import Path
from IPython.display import display, Markdown
import channel_rules as R
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 110); pd.set_option("display.max_rows", 200)

CACHE = Path("../.cache/channel_cmp/raw.parquet")
RX = "chat ?gpt|open ?ai|claude|anthropic|gemini|google one|google ai|grok|perplexity|muse from meta|power plan|maximum plan"
SQL = f'''
SELECT mailbox_id, merchant_id, merchant_name, order_date, email_sent_time, order_id, item_id, description, item_price, order_total
FROM srs_slice.common.items_v
WHERE order_date >= '2024-07-01' AND (
      merchant_id IN (4070, 4078, 20127, 20139, 4212, 4213, 20187, 20191)          -- direct senders
   OR (merchant_id = 3848 AND description ILIKE '%muse%')                            -- Meta (Muse)
   OR (merchant_id IN (5, 20122, 1493, 3452) AND REGEXP_LIKE(description, '.*({RX}).*', 'is')))  -- iTunes / Google Play
'''
if not CACHE.exists():
    import snowflake.connector as sc
    cur = sc.connect(connection_name="default", warehouse="ANALYST_L", network_timeout=3600).cursor()
    cur.execute(SQL); raw = cur.fetch_pandas_all(); raw.columns = [c.lower() for c in raw.columns]
    CACHE.parent.mkdir(parents=True, exist_ok=True); raw.to_parquet(CACHE, index=False)
df = pd.read_parquet(CACHE)
df["d"] = df.description.str.lower().fillna("")
df["dt"] = pd.to_datetime(df.order_date)
df["channel"] = np.select([df.merchant_id.isin([1493, 3452]), df.merchant_id.isin([5, 20122])], ["gp", "itunes"], "direct")
df["cancel_sender"] = df.merchant_id.isin([4078, 20139, 4213, 20191, 3452, 20122])
df["priced"] = df.item_price.fillna(0) > 0
DATA_END = df.dt.max()
LAST_FULL = DATA_END.to_period("M") if DATA_END.is_month_end else pd.Period(DATA_END - pd.offsets.MonthEnd(1), "M")
print(f"{len(df):,} candidate rows; data end {DATA_END.date()}; charts end {LAST_FULL}")

# Modelled gross adds and churn from the ai_consumer job (yesterday's method). Re-read on every run; a copy is cached for offline use.
MODEL_CACHE = Path("../.cache/channel_cmp/model_subs_monthly.parquet")
try:
    import snowflake.connector as sc
    cur = sc.connect(connection_name="default", warehouse="ANALYST_L").cursor()
    cur.execute("SELECT provider, plan, month, gross_adds, churn, held, loaded_at FROM srs_mcp.ai_consumer.subs_monthly "
                "WHERE region = 'us' AND country = 'us' AND month >= '2025-01-01'")
    model_raw = cur.fetch_pandas_all(); model_raw.columns = [c.lower() for c in model_raw.columns]; model_raw.to_parquet(MODEL_CACHE, index=False)
except Exception as e:
    print("Snowflake unavailable, using cached modelled table:", e); model_raw = pd.read_parquet(MODEL_CACHE)
print("modelled table loaded at", model_raw.loaded_at.max())
df.groupby(["merchant_id", "merchant_name"]).size().rename("rows_since_2024_07").to_frame()
""")

code("""
COLORS = {"Direct": "#2a78d6", "Google Play": "#eb6834", "iTunes": "#1baf7a", "Modelled": "#3d3d3a", "Combined": "#8b5cc8"}
EVENTS = {}  # id(monthly table) -> (add events, churn events), each mailbox_id + dt; used to build the deduped combined line
DEDUP_DAYS = 45

def combined(tabs):
    '''Gross adds and churn across channels, deduped: an add (or cancellation) for a mailbox within DEDUP_DAYS after an add
    (or cancellation) for the same mailbox in a different channel is the same event and is counted once, at the first date.'''
    out = []
    for k in (0, 1):
        ev = pd.concat([EVENTS[id(t)][k].assign(ch=lab) for lab, t in tabs.items()]).sort_values(["mailbox_id", "dt"]).reset_index(drop=True)
        same = ev.mailbox_id.eq(ev.mailbox_id.shift())
        dup = same & ev.ch.ne(ev.ch.shift()) & ((ev.dt - ev.dt.shift()).dt.days <= DEDUP_DAYS)
        out.append(ev[~dup])
    return R.monthly(out[0], out[1])

def model_tab(provider, exclude_plans=None):
    '''Modelled monthly gross adds and churn for one provider: the sum over plans, optionally excluding some plans (regex).'''
    m = model_raw[(model_raw.provider == provider) & (model_raw.plan != "all")]
    if exclude_plans: m = m[~m.plan.str.contains(exclude_plans)]
    t = m.assign(month=pd.to_datetime(m.month).dt.to_period("M")).groupby("month")[["gross_adds", "churn"]].sum().round().astype(int)
    held = model_raw[model_raw.held].month.pipe(pd.to_datetime).dt.to_period("M").unique()
    return t[~t.index.isin(held)]

def has(rx):
    return df.d.str.contains(rx, regex=True)

def sequences(mask, n=4, seed=0, since="2025-06-01"):
    '''Print the full email sequence (ordered by mailbox_id, order_date) for n mailboxes that have a cancellation since `since`.'''
    rows = df[mask].sort_values(["mailbox_id", "dt", "email_sent_time"])
    pick = rows[rows.cancel_sender & (rows.dt >= since)].mailbox_id.drop_duplicates()
    pick = pick.sample(min(n, len(pick)), random_state=seed) if len(pick) else rows.mailbox_id.drop_duplicates().sample(min(n, rows.mailbox_id.nunique()), random_state=seed)
    out = rows[rows.mailbox_id.isin(pick)][["mailbox_id", "order_date", "merchant_name", "description", "item_price"]]
    display(out.head(60))

def patterns(mask, top=15):
    '''Most common description patterns (digits replaced by #) since 2025, split by sender, with priced share.'''
    x = df[mask & (df.dt >= "2025-01-01")]
    p = x.assign(pattern=x.d.str.replace(r"\\d+", "#", regex=True).str.slice(0, 110))
    t = p.groupby(["merchant_name", "pattern"]).agg(rows=("item_id", "size"), priced_share=("priced", "mean"), median_price=("item_price", "median"))
    display(t.sort_values("rows", ascending=False).groupby(level=0, group_keys=False).head(top).round(2))

# Google Play paid receipt: priced and "auto-renewing subscription". Free-trial notices quote the same plan text but are unpriced.
GP_PAY = (df.merchant_id == 1493) & df.priced & df.d.str.contains("auto-renewing subscription") & ~df.d.str.startswith("your trial")

def build(mask_rows, signup, pay, cancel, annual=None, parts=False):
    rows = df[mask_rows]
    f = lambda m: (m if isinstance(m, pd.Series) else pd.Series(m, index=df.index))[mask_rows] if m is not None else pd.Series(False, index=rows.index)
    tab, adds, churn, sig_rows = R.run(rows, f(signup), f(pay), f(cancel), f(annual) if annual is not None else None)
    # churn with no sign-up/paid email for the mailbox in this channel in the prior 400 days (e.g. trials cancelled before paying)
    sig = rows[f(signup) | f(pay)][["mailbox_id", "dt"]].rename(columns={"dt": "sdt"}).sort_values("sdt")
    j = pd.merge_asof(churn.sort_values("dt"), sig, left_on="dt", right_on="sdt", by="mailbox_id", direction="backward", tolerance=pd.Timedelta(days=400))
    tab.attrs["churn_no_prior_add"] = j[j.dt >= "2025-01-01"].sdt.isna().mean() if len(j) else np.nan
    EVENTS[id(tab)] = (adds[["mailbox_id", "dt", "row"]], churn[["mailbox_id", "dt", "row"]], sig_rows[["mailbox_id", "dt", "row"]])
    return (tab, adds, churn) if parts else tab

def show(tab, title):
    display(Markdown(f"**{title}** (month {DATA_END.to_period('M')} is partial)"))
    display(tab.T)

def compare(tabs, title, extra_styles=None, model=None, model_covers=None):
    '''tabs: {channel label: monthly table}. Three panels (gross adds, churn, implied net adds = gross adds - churn), one line per channel plus the modelled total, from 2025-01.'''
    chans = {lab: t for lab, t in tabs.items() if lab in ("Direct", "Google Play", "iTunes")}
    comb = combined(chans)
    lines = dict(tabs, Combined=comb, **({"Modelled": model} if model is not None else {}))
    extra_styles = dict({"Combined": {"lw": 2.8}}, **(extra_styles or {}))
    fig, axes = plt.subplots(1, 3, figsize=(21, 4.6), sharex=True)
    for ax, col, name in zip(axes, ["gross_adds", "churn", "net_adds"], ["Gross adds", "Churn (channels: cancellation emails; modelled: lapses)", "Implied net adds (gross adds − churn)"]):
        for lab, t in lines.items():
            t = t[t.index <= LAST_FULL]
            # net adds only where the line has both adds and churn, otherwise it would just repeat one of them
            if col == "net_adds" and (t.gross_adds.sum() == 0 or t.churn.sum() == 0): continue
            s = t.gross_adds - t.churn if col == "net_adds" else t[col]
            if s.sum() == 0 and col != "net_adds": continue
            sty = (extra_styles or {}).get(lab, {})
            ax.plot(s.index.to_timestamp(), s.values, lw=sty.get("lw", 2), label=lab if lab != "Combined" else f"Combined, deduped ({' + '.join(chans)})", color=sty.get("color", COLORS.get(lab)), ls=sty.get("ls", "-"))
        ax.set_title(name, loc="left", fontsize=11); ax.grid(axis="y", color="#e5e5e5", lw=0.8)
        ax.spines[["top", "right"]].set_visible(False)
        if col == "net_adds": ax.axhline(0, color="#999999", lw=0.8)
        else: ax.set_ylim(bottom=0)
        ax.set_ylabel("mailboxes per month")
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10])); ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    axes[0].legend(frameon=False, loc="upper left")
    fig.suptitle(title, x=0.01, ha="left", fontsize=13); fig.tight_layout(); plt.show()
    # channel share of the total over complete months since 2025-01
    tot = pd.DataFrame({lab: t[t.index <= LAST_FULL][["gross_adds", "churn"]].sum() for lab, t in tabs.items()}).T
    share = (tot / tot.sum()).round(3).add_suffix("_share")
    # correlation of each channel's monthly series with the others
    out = pd.concat([tot, share], axis=1)
    ct = comb[(comb.index >= "2025-01") & (comb.index <= LAST_FULL)][["gross_adds", "churn"]].sum()
    out.loc["Combined, deduped"] = ct
    out.loc["Combined / sum of those channels"] = (ct / tot.loc[list(chans)].sum()).round(3)
    if model is not None:
        mt = model[(model.index >= "2025-01") & (model.index <= LAST_FULL)][["gross_adds", "churn"]].sum()
        cov = tot.loc[model_covers or list(tabs)].sum()
        out.loc[f"Sum of channels the model reads ({' + '.join(model_covers or list(tabs))})"] = cov
        out.loc["Modelled"] = mt
        out.loc["Modelled / those channels"] = (mt / cov).round(2)
    display(out)
    for c in ["gross_adds", "churn"]:
        w = pd.DataFrame({lab: t[c][(t.index >= "2025-01") & (t.index <= LAST_FULL)] for lab, t in lines.items()})
        w = w[w.sum(axis=1) > 0]
        if len(w) < 6: continue  # too few months for a meaningful correlation
        m = w.corr().round(2)
        display(Markdown(f"Correlation of monthly {c.replace('_', ' ')} across channels (2025-01 to {LAST_FULL})")); display(m)
""")

# ---------------------------------------------------------------- ChatGPT
md("""
## 1. ChatGPT

**Merchants found:** `Chat GPT` (4070) and `Chat GPT Cancellation` (4078). Both direct merchants exist.
""")
md("""
### 1a. Direct (`Chat GPT`, `Chat GPT Cancellation`)

What the sender carries (patterns below):
- `ChatGPT Plus / Go / Pro Subscription` is priced and sent **once, at sign-up**. Almost every mailbox has a single row, with no monthly renewals.
- `Payment` rows (median about $10.60, amounts of $5/$10/$50…) are **API credit top-ups**, not consumer subscriptions.
- `ChatGPT Business / Team Subscription` is a business plan.
- Cancellations read `ChatGPT <plan> Subscription Cancellation` (one per cancellation).

**Filters used**
- Gross adds: `Chat GPT` rows matching `^chatgpt (plus|go|pro)( \\d+x?)?( subscription)?$` (Plus, Go, Pro and Pro 5x/20x). `Payment`, Business, Team and `(test)` are excluded. Each row is a sign-up, de-duplicated by the series rule.
- Churn: `Chat GPT Cancellation` rows for consumer plans (`plus|go|pro`). Team, Business and `ChatGPT Free … Cancellation` are excluded.
""")
code("""
m_dir = df.merchant_id.isin([4070, 4078])
patterns(m_dir, top=10)
""")
code("""
CG_PLAN = r"^chatgpt (plus|go|pro)( \\d+x?)?( subscription| plan)?( cancellation)?$"
cg_dir = build(m_dir, signup=(df.merchant_id == 4070) & has(CG_PLAN), pay=None,
               cancel=(df.merchant_id == 4078) & has(CG_PLAN))
show(cg_dir, "ChatGPT direct: monthly gross adds and churn")
""")
md("""
### 1b. Google Play

Rows with `(chat ?gpt|open ?ai)` in the description from `Google Play` / `Google Play Cancellation`. The full sequences for a few mailboxes (ordered by mailbox, then date) show the structure:
""")
code("""
m_gp = (df.channel == "gp") & has(r"\\bchat ?gpt\\b|\\bopen ?ai\\b")
patterns(m_gp, top=8)
sequences(m_gp, n=4, seed=3)
""")
md("""
- `ChatGPT Plus/Go/Pro (ChatGPT) Auto-renewing subscription` is priced and arrives **every month**: once at sign-up and once at each renewal.
- `… (ChatGPT)` without "auto-renewing" (prorated upgrade charges) and `Video credits (Sora by OpenAI)` are not subscription receipts.
- `Your trial will end on …` is a free-trial notice.
- A cancellation sends two or three emails: `Your ChatGPT subscription from OpenAI … will be canceled on <date>` when the user cancels, `ChatGPT (ChatGPT Plus) subscription will end on <date>` near the end, and sometimes `… has been canceled.`

**Filters used**
- Gross adds: `Google Play` rows matching `\\(chatgpt\\) auto-renewing subscription`. The first in each consecutive series is the add.
- Churn: `Google Play Cancellation` rows mentioning `chatgpt` (all three formats), de-duplicated by the 45-day rule.
""")
code("""
cg_gp = build(m_gp, signup=None, pay=GP_PAY & has(r"\\(chatgpt\\) auto-renewing subscription"),
              cancel=(df.merchant_id == 3452) & has(r"chatgpt"))
show(cg_gp, "ChatGPT Google Play: monthly gross adds and churn")
""")
md("""
### 1c. iTunes (App Store)
""")
code("""
m_it = (df.channel == "itunes") & has(r"^chatgpt ")
patterns(m_it, top=10)
sequences(m_it, n=4, seed=3)
""")
md("""
- Apple sends **two emails at sign-up**: an unpriced confirmation `ChatGPT ChatGPT Plus $19.99 /month` (or `USD 19.99 /month`) and a priced receipt `ChatGPT : ChatGPT Plus (Monthly)`. The priced receipt is sometimes several days later, or missing if the user cancels first.
- After sign-up, a priced `ChatGPT : ChatGPT Plus (Monthly)` receipt arrives **at each renewal**.
- `iTunes Cancellation` sends one email per cancellation: `ChatGPT ChatGPT Plus (1 month)`.
- `ChatGPT : # Credits` and Sora video packs are one-off purchases.

**Filters used**
- Gross adds: the first iTunes email in a series. That is either a confirmation (unpriced, `/month` or `/year`) or a priced subscription receipt (`(monthly)`, `(annual)`) for the ChatGPT app (description starts `chatgpt `). Credits are excluded.
- Churn: `iTunes Cancellation` rows starting `chatgpt chatgpt`. This excludes third-party "powered by ChatGPT" apps.
""")
code("""
IT_SIGNUP = ~df.priced & has(r"/ ?(month|year|week)") & ~has(r"free trial")
IT_PAY = df.priced & has(r"\\((monthly|annual|yearly|weekly)\\)")
IT_ANNUAL = has(r"annual|yearly|/ ?year|\\(\\d+ year\\)")
cg_it = build(m_it, signup=(df.merchant_id == 5) & IT_SIGNUP, pay=(df.merchant_id == 5) & IT_PAY & ~has("credits"),
              cancel=(df.merchant_id == 20122) & has(r"^chatgpt chatgpt"), annual=IT_ANNUAL)
show(cg_it, "ChatGPT iTunes: monthly gross adds and churn")
""")
md("### 1d. ChatGPT: channel comparison")
code("""
compare({"Direct": cg_dir, "Google Play": cg_gp, "iTunes": cg_it}, "ChatGPT: gross adds and churn by channel", model=model_tab("chatgpt"), model_covers=["Google Play", "iTunes"])
""")
md("""
**Reading it**
- **Adds:** iTunes captures the most ChatGPT adds (about 50% since 2025-01), then direct (about 38%) and Google Play (about 11%). Direct and iTunes agree on the April 2025 spike (which coincides with the image-generation launch) but otherwise diverge. **From July 2026, iTunes adds fall by about half while direct adds rise by a similar amount.** iTunes renewal receipts stay flat over that period, so this looks like a shift of new sign-ups from in-app purchase to web checkout, not a data break. Monthly add correlations are weak (direct vs iTunes about 0).
- **Churn:** all three channels move together (correlations 0.80–0.91): a rise through 2025, a peak in March 2026, then a decline. Direct churn is large relative to direct adds. About half of direct cancellations have no ChatGPT sign-up email in the prior 400 days, which fits direct sign-up emails being captured less reliably than cancellations.
- **Modelled vs observed:** the model reads Google Play and iTunes only. ChatGPT direct is excluded because direct sends no renewals. Modelled adds follow Google Play and iTunes (correlation 0.80 and 0.74) at about 0.8 times their sum. Modelled adds come from the first paid receipt, while the iTunes line here also counts unpriced confirmations and restarts after a cancellation. The model also eases less than iTunes from July 2026, because Google Play keeps growing. Modelled churn tracks the cancellation-email lines closely (correlation 0.84–0.93), at about 0.9 times Google Play plus iTunes.
""")

# ---------------------------------------------------------------- Claude
md("""
## 2. Claude

**Merchants found:** `Anthropic` (20127) and `Anthropic Cancellation` (20139). Both direct merchants exist, under the name Anthropic rather than Claude.
""")
md("""
### 2a. Direct (`Anthropic`, `Anthropic Cancellation`)
""")
code("""
m_dir = df.merchant_id.isin([20127, 20139])
patterns(m_dir, top=10)
sequences(m_dir, n=4, seed=1)
""")
md("""
- `Pro Subscription` / `Max Subscription` is an unpriced welcome, sent **at each sign-up** and at a tier change.
- `Payment` is priced and sent at sign-up and **every renewal**: $20 Pro, $100 Max 5x, $200 Max 20x. Other amounts ($5, $10, $45, $25…) are API or usage credits.
- `Anthropic Cancellation` sends `Claude Pro` / `Claude Max` once per cancellation. About 1.5% of cancellations are tier switches (e.g. `Claude Max` cancelled within 3 days of a `Pro Subscription` welcome).

**Filters used**
- Gross adds: first in series of `Pro Subscription` / `Max Subscription` welcomes and `Payment` rows priced exactly $20, $100 or $200 (renewals keep the series going; credits are excluded).
- Churn: `Anthropic Cancellation` rows (`Claude Pro`, `Claude Max`), excluding cross-tier switches (a cancellation within 3 days of a welcome for the other tier).
""")
code("""
ws = df[m_dir & df.d.isin(["pro subscription", "max subscription"])][["mailbox_id", "dt", "d"]]
cn = df[m_dir & (df.merchant_id == 20139)][["mailbox_id", "dt", "d"]].reset_index()
x = cn.merge(ws, on="mailbox_id", suffixes=("", "_w"))
switch_idx = x[((x.dt_w - x.dt).dt.days.abs() <= 3) & (x.d.str.split().str[-1] != x.d_w.str.split().str[0])]["index"].unique()
print(f"Claude direct cancellations: {len(cn):,}; cross-tier switches excluded: {len(switch_idx):,} ({len(switch_idx) / len(cn):.1%})")
cl_dir = build(m_dir, signup=df.d.isin(["pro subscription", "max subscription"]) & (df.merchant_id == 20127),
               pay=(df.merchant_id == 20127) & (df.d == "payment") & df.item_price.isin([20, 100, 200]),
               cancel=(df.merchant_id == 20139) & ~df.index.isin(switch_idx))
show(cl_dir, "Claude direct: monthly gross adds and churn")
""")
md("### 2b. Google Play")
code("""
m_gp = (df.channel == "gp") & has(r"\\bclaude\\b|anthropic")
patterns(m_gp, top=8)
sequences(m_gp, n=4, seed=1)
""")
md("""
The structure matches ChatGPT on Google Play. `Claude Pro Subscription (Claude by Anthropic) Auto-renewing subscription` (and `Claude Max …`) is priced and sent at sign-up and **each renewal**. Cancellations read `Your Claude by Anthropic subscription from Anthropic, PBC … will be canceled on…`, `… has been canceled.` and `Claude by Anthropic (Claude Pro subscription) subscription will end on…`. Third-party apps (`Vicoa`, `Vibe code`, books about Claude Monet) also match the regex.

**Filters used**
- Gross adds: `Google Play` rows matching `\\(claude by anthropic\\) auto-renewing subscription`. The first in each series is the add.
- Churn: `Google Play Cancellation` rows mentioning `claude by anthropic`.
""")
code("""
cl_gp = build(m_gp, signup=None, pay=GP_PAY & has(r"\\(claude by anthropic\\) auto-renewing subscription"),
              cancel=(df.merchant_id == 3452) & has(r"claude by anthropic"))
show(cl_gp, "Claude Google Play: monthly gross adds and churn")
""")
md("### 2c. iTunes (App Store)")
code("""
m_it = (df.channel == "itunes") & has(r"^claude by anthropic")
patterns(m_it, top=10)
sequences(m_it, n=4, seed=1)
""")
md("""
The structure matches ChatGPT on iTunes: an unpriced confirmation `Claude by Anthropic Claude Pro - Monthly $20.00 /month` at sign-up, and a priced `Claude by Anthropic : Claude Pro - Monthly (Monthly)` at sign-up and each renewal. There are annual (`/year`, `(Annual)`, `(Yearly)`) and Max 5x variants. `Usage credits` are one-off purchases. Cancellations read `Claude by Anthropic Claude Pro - Monthly (1 month)`.

**Filters used**
- Gross adds: the first in a series of confirmations or priced subscription receipts for the `Claude by Anthropic` app. Usage credits are excluded, and annual plans use the 400-day window.
- Churn: `iTunes Cancellation` rows starting `claude by anthropic`. This excludes third-party Claude Code IDE apps.
""")
code("""
cl_it = build(m_it, signup=(df.merchant_id == 5) & IT_SIGNUP, pay=(df.merchant_id == 5) & IT_PAY & ~has("credits"),
              cancel=(df.merchant_id == 20122), annual=IT_ANNUAL)
show(cl_it, "Claude iTunes: monthly gross adds and churn")
""")
md("### 2d. Claude: channel comparison")
code("""
compare({"Direct": cl_dir, "Google Play": cl_gp, "iTunes": cl_it}, "Claude: gross adds and churn by channel", model=model_tab("claude"))
""")
md("""
**Reading it**
- **The trends are almost identical across channels:** monthly correlations are 0.97–1.00 for both adds and churn. All three show the step-up from January 2026, a peak in March–April 2026, and a decline since.
- **Direct dominates:** about 80% of adds and 75% of churn, against iTunes at about 17–19% and Google Play at 3–6%. Any channel tracks the Claude trend well, but direct carries most of the volume.
- **Modelled vs observed:** the model reads all three channels and matches them almost perfectly (correlation 0.97–1.00). Modelled adds are about 0.77 times the sum of the channel lines, because the channel view counts a mailbox again in each channel it uses and restarts a series after a cancellation. Modelled churn equals the sum of cancellations over the period (ratio 1.00).
""")

# ---------------------------------------------------------------- Gemini
md("""
## 3. Gemini

**Merchants found:** no `Gemini` merchant. Gemini consumer plans are sold as **Google One** AI plans (`Google AI Plus / Pro / Ultra`, formerly `Google One AI Premium`), under `Google One` (20187) and `Google One Cancellation` (20191). Google One also sells storage-only plans (`100 GB`, `2 TB`…), which are excluded here. From January 2026, the 2 TB plan has included AI Plus features in some markets, so a plan is counted only when its name says AI.
""")
md("### 3a. Direct (`Google One`, `Google One Cancellation`)")
code("""
m_dir = df.merchant_id.isin([20187, 20191])
G_AI = r"google ai|ai premium|ai pro\\b|ai plus|ai ultra"
patterns(m_dir & has(G_AI), top=12)
""")
md("""
- `Google One` sends **welcome emails only**, all unpriced: `Welcome to Google AI Pro …`, `Welcome to Google One AI Premium …`, `Welcome back to Google One …`. There are no payment receipts, so the direct channel is sign-up only.
- `Google One Cancellation` sends `Google AI Pro plan has ended`, `… has been canceled`, `Google AI Pro trial has ended`, and similar.
- **Google sends these emails whatever the billing channel.** About 64% of AI welcome emails come within 5 days of a Google Play AI receipt for the same mailbox, and about 2% within 5 days of an iTunes one. "Direct" for Gemini is therefore mostly Google Play subscribers seen through a second email, not a separate channel. A **direct-only** variant drops welcomes and cancellations that have a store AI receipt for the same mailbox within ±5 days (welcomes) or in the 75 days before (cancellations).

**Filters used**
- Gross adds: `Google One` rows starting `welcome` that name an AI plan (`google ai|ai premium|ai pro|ai plus|ai ultra`).
- Churn: `Google One Cancellation` rows that name an AI plan and say `ended`, `canceled` or `cancelled`. `… trial has ended` is excluded, because the trial was never paid.
""")
code("""
g_store = df[(df.channel != "direct") & ~df.cancel_sender & has(G_AI) & df.priced][["mailbox_id", "dt"]].rename(columns={"dt": "sdt"})
def near_store(mask, before, after):
    x = df[mask][["mailbox_id", "dt"]].reset_index().merge(g_store, on="mailbox_id")
    d = (x.sdt - x.dt).dt.days
    return df.index.isin(x[(d >= -before) & (d <= after)]["index"].unique())
gw = (df.merchant_id == 20187) & has(r"^welcome") & has(G_AI)
gc = (df.merchant_id == 20191) & has(G_AI) & has(r"ended|cancell?ed") & ~has(r"trial has ended")
gm_dir = build(m_dir, signup=gw, pay=None, cancel=gc)
gm_dir_only = build(m_dir, signup=gw & ~near_store(gw, 5, 5), pay=None, cancel=gc & ~near_store(gc, 75, 0))
show(gm_dir, "Gemini direct (all Google One AI emails): monthly gross adds and churn")
show(gm_dir_only, "Gemini direct-only (no store AI receipt nearby): monthly gross adds and churn")
""")
md("### 3b. Google Play")
code("""
m_gp = (df.channel == "gp") & has(r"google one|google ai|gemini")
patterns(m_gp, top=10)
sequences(m_gp & has(r"google one"), n=3, seed=5)
""")
md("""
- `Google AI Pro (2 TB) (Google One) (by Google LLC) Auto-renewing subscription` (and AI Plus, AI Premium, AI Ultra) is priced and sent at sign-up and **each renewal**. Storage-only plans such as `100 GB (Google One) … Auto-renewing` use the same format.
- Cancellations mostly **don't name the plan**: `Google One subscription from Google LLC on Google Play has been canceled` / `… will be canceled on <date>`. Only the `Google One (Google AI Pro (2 TB)) subscription will end on…` reminder names it (about 8% of rows).

**Filters used**
- Gross adds: `Google Play` rows with `(google one)` and `auto-renewing subscription` that name an AI plan. The first in each series is the add, so a switch from storage to AI counts as an add here.
- **Rename exclusion:** in May and June 2026, Google renamed the 2 TB storage plan ($9.99) to `Google AI Plus (2 TB)` for existing subscribers, so their next receipt carries an AI plan name at the same price. Without a correction, about 30k storage subscribers show up as AI adds in those two months. An AI add is dropped if the mailbox had a Google Play storage receipt **at the same price** in the 45 days before it. Paid upgrades from storage, at a different price, still count.
- Churn: `Google Play Cancellation` rows mentioning `google one`. A row counts as AI churn if it names an AI plan, or if the mailbox's last Google Play Google One receipt before it (within 75 days) was an AI plan.
""")
code("""
gp_g1 = df[GP_PAY & has(r"\\(google one\\)")][["mailbox_id", "dt", "d", "item_price"]].sort_values("dt")
gp_g1["ai"] = gp_g1.d.str.contains(G_AI)
gcan = df[(df.merchant_id == 3452) & has(r"google one")][["mailbox_id", "dt", "d"]].reset_index().sort_values("dt")
last = pd.merge_asof(gcan, gp_g1.rename(columns={"dt": "pdt", "d": "pd"}), left_on="dt", right_on="pdt", by="mailbox_id",
                     direction="backward", tolerance=pd.Timedelta(days=75))
ai_cancel = last[last.d.str.contains(G_AI) | last.ai.fillna(False).astype(bool)]["index"]
print(f"Google Play Google One cancellations: {len(gcan):,}; attributed to AI plans: {len(ai_cancel):,} "
      f"(named AI {gcan.d.str.contains(G_AI).sum():,}; via last receipt {len(ai_cancel) - gcan.d.str.contains(G_AI).sum():,})")
gtab, gadds, gchurn = build(m_gp, signup=None, pay=GP_PAY & has(r"\\(google one\\)") & has(G_AI), cancel=df.index.isin(ai_cancel), parts=True)
# rename exclusion: same-price storage receipt in the 45 days before the AI add
price = gp_g1[gp_g1.ai].drop_duplicates(["mailbox_id", "dt"])[["mailbox_id", "dt", "item_price"]]
ga = gadds.merge(price, on=["mailbox_id", "dt"], how="left").sort_values("dt")
st = gp_g1[~gp_g1.ai][["mailbox_id", "dt", "item_price"]].rename(columns={"dt": "sdt", "item_price": "sprice"}).sort_values("sdt")
ga = pd.merge_asof(ga, st, left_on="dt", right_on="sdt", by="mailbox_id", direction="backward", tolerance=pd.Timedelta(days=45))
ga["is_rename"] = ga.sprice.notna() & (ga.sprice.round(2) == ga.item_price.round(2))
print("AI adds dropped as same-price storage renames, by month:")
display(ga[ga.is_rename].assign(month=ga.dt.dt.to_period("M")).groupby("month").size().rename("renames").loc["2025-01":].to_frame().T)
gm_gp = R.monthly(ga[~ga.is_rename], gchurn); gm_gp.attrs = gtab.attrs
EVENTS[id(gm_gp)] = (ga[~ga.is_rename][["mailbox_id", "dt", "row"]], gchurn[["mailbox_id", "dt", "row"]], EVENTS[id(gtab)][2])
show(gm_gp, "Gemini Google Play: monthly gross adds and churn")
""")
md("### 3c. iTunes (App Store)")
code("""
m_it = (df.channel == "itunes") & has(G_AI)
patterns(m_it, top=12)
sequences(m_it, n=3, seed=5)
""")
md("""
Google AI plans are sold in several Google iOS apps: `Google Gemini`, `Google One`, `Google Photos`, `Gmail`, `Google NotebookLM`. Each has an unpriced confirmation (`Google Gemini Google AI Pro (2 TB) $19.99 /month`) and a priced receipt per sign-up and renewal (`Google Gemini : Google AI Pro (2 TB) (Monthly)`). Some priced rows are bare `Google AI Plus` / `Google AI Pro (2 TB)` with no app name. Cancellations read `Google Gemini Google AI Pro (2 TB) (1 month)`. Storage-only (`Google One : 100 GB`) and third-party "Gemini" apps (duplicate finders, photo cleaners) don't name a Google AI plan, so the AI-plan filter drops them.

**Filters used**
- Gross adds: the first in a series of confirmations or priced receipts naming a Google AI plan (`google ai|ai premium|ai pro|ai plus|ai ultra`). Bare priced `Google AI …` rows count as paid.
- Churn: `iTunes Cancellation` rows naming a Google AI plan.
""")
code("""
gm_it = build(m_it, signup=(df.merchant_id == 5) & IT_SIGNUP,
              pay=(df.merchant_id == 5) & df.priced & (IT_PAY | has(r"^google ai (plus|pro|ultra)")),
              cancel=(df.merchant_id == 20122), annual=IT_ANNUAL)
show(gm_it, "Gemini iTunes: monthly gross adds and churn")
""")
md("### 3d. Gemini: channel comparison")
code("""
compare({"Direct": gm_dir, "Direct-only": gm_dir_only, "Google Play": gm_gp, "iTunes": gm_it}, "Gemini (Google AI plans): gross adds and churn by channel",
        extra_styles={"Direct-only": {"color": COLORS["Direct"], "ls": "--"}}, model=model_tab("gemini"), model_covers=["Google Play", "iTunes"])
""")
md("""
**Reading it**
- **Google Play and iTunes agree** (add correlation 0.78, churn 0.67): both rise from mid-2025, and Google Play adds rise again from June 2026, after the rename spike was removed. Google Play is about 10 times iTunes. Google's AI plans are mostly bought on Android or Google's web.
- **The Google One "direct" emails are not a clean third channel.** Most welcome emails duplicate store subscriptions, and many are probably free trials or promotional offers: the emails are unpriced, and about a quarter of direct cancellations have no welcome email in the prior 400 days. Removing the welcomes that match a store receipt gives a **direct-only** line that moves *against* the stores (correlation −0.27 for adds). That fits it being mostly promotional sign-ups rather than paid web subscriptions. Treat the direct lines as sign-up intent, not paid adds.
- **Modelled vs observed:** the model reads Google Play and iTunes and follows Google Play for adds (0.57) and churn (0.80). It differs in two places:
  - **February 2026 spike (about 23k).** The model counts the 2 TB storage plan as AI Plus from 2026-01-27, so about 19k existing 2 TB subscribers become `ai_plus_2tb_M` adds in February. The channel view drops the matching May–June 2026 rename instead. The two views treat the same 2 TB population differently, and one should be aligned with the other.
  - **Modelled churn rises above every channel from March 2026.** This follows from the larger 2 TB base the model carries.
""")

# ---------------------------------------------------------------- Grok
md("""
## 4. Grok

**Merchants found: no direct Grok / xAI merchant, and no cancellation merchant.** I searched `items_v` merchant names (`grok`, `xai`, `x corp`, `twitter`) and descriptions (`\\bgrok\\b`, `supergrok`) outside the app stores. The only xAI-adjacent sender is `Twitter` (3677), whose rows are all an unpriced `Payment` with no plan name, so they can't be tied to Grok. X Premium+ (which includes Grok) is an X product and is not counted. **This section has Google Play and iTunes only.**
""")
md("### 4a. Google Play")
code("""
m_gp = (df.channel == "gp") & has(r"\\bgrok\\b|supergrok|super grok|x\\.ai")
patterns(m_gp, top=10)
sequences(m_gp, n=3, seed=2)
""")
md("""
xAI has published the app under several names (`Grok - AI Chat & Video`, `Grok – Smartest AI Advisor`, `Grok AI`, `Grok - AI Assistant`). Each sends a priced `SuperGrok (…) Auto-renewing subscription` (plus `SuperGrok Lite` / `Heavy`) at sign-up and **each renewal**. `Grok credits` are one-off. Free-trial notices (`Your trial will end on…`) are common for Grok. Cancellations read `Your <app> subscription from X.AI Corp. on Google Play will be canceled on…`, `… has been canceled.` and `Grok - AI Chat & Video (SuperGrok) subscription will end on…`.

**Filters used**
- Gross adds: `Google Play` rows matching `super ?grok` and `auto-renewing subscription`. The first in each series is the add.
- Churn: `Google Play Cancellation` rows mentioning `x.ai corp` or `(super ?grok`.
""")
code("""
gk_gp = build(m_gp, signup=None, pay=GP_PAY & has(r"super ?grok") & has("auto-renewing subscription"),
              cancel=(df.merchant_id == 3452) & has(r"x\\.ai corp|\\(super ?grok"))
show(gk_gp, "Grok Google Play: monthly gross adds and churn")
""")
md("### 4b. iTunes (App Store)")
code("""
m_it = (df.channel == "itunes") & has(r"super ?grok")
patterns(m_it, top=12)
sequences(m_it, n=3, seed=2)
""")
md("""
The structure matches the other apps: an unpriced confirmation (`Grok SuperGrok $29.99 /month`), a priced `Grok : SuperGrok (Monthly)` at sign-up and each renewal, and `iTunes Cancellation` `Grok SuperGrok (1 month)`. Grok also has many **free-trial confirmations** (`Grok SuperGrok 3 days, starting … free trial. Price: …`), about 18k rows since July 2024. These are excluded, as on Google Play. `Extra usage credits` are one-off.

**Filters used**
- Gross adds: the first in a series of confirmations (excluding free-trial ones) or priced `(monthly)` / `(annual)` receipts mentioning `super ?grok`.
- Churn: `iTunes Cancellation` rows mentioning `super ?grok` (SuperGrok, Lite, Heavy, Plus). This excludes third-party apps such as `Grok Bot Pro`.
""")
code("""
gk_it = build(m_it, signup=(df.merchant_id == 5) & IT_SIGNUP, pay=(df.merchant_id == 5) & IT_PAY & ~has("credits"),
              cancel=(df.merchant_id == 20122), annual=IT_ANNUAL)
show(gk_it, "Grok iTunes: monthly gross adds and churn")
""")
md("### 4c. Grok: channel comparison")
code("""
compare({"Google Play": gk_gp, "iTunes": gk_it}, "Grok: gross adds and churn by channel (no direct receipts)", model=model_tab("grok", exclude_plans=r"^(premium_plus|xsub)"))
""")
md("""
**Reading it**
- **The two stores agree closely** (add correlation 0.90, churn 0.81). iTunes carries about three-quarters of both adds and churn.
- **Churn exceeds gross adds** on both stores. About 40–50% of Grok cancellations have no prior paid or confirmation email in that channel, which fits free trials being cancelled before the first charge (Grok trials are very common). The churn line therefore includes trial cancellations as well as paid churn. The early-2026 churn spike on both stores coincides with heavy trial volumes.
- **Modelled vs observed:** the modelled line excludes X Premium+ plans, to match the stores here. Modelled adds track both stores closely (0.98 Google Play, 0.95 iTunes) at about 0.8 times their sum. Modelled churn is only about 0.4 times the cancellation emails, and it doesn't show the early-2026 cancellation spike. That fits most of those cancellations being trials that never paid, which the model doesn't count as subscriptions.
""")

# ---------------------------------------------------------------- Perplexity
md("""
## 5. Perplexity

**Merchants found:** `Perplexity AI` (4212) and `Perplexity AI Cancellation` (4213). Both direct merchants exist.
""")
md("### 5a. Direct (`Perplexity AI`, `Perplexity AI Cancellation`)")
code("""
m_dir = df.merchant_id.isin([4212, 4213])
patterns(m_dir, top=10)
sequences(m_dir, n=4, seed=2)
""")
md("""
- `Perplexity AI` sends **welcome emails only** (unpriced): `Welcome to Perplexity` (free account), `Welcome to Perplexity Pro` / `Max`, plus `… via Samsung Galaxy`, `Enterprise Pro`, `for Education` and `API organization`. There are no payment receipts. **Caveat:** many Pro welcomes are promotional free Pro (partners, trials). Earlier receipt-tracker work found only about 11% of direct Pro welcomes followed by a paid receipt, so this series measures Pro activations, not paid adds.
- `Perplexity AI Cancellation`: `Pro subscription cancellation`, `Perplexity Pro plan has been canceled`, `Your Perplexity Pro subscription has been canceled`, plus `Perplexity Pro trial has ended` (a trial expiry, not a paid cancellation).

**Filters used**
- Gross adds: `^welcome to perplexity (pro|max)$`. Free accounts, Samsung Galaxy, Enterprise, Education and API are excluded.
- Churn: `Perplexity AI Cancellation` rows, excluding `trial has ended`.
""")
code("""
px_dir = build(m_dir, signup=(df.merchant_id == 4212) & has(r"^welcome to perplexity (pro|max)$"), pay=None,
               cancel=(df.merchant_id == 4213) & ~has(r"trial has ended"))
show(px_dir, "Perplexity direct: monthly gross adds and churn")
""")
md("### 5b. Google Play")
code("""
m_gp = (df.channel == "gp") & has(r"perplexity")
patterns(m_gp, top=8)
sequences(m_gp, n=3, seed=2)
""")
md("""
The structure matches ChatGPT on Google Play: `Perplexity Pro (Perplexity - Ask Anything) Auto-renewing subscription` (and Max) is priced at sign-up and each renewal, and `# Credits` are one-off. Cancellations read `Your Perplexity - Ask Anything subscription from Perplexity AI Inc … will be canceled on…`, `… has been canceled.` and `… (Perplexity Pro) subscription will end on…`.

**Filters used**
- Gross adds: `Google Play` rows matching `perplexity (pro|max) \\(perplexity.*auto-renewing subscription`.
- Churn: `Google Play Cancellation` rows mentioning `perplexity`.
""")
code("""
px_gp = build(m_gp, signup=None, pay=GP_PAY & has(r"perplexity (pro|max) \\(perplexity.*auto-renewing subscription"),
              cancel=(df.merchant_id == 3452))
show(px_gp, "Perplexity Google Play: monthly gross adds and churn")
""")
md("### 5c. iTunes (App Store)")
code("""
m_it = (df.channel == "itunes") & has(r"perplexity (pro|max)")
patterns(m_it, top=12)
sequences(m_it, n=3, seed=2)
""")
md("""
The structure matches the other apps. There is a confirmation `Perplexity - AI Search & Chat Perplexity Pro $20.00 /month` and a priced receipt per sign-up and renewal (`… : Perplexity Pro (Monthly)`, `(Annual)`). The app has two names (`Perplexity - Ask Anything`, then `Perplexity - AI Search & Chat`), and there is a Mac app (`Perplexity Pro for Mac`) and Comet (`Comet - AI Browser & Assistant Perplexity Pro`). Cancellations read `… Perplexity Pro (1 month)`. Credits are excluded by the plan filter.

**Filters used**
- Gross adds: the first in a series of confirmations or priced subscription receipts mentioning `perplexity (pro|max)`. Annual plans use the 400-day window.
- Churn: `iTunes Cancellation` rows mentioning `perplexity (pro|max)`.
""")
code("""
px_it = build(m_it, signup=(df.merchant_id == 5) & IT_SIGNUP, pay=(df.merchant_id == 5) & IT_PAY,
              cancel=(df.merchant_id == 20122), annual=IT_ANNUAL)
show(px_it, "Perplexity iTunes: monthly gross adds and churn")
""")
md("### 5d. Perplexity: channel comparison")
code("""
compare({"Direct": px_dir, "Google Play": px_gp, "iTunes": px_it}, "Perplexity: gross adds and churn by channel", model=model_tab("perplexity"), model_covers=["Google Play", "iTunes"])
""")
md("""
**Reading it**
- **Direct is not comparable with the stores.** Direct "adds" are Pro welcome emails, which are dominated by promotional free Pro activations: the July 2025 spike of about 8.8k and the elevated autumn 2025 months look promotional. Direct does not correlate with the stores (−0.27 against iTunes for adds). Direct churn also changes wording twice (January 2026, July 2026), and the September 2026 spike falls in the new `Your Perplexity Pro subscription has been canceled` format, consistent with a promotional cohort expiring.
- **iTunes and Google Play agree reasonably on adds** (0.68), and iTunes is about 6 times Google Play. Both are small.
- **Modelled vs observed:** the model reads Google Play and iTunes and follows iTunes almost exactly for adds (0.98) and churn (0.82), at about 0.8 times the two stores combined. Direct Perplexity (welcome emails) is not in the model.
""")

# ---------------------------------------------------------------- Muse
md("""
## 6. Muse (Meta)

**Merchants found: no `Muse` merchant and no Muse cancellation merchant.** Muse rows sit under `Meta` (3848) and come only from the descriptions. Meta carries:
- `Welcome to Muse Code Everyday / High / Power / Maximum usage`: priced ($5 / $15 / $50 / $200) sign-up emails for **Muse Code** plans, since September 2026. These are the only direct subscription-like emails, so they are used as the direct series.
- `Muse Spark / Wonder / Image … tokens`: API usage, excluded.
- `Age confirmation on Muse` and `Welcome to the confidential early testing program for Muse`: not subscriptions, excluded.

**No direct receipts were found for the consumer Power / Maximum plans bought on the web**, and Meta has no cancellation sender. The direct line is therefore Muse Code sign-ups only and is **not comparable** to the store lines. Muse launched on 2026-09-07, so every series starts then.
""")
md("### 6a. Direct (`Meta`)")
code("""
m_dir = (df.merchant_id == 3848)
patterns(m_dir & has(r"\\bmuse\\b"), top=15)
mu_dir = build(m_dir, signup=has(r"^welcome to muse code .*usage$"), pay=None, cancel=pd.Series(False, index=df.index))
show(mu_dir, "Muse direct (Muse Code welcome emails): monthly gross adds")
""")
md("### 6b. Google Play")
code("""
m_gp = (df.channel == "gp") & has(r"muse from meta")
patterns(m_gp, top=8)
sequences(m_gp, n=3, seed=1, since="2026-09-01")
""")
md("""
`Power Plan (Muse from Meta) Auto-renewing subscription` ($20) and `Maximum Plan (Muse from Meta) …` ($100) are priced and sent at sign-up and each renewal. Cancellations read `Your Muse from Meta subscription from Facebook Inc on Google Play will be canceled on…` and `Muse from Meta (Power Plan) subscription will end on…`. Volumes are small (under 200 rows).

**Filters used**
- Gross adds: `Google Play` rows matching `\\(muse from meta\\) auto-renewing subscription`.
- Churn: `Google Play Cancellation` rows mentioning `muse from meta`.
""")
code("""
mu_gp = build(m_gp, signup=None, pay=GP_PAY & has(r"\\(muse from meta\\) auto-renewing subscription"),
              cancel=(df.merchant_id == 3452))
show(mu_gp, "Muse Google Play: monthly gross adds and churn")
""")
md("### 6c. iTunes (App Store)")
code("""
m_it = (df.channel == "itunes") & (has(r"^muse from meta") | df.d.isin(["power plan", "maximum plan"]) | has(r"^(power|maximum) plan : (power|maximum) plan"))
patterns(m_it, top=10)
sequences(m_it, n=3, seed=1, since="2026-09-01")
""")
md("""
Apple's Muse receipts **don't name the app on the priced row**. At sign-up there is an unpriced confirmation `Muse from Meta Power Plan $20.00 /month` and a priced receipt that reads only `Power Plan` / `Maximum Plan`. Renewals read `Power Plan : Power Plan (Monthly)`, with the plan used as the app name. Cancellations read `Muse from Meta Power Plan (1 month)`. Rows from unrelated apps (`Power Planner`, `AI-Story … Unlimited Power Plan`) are excluded by requiring the exact `Power Plan` / `Maximum Plan` description or the `Muse from Meta` prefix.

**Filters used**
- Gross adds: the first in a series of `Muse from Meta … /month` confirmations, bare priced `Power Plan` / `Maximum Plan`, or `Power|Maximum Plan : … (Monthly)`.
- Churn: `iTunes Cancellation` rows starting `muse from meta`.
""")
code("""
mu_it = build(m_it, signup=(df.merchant_id == 5) & IT_SIGNUP, pay=(df.merchant_id == 5) & df.priced,
              cancel=(df.merchant_id == 20122))
mu_tabs = {k: v[v.index >= "2026-09"] for k, v in {"Direct": mu_dir, "Google Play": mu_gp, "iTunes": mu_it}.items()}
show(mu_tabs["iTunes"], "Muse iTunes: monthly gross adds and churn")
""")
md("### 6d. Muse: channel comparison")
code("""
compare({"Direct": mu_dir, "Google Play": mu_gp, "iTunes": mu_it}, "Muse: gross adds and churn by channel (direct = Muse Code only)", model=model_tab("muse"), model_covers=["Google Play", "iTunes"])
display(pd.concat(mu_tabs, axis=1))
""")
md("""
**Reading it**
- Muse launched on 2026-09-07, so there is only one complete month (September 2026) and a partial October. Correlations aren't meaningful yet.
- **iTunes captures the most Muse adds**, at about 2.5 times Google Play in both months. The direct line is Muse Code sign-ups only, because consumer web purchases of Power or Maximum send no receipt that NIQ captures, so it is not comparable.
- Churn is very small so far (single and double digits).
- **Modelled vs observed:** modelled adds for September 2026 (133) are about 0.66 times Google Play plus iTunes (203). Modelled churn is still zero, because the first cohorts haven't passed their lapse window.
""")

# ---------------------------------------------------------------- Summary
md("""
## 7. Summary across providers

Totals of gross adds and churn, complete months from 2025-01 (and the last three complete months). `churn_no_prior_add_share` is the share of cancellations whose mailbox had no sign-up or paid email in that channel in the prior 400 days. That covers trials cancelled before any payment and subscriptions whose receipts the panel missed. A high share means the churn line includes people who never show up as adds. A channel missing from a provider has no usable receipts.
""")
code("""
ALL = {"ChatGPT": {"Direct": cg_dir, "Google Play": cg_gp, "iTunes": cg_it},
       "Claude": {"Direct": cl_dir, "Google Play": cl_gp, "iTunes": cl_it},
       "Gemini": {"Direct": gm_dir, "Direct-only": gm_dir_only, "Google Play": gm_gp, "iTunes": gm_it},
       "Grok": {"Google Play": gk_gp, "iTunes": gk_it},
       "Perplexity": {"Direct": px_dir, "Google Play": px_gp, "iTunes": px_it},
       "Muse": {"Direct": mu_dir, "Google Play": mu_gp, "iTunes": mu_it}}
rows = []
MODELS = {"ChatGPT": "chatgpt", "Claude": "claude", "Gemini": "gemini", "Grok": "grok", "Perplexity": "perplexity", "Muse": "muse"}
for p, tabs in ALL.items():
    tabs = dict(tabs, Combined=combined({k: v for k, v in tabs.items() if k != "Direct-only"}), Modelled=model_tab(MODELS[p], exclude_plans=r"^(premium_plus|xsub)" if p == "Grok" else None))
    for ch, t in tabs.items():
        t = t[t.index >= "2025-01"]
        t = t[t.index <= LAST_FULL]
        rows.append(dict(provider=p, channel=ch, gross_adds=t.gross_adds.sum(), churn=t.churn.sum(),
                         adds_last3m=t.gross_adds.tail(3).sum(), churn_last3m=t.churn.tail(3).sum(),
                         churn_no_prior_add_share=round(t.attrs.get("churn_no_prior_add", np.nan), 3)))
summ = pd.DataFrame(rows).set_index(["provider", "channel"])
summ
""")
md("""
### Export for the app

Monthly gross adds, churn and net adds (gross adds minus churn) per provider and channel, plus the deduped combined series, for complete months from 2025-01. The combined series uses the agreed channel set: direct + Google Play + iTunes, except Perplexity and Grok (Google Play + iTunes only). Perplexity direct is mostly free promotional sign-ups, and Grok has no direct sender. Written to `../.cache/channel_cmp/channel_flows.parquet` and merged into the app by `app/channel_flows.py`.
""")
code("""
COMBINE = {"ChatGPT": ["Direct", "Google Play", "iTunes"], "Claude": ["Direct", "Google Play", "iTunes"],
           "Gemini": ["Direct", "Google Play", "iTunes"], "Grok": ["Google Play", "iTunes"],
           "Perplexity": ["Google Play", "iTunes"], "Muse": ["Direct", "Google Play", "iTunes"]}
out = []
for p, tabs in ALL.items():
    use = {k: v for k, v in tabs.items() if k in ("Direct", "Google Play", "iTunes")}
    for ch, t in dict(use, Combined=combined({k: use[k] for k in COMBINE[p]})).items():
        t = t[(t.index >= "2025-01") & (t.index <= LAST_FULL)]
        out.append(pd.DataFrame({"PROVIDER": p.lower(), "CHANNEL": ch, "MONTH": t.index.astype(str), "GROSS_ADDS": t.gross_adds.values,
                                 "CHURN": t.churn.values, "IN_COMBINED": ch in COMBINE[p] or ch == "Combined"}))
flows = pd.concat(out, ignore_index=True)
flows["NET_ADDS"] = flows.GROSS_ADDS - flows.CHURN
flows.to_parquet("../.cache/channel_cmp/channel_flows.parquet", index=False)
flows[flows.CHANNEL == "Combined"].pivot(index="MONTH", columns="PROVIDER", values="NET_ADDS").tail(6)
""")
md("""
### Plan-level split (combined series)

Each email is labelled with the plan it names (tier only; monthly and annual are pooled). Claude direct payments are labelled by price: $20 is Pro, $100 or $200 is Max.
- **Gross adds** take the plan of the first email in the series that names one (some iTunes confirmations and Google Play cancellations don't).
- **Plan switches:** within a series, a change in the named plan (e.g. Plus receipts, then Pro receipts) is a switch. It moves one subscriber from the old plan to the new one, so it is not churn plus a new add. The same switch seen in two channels within 45 days counts once.
- **Churn** takes the mailbox's plan at the time: the last plan named on a sign-up or paid email in any combined channel in the 400 days before the cancellation. Failing that, it uses the plan the cancellation names, else `Unspecified`.
- **Plan net adds** = gross adds + switches in − churn − switches out. Switches net to zero across plans, so plan net adds sum to the provider's net adds. Small differences remain from counting distinct mailboxes per month.

Plan labels:

| Provider | Plans |
|---|---|
| ChatGPT | Plus, Go, Pro |
| Claude | Pro, Max |
| Gemini | AI Plus, AI Pro (incl. AI Premium), AI Ultra |
| Grok | SuperGrok, Lite, Heavy |
| Perplexity | Pro, Max |
| Muse | Power, Maximum, Muse Code (direct) |
""")
code("""
def first_match(rules):
    '''Plan label per row: the first (plan, regex) whose regex matches the description, else None.'''
    out = pd.Series(None, index=df.index, dtype=object)
    for plan, rx in rules:
        out = out.where(out.notna(), pd.Series(np.where(has(rx), plan, None), index=df.index))
    return out

claude_pay = pd.Series(np.select([(df.merchant_id == 20127) & (df.d == "payment") & (df.item_price == 20),
                                  (df.merchant_id == 20127) & (df.d == "payment") & df.item_price.isin([100, 200])], ["Pro", "Max"], None), index=df.index)
muse_code = pd.Series(np.where(df.merchant_id == 3848, "Muse Code", None), index=df.index)
PLANS = {
    "ChatGPT": first_match([("Pro", r"\\bpro\\b"), ("Plus", r"\\bplus\\b"), ("Go", r"\\bgo\\b")]),
    "Claude": claude_pay.where(claude_pay.notna(), first_match([("Max", r"\\bmax\\b"), ("Pro", r"\\bpro\\b")])),
    "Gemini": first_match([("AI Ultra", r"ai ultra"), ("AI Plus", r"ai plus"), ("AI Pro", r"ai pro\\b|ai premium")]),
    "Grok": first_match([("Heavy", r"heavy"), ("Lite", r"lite"), ("SuperGrok", r"super ?grok")]),
    "Perplexity": first_match([("Max", r"\\bmax\\b"), ("Pro", r"\\bpro\\b")]),
    "Muse": muse_code.where(muse_code.notna(), first_match([("Maximum", r"maximum"), ("Power", r"power")])),
}

def dedupe(ev, key=None):
    '''Drop an event within DEDUP_DAYS after one for the same mailbox (and key) in a different channel.'''
    by = ["mailbox_id"] + ([key] if key else [])
    ev = ev.sort_values(by + ["dt"]).reset_index(drop=True)
    same = ev[by].eq(ev[by].shift()).all(axis=1)
    return ev[~(same & ev.ch.ne(ev.ch.shift()) & ((ev.dt - ev.dt.shift()).dt.days <= DEDUP_DAYS))]

def plan_flows(tabs, lab):
    adds, churn, sigs, sw = [], [], [], []
    for ch, t in tabs.items():
        a, c, s = EVENTS[id(t)]
        s = s.assign(ch=ch, plan=lab.reindex(s.row).values, is_add=s.row.isin(set(a.row)))
        s = s.sort_values(["mailbox_id", "dt", "is_add"], ascending=[True, True, False]).reset_index(drop=True)
        s["series"] = (s.is_add | s.mailbox_id.ne(s.mailbox_id.shift())).cumsum()
        g = s.groupby("series").plan
        s["series_plan"] = g.ffill().where(lambda x: x.notna(), s.groupby("series").plan.bfill())
        k = s[s.plan.notna()].copy()
        k["prev"] = k.groupby("series").plan.shift()
        sw.append(k[k.prev.notna() & (k.prev != k.plan)][["mailbox_id", "dt", "ch", "prev", "plan"]])
        adds.append(s[s.is_add][["mailbox_id", "dt", "ch", "series_plan"]].rename(columns={"series_plan": "plan"}))
        churn.append(c.assign(ch=ch, own=lab.reindex(c.row).values))
        sigs.append(k[["mailbox_id", "dt", "plan"]])
    adds = dedupe(pd.concat(adds)); churn = dedupe(pd.concat(churn))
    sw = pd.concat(sw); sw["pair"] = sw.prev + ">" + sw.plan; sw = dedupe(sw, key="pair")
    kk = pd.concat(sigs).sort_values("dt")
    churn = pd.merge_asof(churn.sort_values("dt"), kk.rename(columns={"dt": "kdt"}), left_on="dt", right_on="kdt", by="mailbox_id",
                          direction="backward", tolerance=pd.Timedelta(days=400))
    churn["plan"] = churn.plan.fillna(churn.own).fillna("Unspecified")
    adds["plan"] = adds.plan.fillna("Unspecified")
    m = lambda e: e.assign(MONTH=e.dt.dt.to_period("M"))
    cnt = lambda e, by, name: m(e).groupby([by, "MONTH"]).mailbox_id.nunique().rename(name)
    t = pd.concat([cnt(adds, "plan", "GROSS_ADDS"), cnt(churn, "plan", "CHURN"),
                   cnt(sw.rename(columns={"plan": "to"}).assign(plan=lambda x: x.to), "plan", "SWITCH_IN"),
                   cnt(sw.assign(plan=sw.prev), "plan", "SWITCH_OUT")], axis=1).fillna(0).astype(int).reset_index()
    t = t.rename(columns={"plan": "PLAN"})
    t = t[(t.MONTH >= pd.Period("2025-01")) & (t.MONTH <= LAST_FULL)]
    plans = t.PLAN.unique(); months = pd.period_range("2025-01", LAST_FULL, freq="M")
    t = t.set_index(["PLAN", "MONTH"]).reindex(pd.MultiIndex.from_product([plans, months], names=["PLAN", "MONTH"]), fill_value=0).reset_index()
    t["NET_ADDS"] = t.GROSS_ADDS + t.SWITCH_IN - t.CHURN - t.SWITCH_OUT
    return t

pf = []
for p, tabs in ALL.items():
    use = {k: v for k, v in tabs.items() if k in COMBINE[p]}
    pf.append(plan_flows(use, PLANS[p]).assign(PROVIDER=p.lower()))
plan_flows_df = pd.concat(pf, ignore_index=True)
plan_flows_df["MONTH"] = plan_flows_df.MONTH.astype(str)
plan_flows_df.to_parquet("../.cache/channel_cmp/channel_flows_plan.parquet", index=False)

# check: plan net adds against the provider combined series, and how much is unlabelled
chk = plan_flows_df.groupby("PROVIDER")[["GROSS_ADDS", "CHURN", "SWITCH_IN", "NET_ADDS"]].sum()
prov = flows[flows.CHANNEL == "Combined"].groupby("PROVIDER")[["GROSS_ADDS", "CHURN", "NET_ADDS"]].sum().add_prefix("provider_")
uns = plan_flows_df[plan_flows_df.PLAN == "Unspecified"].groupby("PROVIDER")[["GROSS_ADDS", "CHURN"]].sum().add_prefix("unspecified_")
display(chk.join(prov).join(uns).fillna(0).astype(int))
display(plan_flows_df[plan_flows_df.MONTH >= "2026-07"].pivot_table(index=["PROVIDER", "PLAN"], columns="MONTH", values="NET_ADDS"))
""")

nb["cells"] = C
nb.metadata["kernelspec"] = {"name": "exploration", "display_name": "Python (exploration)", "language": "python"}
nbf.write(nb, "direct_v_channel_comparison.ipynb")
print("wrote direct_v_channel_comparison.ipynb", len(C), "cells")
