"""Meta Muse app: source loads, report sections and their methodology, in one place.

Two layers, mirroring the planned monorepo workflow (`workflows/jobs/meta/meta_muse.yaml`):

1. LOADS (Snowflake SQL). Narrow row-level pulls from the raw panels into what
   will become `srs_slice.meta.*` tables:
     card_txns     one row per matched card/bank transaction (signal = muse_web | agentic)
     panel_totals  distinct transactions per source per day (denominator for per-million)
     member_tenure first / last transaction day per web Muse payer per source (panel presence)
     niq_receipts  one row per Muse e-receipt line item
     app_usage     SensorTower downloads / DAU per app x country x day
     benchmark     SensorTower US downloads per benchmark app x day, day 0 to +120 (+ Clubhouse export)
     ad_spend      Pathmatics Muse digital ad spend per country x publisher x day
     web_traffic   SimilarWeb muse.ai visits per country x day (snapshot fallback)
   Card loads run one query per source per day (multi-day ILIKE scans on the
   279 tables time out) and are cached locally by build_json.py.

2. SECTIONS (portable SQL over the srs_slice.meta.* tables). Run by DuckDB over
   the cached loads here, and by Snowflake in the monorepo exporter, so the
   strings are written in the common subset of both dialects (CASE, COUNT
   DISTINCT, CAST AS VARCHAR, MEDIAN). Column aliases are UPPERCASE because
   that is how Snowflake returns them and how the page reads them.

Each section carries its METHODOLOGY next to its SQL; build_json.py writes it
into the payload and renders METHODOLOGY.md from it, so the document cannot
drift from the code.
"""

from __future__ import annotations

from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Windows and lags
# ---------------------------------------------------------------------------
LAUNCH = "2026-09-08"          # Muse public launch
CARD_START = "2026-08-01"      # card / e-receipt window start (pre-launch baseline)
APP_START = "2026-06-01"       # SensorTower window start (Meta AI baseline)

CARD_LAG_DAYS = 5              # Yodlee/279 day volume is still filling 5-10 days back
NIQ_LAG_DAYS = 1               # NIQ is complete through yesterday
REFRESH_DAYS = 14              # card days newer than this are re-pulled every run
TR_DAYS = 7                    # trailing window for every *_TR7D column
SUB_GAP_DAYS = 35              # card subs: a payment after this many days without one is a new subscription,
                               # and no payment for this long after the last one is a lapse
TENURE_DAYS = 35               # card subs: a gross add needs the member in the panel this long before paying

MUSE_KEY = "6aa0b99dd70c1a09e42dc613"     # SensorTower "Muse from Meta" (com.facebook.aura)
META_AI_KEY = "613aafdee8b8ad2c7f063b8e"  # SensorTower "Meta AI" (com.facebook.stella)

# SensorTower unified product keys, matched by KEY, never by name: "ChatGPT" alone is
# 12 products (mostly clones), and there is a clone "Muse from Meta" too. Keys are the
# official publishers' apps (verified 2026-10-07 against app ids / publisher).
APP_KEYS = {
    "Muse": MUSE_KEY,
    "Meta AI": META_AI_KEY,
    "ChatGPT": "64665f59b3ae2712001279ed",   # OpenAI; com.openai.chatgpt / iOS 6448311069
    "Claude": "663279a2b3ae277df21f2bd0",    # Anthropic; com.anthropic.claude / iOS 6473753684
    "Gemini": "65c58645bd9b7e3bc33c81b4",    # Google; com.google.android.apps.bard / iOS 6477489729
    "Grok": "676652c29ccf2a852260e663",      # xAI (publisher shown as SpaceX); ai.x.grok / iOS 6670324846
}
# The AI-assistant set for the share chart (Meta AI is shown beside Muse, not in the share set).
SHARE_APPS = ["Muse", "ChatGPT", "Gemini", "Claude", "Grok"]

# Launch benchmark: US downloads from each app's day 0, by key (verified 2026-10-08; CORE
# history starts on launch day for each). Clubhouse is not in CORE: it comes from a
# SensorTower portal export (BENCHMARK_SNAPSHOT), with day 0 at its viral breakout rather
# than its spring-2020 invite-only release.
BENCHMARK_KEYS = {
    "Muse": MUSE_KEY,
    "Sora": "68dc489f4e04a24f7d0d0aeb",
    "Threads": "64a72c98ad4adb0e06dbc506",
    "ChatGPT": APP_KEYS["ChatGPT"],
    "Claude": APP_KEYS["Claude"],
}
BENCHMARK_DAYS = 120
BENCHMARK_SNAPSHOT = "benchmark_snapshot.xlsx"
BENCHMARK_DAY0 = {"Clubhouse": "2020-12-15"}   # first day of the sustained jump in US downloads (15k -> 25k)

# Web price ladder (US$, pre-tax list $16 / $80); upper bounds allow for sales tax,
# lower bounds sit just under list so off-price Meta charges (e.g. $15.90) are excluded.
WEB_BUCKETS = {"Power": (15.99, 17.60), "Max": (79.99, 88.00)}


def bucket_filter_sql(amt: str = "amount", plan: str = "plan") -> str:
    """Re-applies WEB_BUCKETS at section level, so a cache loaded under wider bounds stays valid."""
    return "(" + " OR ".join(f"({plan} = '{p}' AND {amt} BETWEEN {lo} AND {hi})"
                             for p, (lo, hi) in WEB_BUCKETS.items()) + ")"

# ---------------------------------------------------------------------------
# Card sources: the deduplicated, live set from card_linkagnt_coverage.ipynb
# (279 PRIME is a subset of Yodlee F3/4/6; mirrors and snapshots are copies).
# ---------------------------------------------------------------------------
#
# QUERY SHAPE. The Yodlee tables are unclustered on transaction_date (F3 bank:
# 62B rows / 4 TB, clustering depth ~255k of 291k partitions), so a date
# filter prunes almost nothing and a one-day query is a full scan. They do
# prune on panel_file_created_date (84% constant partitions), and a
# transaction never lands in a file created more than a day before it
# (F3 card, 2026-09-15: 4 of 1.1M rows at -1 day, none earlier). So Yodlee is
# pulled as ONE range query per source, pruned on that column with a
# PRUNE_SLACK_DAYS margin. The 279 tables time out on multi-day ILIKE scans,
# so they stay at one query per day (`max_days=1`).
PRUNE_SLACK_DAYS = 2


def _yodlee(feed: int, kind: str) -> dict:
    return dict(name=f"Yodlee F{feed} {kind.lower()}",
                table=f"SHARE_CE_SPEND_201_PRIME_EX_TAU.FEED{feed}_PANELS.FEED{feed}_{kind}_PANELS_V1_0",
                desc="description", date="transaction_date", amt="amount",
                txn=f"unique_{kind.lower()}_transaction_id", member="unique_mem_id",
                prune="panel_file_created_date", max_days=None)

CARD_SOURCES = [_yodlee(f, k) for f in (3, 4, 6) for k in ("CARD", "BANK")]

# NOT IN v1 (decided 2026-10-07). 279 PRIME_TAU does not overlap Yodlee members,
# but it is a ~12.5M-transaction/day panel that surfaces only ~3 agentic
# descriptors a day and no web Muse charges, and its one-query-per-day load
# takes ~2.5 min/day on an analyst warehouse. Candidate for the monorepo job,
# where the service warehouse is larger, as a separate raw count only: it must
# never join the per-million denominator (it would make the rate track 279's
# panel size, not agentic adoption).
SOURCE_279_PRIME_TAU = dict(
    name="279 PRIME_TAU", table="SHARE_EARNEST_279.PRIME_TAU.SPEND_279_TRANSACTIONS_V3_0",
    desc="billing_description", date="transaction_date", amt="transaction_amount",
    txn="earnest_transaction_id", member="member_id", prune=None, max_days=1)

DENOMINATOR_SOURCES = CARD_SOURCES

# ---------------------------------------------------------------------------
# Matching rules (Snowflake SQL fragments). Backslashes are doubled for the
# SQL string literal, so '\\*' reaches the regex engine as a literal '*'.
# ---------------------------------------------------------------------------
def agentic_sql(col: str) -> str:
    """Stripe Link agentic checkout: LINKAGNT* (until 2026-09-23) or LINK* anchored on Stripe's descriptor (from 09-23)."""
    return (rf"({col} ILIKE '%linkagnt*%' OR (REGEXP_LIKE({col}, '(^|.*[^a-z.])link\\* .*', 'i') "
            rf"AND ({col} ILIKE '%www.link.co%' OR {col} ILIKE '%south san fra%')))")


def muse_web_sql(col: str, amt: str) -> str:
    """Direct web Muse billing: METAPAY META.COM (no '*') at a web price point."""
    buckets = " OR ".join(f"{amt} BETWEEN {lo} AND {hi}" for lo, hi in WEB_BUCKETS.values())
    return (rf"({col} ILIKE '%metapay%meta.com%' AND NOT REGEXP_LIKE({col}, '.*metapay ?\\*.*', 'i') "
            f"AND ({buckets}))")


def plan_sql(amt: str) -> str:
    whens = " ".join(f"WHEN {amt} BETWEEN {lo} AND {hi} THEN '{name}'" for name, (lo, hi) in WEB_BUCKETS.items())
    return f"CASE {whens} END"


def merchant_sql(col: str) -> str:
    """Merchant text after the Link descriptor, e.g. 'LINKAGNT* SP ACME WWW.LINK.COM' -> 'ACME'."""
    return (rf"TRIM(REGEXP_SUBSTR(UPPER({col}), '(LINKAGNT|LINK)\\* ?(SP |DD \\*|QDI\\*)?([A-Z0-9.'' -]{{2,12}})', "
            r"1, 1, 'e', 3))")


def shopify_sql(col: str) -> str:
    """Agentic purchase at a Shopify store: 'LINK* SP <store>' or an explicit Shopify / Shop Pay marker."""
    return (rf"(REGEXP_LIKE({col}, '.*(linkagnt|link)\\* ?sp .*', 'i') "
            f"OR {col} ILIKE '%shopify%' OR {col} ILIKE '%shop pay%')")


# ---------------------------------------------------------------------------
# LOADS (Snowflake)
# ---------------------------------------------------------------------------
def _window(src: dict, start: str, end: str) -> str:
    """Transaction-date window, plus the file-date pruning predicate where the source has one."""
    w = f"{src['date']} BETWEEN '{start}' AND '{end}'"
    if src["prune"]:
        w += f" AND {src['prune']} >= DATEADD('day', -{PRUNE_SLACK_DAYS}, '{start}'::DATE)"
    return w


def card_rows_sql(src: dict, start: str, end: str) -> str:
    d, a = src["desc"], src["amt"]
    return f"""
        SELECT '{src['name']}' AS source,
               CAST({src['member']} AS VARCHAR) AS member,
               CAST({src['txn']} AS VARCHAR) AS txn_id,
               {src['date']}::DATE AS day,
               ROUND({a}, 2) AS amount,
               {d} AS description,
               IFF({agentic_sql(d)}, 'agentic', 'muse_web') AS signal,
               IFF({agentic_sql(d)}, NULL, {plan_sql(a)}) AS plan,
               IFF({agentic_sql(d)}, {merchant_sql(d)}, NULL) AS merchant,
               IFF({agentic_sql(d)}, {shopify_sql(d)}, FALSE) AS is_shopify
        FROM {src['table']}
        WHERE {_window(src, start, end)}
          AND ({agentic_sql(d)} OR {muse_web_sql(d, a)})
    """


# Panel presence for web Muse payers: first and last transaction (any merchant) per member per source,
# from early enough that the TENURE_DAYS test is decidable for every payment in the card window.
TENURE_START = (date.fromisoformat(CARD_START) - timedelta(days=TENURE_DAYS)).isoformat()


def member_tenure_sql(src: dict, members: list[str], end: str) -> str:
    ids = ", ".join(f"'{m}'" for m in members)
    return f"""
        SELECT '{src['name']}' AS source, CAST({src['member']} AS VARCHAR) AS member,
               MIN({src['date']})::DATE AS first_seen, MAX({src['date']})::DATE AS last_seen
        FROM {src['table']}
        WHERE {_window(src, TENURE_START, end)} AND {src['member']} IN ({ids})
        GROUP BY 1, 2
    """


def panel_total_sql(src: dict, start: str, end: str) -> str:
    return f"""
        SELECT '{src['name']}' AS source, {src['date']}::DATE AS day, COUNT(DISTINCT {src['txn']}) AS total_txn
        FROM {src['table']} WHERE {_window(src, start, end)}
        GROUP BY 1, 2
    """


# Active mailboxes only: the SRS convention for NIQ panels (srs_slice.rblx.receipts joins
# share_niq.srs.mailboxes_enhanced and filters status = 'active' downstream).
NIQ_SQL = f"""
    SELECT i.order_date::DATE AS order_date, i.mailbox_id, i.merchant_name, i.description,
           i.item_price, i.order_total, m.status AS mailbox_status,
           CASE WHEN i.description ILIKE '%power%' THEN 'Power'
                WHEN i.description ILIKE '%max%' THEN 'Max' ELSE 'Other' END AS plan,
           CASE WHEN i.merchant_name ILIKE '%cancel%' OR i.description ILIKE '%cancel%'
                     OR i.description ILIKE '%will end on%' THEN 'cancel'
                WHEN i.description ILIKE '%trial%' THEN 'trial' ELSE 'charge' END AS kind,
           CASE WHEN i.merchant_name ILIKE 'itunes%' THEN 'Apple'
                WHEN i.merchant_name ILIKE 'google play%' THEN 'Google Play' ELSE 'Other' END AS store
    FROM SHARE_NIQ.SRS.ITEMS_EXTENDED i
    JOIN SHARE_NIQ.SRS.MAILBOXES_ENHANCED m ON m.mailbox_id = i.mailbox_id
    WHERE i.order_date BETWEEN '{CARD_START}' AND CURRENT_DATE
      AND i.description ILIKE '%muse from meta%'
      AND m.status ILIKE 'active'
"""

# CORE is unclustered on date (a full ~20 GB scan whatever the filter), so it
# is read once per run into a few hundred rows; see roblox bookings_agg_intl.sql.
APP_USAGE_SQL = f"""
    SELECT date::DATE AS date,
           CASE unified_product_key {" ".join(f"WHEN '{k}' THEN '{a}'" for a, k in APP_KEYS.items())} END AS app,
           country_code AS country,
           SUM(downloads) AS downloads,
           NULLIF(SUM(dau), 0) AS dau
    FROM sensortower.common.core
    WHERE unified_product_key IN ({", ".join(f"'{k}'" for k in APP_KEYS.values())})
      AND country_code IN ('US', 'WW')
      AND date BETWEEN '{APP_START}' AND CURRENT_DATE
    GROUP BY 1, 2, 3
"""

# One CORE read for the benchmark apps: US, from each app's first download day to +BENCHMARK_DAYS.
BENCHMARK_SQL = f"""
    WITH d AS (
        SELECT date::DATE AS date,
               CASE unified_product_key {" ".join(f"WHEN '{k}' THEN '{a}'" for a, k in BENCHMARK_KEYS.items())} END AS app,
               SUM(downloads) AS downloads,
               NULLIF(SUM(dau), 0) AS dau
        FROM sensortower.common.core
        WHERE unified_product_key IN ({", ".join(f"'{k}'" for k in BENCHMARK_KEYS.values())})
          AND country_code = 'US'
        GROUP BY 1, 2
    ), f AS (
        SELECT app, MIN(date) AS day0 FROM d WHERE downloads > 0 GROUP BY app
    )
    SELECT d.date, d.app, d.downloads, d.dau
    FROM d JOIN f ON f.app = d.app
    WHERE d.date BETWEEN f.day0 AND DATEADD('day', {BENCHMARK_DAYS}, f.day0)
"""

# Pathmatics digital ad spend for Muse. US and Canada are the only material regions.
AD_SPEND_SQL = f"""
    SELECT date::DATE AS date,
           CASE region WHEN 'United States' THEN 'US' WHEN 'Canada' THEN 'CA' END AS country,
           publisher,
           SUM(spend) AS spend,
           SUM(ads) AS ads
    FROM pathmatics.common.digital_ad_spend
    WHERE advertiser ILIKE 'muse from meta'
      AND region IN ('United States', 'Canada')
      AND date >= '{CARD_START}'
    GROUP BY 1, 2, 3
"""

# SimilarWeb daily visits. muse.ai was added to the pipeline config on 2026-10-08; until it
# lands, build_json.py falls back to WEB_TRAFFIC_SNAPSHOT (an MCP pull, same columns).
WEB_DOMAINS = ["muse.ai"]
WEB_TRAFFIC_SNAPSHOT = "web_traffic_snapshot.csv"
WEB_TRAFFIC_SQL = f"""
    SELECT date::DATE AS date, domain, country, value AS visits
    FROM similarweb.snowflake_integration.downstream_daily
    WHERE domain IN ({", ".join(f"'{d}'" for d in WEB_DOMAINS)})
      AND metric = 'ALL_TRAFFIC_VISITS'
      AND country IN ('US', 'WW')
      AND date >= '{CARD_START}'
"""

# ---------------------------------------------------------------------------
# SECTIONS (portable SQL). Placeholders filled by build_json.py:
#   {card_start} {card_through} {niq_through} {app_start} {merch_start}
#
# Per section:
#   keys      group columns besides DATE (one dense daily series per key combo)
#   measures  columns that get a *_TR7D twin
#   fill_zero a missing day means zero (counts from a scan) vs unknown (vendor series)
#   zero_before_first  (vendor series) days before a key combo's first row are zero, e.g. before an app's launch
#   start/through  the placeholders bounding the dense calendar
# ---------------------------------------------------------------------------
SECTIONS: list[dict] = [
    dict(
        key="muse_web_daily",
        title="Muse web subscriptions (card panels)",
        keys=["PLAN"], measures=["MEMBERS", "TXNS"], fill_zero=True,
        start="card_start", through="card_through",
        sql="""
            SELECT CAST(day AS VARCHAR) AS DATE, plan AS PLAN,
                   COUNT(DISTINCT member) AS MEMBERS, COUNT(*) AS TXNS
            FROM (SELECT DISTINCT member, day, amount, plan
                  FROM srs_slice.meta.card_txns
                  WHERE signal = 'muse_web' AND day BETWEEN '{card_start}' AND '{card_through}'
                    AND """ + bucket_filter_sql() + """) t
            GROUP BY 1, 2 ORDER BY 1, 2
        """,
        methodology=dict(
            source="Yodlee card & bank panels, feeds 3, 4 and 6 (SHARE_CE_SPEND_201_PRIME_EX_TAU). Feeds 1 and "
                   "2 stopped in 2025-09. The 279 panels are not used: 279 PRIME is a subset of these Yodlee "
                   "feeds, the other 279 schemas are mirrors, snapshots or stale, and 279 PRIME_TAU showed no "
                   "web Muse charges.",
            filters=[
                ("Description contains METAPAY and META.COM (e.g. 'METAPAY META.COM CA')",
                 "Meta bills web subscriptions directly under this descriptor. Muse has no app-name in the "
                 "descriptor, so the descriptor alone identifies Meta direct billing, not Muse."),
                ("Exclude METAPAY* / METAPAY * (with an asterisk)",
                 "That form is Meta Pay: ad payments and peer-to-peer transfers, not subscriptions."),
                ("Amount $15.99-17.60 (Power) or $79.99-88.00 (Max)",
                 "Muse web list prices are $16 and $80; the upper bounds allow for sales tax. The same "
                 "descriptor carried legacy $11.99 / $12.99 charges before launch and occasional off-price "
                 "charges (e.g. $15.90 on 2026-09-11), so the price bucket is what isolates Muse. In-app "
                 "prices ($20 / $100) never bill under this descriptor."),
                ("Not matched: GOOGLE *FACEBOOK, Apple, PP*METAPLATFOR, FACEBK *",
                 "Google Play bills every Meta app as GOOGLE *FACEBOOK, so its small launch uplift cannot be "
                 "isolated from other Meta subscriptions (investigations/android_crosscheck.ipynb), Apple card "
                 "descriptors carry no app name, "
                 "and the PayPal / FACEBK forms are ads and Quest. In-app Muse is measured from e-receipts instead."),
            ],
            dedupe="Distinct (member, day, amount, plan): Yodlee pending and posted copies of one charge can "
                   "carry different transaction ids.",
            measure="MEMBERS = distinct panel members charged that day, per plan. TXNS = deduplicated charges. "
                    "A charge is a new subscription or a monthly renewal. Web Muse first charges appear around "
                    "2026-09-17, nine days after launch; the cause is not confirmed (possible billing delay, "
                    "trial or slow web adoption).",
            lag=f"Complete through run date minus {CARD_LAG_DAYS} days; later days are excluded.",
        ),
    ),
    dict(
        key="muse_inapp_daily",
        title="Muse in-app subscriptions (e-receipts)",
        keys=["STORE", "PLAN"], measures=["CHARGES", "CANCELS", "TRIALS"], fill_zero=True,
        start="card_start", through="niq_through",
        sql="""
            SELECT CAST(order_date AS VARCHAR) AS DATE, store AS STORE, plan AS PLAN,
                   COUNT(DISTINCT CASE WHEN kind = 'charge' THEN mailbox_id END) AS CHARGES,
                   COUNT(DISTINCT CASE WHEN kind = 'cancel' THEN mailbox_id END) AS CANCELS,
                   COUNT(DISTINCT CASE WHEN kind = 'trial' THEN mailbox_id END) AS TRIALS
            FROM srs_slice.meta.niq_receipts
            WHERE order_date BETWEEN '{card_start}' AND '{niq_through}' AND store <> 'Other'
            GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
        """,
        methodology=dict(
            source="NIQ e-receipts, SHARE_NIQ.SRS.ITEMS_EXTENDED (one row per receipt line item), joined to "
                   "SHARE_NIQ.SRS.MAILBOXES_ENHANCED for mailbox status.",
            filters=[
                ("Active mailboxes only (MAILBOXES_ENHANCED.status = 'active')",
                 "Inactive mailboxes have disconnected or stopped syncing, so their receipt history stops. "
                 "Keeping them would mix panel churn into the trend; this is the SRS convention for NIQ "
                 "(e.g. the Roblox bookings slice). It removes 11 of 275 Muse mailboxes as of 2026-10-07."),
                ("Description contains 'Muse from Meta'",
                 "The App Store / Google Play receipt names the subscription. 'Muse' alone also matches other "
                 "apps and museums; the pre-launch 'Meta One' Core / Premium plans are a different product."),
                ("Merchant iTunes* -> Apple, Google Play* -> Google Play; other merchants dropped",
                 "In-app subscriptions are billed by the store. No direct-from-Meta Muse receipts exist (Meta "
                 "receipts near $16 are Quest games and Instagram boosts), so web Muse is measured on cards."),
                ("Plan from the description: 'power' -> Power, 'max' -> Max, else Other",
                 "In-app list prices are $20 (Power) and $100 (Max); the plan name is more reliable than the "
                 "amount, which varies with tax and occasional $28 regional prices."),
                ("Kind: cancel (merchant or text says cancel / 'will end on'), trial ('trial'), else charge",
                 "Stores send separate receipts for trial starts and cancellation confirmations."),
            ],
            dedupe="Distinct mailboxes per day, store, plan and kind (a receipt can repeat across line items).",
            measure="CHARGES = mailboxes with a paid Muse receipt that day; CANCELS = cancellation notices; "
                    "TRIALS = trial-start receipts.",
            lag=f"Complete through run date minus {NIQ_LAG_DAYS} day.",
        ),
    ),
    dict(
        key="inapp_flows_daily",
        title="Muse in-app subscriber flows (e-receipts)",
        keys=["STORE", "PLAN"], measures=["GROSS_ADDS", "CANCELS", "NET_ADDS"], fill_zero=True,
        start="card_start", through="niq_through",
        sql="""
            WITH r AS (
                SELECT DISTINCT order_date, mailbox_id, store, plan, kind
                FROM srs_slice.meta.niq_receipts
                WHERE order_date BETWEEN '{card_start}' AND '{niq_through}' AND store <> 'Other'
            ), g AS (
                SELECT first_day AS day, store, plan, COUNT(*) AS gross_adds
                FROM (SELECT mailbox_id, store, plan, MIN(order_date) AS first_day
                      FROM r WHERE kind = 'charge' GROUP BY 1, 2, 3) f
                GROUP BY 1, 2, 3
            ), c AS (
                SELECT order_date AS day, store, plan, COUNT(DISTINCT mailbox_id) AS cancels
                FROM r WHERE kind = 'cancel' GROUP BY 1, 2, 3
            )
            SELECT CAST(COALESCE(g.day, c.day) AS VARCHAR) AS DATE,
                   COALESCE(g.store, c.store) AS STORE, COALESCE(g.plan, c.plan) AS PLAN,
                   COALESCE(g.gross_adds, 0) AS GROSS_ADDS,
                   COALESCE(c.cancels, 0) AS CANCELS,
                   COALESCE(g.gross_adds, 0) - COALESCE(c.cancels, 0) AS NET_ADDS
            FROM g FULL OUTER JOIN c ON c.day = g.day AND c.store = g.store AND c.plan = g.plan
            ORDER BY 1, 2, 3
        """,
        methodology=dict(
            source="The in-app e-receipts above (same filters: active mailboxes, 'Muse from Meta', Apple / "
                   "Google Play).",
            filters=[
                ("Gross add = the day of a mailbox's first charge receipt, per store and plan",
                 "Every mailbox's first paid Muse receipt is a new subscriber; later charges are renewals. The "
                 "window starts before launch, so no subscriber predates it."),
                ("Cancel = a cancellation-confirmation receipt",
                 "Stores email a confirmation when a user cancels; the plan usually runs to the end of the paid "
                 "period, so a cancel is a churn notice, not an immediate loss."),
                ("Trial-start receipts are left out",
                 "Muse is freemium, trials are not a standard offering, and the few trial receipts were judged "
                 "noise (team review, 2026-10-07)."),
            ],
            dedupe="One first charge per mailbox, store and plan; cancels are distinct mailboxes per day.",
            measure="GROSS_ADDS = new paying mailboxes that day. CANCELS = cancellation notices. NET_ADDS = "
                    "GROSS_ADDS - CANCELS. A plan switch counts as a gross add on the new plan. Whether "
                    "Google Play and Apple both send a receipt for every renewal is under investigation, so "
                    "renewals are not shown here.",
            lag=f"Complete through run date minus {NIQ_LAG_DAYS} day.",
        ),
    ),
    dict(
        key="web_flows_daily",
        title="Muse web subscriber flows (card panels)",
        keys=["PLAN"], measures=["GROSS_ADDS", "CANCELS", "NET_ADDS", "RENEWALS", "NEW_TO_PANEL", "PANEL_EXITS"],
        fill_zero=True, start="card_start", through="card_through",
        sql=f"""
            WITH c AS (
                SELECT DISTINCT member, day, plan
                FROM srs_slice.meta.card_txns
                WHERE signal = 'muse_web' AND day BETWEEN '{{card_start}}' AND '{{card_through}}'
                  AND {bucket_filter_sql()}
            ), t AS (
                SELECT member, MIN(first_seen) AS first_seen, MAX(last_seen) AS last_seen
                FROM srs_slice.meta.member_tenure GROUP BY member
            ), l AS (
                SELECT c.member, c.day, c.plan, t.first_seen, t.last_seen,
                       CASE WHEN LAG(c.day) OVER (PARTITION BY c.member ORDER BY c.day) IS NOT NULL
                             AND DATEDIFF('day', LAG(c.day) OVER (PARTITION BY c.member ORDER BY c.day), c.day)
                                 <= {SUB_GAP_DAYS} THEN 1 ELSE 0 END AS is_renewal,
                       CASE WHEN DATEDIFF('day', t.first_seen, c.day) > {TENURE_DAYS} THEN 1 ELSE 0 END AS is_tenured,
                       LEAD(c.day) OVER (PARTITION BY c.member ORDER BY c.day) AS next_day
                FROM c LEFT JOIN t ON t.member = c.member
            ), ev AS (
                -- payments: renewal, gross add (tenured member, no payment in the gap), or too new to the panel to tell
                SELECT day, plan,
                       CASE WHEN is_renewal = 0 AND is_tenured = 1 THEN 1 ELSE 0 END AS gross_adds,
                       0 AS cancels,
                       is_renewal AS renewals,
                       CASE WHEN is_renewal = 0 AND is_tenured = 0 THEN 1 ELSE 0 END AS new_to_panel,
                       0 AS panel_exits
                FROM l
                UNION ALL
                -- lapses: no payment within the gap after this one, dated at the end of the gap; a cancellation
                -- only if the member is still transacting in the panel after that date, else panel attrition
                SELECT day + {SUB_GAP_DAYS} AS day, plan, 0,
                       CASE WHEN last_seen > day + {SUB_GAP_DAYS} THEN 1 ELSE 0 END,
                       0, 0,
                       CASE WHEN last_seen > day + {SUB_GAP_DAYS} THEN 0 ELSE 1 END
                FROM l
                WHERE (next_day IS NULL OR DATEDIFF('day', day, next_day) > {SUB_GAP_DAYS})
                  AND day + {SUB_GAP_DAYS} <= '{{card_through}}'
            )
            SELECT CAST(day AS VARCHAR) AS DATE, plan AS PLAN,
                   SUM(gross_adds) AS GROSS_ADDS, SUM(cancels) AS CANCELS,
                   SUM(gross_adds) - SUM(cancels) AS NET_ADDS,
                   SUM(renewals) AS RENEWALS, SUM(new_to_panel) AS NEW_TO_PANEL, SUM(panel_exits) AS PANEL_EXITS
            FROM ev GROUP BY 1, 2 ORDER BY 1, 2
        """,
        methodology=dict(
            source="The web Muse card charges above (Yodlee feeds 3, 4 and 6, same descriptor and price filters), "
                   "plus each charged member's first and last transaction date in the same panels "
                   "(member_tenure, any merchant).",
            filters=[
                (f"Gross add = a payment with no payment in the previous {SUB_GAP_DAYS} days, by a member first "
                 f"seen in the panel more than {TENURE_DAYS} days earlier",
                 "Cards have no sign-up event, so a new subscription is a payment after a gap. The tenure test "
                 "stops an existing subscriber who has just joined the panel from counting as a sign-up; those "
                 "payments are NEW_TO_PANEL instead."),
                (f"Cancellation = no payment within {SUB_GAP_DAYS} days of a member's last payment, dated at last "
                 f"payment + {SUB_GAP_DAYS} days, if the member is still transacting in the panel after that date",
                 "Monthly plans renew about every 30 days, so a missed renewal means the plan ended. Requiring "
                 "later panel activity separates Muse churn from panel churn; lapses by members who have left "
                 "the panel are PANEL_EXITS instead."),
                (f"Renewal = a payment within {SUB_GAP_DAYS} days of the member's previous payment",
                 "The sequence is per member across plans, so a Power-to-Max switch counts as a renewal on the "
                 "new plan, not a gross add."),
            ],
            dedupe="Distinct (member, day, plan), as for subscriptions.",
            measure=f"GROSS_ADDS, CANCELS and NET_ADDS = GROSS_ADDS - CANCELS per day and plan; RENEWALS, "
                    f"NEW_TO_PANEL and PANEL_EXITS complete the reconciliation (every payment is a gross add, "
                    f"renewal or new-to-panel; every lapse a cancellation or panel exit). The first web payment "
                    f"was 2026-09-17, so the first possible cancellation is 2026-10-22.",
            lag=f"Complete through run date minus {CARD_LAG_DAYS} days; a cancellation appears once its date "
                f"is inside that window.",
        ),
    ),
    dict(
        key="agentic_daily",
        title="Agentic Checkout to Non-Stripe Merchants",
        keys=[], measures=["TXNS", "SHOPIFY_TXNS", "PANEL_TXNS"], fill_zero=True,
        start="card_start", through="card_through",
        sql="""
            WITH t AS (
                SELECT day,
                       COUNT(DISTINCT source || '|' || txn_id) AS txns,
                       COUNT(DISTINCT CASE WHEN is_shopify THEN source || '|' || txn_id END) AS shopify_txns
                FROM srs_slice.meta.card_txns
                WHERE signal = 'agentic'
                GROUP BY day
            ), p AS (
                SELECT day, SUM(total_txn) AS panel_txns FROM srs_slice.meta.panel_totals GROUP BY day
            )
            SELECT CAST(p.day AS VARCHAR) AS DATE,
                   COALESCE(t.txns, 0) AS TXNS,
                   COALESCE(t.shopify_txns, 0) AS SHOPIFY_TXNS,
                   p.panel_txns AS PANEL_TXNS
            FROM p LEFT JOIN t ON t.day = p.day
            WHERE p.day BETWEEN '{card_start}' AND '{card_through}'
            ORDER BY 1
        """,
        derived={
            "PER_MILLION": ("TXNS", "PANEL_TXNS", 1e6),
            "PER_MILLION_TR7D": ("TXNS_TR7D", "PANEL_TXNS_TR7D", 1e6),
            "SHOPIFY_SHARE_TR7D": ("SHOPIFY_TXNS_TR7D", "TXNS_TR7D", 1.0),
        },
        methodology=dict(
            source="Same card & bank set as Muse web: Yodlee feeds 3, 4 and 6. Feed 4 bank has had no agentic "
                   "rows to date. 279 PRIME_TAU is left out of v1: its members do not overlap Yodlee, but it is a "
                   "~12.5M-transaction/day panel that surfaces only ~3 agentic descriptors a day (about 10% on "
                   "top of Yodlee), and pooling it would make the per-million rate track 279's panel size rather "
                   "than agentic adoption.",
            filters=[
                ("Description contains LINKAGNT*",
                 "Stripe Link's agent-wallet descriptor ('LINKAGNT* <merchant> WWW.LINK.COM CA'), used until "
                 "2026-09-23."),
                ("Or LINK* followed by a space, anchored on WWW.LINK.CO or SOUTH SAN FRA",
                 "From 09-23/24 Stripe shortened the descriptor to 'LINK* <merchant>'. Bare LINK* also matches "
                 "Cash App and other unrelated billers, so it must carry Stripe's URL or city. LINK.COM* is the "
                 "ordinary Link wallet and is excluded by the 'space after *' rule."),
                ("Shopify flag: 'LINK* SP <store>' or a Shopify / Shop Pay marker",
                 "SP is Shopify's store prefix, so these are agent purchases at Shopify merchants."),
            ],
            dedupe="Distinct (source, transaction id).",
            measure="TXNS = agentic transactions that day. PER_MILLION = TXNS per million panel transactions "
                    "(same feeds, same day). Panel coverage still fills in for ~10 days, so the rate is the "
                    "comparable series and raw counts in the latest days run low. PER_MILLION_TR7D is the ratio "
                    "of 7-day sums, not a mean of daily ratios. SHOPIFY_SHARE_TR7D = Shopify-store share of "
                    "7-day agentic volume. The count is a floor: at merchants that take Stripe directly, an agent "
                    "purchase carries the merchant's own descriptor and is invisible here; at the top agentic "
                    "merchants Link-agent rows are under 0.01% of panel transactions (0.5% at Porkbun) since "
                    "launch (investigations/stripe_vs_link_share.ipynb).",
            lag=f"Complete through run date minus {CARD_LAG_DAYS} days.",
        ),
    ),
    dict(
        key="agentic_merchants",
        title="Top agentic-checkout merchants (trailing 28 days)",
        keys=None, measures=[], fill_zero=False,
        sql="""
            SELECT merchant AS MERCHANT,
                   COUNT(DISTINCT source || '|' || txn_id) AS TXNS,
                   COUNT(DISTINCT source || '|' || member) AS CARDHOLDERS,
                   ROUND(MEDIAN(amount), 2) AS MEDIAN_AMOUNT
            FROM srs_slice.meta.card_txns
            WHERE signal = 'agentic' AND merchant IS NOT NULL
              AND day BETWEEN '{merch_start}' AND '{card_through}'
            GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 25
        """,
        methodology=dict(
            source="The agentic transactions above.",
            filters=[("Merchant = the 2-12 characters after the LINKAGNT* / LINK* prefix (and any SP / DD * / "
                      "QDI* processor prefix)",
                      "Descriptors truncate merchant names, so this is a label for reading, not an entity match.")],
            dedupe="As above.",
            measure="A breakdown table rather than a daily series: transactions, unique cardholders and median "
                    "amount per merchant over the 28 days ending at the card complete-through date. CARDHOLDERS "
                    "= distinct panel members (per source); TXNS well above CARDHOLDERS means repeat agent "
                    "purchases by the same people.",
            lag=f"Complete through run date minus {CARD_LAG_DAYS} days.",
        ),
    ),
    dict(
        key="agentic_samples",
        title="Example agentic-checkout records",
        keys=None, measures=[], fill_zero=False,
        sql="""
            WITH a AS (
                SELECT day, source, amount, merchant, is_shopify,
                       REGEXP_REPLACE(description, 'XXXX+[0-9]+', 'XXXX') AS description,
                       CASE WHEN description ILIKE '%linkagnt*%' THEN 'LINKAGNT*' ELSE 'LINK*' END AS form
                FROM srs_slice.meta.card_txns
                WHERE signal = 'agentic' AND merchant IS NOT NULL AND day <= '{card_through}'
            ), r AS (
                -- Card panels first: they carry the plain Stripe descriptor, where bank rows wrap it in
                -- 'DEBIT CARD PURCHASE AT ... CARD#' text.
                SELECT a.*, ROW_NUMBER() OVER (PARTITION BY form
                                               ORDER BY CASE WHEN source LIKE '% card' THEN 0 ELSE 1 END,
                                                        day DESC, description) AS rn
                FROM a
                WHERE (form = 'LINKAGNT*' AND day < '2026-09-23') OR (form = 'LINK*' AND day >= '2026-09-23')
            )
            SELECT CAST(day AS VARCHAR) AS DATE, form AS FORM, description AS DESCRIPTION,
                   amount AS AMOUNT, merchant AS MERCHANT, is_shopify AS IS_SHOPIFY
            FROM r WHERE rn = 1 ORDER BY 1
        """,
        methodology=dict(
            source="The agentic transactions above.",
            filters=[("The latest LINKAGNT* record before 2026-09-23 and the latest LINK* record from that date",
                      "One example of each descriptor form, to show what the matching rules see.")],
            dedupe="One row per form, from a card panel where one exists; no member or transaction ids are "
                   "published, and masked card-number tails are blanked.",
            measure="DESCRIPTION is the raw card descriptor, MERCHANT the label extracted from it, IS_SHOPIFY "
                    "the Shopify flag.",
            lag=f"Complete through run date minus {CARD_LAG_DAYS} days.",
        ),
    ),
    dict(
        key="app_usage_daily",
        title="AI assistant app downloads and DAU (SensorTower)",
        keys=["APP", "COUNTRY"], measures=["DOWNLOADS", "DAU"], fill_zero=False, zero_before_first=True,
        start="app_start", through=None,
        sql="""
            SELECT CAST(date AS VARCHAR) AS DATE, app AS APP, country AS COUNTRY,
                   downloads AS DOWNLOADS, dau AS DAU
            FROM srs_slice.meta.app_usage
            WHERE date >= '{app_start}'
            ORDER BY 2, 3, 1
        """,
        methodology=dict(
            source="SensorTower SENSORTOWER.COMMON.CORE (refreshed daily by sync_sensortower_core).",
            filters=[
                (f"Unified product {MUSE_KEY} ('Muse from Meta', com.facebook.aura / iOS 6760173601)",
                 "Muse is a new app, not a rename of Meta AI. It is live in the US (from 2026-09-07) and Canada "
                 "(from 09-14) only."),
                (f"Unified product {META_AI_KEY} ('Meta AI', com.facebook.stella)",
                 "The predecessor app, shown for cannibalisation: its US downloads fell by about 60% in launch week."),
                ("Share set: Muse, ChatGPT (OpenAI), Gemini (Google), Claude (Anthropic), Grok (xAI), each by its "
                 "unified product key: " + ", ".join(f"{a} {APP_KEYS[a]}" for a in SHARE_APPS if a != "Muse"),
                 "Matched by key, never by name: 'ChatGPT' alone is 12 SensorTower products, mostly clones, and "
                 "there is a clone 'Muse from Meta'. Share chart = the app's daily value over the sum of the five "
                 "apps' daily values, for the same metric and country (the summary tile uses TR7D). Meta AI is excluded from the share set (it is the app Muse "
                 "sits beside, shown in its own chart)."),
                ("Country US and WW only",
                 "WW is SensorTower's worldwide aggregate row; summing countries would double count it."),
            ],
            dedupe="iPhone and Android phone summed per app, country and day (a user active on both counts twice "
                   "in DAU; small for a phone app).",
            measure="DOWNLOADS = estimated first-time downloads; DAU = estimated daily active users. Values are "
                    "modelled vendor estimates, best read as trends.",
            lag="Downloads run to about T-2 and DAU to T-3; the latest DAU day arrives as 0 and is treated as "
                "missing. TR7D is shown only where all 7 days are present. Days before an app's first SensorTower "
                "row are zero (the app did not exist), so Muse's TR7D starts on launch day and builds over its "
                "first week.",
        ),
    ),
    dict(
        key="ad_spend_daily",
        title="Muse digital ad spend (Pathmatics)",
        keys=["COUNTRY", "PUBLISHER"], measures=["SPEND"], fill_zero=True,
        start="card_start", through=None,
        sql="""
            SELECT CAST(date AS VARCHAR) AS DATE, country AS COUNTRY, publisher AS PUBLISHER,
                   ROUND(SUM(spend), 0) AS SPEND
            FROM srs_slice.meta.ad_spend
            WHERE date >= '{card_start}'
            GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
        """,
        methodology=dict(
            source="Pathmatics PATHMATICS.COMMON.DIGITAL_AD_SPEND (estimated digital ad spend by advertiser, "
                   "publisher, region and day).",
            filters=[
                ("Advertiser 'Muse from Meta'",
                 "Pathmatics tracks Muse as its own advertiser, separate from Meta AI and Meta's other brands."),
                ("Region United States or Canada",
                 "Muse is live in the US and Canada only; other regions carry negligible spend."),
            ],
            dedupe="Summed per day, country and publisher.",
            measure="SPEND = estimated US$ spend. A day with no row is no observed spend. Pathmatics covers "
                    "digital channels only, not TV, and the "
                    "team suspects budget has moved to TV, so a fall here is not a fall in total marketing.",
            lag="Vendor series; the latest day shown is the latest Pathmatics has published (about T-3).",
        ),
    ),
    dict(
        key="web_traffic_daily",
        title="muse.ai web traffic (SimilarWeb)",
        keys=["COUNTRY"], measures=["VISITS"], fill_zero=False,
        start="card_start", through=None,
        sql="""
            SELECT CAST(date AS VARCHAR) AS DATE, country AS COUNTRY, ROUND(SUM(visits), 0) AS VISITS
            FROM srs_slice.meta.web_traffic
            WHERE date >= '{card_start}'
            GROUP BY 1, 2 ORDER BY 1, 2
        """,
        methodology=dict(
            source="SimilarWeb daily visits, SIMILARWEB.SNOWFLAKE_INTEGRATION.DOWNSTREAM_DAILY (metric "
                   "ALL_TRAFFIC_VISITS). Until the pipeline loads muse.ai, the build uses a SimilarWeb API "
                   "snapshot with the same definition; the freshness line names the source used.",
            filters=[
                ("Domain muse.ai, desktop plus mobile web, subdomains included", "Muse's web app."),
                ("Country US and WW", "WW is SimilarWeb's worldwide total, not a sum of countries."),
            ],
            dedupe="One value per day and country.",
            measure="VISITS = estimated visits. Modelled vendor estimates, best read as trends. l.meta.ai (Meta "
                    "AI's link-routing domain) is not yet tracked. muse.ai sends few outgoing clicks, which fits "
                    "an agentic browser that acts on pages itself.",
            lag="Vendor series, about T-3.",
        ),
    ),
    dict(
        key="launch_benchmark",
        title="Launch benchmark: US downloads by day since launch (SensorTower)",
        keys=None, measures=[], fill_zero=False,
        sql="""
            SELECT APP, DATE, DAY_N, DOWNLOADS, CUM_DOWNLOADS,
                   CASE WHEN N7 = 7 THEN ROUND(SUM7 / 7, 0) END AS DOWNLOADS_TR7D
            FROM (
                SELECT app AS APP, CAST(date AS VARCHAR) AS DATE,
                       DATEDIFF('day', MIN(date) OVER (PARTITION BY app), date) AS DAY_N,
                       downloads AS DOWNLOADS,
                       SUM(downloads) OVER (PARTITION BY app ORDER BY date
                                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS CUM_DOWNLOADS,
                       SUM(downloads) OVER (PARTITION BY app ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS SUM7,
                       COUNT(*) OVER (PARTITION BY app ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS N7
                FROM srs_slice.meta.benchmark
            ) t
            ORDER BY APP, DAY_N
        """,
        methodology=dict(
            source="SensorTower SENSORTOWER.COMMON.CORE for Muse, Sora, Threads, ChatGPT and Claude; Clubhouse "
                   "from a SensorTower portal export (it is not in CORE).",
            filters=[
                ("Unified product keys: " + ", ".join(f"{a} {k}" for a, k in BENCHMARK_KEYS.items()),
                 "Matched by key, never by name (clones share names)."),
                ("US only; iPhone + Android phone", "The export for Clubhouse is summed the same way (iPad excluded)."),
                (f"Day 0 = first day with downloads; window day 0 to {BENCHMARK_DAYS}",
                 "Each app's CORE history starts on its launch day."),
                (f"Clubhouse day 0 = {BENCHMARK_DAY0['Clubhouse']}",
                 "Its viral breakout, the first day of the sustained jump in US downloads, rather than its "
                 "invite-only iOS release in spring 2020."),
            ],
            dedupe="Summed per app and day.",
            measure="DOWNLOADS = estimated first-time US downloads; CUM_DOWNLOADS = running total from day 0; "
                    "DOWNLOADS_TR7D = mean of the last 7 days. Muse has fewer days than the others.",
            lag="Downloads run to about T-2.",
        ),
    ),
]

# Methodology order follows the page.
_PAGE_ORDER = ["app_usage_daily", "ad_spend_daily", "launch_benchmark", "web_traffic_daily", "muse_web_daily",
               "muse_inapp_daily", "inapp_flows_daily", "web_flows_daily", "agentic_daily", "agentic_merchants",
               "agentic_samples"]
SECTIONS.sort(key=lambda s: _PAGE_ORDER.index(s["key"]))

# Headline tiles, read from the latest complete TR7D value of each series.
SUMMARY = [
    dict(label="Muse US downloads/day", section="app_usage_daily", col="DOWNLOADS_TR7D",
         where={"APP": "Muse", "COUNTRY": "US"}),
    dict(label="Muse US DAU", section="app_usage_daily", col="DAU_TR7D", where={"APP": "Muse", "COUNTRY": "US"}),
    dict(label="Meta AI US DAU", section="app_usage_daily", col="DAU_TR7D", where={"APP": "Meta AI", "COUNTRY": "US"}),
    dict(label="Muse US ad spend $/day", section="ad_spend_daily", col="SPEND_TR7D", where={"COUNTRY": "US"}),
    # share_of: VALUE = this app's TR7D / the sum over share_of apps' TR7D on the same day
    dict(label="Muse share of US AI-assistant DAU", section="app_usage_daily", col="DAU_TR7D",
         where={"APP": "Muse", "COUNTRY": "US"}, share_of={"key": "APP", "values": SHARE_APPS}),
    dict(label="muse.ai WW visits/day", section="web_traffic_daily", col="VISITS_TR7D", where={"COUNTRY": "WW"}),
    dict(label="Muse web gross adds/day", section="web_flows_daily", col="GROSS_ADDS_TR7D", where={}),
    dict(label="Muse in-app gross adds/day", section="inapp_flows_daily", col="GROSS_ADDS_TR7D", where={}),
    dict(label="Muse in-app cancels/day", section="inapp_flows_daily", col="CANCELS_TR7D", where={}),
    dict(label="Agentic txns per million", section="agentic_daily", col="PER_MILLION_TR7D", where={}),
]
