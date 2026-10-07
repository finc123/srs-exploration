"""Meta Muse app: source loads, report sections and their methodology, in one place.

Two layers, mirroring the planned monorepo workflow (`workflows/jobs/meta/meta_muse.yaml`):

1. LOADS (Snowflake SQL). Narrow row-level pulls from the raw panels into what
   will become `srs_slice.meta.*` tables:
     card_txns     one row per matched card/bank transaction (signal = muse_web | agentic)
     panel_totals  distinct transactions per source per day (denominator for per-million)
     niq_receipts  one row per Muse e-receipt line item
     app_usage     SensorTower downloads / DAU per app x country x day
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

# ---------------------------------------------------------------------------
# SECTIONS (portable SQL). Placeholders filled by build_json.py:
#   {card_start} {card_through} {niq_through} {app_start} {merch_start}
#
# Per section:
#   keys      group columns besides DATE (one dense daily series per key combo)
#   measures  columns that get a *_TR7D twin
#   fill_zero a missing day means zero (counts from a scan) vs unknown (vendor series)
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
                 "Google Play pass-through showed no launch uplift, Apple card descriptors carry no app name, "
                 "and the PayPal / FACEBK forms are ads and Quest. In-app Muse is measured from e-receipts instead."),
            ],
            dedupe="Distinct (member, day, amount, plan): Yodlee pending and posted copies of one charge can "
                   "carry different transaction ids.",
            measure="MEMBERS = distinct panel members charged that day, per plan. TXNS = deduplicated charges. "
                    "A charge is a new subscription or a monthly renewal; with a 2-week free trial, first "
                    "charges start about 14 days after sign-up (first seen 2026-09-17).",
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
                    "7-day agentic volume.",
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
            measure="A breakdown table rather than a daily series: transactions and median amount per merchant "
                    "over the 28 days ending at the card complete-through date.",
            lag=f"Complete through run date minus {CARD_LAG_DAYS} days.",
        ),
    ),
    dict(
        key="app_usage_daily",
        title="AI assistant app downloads and DAU (SensorTower)",
        keys=["APP", "COUNTRY"], measures=["DOWNLOADS", "DAU"], fill_zero=False,
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
                 "there is a clone 'Muse from Meta'. Share = the app's TR7D over the sum of the five apps' TR7D, "
                 "for the same metric and country. Meta AI is excluded from the share set (it is the app Muse "
                 "sits beside, shown in its own chart)."),
                ("Country US and WW only",
                 "WW is SensorTower's worldwide aggregate row; summing countries would double count it."),
            ],
            dedupe="iPhone and Android phone summed per app, country and day (a user active on both counts twice "
                   "in DAU; small for a phone app).",
            measure="DOWNLOADS = estimated first-time downloads; DAU = estimated daily active users. Values are "
                    "modelled vendor estimates, best read as trends.",
            lag="Downloads run to about T-2 and DAU to T-3; the latest DAU day arrives as 0 and is treated as "
                "missing. TR7D is shown only where all 7 days are present.",
        ),
    ),
]

# Headline tiles, read from the latest complete TR7D value of each series.
SUMMARY = [
    dict(label="Muse web subs, members/day", section="muse_web_daily", col="MEMBERS_TR7D", where={}),
    dict(label="Muse in-app charges/day", section="muse_inapp_daily", col="CHARGES_TR7D", where={}),
    dict(label="Muse in-app cancels/day", section="muse_inapp_daily", col="CANCELS_TR7D", where={}),
    dict(label="Agentic txns per million", section="agentic_daily", col="PER_MILLION_TR7D", where={}),
    dict(label="Muse US downloads/day", section="app_usage_daily", col="DOWNLOADS_TR7D",
         where={"APP": "Muse", "COUNTRY": "US"}),
    dict(label="Muse US DAU", section="app_usage_daily", col="DAU_TR7D", where={"APP": "Muse", "COUNTRY": "US"}),
    dict(label="Meta AI US DAU", section="app_usage_daily", col="DAU_TR7D", where={"APP": "Meta AI", "COUNTRY": "US"}),
    # share_of: VALUE = this app's TR7D / the sum over share_of apps' TR7D on the same day
    dict(label="Muse share of US AI-assistant DAU", section="app_usage_daily", col="DAU_TR7D",
         where={"APP": "Muse", "COUNTRY": "US"}, share_of={"key": "APP", "values": SHARE_APPS}),
]
