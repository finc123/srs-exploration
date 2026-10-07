# Plan: Meta Muse pre-app investigations (3 notebooks)

## Context
Before building a Meta Muse app in SRS Apps, we need to know which card and e-receipt sources can see (a) agentic-checkout transactions (`linkagnt*`), (b) Muse subscription charges at $16 or $80, and (c) other agentic-commerce signals in Spotify and Shop Pay billing descriptions around the Muse launch (2026-09-08). Each step gets its own notebook in `investigations\`.

## Execution approach (important)
- **Run every query through the SRS MCP Snowflake tool** (`mcp__claude_ai_SRS_MCP__snowflake`), not the local connector. As of 2026-10-07, the local key-pair login (`connection_name='default'`) fails with `JWT token is invalid`, so the notebooks cannot be executed locally yet.
- Each notebook still contains the full runnable code (connector + `q()` helper), so it runs as-is once the local login is fixed.
- **Record results in each notebook's "Status as of <date>" markdown section**, following `supra_google_muse_access.ipynb`: the sources checked, the key counts and tables, and the conclusions.
- Keep each MCP query to one day, or a few days, per source. Month-long `ILIKE` scans on the 279 tables time out.

## What exploration found
- **Card tables with a free-text description** (Snowflake):
  - `SPEND_279_TRANSACTIONS_V3_0` / `_LOG_V3_0` (`BILLING_DESCRIPTION`) in schemas `PRIME`, `PRIME_TAU`, `PRIME_SNAPSHOTS[_TAU|_SIGMA]`, `PRIME_INCREMENTAL[_TAU]`, `DIRECT`, `DIRECT_TAU`, `DIRECT_SIGMA`, `DIRECT_SNAPSHOTS*` and `DIRECT_INCREMENTAL*`.
  - These schemas repeat across 3 databases: `SHARE_CE_SPEND_279_FINANCIAL_PRIME_ENRICHED`, `..._PRIME_ENRICHED_TAU` and `SHARE_EARNEST_279`.
  - `SHARE_CE_SPEND_201_PRIME_EX_TAU.FEEDn_PANELS.FEEDn_{CARD,BANK}_PANELS_V1_0` (Yodlee feeds 1, 2, 3, 4 and 6; `DESCRIPTION`, `AMOUNT`, `TRANSACTION_DATE`, `UNIQUE_CARD_TRANSACTION_ID`).
  - `SHARE_FABLE.FABLE_SIGNAL.{UK,FR,DE,ES,IT}_V2_TXN` and `FR_V3_TXN` (`DESCRIPTION`, `SPENDOUT`, `TXNDATE`, `FDTXNKEY`). These are European panels.
  - Ticker extracts in `EARNEST.<TICKER>.TXNS`, for example `EARNEST.SPOT.TXNS` and `EARNEST.META.TXNS`. These are derived, so they are used only as cross-checks.
  - Excluded: `SHARE_FACTEUS` (aggregates only), `SHARE_CE_TRANSACT_*` (no descriptions) and `SRS_FACTEUS` (HIMS and TPR only).
- **`linkagnt` is present** in `PRIME.SPEND_279_TRANSACTIONS_V3_0`, for example `linkagnt* target.com www.link.com ca`. A tagged merchant `link_agent_wallet` exists.
  - **The same transaction appears once per merchant tag** (once as `link_agent_wallet` and once as `target`, say). Counts must use `COUNT(DISTINCT earnest_transaction_id)`, or `partner_transaction_id` as the fallback.
- **Meta at $16 is visible**: `google *facebook`, `pp*metaplatfor`, `paypal *facebooktec` and similar descriptions at $15.74–$16.49. The match is noisy: `metapay`, `metacoregame` and ads-related `facebooktec` all show up, so the notebook needs an exclusion list and manual review.
- **NIQ** `SHARE_NIQ.SRS.ITEMS_EXTENDED` columns: `MERCHANT_NAME`, `DESCRIPTION`, `ITEM_PRICE`, `ORDER_TOTAL`, `ORDER_DATE`, `DIGITAL_GOOD` and `MAILBOX_ID`.

## Shared notebook pattern
Reuse the setup cell from `investigations\supra_google_muse_access.ipynb`:
- `snowflake.connector.connect(connection_name=...)` and the `q()` helper.
- A `SOURCES` list of dicts with keys `name`, `table`, `desc_col`, `date_col`, `amt_col`, `txn_id_col` and `merchant_col` (`None` where absent).
- The same markdown-header style, including a "Status as of" section.

Each notebook defines `SEPT = pd.date_range('2026-09-01', '2026-09-30')` (notebooks 2 and 3 extend the range back to 2026-08-01 for a baseline) and a `scan_daily(src, where_sql)` helper. The helper runs one query per day per source and concatenates the results.

## Notebook 1: `investigations\card_linkagnt_coverage.ipynb`
1. **Source inventory.** Build `SOURCES` from `INFORMATION_SCHEMA` across the 279 databases (3), the 201 feeds and Fable. Use `_V3_0` snapshot and current tables, and skip the `_LOG` and incremental tables because they are change logs.
2. **Presence check.** For each source, count rows on 2026-09-15 where the description is `ILIKE '%linkagnt%'`, plus the total row count for that day.
3. **Duplicate detection.** On one day, compare the sets of `partner_transaction_id` across sources that have hits. This flags which schemas or databases are copies of each other: the `PRIME` share against the `SHARE_EARNEST_279` mirror, and `PRIME` against `PRIME_TAU` against `SNAPSHOTS`.
4. **Daily September series** for every source with hits:
   - Distinct linkagnt transactions, plus total daily transactions so linkagnt can be shown as a share of each panel's volume.
   - Output: a pivot table (day × source) and a line chart.
5. Top linkagnt merchants and their descriptions, to show what agents are buying.

## Notebook 2: `investigations\meta_muse_price_points.ipynb`
1. **NIQ** `ITEMS_EXTENDED` for 2026-08-01 onward:
   - Match `merchant_name` or `description` `ILIKE` meta, facebook, muse, `meta ai`, `power` or `max`. For power and max, only count rows where meta, facebook or muse also matches, otherwise they pick up noise.
   - Keep rows with `item_price` or `order_total` in {16, 80} ± $0.01.
   - Output: daily counts, merchant/description breakdown and distinct mailboxes.
   - Also review Apple and Google Play receipts whose description mentions Meta/Muse, because in-app subscriptions are billed there.
2. **Card sources** (only the deduplicated set from notebook 1, plus those without linkagnt):
   - Match descriptions on `meta|facebook|facebk|fb\.me|muse`.
   - Exclusion list: `metapay`, `metacoregame`, `metro`, `metal` and similar.
   - Keep amounts between 15.5–16.5 or 79–81.
   - Output: day-by-day counts from 2026-08-01, split into the two price buckets and by billing intermediary (direct, Google Play, Apple, PayPal).
   - Compare before and after 2026-09-08.
3. A list of the top descriptions for manual review, flagging which look like Muse subscriptions and which look like ads or other noise.

## Notebook 3: `investigations\spotify_shoppay_agentic_descriptions.ipynb`
1. Scope: card sources from notebook 1 that have descriptions, rows where merchant is Spotify or Shopify/Shop Pay, or the description matches `spotify|shopify|shop pay|shoppay|shp*`.
2. **Agentic keyword scan** for 2026-08-01 to 2026-09-30:
   - Terms: `agnt`, `agent`, `gpt`, `claude`, `muse`, `openai`, `perplexity`, and `ai` matched only as a word boundary token (`REGEXP '(^|[^a-z])ai([^a-z]|$)'`) to avoid hits like "paid" and "main".
   - Output: counts and example descriptions.
3. **Fallback / pattern mining**, which always runs:
   - Normalise descriptions by lowercasing, stripping digits and card or location noise, and collapsing whitespace.
   - Find the top 50 patterns for Spotify and for Shop Pay.
   - Compute each pattern's share before 2026-09-08 against after it, and its lift.
   - Rank by lift, with a minimum-volume floor, to flag descriptions that surged after the Muse launch.
4. A chart of daily counts for the top surging patterns.

## Verification
- Validate each notebook's SQL via the SRS MCP Snowflake tool, and record the outputs in the notebook's status section.
- Once the local login is fixed, run each notebook top to bottom and check the results match the status sections.
- Check notebook 1's single-day counts against the ad hoc result: around 7 distinct linkagnt transactions in `PRIME` on 2026-09-15.
- Spot-check that the deduplicated counts equal raw rows ÷ the number of merchant tags.
- Notebook 2: confirm the $15.89 `google *facebook` rows reappear, and eyeball the exclusion list.
- Report back a short summary per notebook: sources with coverage, daily tables, and candidate descriptions for the app.
