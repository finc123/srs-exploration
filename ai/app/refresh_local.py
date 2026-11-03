"""Rebuild app/ai_consumer.json from the live sources, read-only, with the production exporter.

Runs srs workflows/jobs/ai/consumer's export_dashboard_json with each srs_mcp.ai_consumer.* table swapped for its
load SELECT (so nothing is written to Snowflake), email_flows and email_flows_daily built in-process by
engine/email_flows.py (the daily table inlined as VALUES), and the S3
put redirected to the local file (the previous one is kept as ai_consumer.json.bak). Snowflake connection "default".
Local only (not in the srs job yet): sections card_spend_daily (observable AI-plan spend on the card panel) and
card_panel_spend_daily (total panel spend at tagged merchants), built by notebooks/card_ereceipt_rules.py: a fresh
Omega pull on ANALYST_XL (about 15 minutes) and the panel total, cached in .cache/card_ereceipt/panel_spend_daily.parquet
with its last 45 days re-pulled each run. Also local only: card_flows and card_plans (Provider Analysis card series and
plan share, from the same card pull), email_plans (e-receipt plan share, the engine's unwritten plan split) and
switching (Switching Heatmap), both from the email_flows events.
Run from exploration/ai: python app/refresh_local.py [srs checkout; default ../../srs]."""
import json, os, re, shutil, sys
from pathlib import Path
import pandas as pd
import snowflake.connector as sc

SRS = Path(sys.argv[1] if len(sys.argv) > 1 else "../../srs").resolve()
JOB = SRS / "workflows/jobs/ai/consumer/artifacts"
OUT = Path(__file__).resolve().parent / "ai_consumer.json"
sys.path[:0] = [str(JOB / "engine"), str(JOB / "export"), str(SRS / "packages/srs-core")]
os.environ["_SRS_TAG_WORKFLOW"] = "ai_consumer"
import email_flows as F  # noqa: E402
import export_dashboard_json as E  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))
import card_ereceipt_rules as C  # noqa: E402


def bodies(path):
    """{table: SELECT body} from a load file's CREATE OR REPLACE TABLE ... AS <select>; statements."""
    out = {}
    for chunk in re.split(r"CREATE OR REPLACE TABLE ", path.read_text())[1:]:
        name = chunk.split()[0].split(".")[-1].split("(")[0]
        out[name] = re.split(r"^;\s*$", chunk.split("\nAS\n", 1)[1], maxsplit=1, flags=re.M)[0]
    return out


SUBS = {**bodies(JOB / "load/app_web.sql"), **bodies(JOB / "load/receipts_us.sql")}
cur = sc.connect(connection_name="default").cursor()


def fetch(sql):
    for name, body in SUBS.items():
        sql = re.sub(rf"srs_mcp\.ai_consumer\.{name}\b", f"(\n{body}\n)", sql, flags=re.I)
    cur.execute(sql)
    return cur.fetch_pandas_all()


SWITCH_DAYS, SWITCH_MONTHS = (14, 30), 6


def events(raw):
    """email_flows' per-mailbox events: the prepared rows and, per provider, its channels' adds, churn (only while
    subscribed) and signals, as build() makes them."""
    df = F._prepare(raw)
    ev = F._channels(df)
    for chans in ev.values():
        F._subscribed_churn(chans)
    return df, ev


def plan_flows(df, ev, data_end):
    """The engine's plan split (_plan_flows, not written by the job since 2026-10-26) on each provider's Combined
    channels: gross adds, churn and plan switches per provider x plan x month from START."""
    labels, out = F._plans(df), []
    for p, chans in ev.items():
        t = F._plan_flows({ch: chans[ch] for ch in F.COMBINE[p] if ch in chans}, labels[p], p)
        out.append(t[t.month >= pd.Period(F.START, "M")].assign(provider=p))
    t = pd.concat(out, ignore_index=True)
    t["net_adds"] = t.gross_adds + t.switch_in - t.churn - t.switch_out
    partial = None if data_end.is_month_end else data_end.to_period("M")
    return [dict(MONTH=str(r.month.start_time.date()), PROVIDER=r.provider, PLAN=r.plan, GROSS_ADDS=int(r.gross_adds),
                 CHURN=int(r.churn), SWITCH_IN=int(r.switch_in), SWITCH_OUT=int(r.switch_out),
                 NET_ADDS=int(r.net_adds), PARTIAL=r.month == partial) for r in t.itertuples()]


def switching(df, ev):
    """Where churners go: for each provider's cancellations in a month (counted only while subscribed, as in
    email_flows), the mailboxes with a gross add to each provider within N days after the cancellation (same day or
    later; a later day for the provider itself), or to none. A mailbox can join several providers, so a row can sum
    to more than 100%. Months are the last SWITCH_MONTHS whose N-day window has passed the data end."""
    data_end, adds, churn = df.dt.max(), [], []
    for p, chans in ev.items():
        for ch in F.COMBINE[p]:
            if ch in chans:
                adds.append(chans[ch]["adds"][["mailbox_id", "dt"]].assign(to=p))
                churn.append(chans[ch]["churn"][["mailbox_id", "dt"]].assign(src=p))
    adds = pd.concat(adds, ignore_index=True)
    churn = pd.concat(churn, ignore_index=True).assign(month=lambda d: d.dt.dt.to_period("M"))
    churn = churn.sort_values("dt").drop_duplicates(["mailbox_id", "src", "month"])  # one churner per month
    out = []
    for n in SWITCH_DAYS:
        lim = data_end - pd.Timedelta(days=n)
        last = lim.to_period("M") if lim.is_month_end else lim.to_period("M") - 1
        k = churn[churn.month.between(last - SWITCH_MONTHS + 1, last)]
        j = k.merge(adds, on="mailbox_id", suffixes=("", "_add"))
        gap = (j.dt_add - j.dt).dt.days
        j = j[(gap <= n) & ((gap > 0) | ((gap == 0) & (j.to != j.src)))].drop_duplicates(["mailbox_id", "src", "month", "to"])
        moved = j.groupby(["month", "src", "to"]).mailbox_id.nunique()
        none = k[~k.set_index(["mailbox_id", "src", "month"]).index.isin(j.set_index(["mailbox_id", "src", "month"]).index)]
        none = none.assign(to="none").groupby(["month", "src", "to"]).mailbox_id.nunique()
        tot = k.groupby(["month", "src"]).mailbox_id.nunique().rename("churners")
        t = pd.concat([moved, none]).rename("mailboxes").reset_index().merge(tot.reset_index(), on=["month", "src"])
        out.append(t.assign(days=n))
    t = pd.concat(out, ignore_index=True)
    return [dict(MONTH=str(r.month.start_time.date()), DAYS=int(r.days), FROM=r.src, TO=r.to,
                 MAILBOXES=int(r.mailboxes), CHURNERS=int(r.churners)) for r in t.itertuples()]


print("email flows: reading receipts ...", flush=True)
raw = fetch(F.READ_SQL.format(schema="srs_mcp.ai_consumer"))
flows, daily, end = F.build(raw)
rdf, rev = events(raw)
switch_sec, plans_sec = switching(rdf, rev), plan_flows(rdf, rev, end)
print(f"switching built: {len(switch_sec)} rows; e-receipt plan flows: {len(plans_sec)} rows", flush=True)
panel = int(fetch(F.PANEL_SQL).iloc[0, 0])
print(f"email flows built, data end {end.date()}, panel {panel:,}", flush=True)
SUBS["email_flows_daily"] = ("SELECT column1 AS region, column2 AS provider, column3::DATE AS date, column4 AS gross_adds, "
                             f"column5 AS churn, column6 AS net_adds, {panel} AS panel FROM VALUES " + ",".join(
    f"('{r.region}','{r.provider}','{r.date.date()}',{r.gross_adds},{r.churn},{r.net_adds})" for r in daily.itertuples()))
flows_sec = pd.DataFrame({
    "MONTH": flows.month.dt.strftime("%Y-%m-%d"), "PROVIDER": flows.provider, "CHANNEL": flows.channel,
    "PLAN": flows.plan, "GROSS_ADDS": flows.gross_adds, "CHURN": flows.churn, "SWITCH_IN": flows.switch_in,
    "SWITCH_OUT": flows.switch_out, "NET_ADDS": flows.net_adds, "IN_COMBINED": flows.in_combined,
    "PARTIAL": flows.partial}).sort_values(["PROVIDER", "CHANNEL", "PLAN", "MONTH"]).reset_index(drop=True)


print("card spend: pulling the card panel ...", flush=True)
card = C.pull_card(save=False)
card_end = card.dt.max()
pay = C.card_payments(card, C.SPEND_PROVIDERS)
spend = C.card_spend_daily(pay, card_end)
card_flows_sec = [dict(MONTH=str(r.month.start_time.date()), PROVIDER=r.provider, CHANNEL=r.channel,
                       GROSS_ADDS=int(r.gross_adds), CHURN=int(r.churn), NET_ADDS=int(r.net_adds), PARTIAL=bool(r.partial))
                  for r in C.app_card_flows(pay, card_end).itertuples()]
card_plans_sec = [dict(MONTH=str(r.month.date()), PROVIDER=r.provider, PLAN=r.tier, SUBSCRIBERS=int(r.subscribers))
                  for r in C.app_card_plans(pay, card_end).itertuples()]
panel_spend = C.panel_spend_daily(spend.date.max())
d0 = fetch("SELECT DISTINCT LOWER(app) AS provider, day0 FROM srs_mcp.ai_consumer.app_usage WHERE country = 'US'")
spend = spend.merge(d0.rename(columns=str.lower), on="provider", how="left")
spend["day_n"] = (spend.date - pd.to_datetime(spend.day0)).dt.days
spend_sec = [dict(PROVIDER=r.provider, DATE=str(r.date.date()), DAY_N=None if pd.isna(r.day_n) else int(r.day_n),
                  SPEND=round(float(r.spend), 2), ACCOUNTS=int(r.accounts))
             for r in spend.sort_values(["provider", "date"]).itertuples()]
panel_sec = [dict(DATE=str(r.date.date()), SPEND=round(float(r.spend), 0)) for r in panel_spend.itertuples()]
print(f"card spend built, data end {card_end.date()} (shown to {spend.date.max().date()}), "
      f"panel spend {panel_spend.date.min().date()} to {panel_spend.date.max().date()}", flush=True)


def query(sql, warehouse):
    if re.search(r"ai_consumer\.email_flows\b", sql, flags=re.I):
        return flows_sec.copy()
    df = fetch(sql)
    df.columns = [c.upper() for c in df.columns]
    for c in df.columns:  # dates as ISO strings, as execute_sql returns them
        if df[c].map(lambda v: hasattr(v, "isoformat")).any():
            df[c] = df[c].map(lambda v: v.isoformat() if hasattr(v, "isoformat") else v)
    return df


class _LocalS3:
    def put_object(self, Body, **_):
        if OUT.exists():
            shutil.copy(OUT, OUT.with_suffix(".json.bak"))
        OUT.write_bytes(Body)


E._query = query
E.boto3.client = lambda *_a, **_k: _LocalS3()
res = E._export({})
# Local preview shows the e-receipt data end, not the month the exporter reports.
j = json.loads(OUT.read_text())
j["freshness"][0] = dict(DATASET="E-receipt emails (to date)", MAX_DATE=str(end.date()))
j["freshness"].append(dict(DATASET="Card panel spend (to date)", MAX_DATE=str(spend.date.max().date())))
j["sections"]["card_spend_daily"] = spend_sec
j["sections"]["card_panel_spend_daily"] = panel_sec
j["sections"]["card_flows"] = card_flows_sec
j["sections"]["card_plans"] = card_plans_sec
j["sections"]["switching"] = switch_sec
j["sections"]["email_plans"] = plans_sec
CARD_SOURCE = ("Consumer Edge Omega card panel (2022 consistent-shopper panel, affected accounts excluded): tagged rows "
               "from EARNEST.COMMON.TXNS_CORE_V plus untagged AI merchids from PRIME_OMEGA TRANS_V1_0, classified by "
               "exploration/ai/filters/{provider}.py (notebooks/card_ereceipt_rules.py). Built locally, not yet in the job.")
CARD_PAY_RULE = dict(RULE="Kept consumer AI-plan payments only: web (shown as Direct) and Google Play billing; Apple App "
                          "Store charges carry no provider, so iTunes is not visible",
                     WHY="The same payments as the Spend metric and card_ereceipt_comparison.ipynb. Providers billed "
                         "mostly through Apple are understated, and a move from iTunes to the web reads as growth.")
j["methodology"] += [dict(
    KEY="card_flows", TITLE="Provider Analysis: gross adds, churn and net adds from the card panel (US)",
    SOURCE=CARD_SOURCE,
    FILTERS=[CARD_PAY_RULE,
             dict(RULE=f"Gross add = a payment with no earlier payment for the account x provider x channel in the "
                       f"previous {C.CUTOFF} days ({C.CUTOFF_ANNUAL} after an annual payment)",
                  WHY="Cards show every renewal; only the first in a run is a new subscription. History from "
                      f"{C.CARD_START}, so 2025 adds are not renewals of earlier subscriptions."),
             dict(RULE=f"Churn = lapse: no further payment within {C.CUTOFF} days ({C.CUTOFF_ANNUAL} after an annual "
                       f"payment), dated at the last payment + {C.CUTOFF} ({C.CUTOFF_ANNUAL}) days",
                  WHY="Cards carry no cancellation; a subscription has ended when the renewal does not arrive."),
             dict(RULE="Card (all) = Direct + Google Play, summed",
                  WHY="As the e-receipt Combined series (no de-duplication across channels).")],
    DEDUPE="One row per transaction; same-day payments for an account x provider x channel are one. Accounts are "
           "counted once per month per channel.",
    MEASURE="Monthly GROSS_ADDS, CHURN and NET_ADDS by provider x channel. Unweighted panel counts, not scaled to the US.",
    LAG=f"Card transactions post over about {C.CARD_LAG} days, so months run to the data end - {C.CARD_LAG} days and the "
        "last one is month-to-date. Churn is dated only once its lapse date has passed.",
), dict(
    KEY="card_plans", TITLE="Provider Analysis: plan share of active card subscribers (US)",
    SOURCE=CARD_SOURCE,
    FILTERS=[CARD_PAY_RULE,
             dict(RULE=f"Active at a month-end = the latest payment on or before it (per account x provider x channel) "
                       f"is under {C.CUTOFF} days old ({C.CUTOFF_ANNUAL} after an annual payment)",
                  WHY="The same rule that ends a card subscription in the gross adds and churn series."),
             dict(RULE="Plan = the tier of that latest payment, from the amount and descriptor in filters/{provider}.py; "
                       "monthly and annual pooled",
                  WHY="Card descriptors rarely name the plan; price bands do. Grok includes X Premium+ and, from "
                      "2026-10-10, The X Subscription tiers billed by xAI.")],
    DEDUPE="An account counts once per provider x plan at each month-end.",
    MEASURE="SUBSCRIBERS per provider x plan at each month-end; share = a plan over the provider's total. Unweighted.",
    LAG=f"Month-ends later than the data end - {C.CARD_LAG} days are left out (payments still posting).",
), dict(
    KEY="email_plans", TITLE="Provider Analysis: plan share of e-receipt net adds since January 2025 (US)",
    SOURCE="NIQ e-receipts, the same events as the Provider Analysis e-receipt series, split by plan with "
           "engine/email_flows.py _plans and _plan_flows (kept in the code, not written by the job).",
    FILTERS=[dict(RULE="Plan = the plan named in the email (tier only, monthly and annual pooled); Claude direct "
                       "payments by price ($20 Pro, $100 / $200 Max)",
                  WHY="Receipts name the tier, not the price point, so Claude Max is not split into 5x / 20x and "
                      "ChatGPT Pro is not split by price."),
             dict(RULE="A gross add takes its series' first named plan; a later established plan is a switch (out of "
                       "the old plan, into the new); churn takes the last established plan within the lookback, else "
                       "the plan the cancellation names, else Unspecified",
                  WHY="Plan changes move subscribers between plans without adding or losing them."),
             dict(RULE="Combined channels only, de-duplicated across channels",
                  WHY="As the provider's Combined series; the same mailbox on two channels within days is one event.")],
    DEDUPE="Mailboxes are counted once per plan, month and event kind.",
    MEASURE="Monthly GROSS_ADDS, CHURN, SWITCH_IN, SWITCH_OUT and NET_ADDS (= adds + switches in - churn - switches out) "
            "per provider x plan; the page sums NET_ADDS from January 2025 (no opening stock). Share is over plans "
            "with a positive total; Unspecified and negative plans show in Level only. Panel counts.",
    LAG="As the e-receipt series; the current month is month-to-date.",
), dict(
    KEY="switching", TITLE="Switching heatmap: where churners subscribe next (US, emails)",
    SOURCE="NIQ e-receipts, the same events as the Provider Analysis e-receipt series (engine/email_flows.py).",
    FILTERS=[dict(RULE="Churner = a mailbox with a cancellation email for the provider in the month, counted only while "
                       "subscribed (its previous event for the provider, on any channel, is a gross add)",
                  WHY="Cancellations with no observed sign-up (free trials, missed sign-up emails) are not churners."),
             dict(RULE="Destination = a gross add (Combined channels) to any provider within N days (14 or 30) after "
                       "the cancellation: on the same day or later for another provider, a later day for the same one",
                  WHY="The same provider on the same day is the sign-up the cancellation ends, not a return."),
             dict(RULE="A churner counts under every provider they join; None = no gross add to any provider",
                  WHY="Shows multi-homing; a row can sum to more than 100%.")],
    DEDUPE="A mailbox counts once per provider and churn month (its first cancellation in the month).",
    MEASURE="MAILBOXES per churn month x from x to; CHURNERS per churn month x from. Share = MAILBOXES / CHURNERS.",
    LAG=f"A month shows once its N-day window after the month end has passed the e-receipt data end; the last "
        f"{SWITCH_MONTHS} such months are kept for each N.",
)]
j["methodology"].append(dict(
    KEY="card_spend_daily", TITLE="Provider market share: daily spend on consumer AI plans from the card panel (US)",
    SOURCE="Consumer Edge Omega card panel (2022 consistent-shopper panel, affected accounts excluded): tagged rows from "
           "EARNEST.COMMON.TXNS_CORE_V plus untagged AI merchids from PRIME_OMEGA TRANS_V1_0, classified by "
           "exploration/ai/filters/{provider}.py (notebooks/card_ereceipt_rules.py). Built locally, not yet in the job.",
    FILTERS=[
        dict(RULE="Kept consumer AI-plan payments only: web and Google Play billing (Apple App Store charges carry no "
                  "provider and are not visible)",
             WHY="The same payments the card gross adds and churn use. Providers billed mostly through Apple (Grok, "
                 "ChatGPT) are understated, and a move from iTunes to the web reads as spend growth."),
        dict(RULE="Gemini = Google One AI plans, including 2 TB from 2026-01-27 (it includes AI Plus); Grok = SuperGrok "
                  "+ X Premium+; Muse = Muse Power / Max from 2026-09-07",
             WHY="The current card methodology. About 6% of Gemini accounts appear only under the generic "
                 "'GOOGLE *GOOGLE MOUNTAIN VIE' descriptor at AI prices."),
        dict(RULE="Annual plans count on the day charged", WHY="Observable spend, not a monthly equivalent."),
    ],
    DEDUPE="One row per transaction; spend is summed per provider and day.",
    MEASURE="SPEND = the sum of charged amounts (USD, incl. sales tax) per provider and day; ACCOUNTS = distinct paying "
            "card accounts. Share = a provider's spend over the six-provider total. % of Panel = a provider's spend over "
            "card_panel_spend_daily: all panel USD debits at merchants tagged to a brand (MID_MATCH main_brand_id), "
            "which leaves out bank transfers, rent and bill payments (untagged, about 80% of all debits by value). Most "
            "AI charges are untagged, so they are not in the denominator. TR7D = 7-day sums over 7-day sums; Monthly = "
            "monthly sums. Unweighted panel totals, not scaled to the US.",
    LAG=f"Card transactions post over about {C.CARD_LAG} days, so the last {C.CARD_LAG} days before the data end are "
        "dropped.",
))
OUT.write_text(json.dumps(j, separators=(",", ":"), allow_nan=False, default=str))
print(json.dumps({k: res[k] for k in ("status", "sections", "bytes")}, default=str))
