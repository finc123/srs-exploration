"""Meta Muse app: source loads, report sections and their methodology, in one place.

Two layers, mirroring the monorepo workflow (`workflows/jobs/meta/muse.yaml`):

1. LOADS (Snowflake SQL). Narrow pulls into what are `srs_mcp.meta.muse_*` in the
   monorepo: the card panels are tables there; everything else is a view over a
   production table (SensorTower CORE, Pathmatics, SimilarWeb VISITS_V2, NIQ ITEMS_LIVE):
     card_txns     one row per matched card/bank transaction (signal = muse_web | agentic)
     panel_totals  distinct transactions per source per day (denominator for per-million)
     member_panel  days each web Muse payer transacted (any merchant), per source (panel activity)
     niq_receipts  one row per Muse e-receipt line item
     app_usage     SensorTower downloads / DAU per app x country x day
     benchmark     SensorTower US downloads, DAU, sessions, minutes per benchmark app x day: day 0 to +120
                   and the last 100 days, tagged by bench_window
     ad_spend      Pathmatics Muse digital ad spend per country x publisher x day
     web_traffic   SimilarWeb muse.ai visits per country x day
   Each table is named with a muse_ prefix (srs_mcp.meta.muse_card_txns, ...): the
   schema is shared with other Meta datasets. Card loads are one pruned range query
   per source, cached locally per day by build_json.py.

2. SECTIONS (portable SQL over the srs_mcp.meta.muse_* tables). Run by DuckDB over
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
NIQ_LAG_DAYS = 2               # SRS_SLICE.COMMON.ITEMS_LIVE is rebuilt ~2:30 AM ET, before NIQ fills in
                               # yesterday (~10:45 AM ET), so it is complete through two days ago
REFRESH_DAYS = 14              # card days newer than this are re-pulled every run
TR_DAYS = 7                    # trailing window for every *_TR7D column
SUB_GAP_DAYS = 35              # card subs: a payment after this many days without one is a new subscription,
                               # and no payment for this long after the last one is a lapse
TENURE_DAYS = 35               # card subs: a gross add needs the member in the panel this long before paying
ACTIVE_DAYS = 30               # card subs: a member is active (still in the panel) with >= 1 transaction in this
                               # many days ending on the lapse date; else the lapse is a panel exit

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
# history starts on launch day for each). Clubhouse is not in CORE yet (being added
# upstream); once it is, add its key here, with day 0 at its viral breakout (BENCHMARK_DAY0)
# rather than its spring-2020 invite-only release.
BENCHMARK_KEYS = {
    "Muse": MUSE_KEY,
    "Sora": "68dc489f4e04a24f7d0d0aeb",
    "Threads": "64a72c98ad4adb0e06dbc506",
    "ChatGPT": APP_KEYS["ChatGPT"],
    "Claude": APP_KEYS["Claude"],
}
BENCHMARK_DAYS = 120
RECENT_DAYS = 90               # time spent: the "Last 90 days" calendar view
RECENT_PULL_DAYS = RECENT_DAYS + 10   # margin for the SensorTower lag; the section trims to RECENT_DAYS
BENCHMARK_DAY0 = {"Clubhouse": "2020-12-15"}   # first day of the sustained jump in US downloads (15k -> 25k)
# Muse's day 0 is the public launch (LAUNCH), not its partial first SensorTower day (09-07); applied in the section SQL.

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
               {src['prune'] or 'NULL'}::DATE AS file_date,
               ROUND({a}, 2) AS amount,
               {d} AS description,
               IFF({agentic_sql(d)}, 'agentic', 'muse_web') AS signal,
               IFF({agentic_sql(d)}, NULL, {plan_sql(a)}) AS plan,
               IFF({agentic_sql(d)}, {merchant_sql(d)}, NULL) AS merchant
        FROM {src['table']}
        WHERE {_window(src, start, end)}
          AND ({agentic_sql(d)} OR {muse_web_sql(d, a)})
    """


# Panel activity for web Muse payers: one row per member per source per day they transacted (any merchant),
# from early enough that the TENURE_DAYS test is decidable for every payment in the card window. The web
# flows read first_seen (MIN day) and the ACTIVE_DAYS window before each lapse from it.
# Yodlee's own membership metadata is not used: on 2026-10-09 its LAST_REFRESH files were missing 15 of 69
# payers (and ACCOUNT_ATTRIBUTES 26) who were still transacting daily, so observed transactions are the
# only complete record of who is in the panel.
TENURE_START = (date.fromisoformat(CARD_START) - timedelta(days=TENURE_DAYS)).isoformat()


def member_panel_sql(src: dict, members: list[str], end: str) -> str:
    ids = ", ".join(f"'{m}'" for m in members)
    return f"""
        SELECT '{src['name']}' AS source, CAST({src['member']} AS VARCHAR) AS member,
               {src['date']}::DATE AS day, COUNT(*) AS txns
        FROM {src['table']}
        WHERE {_window(src, TENURE_START, end)} AND {src['member']} IN ({ids})
        GROUP BY 1, 2, 3
    """


def panel_total_sql(src: dict, start: str, end: str) -> str:
    return f"""
        SELECT '{src['name']}' AS source, {src['date']}::DATE AS day, COUNT(DISTINCT {src['txn']}) AS total_txn
        FROM {src['table']} WHERE {_window(src, start, end)}
        GROUP BY 1, 2
    """


# Active mailboxes only: the SRS convention for NIQ panels. Read from SRS_SLICE.COMMON.ITEMS_LIVE, the
# processed NIQ line-item table (mailbox status already joined). No QUALITY filter: for Muse the only
# non-quality merchants are the iTunes / Google Play "Cancellation" senders, which the flows need.
NIQ_SQL = f"""
    SELECT orderdate::DATE AS order_date, mailbox_id, merchant_name, item_description AS description,
           item_price, ordertotal AS order_total, mailbox_status,
           CASE WHEN item_description ILIKE '%power%' THEN 'Power'
                WHEN item_description ILIKE '%max%' THEN 'Max' ELSE 'Other' END AS plan,
           CASE WHEN merchant_name ILIKE '%cancel%' OR item_description ILIKE '%cancel%'
                     OR item_description ILIKE '%will end on%' THEN 'cancel'
                WHEN item_description ILIKE '%trial%' THEN 'trial' ELSE 'charge' END AS kind,
           CASE WHEN merchant_name ILIKE 'itunes%' THEN 'Apple'
                WHEN merchant_name ILIKE 'google play%' THEN 'Google Play' ELSE 'Other' END AS store
    FROM srs_slice.common.items_live
    WHERE orderdate BETWEEN '{CARD_START}' AND CURRENT_DATE
      AND item_description ILIKE '%muse from meta%'
      AND mailbox_status ILIKE 'active'
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

# One CORE read for the benchmark apps, US, in two windows (bench_window): 'launch' = each app's first
# download day to +BENCHMARK_DAYS, 'recent' = the last RECENT_PULL_DAYS. A day in both is returned twice.
# Zero sessions or minutes is a missing value, like DAU.
BENCHMARK_SQL = f"""
    WITH d AS (
        SELECT date::DATE AS date,
               CASE unified_product_key {" ".join(f"WHEN '{k}' THEN '{a}'" for a, k in BENCHMARK_KEYS.items())} END AS app,
               SUM(downloads) AS downloads,
               NULLIF(SUM(dau), 0) AS dau,
               NULLIF(SUM(sessions), 0) AS sessions,
               NULLIF(SUM(minutes), 0) AS minutes
        FROM sensortower.common.core
        WHERE unified_product_key IN ({", ".join(f"'{k}'" for k in BENCHMARK_KEYS.values())})
          AND country_code = 'US'
        GROUP BY 1, 2
    ), f AS (
        SELECT app, MIN(date) AS day0 FROM d WHERE downloads > 0 GROUP BY app
    )
    SELECT d.date, d.app, 'launch' AS bench_window, d.downloads, d.dau, d.sessions, d.minutes
    FROM d JOIN f ON f.app = d.app
    WHERE d.date BETWEEN f.day0 AND DATEADD('day', {BENCHMARK_DAYS}, f.day0)
    UNION ALL
    SELECT d.date, d.app, 'recent', d.downloads, d.dau, d.sessions, d.minutes
    FROM d
    WHERE d.date >= DATEADD('day', -{RECENT_PULL_DAYS}, CURRENT_DATE)
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

# SimilarWeb daily visits and total time spent from the pipeline's consumer table. time_spent is
# total minutes (visits x average visit duration), so minutes per visit = time_spent / visits.
# chatgpt.com and claude.ai are the comparison sites for the web time-spent chart.
WEB_DOMAINS = ["muse.ai", "chatgpt.com", "claude.ai"]
WEB_TRAFFIC_SQL = f"""
    SELECT date::DATE AS date, domain, country,
           SUM(CASE WHEN metric = 'all_traffic_visits' THEN value END) AS visits,
           SUM(CASE WHEN metric = 'all_traffic_time_spent' THEN value END) AS time_spent
    FROM similarweb.common.visits_v2
    WHERE domain IN ({", ".join(f"'{d}'" for d in WEB_DOMAINS)})
      AND panel = 'all domain'
      AND metric IN ('all_traffic_visits', 'all_traffic_time_spent')
      AND channel IS NULL
      AND country IN ('US', 'WW')
      AND date >= '{CARD_START}'
    GROUP BY 1, 2, 3
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
                  FROM srs_mcp.meta.muse_card_txns
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
            FROM srs_mcp.meta.muse_niq_receipts
            WHERE order_date BETWEEN '{card_start}' AND '{niq_through}' AND store <> 'Other'
            GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
        """,
        methodology=dict(
            source="NIQ e-receipts, SRS_SLICE.COMMON.ITEMS_LIVE (the processed NIQ line-item table, one row per "
                   "receipt line item, with mailbox status), via the SRS_MCP.META.MUSE_NIQ_RECEIPTS view.",
            filters=[
                ("Active mailboxes only (mailbox_status = 'active')",
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
                FROM srs_mcp.meta.muse_niq_receipts
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
        keys=["PLAN"],
        measures=["GROSS_ADDS", "CANCELS", "NET_ADDS", "RENEWALS", "NEW_TO_PANEL", "PANEL_EXITS", "EXITED_ADDS",
                  "UNSEEN_LAPSES"],
        fill_zero=True, start="card_start", through="card_through",
        sql=f"""
            WITH c AS (
                SELECT DISTINCT member, day, plan
                FROM srs_mcp.meta.muse_card_txns
                WHERE signal = 'muse_web' AND day BETWEEN '{{card_start}}' AND '{{card_through}}'
                  AND {bucket_filter_sql()}
            ), d AS (
                -- days each payer transacted with any merchant (panel activity)
                SELECT DISTINCT member, day FROM srs_mcp.meta.muse_member_panel
            ), t AS (
                SELECT member, MIN(day) AS first_seen FROM d GROUP BY member
            ), p AS (
                SELECT c.member, c.day, c.plan,
                       CASE WHEN LAG(c.day) OVER (PARTITION BY c.member ORDER BY c.day) IS NOT NULL
                             AND DATEDIFF('day', LAG(c.day) OVER (PARTITION BY c.member ORDER BY c.day), c.day)
                                 <= {SUB_GAP_DAYS} THEN 1 ELSE 0 END AS is_renewal,
                       CASE WHEN DATEDIFF('day', t.first_seen, c.day) > {TENURE_DAYS} THEN 1 ELSE 0 END AS is_tenured,
                       LEAD(c.day) OVER (PARTITION BY c.member ORDER BY c.day) AS next_day
                FROM c LEFT JOIN t ON t.member = c.member
            ), s AS (
                -- spell = one subscription: a non-renewal payment and the renewals after it
                SELECT p.*, SUM(1 - is_renewal) OVER (PARTITION BY member ORDER BY day
                                                      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS spell
                FROM p
            ), l AS (
                -- unseen_start = the spell began with a NEW_TO_PANEL payment, so we never saw it start
                SELECT s.*, MAX(CASE WHEN is_renewal = 0 THEN 1 - is_tenured END)
                                OVER (PARTITION BY member, spell) AS unseen_start
                FROM s
            ), lapse AS (
                -- no payment within the gap after this one: the spell ended, dated at the end of the gap
                SELECT member, spell, plan, unseen_start, day + {SUB_GAP_DAYS} AS lapse_day
                FROM l
                WHERE (next_day IS NULL OR DATEDIFF('day', day, next_day) > {SUB_GAP_DAYS})
                  AND day + {SUB_GAP_DAYS} <= '{{card_through}}'
            ), lapse_act AS (
                -- active member = at least one transaction (any merchant) in the {ACTIVE_DAYS} days ending on the lapse
                SELECT x.member, x.spell, x.plan, x.unseen_start, x.lapse_day, COUNT(d.day) AS active_days
                FROM lapse x
                LEFT JOIN d ON d.member = x.member
                           AND d.day BETWEEN x.lapse_day - {ACTIVE_DAYS - 1} AND x.lapse_day
                GROUP BY 1, 2, 3, 4, 5
            ), exited AS (
                SELECT DISTINCT member, spell FROM lapse_act WHERE active_days = 0
            ), ev AS (
                -- payments: renewal, gross add (tenured member, no payment in the gap), or too new to the panel
                -- to tell; a gross add whose spell ended with the member gone from the panel is EXITED_ADDS
                SELECT l.day, l.plan,
                       CASE WHEN is_renewal = 0 AND is_tenured = 1 AND e.member IS NULL THEN 1 ELSE 0 END AS gross_adds,
                       0 AS cancels,
                       is_renewal AS renewals,
                       CASE WHEN is_renewal = 0 AND is_tenured = 0 THEN 1 ELSE 0 END AS new_to_panel,
                       0 AS panel_exits,
                       CASE WHEN is_renewal = 0 AND is_tenured = 1 AND e.member IS NOT NULL THEN 1 ELSE 0 END
                           AS exited_adds,
                       0 AS unseen_lapses
                FROM l LEFT JOIN exited e ON e.member = l.member AND e.spell = l.spell
                UNION ALL
                -- lapses: a cancellation if the member was active in the panel, else a panel exit; a spell we
                -- never saw start (no gross add counted) ends as UNSEEN_LAPSES, so both ends are excluded
                SELECT lapse_day, plan, 0,
                       CASE WHEN unseen_start = 0 AND active_days > 0 THEN 1 ELSE 0 END,
                       0, 0,
                       CASE WHEN unseen_start = 0 AND active_days = 0 THEN 1 ELSE 0 END,
                       0,
                       unseen_start
                FROM lapse_act
            )
            SELECT CAST(day AS VARCHAR) AS DATE, plan AS PLAN,
                   SUM(gross_adds) AS GROSS_ADDS, SUM(cancels) AS CANCELS,
                   SUM(gross_adds) - SUM(cancels) AS NET_ADDS,
                   SUM(renewals) AS RENEWALS, SUM(new_to_panel) AS NEW_TO_PANEL, SUM(panel_exits) AS PANEL_EXITS,
                   SUM(exited_adds) AS EXITED_ADDS, SUM(unseen_lapses) AS UNSEEN_LAPSES
            FROM ev GROUP BY 1, 2 ORDER BY 1, 2
        """,
        methodology=dict(
            source="The web Muse card charges above (Yodlee feeds 3, 4 and 6, same descriptor and price filters), "
                   "plus each charged member's panel activity: the days they transacted with any merchant in "
                   "the same panels (muse_member_panel). There is no card-panel active-member table to reuse "
                   "(srs_slice.common.normal_active is NIQ mailboxes only), and Yodlee's own membership tables "
                   "(LAST_REFRESH, ACCOUNT_ATTRIBUTES) are incomplete: on 2026-10-09 they were missing 15 and "
                   "26 of 69 payers who were still transacting daily.",
            filters=[
                (f"Gross add = a payment with no payment in the previous {SUB_GAP_DAYS} days, by a member first "
                 f"seen transacting in the panel more than {TENURE_DAYS} days earlier",
                 "Cards have no sign-up event, so a new subscription is a payment after a gap. The membership "
                 "test stops an existing subscriber who has just joined the panel from counting as a sign-up; "
                 "those payments are NEW_TO_PANEL instead."),
                (f"Cancellation = no payment within {SUB_GAP_DAYS} days of a member's last payment, dated at last "
                 f"payment + {SUB_GAP_DAYS} days, if the member is active: at least one transaction with any "
                 f"merchant in the {ACTIVE_DAYS} days ending on that date",
                 "Monthly plans renew about every 30 days, so a missed renewal means the plan ended. The activity "
                 "test separates Muse churn from panel churn, and its window sits wholly inside complete data, "
                 "so a recent lapse needs no settling period."),
                ("Panel exit = the same lapse by a member with no transaction in that window; the gross add that "
                 "started their subscription is then removed (EXITED_ADDS)",
                 "A member who has left the panel tells us nothing about whether they cancelled, so neither their "
                 "lapse nor their sign-up is counted. This rewrites history: a gross add drops off its original "
                 "date once the member is found to have left."),
                ("A lapse ending a subscription that began as NEW_TO_PANEL is UNSEEN_LAPSES, not a cancellation",
                 "We never saw that subscription start (the member joined the panel already subscribed), so it "
                 "has no gross add; counting its end as a cancellation would bias net adds down. Both ends of a "
                 "subscription are counted only when we saw it start."),
                (f"Renewal = a payment within {SUB_GAP_DAYS} days of the member's previous payment",
                 "The sequence is per member across plans, so a Power-to-Max switch counts as a renewal on the "
                 "new plan, not a gross add."),
            ],
            dedupe="Distinct (member, day, plan), as for subscriptions.",
            measure=f"GROSS_ADDS, CANCELS and NET_ADDS = GROSS_ADDS - CANCELS per day and plan; RENEWALS, "
                    f"NEW_TO_PANEL, PANEL_EXITS, EXITED_ADDS and UNSEEN_LAPSES complete the reconciliation (every "
                    f"payment is a gross add, exited add, renewal or new-to-panel; every lapse a cancellation, panel "
                    f"exit or unseen lapse). "
                    f"The first web payment "
                    f"was 2026-09-17, so the first possible cancellation is 2026-10-22.",
            lag=f"Complete through run date minus {CARD_LAG_DAYS} days; a cancellation appears once its date "
                f"is inside that window.",
        ),
    ),
    dict(
        key="agentic_daily",
        title="Agentic Checkout to Non-Stripe Merchants",
        keys=[], measures=["TXNS", "PANEL_TXNS"], fill_zero=True,
        start="card_start", through="card_through",
        sql="""
            WITH t AS (
                SELECT day, COUNT(DISTINCT source || '|' || txn_id) AS txns
                FROM srs_mcp.meta.muse_card_txns
                WHERE signal = 'agentic'
                GROUP BY day
            ), p AS (
                SELECT day, SUM(total_txn) AS panel_txns FROM srs_mcp.meta.muse_panel_totals GROUP BY day
            )
            SELECT CAST(p.day AS VARCHAR) AS DATE,
                   COALESCE(t.txns, 0) AS TXNS,
                   p.panel_txns AS PANEL_TXNS
            FROM p LEFT JOIN t ON t.day = p.day
            WHERE p.day BETWEEN '{card_start}' AND '{card_through}'
            ORDER BY 1
        """,
        derived={
            "PER_MILLION": ("TXNS", "PANEL_TXNS", 1e6),
            "PER_MILLION_TR7D": ("TXNS_TR7D", "PANEL_TXNS_TR7D", 1e6),
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
            ],
            dedupe="Distinct (source, transaction id).",
            measure="TXNS = agentic transactions that day. PER_MILLION = TXNS per million panel transactions "
                    "(same feeds, same day). Panel coverage still fills in for ~10 days, so the rate is the "
                    "comparable series and raw counts in the latest days run low. PER_MILLION_TR7D is the ratio "
                    "of 7-day sums, not a mean of daily ratios. The count is a floor: at merchants that take Stripe directly, an agent "
                    "purchase carries the merchant's own descriptor and is invisible here; at the top agentic "
                    "merchants Link-agent rows are under 0.01% of panel transactions (0.5% at Porkbun) since "
                    "launch (investigations/stripe_vs_link_share.ipynb).",
            lag=f"Complete through run date minus {CARD_LAG_DAYS} days.",
        ),
    ),
    dict(
        key="agentic_merchants",
        title="Top agentic-checkout merchants (since launch and trailing 28 days)",
        keys=None, measures=[], fill_zero=False,
        sql="""
            WITH w AS (
                SELECT 'Since launch' AS window_name, CAST('""" + LAUNCH + """' AS DATE) AS start_day
                UNION ALL SELECT 'Last 28 days', CAST('{merch_start}' AS DATE)
            ), t AS (
                SELECT DISTINCT w.window_name, c.source, c.txn_id, c.member, c.amount, c.merchant
                FROM srs_mcp.meta.muse_card_txns c
                JOIN w ON c.day BETWEEN w.start_day AND '{card_through}'
                WHERE c.signal = 'agentic'
            ), tot AS (
                -- denominator: every agentic transaction in the window, including unlabelled ones
                SELECT window_name, SUM(amount) AS spend FROM t GROUP BY 1
            ), m AS (
                SELECT t.window_name, t.merchant,
                       COUNT(DISTINCT t.source || '|' || t.txn_id) AS txns,
                       COUNT(DISTINCT t.source || '|' || t.member) AS cardholders,
                       ROUND(MEDIAN(t.amount), 2) AS median_amount,
                       ROUND(1.0 * SUM(t.amount) / MAX(tot.spend), 4) AS spend_share
                FROM t JOIN tot ON tot.window_name = t.window_name
                WHERE t.merchant IS NOT NULL
                GROUP BY 1, 2
            )
            SELECT window_name AS PERIOD, merchant AS MERCHANT, txns AS TXNS, cardholders AS CARDHOLDERS,
                   median_amount AS MEDIAN_AMOUNT, spend_share AS SPEND_SHARE
            FROM (SELECT m.*, ROW_NUMBER() OVER (PARTITION BY window_name ORDER BY txns DESC, merchant) AS rn FROM m) r
            WHERE rn <= 25
            ORDER BY 1 DESC, rn
        """,
        methodology=dict(
            source="The agentic transactions above.",
            filters=[("Merchant = the 2-12 characters after the LINKAGNT* / LINK* prefix (and any SP / DD * / "
                      "QDI* processor prefix)",
                      "Descriptors truncate merchant names, so this is a label for reading, not an entity match.")],
            dedupe="As above.",
            measure="A breakdown table rather than a daily series: the top 25 merchants by transactions, with "
                    "unique cardholders and median amount, for two windows ending at the card complete-through "
                    f"date: PERIOD = 'Since launch' (from {LAUNCH}, growing each day) or 'Last 28 days'. CARDHOLDERS "
                    "= distinct panel members (per source); TXNS well above CARDHOLDERS means repeat agent "
                    "purchases by the same people. SPEND_SHARE = the merchant's agentic $ over all agentic $ "
                    "observed in the same window (every Link-agent transaction, including the few with no "
                    "readable merchant label), so it is a share of observed agentic spend, not of the "
                    "merchant's total sales.",
            lag=f"Complete through run date minus {CARD_LAG_DAYS} days.",
        ),
    ),
    dict(
        key="agentic_samples",
        title="Example agentic-checkout records",
        keys=None, measures=[], fill_zero=False,
        sql="""
            WITH a AS (
                SELECT day, source, amount, merchant,
                       REGEXP_REPLACE(description, 'XXXX+[0-9]+', 'XXXX') AS description,
                       CASE WHEN description ILIKE '%linkagnt*%' THEN 'LINKAGNT*' ELSE 'LINK*' END AS form
                FROM srs_mcp.meta.muse_card_txns
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
                   amount AS AMOUNT, merchant AS MERCHANT
            FROM r WHERE rn = 1 ORDER BY 1
        """,
        methodology=dict(
            source="The agentic transactions above.",
            filters=[("The latest LINKAGNT* record before 2026-09-23 and the latest LINK* record from that date",
                      "One example of each descriptor form, to show what the matching rules see.")],
            dedupe="One row per form, from a card panel where one exists; no member or transaction ids are "
                   "published, and masked card-number tails are blanked.",
            measure="DESCRIPTION is the raw card descriptor, MERCHANT the label extracted from it.",
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
            FROM srs_mcp.meta.muse_app_usage
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
            FROM srs_mcp.meta.muse_ad_spend
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
            FROM srs_mcp.meta.muse_web_traffic
            WHERE domain = 'muse.ai'
              AND date >= '{card_start}'
            GROUP BY 1, 2 ORDER BY 1, 2
        """,
        methodology=dict(
            source="SimilarWeb daily visits, SIMILARWEB.COMMON.VISITS_V2 (the SimilarWeb pipeline's consumer "
                   "table; metric all_traffic_visits).",
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
        title="Launch benchmark: US downloads and DAU by day since launch (SensorTower)",
        keys=None, measures=[], fill_zero=False,
        sql="""
            SELECT APP, DATE, DAY_N, DOWNLOADS, CUM_DOWNLOADS,
                   CASE WHEN N7 = 7 THEN ROUND(SUM7 / 7, 0) END AS DOWNLOADS_TR7D,
                   DAU,
                   ROUND(1.0 * DAU / NULLIF(CUM_DOWNLOADS, 0), 4) AS RETENTION
            FROM (
                SELECT app AS APP, CAST(date AS VARCHAR) AS DATE,
                       DATEDIFF('day', MIN(date) OVER (PARTITION BY app), date) AS DAY_N,
                       downloads AS DOWNLOADS, dau AS DAU,
                       SUM(downloads) OVER (PARTITION BY app ORDER BY date
                                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS CUM_DOWNLOADS,
                       SUM(downloads) OVER (PARTITION BY app ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS SUM7,
                       COUNT(*) OVER (PARTITION BY app ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS N7
                FROM srs_mcp.meta.muse_benchmark
                WHERE bench_window = 'launch'
                  AND NOT (app = 'Muse' AND date < '""" + LAUNCH + """')   -- Muse day 0 = public launch
            ) t
            ORDER BY APP, DAY_N
        """,
        methodology=dict(
            source="SensorTower SENSORTOWER.COMMON.CORE for Muse, Sora, Threads, ChatGPT and Claude. Clubhouse "
                   "will be added once it is in CORE.",
            filters=[
                ("Unified product keys: " + ", ".join(f"{a} {k}" for a, k in BENCHMARK_KEYS.items()),
                 "Matched by key, never by name (clones share names)."),
                ("US only; iPhone + Android phone", "iPad excluded, as in every SensorTower section."),
                (f"Day 0 = first day with downloads; window day 0 to {BENCHMARK_DAYS}",
                 "Each app's CORE history starts on its launch day."),
                (f"Muse day 0 = {LAUNCH} (public launch)",
                 "SensorTower's first Muse day, 2026-09-07, is a partial pre-launch day (about 8k US downloads "
                 "against about 115k on launch day), so day 0 is the first full day. Those ~8k downloads "
                 "are left out of Muse's cumulative total, which understates it by under 1% after the first "
                 "week."),
            ],
            dedupe="Summed per app and day.",
            measure="DOWNLOADS = estimated first-time US downloads; CUM_DOWNLOADS = running total from day 0; "
                    "DOWNLOADS_TR7D = mean of the last 7 days. DAU = estimated US daily active users that day. "
                    "RETENTION = DAU / CUM_DOWNLOADS on the same day: a proxy for the share of everyone who has "
                    "downloaded the app who is still using it daily. It is not cohort retention (re-installs and "
                    "multi-device users blur it) and is best compared across apps at the same day since launch. "
                    "Muse has fewer days than the others.",
            lag="Downloads run to about T-2 and DAU to about T-3; the latest DAU day arrives as 0 and is treated "
                "as missing.",
        ),
    ),
    dict(
        key="time_spent",
        title="Engagement: time spent, US, by day since launch and over the last 90 days (SensorTower)",
        keys=None, measures=[], fill_zero=False,
        # Two views of the same apps (BENCH_WINDOW): 'launch' by DAY_N from each app's day 0, and 'recent' by DATE over
        # the RECENT_DAYS ending on the latest day with minutes. The *_TR7D ratios divide 7-day sums, using only
        # the days in the window where both the numerator and the denominator are present.
        sql="""
            WITH b AS (
                SELECT app, bench_window, date, sessions, minutes, dau
                FROM srs_mcp.meta.muse_benchmark
                WHERE app <> 'Clubhouse'
                  AND NOT (app = 'Muse' AND date < '""" + LAUNCH + """')   -- Muse day 0 = public launch
            ), r AS (
                SELECT MAX(date) AS through FROM b WHERE bench_window = 'recent' AND minutes IS NOT NULL
            ), w AS (
                SELECT b.*,
                       CASE WHEN sessions IS NOT NULL AND minutes IS NOT NULL THEN minutes END AS min_s,
                       CASE WHEN sessions IS NOT NULL AND minutes IS NOT NULL THEN sessions END AS ses_s,
                       CASE WHEN dau IS NOT NULL AND minutes IS NOT NULL THEN minutes END AS min_d,
                       CASE WHEN dau IS NOT NULL AND minutes IS NOT NULL THEN dau END AS dau_d,
                       CASE WHEN sessions IS NOT NULL AND dau IS NOT NULL THEN sessions END AS ses_p,
                       CASE WHEN sessions IS NOT NULL AND dau IS NOT NULL THEN dau END AS dau_p
                FROM b
            ), t AS (
                SELECT app, bench_window, date,
                       DATEDIFF('day', MIN(date) OVER (PARTITION BY app, bench_window), date) AS day_n,
                       sessions, minutes, dau, min_s, ses_s, min_d, dau_d, ses_p, dau_p,
                       -- TR7D stops at the last day with minutes rather than trailing on through the lag
                       MAX(CASE WHEN minutes IS NOT NULL THEN date END) OVER (PARTITION BY app, bench_window) AS last_min,
                       SUM(min_s) OVER (PARTITION BY app, bench_window ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS min_s7,
                       SUM(ses_s) OVER (PARTITION BY app, bench_window ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS ses_s7,
                       SUM(min_d) OVER (PARTITION BY app, bench_window ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS min_d7,
                       SUM(dau_d) OVER (PARTITION BY app, bench_window ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS dau_d7,
                       SUM(ses_p) OVER (PARTITION BY app, bench_window ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS ses_p7,
                       SUM(dau_p) OVER (PARTITION BY app, bench_window ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS dau_p7
                FROM w
            )
            SELECT t.app AS APP, t.bench_window AS BENCH_WINDOW, CAST(t.date AS VARCHAR) AS DATE, t.day_n AS DAY_N,
                   t.sessions AS SESSIONS, t.minutes AS MINUTES, t.dau AS DAU,
                   ROUND(1.0 * t.min_s / t.ses_s, 2) AS MIN_PER_SESSION,
                   CASE WHEN t.date <= t.last_min THEN ROUND(1.0 * t.min_s7 / t.ses_s7, 2) END AS MIN_PER_SESSION_TR7D,
                   ROUND(1.0 * t.min_d / t.dau_d, 2) AS MIN_PER_DAU,
                   CASE WHEN t.date <= t.last_min THEN ROUND(1.0 * t.min_d7 / t.dau_d7, 2) END AS MIN_PER_DAU_TR7D,
                   ROUND(1.0 * t.ses_p / t.dau_p, 2) AS SESSIONS_PER_DAU,
                   CASE WHEN t.date <= t.last_min THEN ROUND(1.0 * t.ses_p7 / t.dau_p7, 2) END AS SESSIONS_PER_DAU_TR7D
            FROM t CROSS JOIN r
            WHERE t.bench_window = 'launch'
               OR (t.date > r.through - """ + str(RECENT_DAYS) + """ AND t.date <= r.through)
            ORDER BY 2, 1, 3
        """,
        methodology=dict(
            source="SensorTower SENSORTOWER.COMMON.CORE (sessions and minutes from SensorTower's cross-platform "
                   "daily session estimates), for the launch benchmark apps: " + ", ".join(BENCHMARK_KEYS) + ".",
            filters=[
                ("Same apps, keys, US scope and day 0 as the launch benchmark (Muse day 0 = " + LAUNCH + ")",
                 "So the time-spent view lines up with the benchmark above it."),
                ("Clubhouse not shown",
                 "Clubhouse is not in SensorTower CORE yet, so it has no session or time-spent data here."),
                ("Sora in Days since launch only",
                 "CORE has no Sora rows after 2026-03-24 (checked 2026-10-12), so it has no last-90-days data."),
                (f"Days since launch: day 0 to {BENCHMARK_DAYS}. Last {RECENT_DAYS} days: the {RECENT_DAYS} calendar "
                 "days ending on the latest day with minutes",
                 "The first compares each app's launch period; the second compares the apps as they are today."),
                ("Zero sessions, minutes or DAU = missing",
                 "SensorTower's latest days arrive as 0 before they are filled in, so a zero is not a real value."),
            ],
            dedupe="iPhone and Android phone summed per app and day.",
            measure="SESSIONS_PER_DAU = sessions / DAU: how many times an average daily user opens the app (a "
                    "session is each time the app is opened). "
                    "MIN_PER_SESSION = minutes / sessions: the average session length. MIN_PER_DAU = minutes / "
                    "DAU: average daily time per active user, which also reflects how often users open the app. "
                    "The *_TR7D ratios are 7-day sums over 7-day sums (minutes over sessions or DAU, sessions over DAU), not means of "
                    "daily ratios, over the days in the window where both values are present; early days since "
                    "launch use fewer than 7 days. Modelled vendor estimates, best read as trends.",
            lag="Sessions and minutes arrive about a week after DAU (on 2026-10-12 they ran to 10-03, DAU to "
                "10-09), so the last 90 days end earlier than the DAU charts. The TR7D line stops at each app's "
                "last day with minutes.",
        ),
    ),
    dict(
        key="web_time_spent",
        title="Engagement: web minutes per visit, US (SimilarWeb)",
        keys=None, measures=[], fill_zero=False,
        # The TR7D ratio divides 7-day sums (time spent over visits), using only days with both, and stops at
        # each site's last day with time spent. A site with no time spent yet has no rows with a ratio, and the
        # page leaves it off the chart.
        sql="""
            WITH w AS (
                SELECT CASE domain
                           WHEN 'muse.ai' THEN 'Muse'
                           WHEN 'chatgpt.com' THEN 'ChatGPT'
                           WHEN 'claude.ai' THEN 'Claude'
                       END AS app,
                       domain, date, visits, time_spent,
                       CASE WHEN visits > 0 AND time_spent IS NOT NULL THEN time_spent END AS ts_v,
                       CASE WHEN visits > 0 AND time_spent IS NOT NULL THEN visits END AS vis_v
                FROM srs_mcp.meta.muse_web_traffic
                WHERE country = 'US'
                  AND date >= '{card_start}'
                  AND NOT (domain = 'muse.ai' AND date < '""" + LAUNCH + """')   -- Muse starts at public launch
            ), t AS (
                SELECT w.*,
                       MAX(CASE WHEN ts_v IS NOT NULL THEN date END) OVER (PARTITION BY app) AS last_ts,
                       SUM(ts_v) OVER (PARTITION BY app ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS ts7,
                       SUM(vis_v) OVER (PARTITION BY app ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS vis7
                FROM w
            )
            SELECT app AS APP, domain AS DOMAIN, CAST(date AS VARCHAR) AS DATE,
                   ROUND(visits, 0) AS VISITS, ROUND(time_spent, 0) AS TIME_SPENT,
                   ROUND(1.0 * ts_v / vis_v, 2) AS MIN_PER_VISIT,
                   CASE WHEN date <= last_ts THEN ROUND(1.0 * ts7 / NULLIF(vis7, 0), 2) END AS MIN_PER_VISIT_TR7D
            FROM t
            ORDER BY 1, 3
        """,
        methodology=dict(
            source="SimilarWeb SIMILARWEB.COMMON.VISITS_V2 (the SimilarWeb pipeline's consumer table): "
                   "all_traffic_time_spent (total minutes = visits x average visit duration) and all_traffic_visits.",
            filters=[
                ("Domains muse.ai, chatgpt.com and claude.ai; desktop plus mobile web, subdomains included",
                 "Muse's web app against the two assistants in the app benchmark. chatgpt.com includes "
                 "chat.openai.com, which the pipeline sums into it."),
                ("US only", "Same scope as the app time-spent chart."),
                (f"Muse from {LAUNCH} (public launch)", "Pre-launch muse.ai traffic is not Muse usage."),
            ],
            dedupe="One value per site and day.",
            measure="MIN_PER_VISIT = time spent / visits: the average visit length in minutes. MIN_PER_VISIT_TR7D = "
                    "7-day time spent over 7-day visits (weighted by visits, not a mean of daily averages), over the "
                    "days with both. A SimilarWeb visit lasts until 30 minutes idle, while an app session is each "
                    "time the app is opened, so compare sites with each other, not with the app chart. Modelled "
                    "vendor estimates, best read as trends.",
            lag="Vendor series, about T-3. The TR7D line stops at each site's last day with time spent.",
        ),
    ),
]

# Methodology order follows the page.
_PAGE_ORDER = ["launch_benchmark", "time_spent", "web_time_spent", "app_usage_daily", "ad_spend_daily", "web_traffic_daily", "muse_web_daily",
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
