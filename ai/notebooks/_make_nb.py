"""Builds ai_subs_receipts_walkthrough.ipynb (run: python _make_nb.py, then execute with nbconvert)."""
import nbformat as nbf

nb = nbf.v4.new_notebook()
C = []
md = lambda s: C.append(nbf.v4.new_markdown_cell(s.strip()))
code = lambda s: C.append(nbf.v4.new_code_cell(s.strip()))

md("""
# Consumer AI subscriptions on e-receipts: a step-by-step walkthrough

This notebook shows how the `ai_consumer` job (branch `feat/ai-consumer-subs`) measures gross adds, churn and subscribers for each AI provider, using the tables its local run wrote to `SRS_MCP.AI_CONSUMER`. It also checks the meeting suggestion that NIQ's `CANCELLATION_ITEMS` feed holds cancellation emails we don't already read.

1. **Cancellation feed check:** `CANCELLATION_ITEMS` against `ITEMS_EXTENDED`.
2. **Receipts we classify:** what each provider's emails look like.
3. **Gross adds, step by step, per provider.**
4. **Churn, step by step, per provider:** observed lapses, then the churn rates the model uses.
5. **Subscribers:** the stock-flow index, reconciled month by month.

Set `REGION` to `"us"` or `"eu"`. Queries run on `ANALYST_L`.
""")
code("""
import pandas as pd, numpy as np, snowflake.connector as sc
from IPython.display import display
pd.set_option("display.width", 200); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 80)
con = sc.connect(connection_name="default"); con.cursor().execute("USE WAREHOUSE ANALYST_L")

def q(sql):
    cur = con.cursor(); cur.execute(sql); df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    return df

REGION = "us"
COUNTRY = "us" if REGION == "us" else "eu"
WINDOWS = pd.read_csv("../../../srs/workflows/jobs/ai/consumer/artifacts/engine/params/lapse_windows.csv")
DATA_END = pd.Timestamp(q(f"SELECT MAX(dt) AS d FROM srs_mcp.ai_consumer.receipt_events WHERE region = '{REGION}'").d[0])
print("data end:", DATA_END.date())
WINDOWS[WINDOWS.region == REGION][["prov", "channel", "capture_all", "W_monthly", "W_source", "rate_source"]]
""")

md("""
## 1. Does `CANCELLATION_ITEMS` add cancellation emails?

The question from the 20 Oct meeting was whether NIQ keeps most cancellations in a separate `SHARE_NIQ.SRS.CANCELLATION_ITEMS` view rather than in `ITEMS_EXTENDED`, the receipt table behind `srs_slice.common.items_v` that the job reads.

We match the two views on `item_id` for the cancellation senders that carry AI items:

| merchant_id | Sender |
|---|---|
| 20122 | iTunes Cancellation |
| 3452 | Google Play Cancellation |
| 20191 | Google One Cancellation |
| 4078 | Chat GPT Cancellation |
| 20139 | Anthropic Cancellation |
| 20140 | Cursor Cancellation |
| 4213 | Perplexity AI Cancellation |
""")
code("""
IDS = "20122, 3452, 20191, 4078, 20139, 20140, 4213"
overlap = q(f'''
WITH c AS (SELECT item_id, merchant_id, merchant_name FROM SHARE_NIQ.SRS.CANCELLATION_ITEMS
           WHERE merchant_id IN ({IDS}) AND order_date >= '2025-10-01'),
     e AS (SELECT item_id, merchant_id, merchant_name FROM SHARE_NIQ.SRS.ITEMS_EXTENDED
           WHERE merchant_id IN ({IDS}) AND order_date >= '2025-10-01')
SELECT COALESCE(c.merchant_id, e.merchant_id) AS merchant_id,
       COALESCE(ANY_VALUE(c.merchant_name), ANY_VALUE(e.merchant_name)) AS sender,
       COUNT(c.item_id) AS in_cancellation_items, COUNT(e.item_id) AS in_items_extended,
       COUNT_IF(c.item_id IS NOT NULL AND e.item_id IS NOT NULL) AS in_both,
       COUNT_IF(e.item_id IS NULL) AS only_in_cancellation_items
FROM c FULL OUTER JOIN e ON c.item_id = e.item_id
GROUP BY 1 ORDER BY 1''')
overlap["share_of_ci_already_read"] = (overlap.in_both / overlap.in_cancellation_items.replace(0, np.nan)).round(4)
overlap
""")
md("""
**Reading it:** almost every `CANCELLATION_ITEMS` row (October 2025 onward) is already in `ITEMS_EXTENDED`, so we already read it. Perplexity AI Cancellation (4213) has no rows in `CANCELLATION_ITEMS`, but we read it from `ITEMS_EXTENDED`.

Next: are the few rows found only in `CANCELLATION_ITEMS` AI cancellations, and are they in mailboxes still in the panel?
""")
code("""
extra = q(f'''
WITH c AS (SELECT item_id, mailbox_id, merchant_id FROM SHARE_NIQ.SRS.CANCELLATION_ITEMS
           WHERE merchant_id IN ({IDS}) AND order_date >= '2022-01-01'
             AND (merchant_name || ' ' || COALESCE(description, '')) ILIKE ANY ('%chatgpt%', '%chat gpt%', '%openai%', '%anthropic%',
                 '%claude%', '%google ai%', '%gemini%', '%ai premium%', '%ai pro%', '%grok%', '%x premium%', '%premium+%', '%muse%',
                 '%power plan%', '%perplexity%', '%cursor%')),
     e AS (SELECT item_id FROM SHARE_NIQ.SRS.ITEMS_EXTENDED WHERE merchant_id IN ({IDS}) AND order_date >= '2021-12-01'),
     act AS (SELECT mailbox_id FROM SHARE_NIQ.SRS.MAILBOXES_ENHANCED WHERE status = 'ACTIVE')
SELECT c.merchant_id, COUNT(*) AS ai_cancel_rows, COUNT_IF(e.item_id IS NULL) AS only_in_cancellation_items,
       COUNT_IF(e.item_id IS NULL AND c.mailbox_id IN (SELECT mailbox_id FROM act)) AS only_in_ci_active_mailbox
FROM c LEFT JOIN e ON c.item_id = e.item_id
GROUP BY 1 ORDER BY 1''')
extra.loc["total"] = extra.sum(numeric_only=True)
extra
""")
md("""
**Conclusion:** `CANCELLATION_ITEMS` adds essentially nothing for these providers. The rows missing from `ITEMS_EXTENDED` almost all come from mailboxes that have left the panel, which the panel rules exclude anyway. Only a few dozen AI cancellation rows since 2022 sit in active mailboxes. Cancellation coverage therefore stays where Phase 1 measured it (no provider × channel reaches 95%), and churn stays lapse-based.
""")

md("""
## 2. The receipts we classify

`receipt_events` holds one row per kept paid receipt (`kind = 'charge'`) or cancellation email (`kind = 'cancel'`). Each row carries its provider, plan (tier × cadence) and billing channel.

Direct ChatGPT paid receipts are kept with `reference_only = TRUE`: they are sign-ups only, with no renewals, so they never form subscriptions. Below are the last 12 months by provider × channel × kind.
""")
code("""
mix = q(f'''
SELECT provider, channel, kind, COUNT(*) AS rows_, COUNT(DISTINCT uid) AS members
FROM srs_mcp.ai_consumer.receipt_events
WHERE region = '{REGION}' AND dt > DATEADD(month, -12, '{DATA_END.date()}') AND NOT reference_only
GROUP BY ALL ORDER BY provider, channel, kind''')
mix.pivot_table(index=["provider", "channel"], columns="kind", values=["rows_", "members"], aggfunc="sum").fillna(0).astype(int)
""")
code("""
# A few recent raw receipt lines from items_v behind the classification (US only).
if REGION == "us":
    display(q('''
    SELECT merchant_name, description, item_price, order_date
    FROM srs_slice.common.items_v
    WHERE merchant_id IN (5, 20122, 1493, 3452, 4070, 4078, 20127, 20139, 20187, 20191, 4212, 4213)
      AND order_date >= DATEADD(day, -14, CURRENT_DATE)
      AND description ILIKE ANY ('%chatgpt%', '%claude%', '%google ai%', '%supergrok%', '%perplexity%', '%muse%', '%power plan%')
    QUALIFY ROW_NUMBER() OVER (PARTITION BY merchant_name, LEFT(description, 25) ORDER BY order_date DESC) = 1
    ORDER BY merchant_name LIMIT 40'''))
""")

md("""
## 3 and 4. Gross adds and churn, step by step

For each provider, `walkthrough(provider)` reproduces the rules from `FINAL_SPEC.md` in plain pandas.

**Gross adds**
1. Take the provider's paid receipts (`kind = 'charge'`, `reference_only = FALSE`), one per member per day.
2. Sort each member's receipts by date. A new subscription starts at the first receipt, and again whenever the gap since the previous receipt is longer than the lapse window `W`.
   - `W` is the 99th-percentile renewal gap for that provider × channel (`lapse_windows.csv`; 135 days for quarterly plans, 400 for annual).
3. **Gross add** = the first receipt of each subscription, counted in the month it falls in.

**Churn (observed)**
4. A subscription ends when no receipt arrives within `W` of its last payment. The churn is dated when it becomes known: last payment + `W`.
   - Subscriptions whose window hasn't passed by the data end are still live.
5. **Observed churn rate** = churns detected in the month ÷ subscriptions live at the start of the month.

The model differs from this simplified version in four ways:
- Churn **rates** come only from members whose renewals we see reliably: the full panel on channels with ≥ 97.5% capture, and the reliable subset (another regular subscription email in the same mailbox that month) for Apple and the rest. See the `churn_rates` table.
- The rates are applied to all subscriptions by plan and tenure.
- It handles mailbox exits and held months.
- A cancel followed by a later payment counts as churn plus a gross add.

So the simple counts below should be close to, but not exactly equal to, the published `subs_monthly` (`pub_*` columns). What to look for:

- **Gross adds:** published is a few percent higher. It also counts a re-subscription after a cancellation as a new add, and uses mailbox history the simple version drops.
- **Churn rate:** for Apple-heavy providers (ChatGPT, Grok, Perplexity) the simple rate is higher than published. A missed Apple renewal email looks like churn in the simple version. The model avoids this by taking Apple's rate only from the reliable subset, which is the reason that subset exists.
- **Claude and Gemini:** mostly direct and Google Play, where nearly every renewal is captured, so simple and published churn are close (published a little higher, because it adds the cancel-then-pay churns).
- **`pub_subs` vs `live_end`:** `live_end` is the observed count, equal to `pub_subs_observed`. `pub_subs` is the modelled count, which adds back Apple subscribers wrongly treated as churned.
""")
code("""
def load_charges(provider):
    ev = q(f'''
    SELECT uid, dt, channel, plan, cadence
    FROM srs_mcp.ai_consumer.receipt_events
    WHERE region = '{REGION}' AND provider = '{provider}' AND kind = 'charge' AND NOT reference_only
    QUALIFY ROW_NUMBER() OVER (PARTITION BY uid, dt ORDER BY channel) = 1''')
    ev["dt"] = pd.to_datetime(ev.dt)
    w = WINDOWS[(WINDOWS.region == REGION) & (WINDOWS.prov == provider)].set_index("channel").W_monthly
    ev["W"] = np.select([ev.cadence == "A", ev.cadence == "Q"], [400, 135], ev.channel.map(w).fillna(62)).astype(int)
    return ev.sort_values(["uid", "dt"]).reset_index(drop=True)

def build_subs(ev):
    gap = ev.groupby("uid").dt.diff().dt.days
    prev_W = ev.groupby("uid").W.shift()
    ev["new_sub"] = gap.isna() | (gap > prev_W)                      # step 2
    ev["sub_id"] = ev.new_sub.cumsum()
    s = ev.groupby("sub_id").agg(uid=("uid", "first"), start=("dt", "first"), last_pay=("dt", "last"),
                                 n_pay=("dt", "size"), channel=("channel", "first"), plan=("plan", "first"),
                                 W=("W", "last"))
    s["detect"] = s.last_pay + pd.to_timedelta(s.W, unit="D")      # step 4
    s["churned"] = s.detect <= DATA_END
    return ev, s

def monthly(s):
    out = []
    for m in pd.period_range("2024-01", DATA_END.to_period("M"), freq="M"):
        ms, me = m.start_time, min(m.end_time.normalize(), DATA_END)
        live_start = ((s.start < ms) & (~s.churned | (s.detect >= ms))).sum()
        out.append(dict(month=str(m),
                        gross_adds=((s.start >= ms) & (s.start <= me)).sum(),             # step 3
                        churn=(s.churned & (s.detect >= ms) & (s.detect <= me)).sum(),    # step 4
                        live_start=live_start,
                        live_end=((s.start <= me) & (~s.churned | (s.detect > me))).sum()))
    d = pd.DataFrame(out)
    d["churn_rate"] = (d.churn / d.live_start.replace(0, np.nan)).round(4)                  # step 5
    return d

def published(provider):
    return q(f'''
    SELECT TO_VARCHAR(month, 'YYYY-MM') AS month, gross_adds AS pub_gross_adds, ROUND(churn) AS pub_churn,
           ROUND(churn_rate, 4) AS pub_churn_rate, ROUND(subs) AS pub_subs, subs_observed AS pub_subs_observed, held
    FROM srs_mcp.ai_consumer.subs_monthly
    WHERE region = '{REGION}' AND country = '{COUNTRY}' AND provider = '{provider}' AND plan = 'all'
    ORDER BY 1''')

def rates(provider):
    return q(f'''
    SELECT TO_VARCHAR(month, 'YYYY-MM') AS month, channel, rate_source, SUM(active) AS active, SUM(churned) AS churned,
           ROUND(SUM(churned) / NULLIF(SUM(active), 0), 4) AS rate
    FROM srs_mcp.ai_consumer.churn_rates
    WHERE region = '{REGION}' AND provider = '{provider}' AND month >= DATEADD(month, -3, '{DATA_END.date()}')
    GROUP BY ALL ORDER BY month, channel''')

def walkthrough(provider, example_rows=12):
    ev = load_charges(provider)
    ev, s = build_subs(ev)
    print(f"{provider}: {len(ev):,} paid receipts, {ev.uid.nunique():,} members, {len(s):,} subscriptions")
    print("Lapse window W (days) by channel x cadence:", ev.groupby(["channel", "cadence"]).W.first().to_dict())
    many = s[s.n_pay >= 3].groupby("uid").size()
    ex_uid = many[many >= 2].index[0] if (many >= 2).any() else s.uid.iloc[0]
    print("\\nStep 2 example: one member's receipts (a gap > W starts a new subscription)")
    e = ev[ev.uid == ex_uid].copy(); e["gap_days"] = e.dt.diff().dt.days
    display(e[["dt", "channel", "plan", "gap_days", "W", "new_sub", "sub_id"]].head(example_rows))
    print("...and the subscriptions built from them (detect = last payment + W; churned if detect <= data end)")
    display(s[s.uid == ex_uid][["start", "last_pay", "n_pay", "channel", "plan", "W", "detect", "churned"]])
    m = monthly(s).merge(published(provider), on="month", how="left")
    print("\\nSteps 3-5 by month: simple recompute vs published subs_monthly (pub_*)")
    display(m.tail(15))
    print("Churn rates the model applied, last 3 months (rate_source = full_panel or reliable_subset):")
    display(rates(provider))
    return ev, s, m
""")
NOTES = [
    ("chatgpt", "ChatGPT", "Apple, Google Play and (EU) PayPal/Stripe. **Direct ChatGPT is excluded**: its sign-up receipts have no renewals, so churn can't be measured."),
    ("claude", "Claude", "Mostly direct (Anthropic receipts at list price), plus Apple and Google Play. Direct and Google Play use full-panel churn rates."),
    ("gemini", "Gemini", "Google Play (including Google One web purchases) and Apple; AI tiers only. Storage-only plans are excluded; AI Plus 2 TB is included."),
    ("grok", "Grok (incl. X Premium+)", "Apple and Google Play SuperGrok/Lite/Heavy, plus X Premium+. There are no direct xAI receipts. Long lapse windows (60–90 days) because renewals arrive irregularly."),
    ("perplexity", "Perplexity", "Apple and Google Play only. Direct Perplexity sends unpriced welcome emails, not paid receipts, so it is not counted."),
    ("muse", "Muse", "Apple 'Power Plan' and Google Play since 7 Sep 2026. Churn becomes observable once the first cohorts pass their window (late October 2026)."),
]
for p, title, note in NOTES:
    md(f"### {title}\n\n{note}")
    code(f'ev_{p}, s_{p}, m_{p} = walkthrough("{p}")')

md("""
## 5. Subscribers: the stock-flow index

The published subscriber count (`subs`) follows a monthly identity:

> subs(t) = subs(t−1) + gross adds(t) − churn(t)

Churn(t) is the sum over plans and tenure bands of (churn rate × subscribers), using the rates in `churn_rates`. The check below confirms the published table adds up.

`subs_observed` is the simple open-subscription count from the full panel, shown for comparison. The model sits above it mainly on Apple, where missed renewal emails make some live subscribers look churned.
""")
code("""
pub = q(f'''
SELECT provider, TO_VARCHAR(month, 'YYYY-MM') AS month, subs, gross_adds, churn, subs_observed, share, held
FROM srs_mcp.ai_consumer.subs_monthly
WHERE region = '{REGION}' AND country = '{COUNTRY}' AND plan = 'all' ORDER BY 1, 2''')
pub["identity_gap"] = (pub.subs - (pub.groupby("provider").subs.shift() + pub.gross_adds - pub.churn)).round(1)
print("Largest absolute identity gap by provider, excluding held months (should be ~0):")
display(pub[~pub.held].groupby("provider").identity_gap.apply(lambda x: x.abs().max()))
latest = pub[~pub.held].month.max()
print("Latest non-held month:", latest)
pub[pub.month == latest][["provider", "subs", "subs_observed", "share", "gross_adds", "churn"]]
""")
nb.cells = C
nbf.write(nb, "ai_subs_receipts_walkthrough.ipynb")
print("written")
