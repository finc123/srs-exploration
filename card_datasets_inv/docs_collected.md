# Card / bank transaction datasets: collected documentation

Compiled 2026-10-16. This is read-only research: no repo files were changed and nothing was written to Snowflake, Slack or Notion.

**Tags used below**
- **[S]**: stated in a source. The source is cited inline or in the dataset's source list.
- **[I]**: my inference. It is not stated anywhere.
- **[M]**: measured from Snowflake metadata on 2026-10-15/16 (INFORMATION_SCHEMA, MANIFEST tables, small GROUP BYs).

---

## 0. The family tree

All of the US data below is **Consumer Edge (CE, "CER")**. Earnest Analytics merged into CE: CE "is the underlying panel provider behind the Earnest Analytics branded products". SRS subscribes to **Orion Prime** (row-level, plus the Earnest-enriched version) and **Orion Daily Signal** (aggregates) [S: Notion *CER / Data Notes*]. The raw card and bank data comes from **Yodlee** aggregation [S: Notion *Earnest/Yodlee / Updates*, 2025-07-16: "Raw Yodlee data – enrichment from both CER and Earnest side … Orion Prime Enriched"].

```
Yodlee raw card/bank feeds ──► SHARE_CE_SPEND_201_PRIME_EX_TAU   (feeds 1-6, raw descriptors, not enriched)
        │
        ├─ Earnest enrichment, legacy schema ("Spend 279", v3_0)
        │     SHARE_EARNEST_279 (= SPEND_279_FINANCIAL_DIRECT share)  ─┐ exact mirrors:
        │     SHARE_CE_SPEND_279_FINANCIAL_PRIME_ENRICHED[_TAU]       ─┘ PRIME / PRIME_TAU / DIRECT* / SIGMA
        │          └─► sync-service earnest-<TICKER> jobs ─► EARNEST.<TICKER>.TXNS
        │
        └─ CE enrichment, new "Orion Prime 2.0" schema (2822, v1_0)
              SHARE_CE_PRIME_ENRICHED_OMEGA_2822 / _TAU_2822 (mirrors)
                 PRIME_OMEGA (Omega panel) + PRIME_TAU (Tau panel) + PRIME_GROUND_TRUTH (brands/symbols)
                 └─► EARNEST.COMMON.CE_PRIME_OMEGA_PANEL_TXNS (view; Josh Singer, PR #2513 / #2522)

Fable Data (Europe, separate vendor) ─► SHARE_FABLE.FABLE_SIGNAL.*_TXN (row level)
                                    ─► SHARE_FABLE_DAILY_T7[_V2] (Signal Daily aggs) ─► FABLE.COMMON.* (sync-service `fable`)
```

---

## 1. Consumer Edge Prime Enriched "2822": Omega and Tau

### What it is
- **[S]** This is the new production row-level schema. Josh Singer (Slack C0C8FNZGQMD, 2026-10-14 03:14–03:19 BST): "NEW PRODUCTION TABLES W NEW SCHEMA (This is what we will use, just requires joining on the panel and metadata)", "Earnest on a new schema. OMEGA is the old cpanel", "same schema as the 1315/KAPPA and 1415/MU feeds".
- **[S]** The legacy-schema copy `SHARE_CE_SPEND_279_FINANCIAL_PRIME_ENRICHED.PRIME.SPEND_279_TRANSACTIONS_V3_0` "is just a 1:1 match of the old 279, but this will not be production" (same thread).
- **[S]** CE changeover call 2026-08-03 (Notion *CER Change over call 2026-08-03*), under "orion 2.0":
  - **Omega**: "2011 transaction with all history, use members panel to create member panels, was C panel". Recommended: "use 2022 members panel, 2019 if you need more history". "110M users and 45M active".
  - **Tau**: "different sources, a year ago, much shorter data history (2024 Jan 1). no member panel recommended here, we have to do it. completely separate from omega."
  - The AI summary of the same call adds: "Omega is described as equivalent to the C panel / Legacy MC panel, related to the loss of F5 restrictions in 2024". "Tau is a completely separate panel from Omega — different data as well".
  - "orion prime 2.0 enriched – same as CE Transact Prime". "On dash right now: consistent 2022 member on omega (aggregate consistent shopper 2022_V2), found in card link table". "machine data daily and daily enhanced are NOT changing yet. maybe Oct."
- **[S]** Tau: "income distribution similar to Sigma" (Notion *Updates*, 2025-07-16).
- **[S]** #vendor-changes describes Orion Prime 2.0 (2026-07-15) as a "new normalized schema with revised dedup logic and a 20+ transaction member-onboarding rule … 5,000 newly tagged brands … adoption optional, legacy schema keeps running in parallel".
- **What "Omega" and "Tau" mean.** They are two separate panels built from different upstream sources, not a card/bank split. Omega is the long-history legacy "C" panel. Tau is a newer, separately sourced panel. **[I]** The Greek letters are CE internal panel code names (other names seen: Sigma, Kappa, Mu). No source explains the letters themselves.
- **Geography [S]:** US. `CURRENCY` is "almost all USD; a small CAD/AUD/EUR tail" (view DDL, srs `scripts/sql/earnest_ce_prime_omega_panel_txns_view.sql:119`).

### Objects and size [M]
`SHARE_CE_PRIME_ENRICHED_OMEGA_2822` and `SHARE_CE_PRIME_ENRICHED_TAU_2822` hold the **same eight schemas** and identical row counts, so they are mirrors. The status notes record "TAU_2822 mirrors OMEGA_2822" (`card_datasets_inv/status.md:13`). Role `DATA_TEAM` cannot use `OMEGA_2822.PRIME_TAU` ("does not exist or not authorized"), so read Tau through `SHARE_CE_PRIME_ENRICHED_TAU_2822.PRIME_TAU`.

| Schema.table | Rows | Notes |
|---|---:|---|
| PRIME_OMEGA.TRANS_V1_0 | 156.1B (12.9 TB) | Transactions. Status notes give 2000 → 2026-10-13, about 1.94B distinct txns in Dec-25 |
| PRIME_OMEGA.MID_V1_0 | 5.10B | MERCHID → MERCHDESC |
| PRIME_OMEGA.MID_MATCH_V1_0 | 5.08B | MERCHID → main / distribution / payment brand, channel, merchant geo |
| PRIME_OMEGA.CARD_V1_0 | 254M | (CARDID, CARDLINKID) attributes |
| PRIME_OMEGA.CARDLINK_PANEL_V1_0 | 125.5M | (CARDLINKID, PANEL) → WEIGHT, PANEL_START_DATE. 22 panels |
| PRIME_OMEGA.CARDLINK_INCOME_V1_0 / _HOME_LOCATION_V1_0 | 6.26B / 2.68B | Monthly income and quarterly home location |
| PRIME_OMEGA.NORMALIZER_PANEL_V1_0 | 483k | delivery × trans_date × user-score range × method normalizer |
| PRIME_TAU.TRANS_V1_0 | 23.1B | Status notes give 2013 → 2026-10-13, about 822M Dec-25 txns. **No CARDLINK_PANEL in PRIME_TAU** |
| PRIME_TAU.CARD / MID / MID_MATCH | 49M / 276M / 276M | |
| PRIME_GROUND_TRUTH.BRAND_V1_0, SYMBOL_BRAND_V1_0, SYMBOL_DETAIL_V1_0, INDUSTRY_LIST_V1_0 | 11.9k / 2.9k / 789 / 138 | CE brand and symbol taxonomy |
| PRIME_OMEGA_STATIC.AFFECTED_ACCOUNTS_092026 | 66k | Accounts flagged for exclusion (Sep 2026) |
| PRIME_SNAPSHOTS_{OMEGA,TAU}, PRIME_INCREMENTAL_{OMEGA,TAU}.TRANS_LOG_V1_0 | | Snapshot copies and change logs |

**Delivery [M]:** `DATADELIVERED_V3_0` shows daily versions, delivered about 08:50–13:00 PT. CE quoted "ORION prime and aggregate – 3-6pm" [S: 2026-08-03 call].

### Key columns [S: Snowflake column comments on TRANS_V1_0 and siblings]
- **Transaction id:** `TRANSID` ("CE-generated unique ID of transaction") and `PARTNER_TRANSID` ("originally partner_transaction_id").
- **Dates:**
  - `TRANS_DATE`: "previously optimized_date". Use this one.
  - `PARTNER_TRANS_DATE`: previously transaction_date.
  - `PARTNER_POST_DATE`: previously post_date.
  - `FILEDATE`.
- **Descriptor:** there is **no per-transaction description**. `MERCHID` → `MID_V1_0.MERCHDESC` ("Merchant description, scrubbed by secondary PII rules when applicable") is per merchant-location id [S]. The status notes call this "merchant-level only" (`status.md:23,46`).
- **Panelist:** `CARDLINKID` ("AKA member_id, unique_mem_id"). `CARDID` ("AKA account_id, unique_bank/card_account_id").
- **Amount and type:** `TRANS_AMOUNT`, `CURRENCY`, `TRANSTYPE` (debit/credit), `CARDTYPE` (bank/card: "credit card file or debit card file"), `USER_SCORE`.
- **Panel and weight:** `CARDLINK_PANEL_V1_0.PANEL / PANEL_START_DATE / WEIGHT`. "The table makes available different versions of the panel with variable annual start-dates."
- **Brand:** `MID_MATCH.MAIN_BRAND_ID / DISTRIBUTION_BRAND_ID` ("e.g., DoorDash") / `PAYMENT_BRAND_ID` ("e.g., PayPal"), and `CHANNEL` (ONLINE/OFFLINE/UNKNOWN).
- **Ticker mapping:** `SYMBOL_BRAND` start/end dates. The defaults are 2013-06-01 and 2050-01-01.
- **Amount cap:** `BRAND.TRANS_AMOUNT_LIMIT` defaults to $20,000.

### The 22 panels in CARDLINK_PANEL_V1_0 [S: srs commit 52003321, `scripts/sql/earnest_ce_prime_omega_panel_txns_view.sql` header]
Card counts are CARDLINKIDs:
- `aggregate_consistent_shopper_2019_v2` (about 0.5M)
- `aggregate_consistent_shopper_2022_v2` (about 3.6M)
- `blended_index_2019_v2` (about 0.5M)
- `consistent_shopper_2016` … `_2026`: 0.6M rising to 13.8M
- `income_longterm_panel_2019` … `_2026`: 2.9M rising to 16.8M

Each panel has a single PANEL_START_DATE (1 January of its year). A card can sit in several panels.

### Caveats
- **[S] Grain fan-out.** One row per (CARDLINKID, PANEL) in the panel table. In the SRS view, a transaction repeats once per matching CER symbol (acquired brands map to the old and new tickers; 224 overlapping windows). See dataset 6.
- **[S]** `CARD_V1_0` is not unique per CARDID: there are 5 duplicate (CARDID, CARDLINKID) pairs in 254M (view DDL lines 62-64).
- **[S] Exclude the affected accounts.** Earnest flagged `AFFECTED_ACCOUNTS_092026` for exclusion. #vendor-changes reports an "Orion panel recomposition (Sep 22) … historical data not corrected for ~2.5% affected members".
- **[S] Mapping caveat (CER MIGRATION page, Notion).** The 279→2822 validation SQL excludes `cardtype='card'` rows whose `avg_user_score` falls between -4.98225 and 0 when it reproduces the 279 Netflix series. **[I]** So the 279 production panel applied a user-score filter that a plain `CARDLINK_PANEL` join does not reproduce exactly.
- **[S]** PRIME_TAU has no panel table. "no member panel recommended here, we have to do it."
- **[M] Inconsistent Tau history.** The status notes show Tau TRANS starting in 2013. CE said "2024 Jan 1", and 279 PRIME_TAU starts 2023-03-28. These do not agree (see gaps).

### Relation to other datasets
- This replaces 279. The SRS view comment reads "replaces SHARE_EARNEST_279" [S].
- `aggregate_consistent_shopper_2019_v2` / `_2022_v2` are "Panels that map to our old 279 feed" [S: Josh, 2026-10-14].
- **[M/I] Panel sizes line up with 279.**
  - The 279 2019 production consistent-shopper panel has 510,584 members, against about 0.5M in agg_cs2019_v2.
  - The 279 `cs_panel_2022_v2` weights cover 3.42M members, against about 3.6M in agg_cs2022_v2.
- **[S/I] Ids.** The column comments say `CARDLINKID` is "AKA member_id, unique_mem_id". That suggests the same panelist ids as 279 (`member_id`) and Yodlee (`unique_mem_id`). The id equality has **not** been verified on 2822.

---

## 2. Consumer Edge Yodlee card and bank feeds ("Spend 201", `SHARE_CE_SPEND_201_PRIME_EX_TAU`)

### What it is
- **[S]** These are raw Yodlee transactions, delivered by CE. The 2026-02-20 renewal call (Notion *CER (Earnest Orion renewal call)*) notes "new prime will also get the Yodlee feed… not enriched." The column comments use Yodlee field names: `YODLEE_TRANSACTION_STATUS`, `MCC_RAW`, and "The original transaction description that comes from the FIs".
- **[M] Share layout:**
  - `FEED{1,2}_PANELS`: transaction tables only.
  - `FEED{3,4,6}_PANELS`, `_ACCOUNT_ATTRIBUTES` and `_LAST_REFRESH`: transactions, account balances/APR/credit line, and refresh files.
  - `QUARTERLY.USER_ATTRIBUTES`: member × quarter NTILE spend rankings by category.
  - `STATIC.BANK_STORE_ID` / `CARD_STORE_ID`, and `STATIC.DUPLICATE_{BANK,CARD}_ACCOUNTS_202509`.
  - The share was created on 2025-07-24/28.
- **Geography [I]:** US (Yodlee US FIs). Currency is a column, but no non-US mix has been documented.

| Table | Rows [M] | Last altered [M] | Range (status.md) |
|---|---:|---|---|
| FEED1_BANK / FEED1_CARD | 12.7B / 2.5B | **2025-09-15** | stopped |
| FEED2_BANK / FEED2_CARD | 2.6B / 1.3B | **2025-09-15** | stopped |
| FEED3_BANK / FEED3_CARD | 61.9B (4 TB) / 3.1B | 2026-10-15/16 | bank 2005 → 2026-10-14; Dec-25 759M / 36M txns |
| FEED4_BANK / FEED4_CARD | 28.4B / 7.5B | 2026-10-16 | Dec-25 29M / 27M |
| FEED6_BANK / FEED6_CARD | 54.7B / 3.0B | 2026-10-15/16 | bank 2001 → 2026-10-16; Dec-25 246M / 18M |

There is no feed 5 in the share [M].

### Key columns [S: column comments, FEED3_*_PANELS_V1_0]
- **Ids:** `UNIQUE_MEM_ID` (user), `UNIQUE_{BANK|CARD}_ACCOUNT_ID`, `UNIQUE_{BANK|CARD}_TRANSACTION_ID`.
- **Transaction fields:** `DESCRIPTION` (per-transaction raw FI text), `AMOUNT`, `CURRENCY`, `TRANSACTION_DATE`, `POST_DATE`, `TRANSACTION_BASE_TYPE` (debit/credit), `YODLEE_TRANSACTION_STATUS`, `MCC_RAW`.
- **File and update tracking:** `PANEL_FILE_CREATED_DATE` ("date the transaction appeared in the panel"), `FILE_CREATED_DATE`, `FILE_NAME_DATE` ("Date file was delivered to CE"), `UPDATE_TYPE`, `CHANGE_SOURCE`.
- **Account and quality:** `ACCOUNT_TYPE`, `ACCOUNT_SOURCE_TYPE`, `ACCOUNT_SCORE`, `USER_SCORE`.
- **No panel weight or panel membership column.** Panelisation is left to the user [M].

### Caveats [S unless marked]
- **Unclustered.** The tables are not clustered on `transaction_date`: a one-day F3 bank query is a full scan of about a minute. They prune on `panel_file_created_date`, and rows never land in a file created more than a day before the transaction (`exploration/meta/app/README.md:30-34`; `sections.py:103-108`; `srs-meta-muse/workflows/jobs/meta/CLAUDE.md:68-70`).
- **Pending and posted duplicates.** "Yodlee pending and posted copies of one charge can carry different transaction ids". The Muse work dedupes on (member, day, amount, plan) (`METHODOLOGY.md:150`; `srs-meta-muse/.../CLAUDE.md:94`).
- **Membership tables are incomplete.** On 2026-10-09, `LAST_REFRESH` missed 15 of 69 payers who were still transacting, and `ACCOUNT_ATTRIBUTES` missed 26 (`README.md:64`; `sections.py:199`).
- **Feed 4 bank** had zero agentic rows in Aug–Sep 2026 (notebook `card_linkagnt_coverage.ipynb`, cell 1).
- **No production pipeline.** "No production pipeline lands the Yodlee feeds … the source is being agreed" (`srs-meta-muse/.../CLAUDE.md:48-49`). Only Muse (`SRS_MCP.META.MUSE_CARD_TXNS`, `srs-meta-muse/workflows/jobs/meta/artifacts/load/card_txns.sql`) reads it.

### Feeds 1–6, the September 2025 stop, and "PRIME_EX_TAU"
- **[M]** Feeds 1 and 2 were last altered on 2025-09-15. The notebook states "feeds 1 and 2 stopped on 2025-09-15" (cell 1). `STATIC.DUPLICATE_*_ACCOUNTS_202509` was delivered on 2025-09-03.
- **[S, context]** Yodlee and Earnest history around that time:
  - The Yodlee **5640** cobrand feed was lost on 2025-05-02 (60–90 day outage). Earnest switched production to about 30 other cobrands and a new panel **3080** ("y panel", history from April 2024) (Notion *Yodlee 5640 Outage May - July 2025*).
  - "Yodlee is going to stop generating data by Oct 29 – Direct feed (data light feed) – Prime is the replacement – no cobrand in Prime – user scores are replacement for cobrands" (Notion *Earnest Update Call*, 2025-10-03).
  - The 279 `DIRECT*` tables were last altered on 2025-10-29 [M].
- **[I]** Feed numbers probably correspond to upstream FI/cobrand groups, and feeds 1 and 2 probably ended with the Yodlee Direct/cobrand retirement in Sept–Oct 2025. **No source confirms what feeds 1–6 are or why 1 and 2 stopped.**
- **[I]** "PRIME_EX_TAU" probably means the raw feeds behind the Prime (Omega) panel *excluding* the Tau sources. Two things support this:
  - Muse found 279 PRIME_TAU's members and agentic transactions absent from feeds 3/4/6, while 279 PRIME ⊂ feeds 3/4/6 (see dataset 3).
  - The share name pairs with CE's Omega/Tau split.

  **No source states this.**

---

## 3. Earnest Spend 279 (legacy schema, `SPEND_279_TRANSACTIONS_V3_0`)

### What it is
- **[S]** "SPEND_279 is the vendor product name (feed/bucket earnest-spend-279-us-east-1, share SHARE_EARNEST_279) — not '279 merchants'". It is the "US credit/debit-card transaction panel from Earnest Analytics ("Spend 279" / Vela feed)" (srs `apps/mcp/skills/public/dataset-knowledge/references/earnest.md`, branch `origin/feat/dataset-knowledge-skill`, commit 79abb25d).
- **[M]** `SHARE_EARNEST_279` is SRS's name for the CE share `SPEND_279_FINANCIAL_DIRECT`. `SHARE_CE_SPEND_279_FINANCIAL_PRIME_ENRICHED`, `_PRIME_ENRICHED_TAU` and `_AGGREGATE` are the other 279 shares. The notebook (cell 1) says "the three 279 databases … are **exact mirrors**: identical row counts for every table, and identical `HASH_AGG(partner_transaction_id, merchant, amount)` for PRIME and PRIME_TAU on 2026-09-15". `status.md:12` says "the four `*_279` databases are mirrors". The `EARNEST` database comment reads "this is SRS's copy of eanest 279 share, etl and processing".
- **[S] Delivery** (Orion Prime Enriched data dictionary v2, Notion *Earnest Data Dictionary* attachment):
  - `spend_279_transactions`: daily into `spend_279_financial.prime` / `.prime_tau`.
  - Monthly full snapshots (`prime-snapshots[-tau]`, on the 1st).
  - Daily change logs (`prime-incremental[-tau]`, with `change_type` U/N/D and `change_date`; "to find the latest version use earnest_transaction_id & parent_merchant & merchant, sort by change_date").
  - Static tables: `member_weights`, `avg_user_scores`, `user_ranges` (one-time).
- **[S] Direct to Prime.** "Prime is the replacement" for Direct. "No cobrand in Prime – user scores are replacement for cobrands". "member_weights is supplemental … takes advantage of group of cards that only have history since 2022 in order to get bigger panel" (Notion *Earnest Update Call*). The *Direct to Prime Migration in Snowflake Share* page builds `EARNEST.COMMON.COBRAND_USER_RANGE` / `COBRAND_USER_SCORE_MEMBER` to map user-score ranges back to old cobrand ids.

| Schema | Rows [M] | Last altered [M] | Range / status |
|---|---:|---|---|
| PRIME | 50.7B | 2026-10-15 | 2015-02-26 → 2026-10-14. About 1.4 rows per distinct txn: 390M rows vs 278M ids in Dec-25 (`status.md:28,48`) |
| PRIME_TAU | 14.6B | 2026-10-15 | **2023-03-28** → 2026-10-14. 432M Dec-25 txns |
| DIRECT / DIRECT_TAU | 44.4B / 8.5B | 2025-10-29 | stopped (has `COBRAND_ID`) |
| DIRECT_SIGMA | 22.4B | 2025-05-01 | stopped |
| PRIME_SNAPSHOTS*, PRIME_INCREMENTAL* | | live | copies and change logs. Snapshots match current within 0.1% for Dec-25 |

Panel tables:
- `PRIME.MEMBER_PANELS_V3_0`: `panel_name` is consistent_shopper or consistent_subscriber, `panel_start_date` runs 2016–2026, and `production_cs_panel` is a flag.
- `PRIME_STATIC.MEMBER_WEIGHTS_V1_0`: (member_id, weight, method). The methods are legacy `cs_panel_YYYY` (2016–2024) and `cs_panel_YYYY_v2` (2016–2025) [M].
- Production consistent shopper is 510,584 members for every start year from 2019 onward. The 2022 non-production consistent-shopper panel is 3.83M members [M].

### Key columns [S: Snowflake column comments and the data dictionary]
- **Transaction ids:** `EARNEST_TRANSACTION_ID` (UUID, Earnest internal) and `PARTNER_TRANSACTION_ID`.
- **Member:** `MEMBER_ID` ("unique across cobrands and does not change throughout our panel's history").
- **Descriptor:** `BILLING_DESCRIPTION`, a per-transaction partner description.
- **Dates:** `OPTIMIZED_DATE` ("Date of transaction determined by Earnest methodology"; use this), `TRANSACTION_DATE`, `POST_DATE`, `FILE_CREATE_DATE`.
- **Amount and type:** `TRANSACTION_AMOUNT` ("negative for credits"), `TRANSACTION_TYPE`, `SOURCE` (bank/card).
- **Merchant tagging:** `PARENT_MERCHANT`, `MERCHANT` (Earnest tags), `CATEGORY`, `SUBCATEGORY`, `CHANNEL` (Online / In-store / Store Card), `EARNEST_BACKTEST_LIMIT_FLAG`, `EARNEST_BACKTEST_MERCHANT_FLAG`, `STORE_CARD_PAYMENT_FLAG`.
- **Geography:** geo columns and `MEMBER_HOME_STATE`.
- **Not in PRIME:** `COBRAND_ID` exists only in DIRECT* [M].
- **No weight column.** Weights come from `MEMBER_WEIGHTS`.

### Caveats
- **[S] Multiple merchant tags.** Rows repeat per merchant tag: "15 rows: each txn tagged twice (`link_agent_wallet` + real merchant)" on 2026-09-15 (notebook cell 1). Deduplicate on the transaction id (`status.md:48`).
- **[S] Panel recalibration, 1 July 2026.** Legacy panels were removed, there are `_v2` methods and a new `production_member_ids_v2`. A "double-count bug … 189K members carrying two weights … ~1.4M duplicate rows in earnest.nflx.txns" was raised, with fix PR sync-service #2269 and the srs companion PR #1705 (#vendor-changes digests 2026-07-27 to 2026-10-05).
- **[M]** The `company_data` template on srs master still joins `METHOD = 'cs_panel_2022'` / `'cs_panel_2019'` (legacy) (`workflows/jobs/company_data/artifacts/sync_raw_data_prepare.py:116-121`). The legacy methods still exist in the share.
- **[S] Muse findings** (notebook cell 1; `METHODOLOGY.md:139,224`; `sections.py:100,124-132`):
  - **PRIME ⊂ Yodlee feeds 3/4/6**: "Yodlee `unique_mem_id` = 279 `member_id`", and all 9 PRIME agentic transactions were found in F3/4/6.
  - **PRIME vs PRIME_TAU are disjoint** (0 of 1,986 sampled ids).
  - **PRIME_TAU is not in Yodlee F3/4/6**, so it is a separate panel.
  - PRIME_TAU "times out on multi-day text scans, so it is one query per day" (`README.md:35`).
- **[S] Stale tables.** `RAW.TXNS_RAW` is a frozen legacy extract (2016-01 → 2023-07-14). `ANALYST.MEMBER_MERCHANT_MONTH` ends 2025-10 (dataset-knowledge `earnest.md`).

### Relation to 2822 [S]
- The 2822 schema replaces 279. SRS's view comment says "the consistent-panel replacement for SHARE_EARNEST_279".
- CE's to-do from the 2026-08-03 call: "only the transaction level data changed – and we should use SHARE_CE_SPEND_279_FINANCIAL_PRIME_ENRICHED; use the 2022 members panel via the card link table (aggregate consistent shopper 2022_V2)".
- **[I]** PRIME (279) ≈ Omega panel transactions with Earnest tagging; PRIME_TAU (279) ≈ Tau panel with Earnest tagging. This is supported by the matching names and by both pairs being disjoint, but there is no direct id-level check between 279 and 2822.

---

## 4. Fable Data European card panels

### What it is
- **[S] Vendor and sources.** Fable Data is a European multi-source panel. "The fable data set is made of 4 broad panels across all data partners: Consumer Credit cards, Consumer Debit cards, Business debit cards, and Open banking based debit cards." Countries are UK, DE, FR, ES, AT, IT. Currency is GBP for the UK and EUR otherwise (*Fable Data Rolling Panel Aggregate Product Guide*, PDF attached to Notion *Fable data*, pp. 6, 10, 23).
- **[S] Version 2** (Notion *Fable Call 2025-07-31*): "new open banking data … UK increased by 3x, FR increased by 8-9x … almost 2-3x increase in total. v2 available and LIVE now". v1 support was TBD.
- **[S] FRv3** (#vendor-changes, 2026-06-01 to 2026-10-05):
  - "Signal T3 FRv3" swaps France's credit-card panel for a debit-card panel about 70–80% larger.
  - FRv3 full history (2012 →) landed in Snowflake in early June 2026, with daily feeds from 15 June 2026.
  - The **FRv2 credit panel shrinks from Q4 2026 and is removed by 31 Dec 2026**, with full decommission in Q2 2027.
  - Signal Daily v3 also "expands UK/DE/IT coverage".
- **[M] Objects:**
  - `SHARE_FABLE.FABLE_SIGNAL.{DE,ES,FR,IT,UK}_V2_TXN` and `FR_V3_TXN`: 0.68B–4.06B rows, all altered 2026-10-16.
  - Each has `_SUPP` (same row count), `_UPDATES` and `_SIGNAL` (views; `status.md:40` says "Fable `*_SIGNAL` views equal their `*_TXN` tables").
  - `USER_MASTER` (47.4M).
  - `REFERENCE_DATA.{MERCHANT_HIERARCHY, MERCHANT_WEIGHTS, FABLE_FX}`.
  - The three Fable databases are identical (`status.md:14`).
  - `CLIENT_VIEW.SIGNAL_DAILY_V2_SPOTIFY_PATCH` is not readable by DATA_TEAM.
  - Dec-25 distinct txns: FR v3 71M, FR v2 55M, UK 53M, ES 26M, IT 13M, DE 11M (`status.md:30`).

### Key columns [M: INFORMATION_SCHEMA; no Snowflake comments exist. Meanings from the PDF guide, pp. 29-35]
- **`*_TXN`:**
  - Ids: `FDTXNKEY` (transaction id), `FDUSERKEY` (user/card).
  - Dates: `TXNDATE`, `POSTEDDATE`, `REPORTDATE` (the guide filters `ABS(reportdate − txndate) <= 7` for reproducibility: "98% of the txns of a day are received within the following week").
  - Descriptor: `DESCRIPTION`, per transaction.
  - Amounts: `SPENDOUT` / `SPENDIN`. The guide filters `SpendOut < 0` to "Remove refunds"; **[I]** spend is signed negative in SPENDOUT.
  - Merchant: `TAG` (merchant tag → `MERCHANT_HIERARCHY`), `MCC`, `PAYMENTPROCESSORNAME`, `FDLOCATIONID`.
  - User: `USERTYPE`, `USERCOUNTRY`, UK ONS geodemographics.
  - Other: `TXNTYPE`, `RECORDSTATUS`, `CAPPEDAMOUNT`, `TXNCURRENCY`.
- **`*_SUPP`:** `FDACCOUNTKEY`, `SOURCEACCOUNTTYPE`, `BANKID`, `APIPULLDATE`, `SIGNALSELECTFLAG`.
- **`*_UPDATES`:** adds `PATCHEDDATE`.
- **`USER_MASTER`:** `CARDTYPE`, `USERTYPE` (C = consumer), `GENDER`, `AGEGROUP`, `INCOMEBAND`, `OPENBANKINGFLAG`, `STARTDATE` / `ENDDATE`. This is SCD2; the guide joins on `enddate = '2099-12-31'`.
- **No panel weight on rows.** Fable's method is a **rolling panel**: per period, keep users active in both the current and prior-year window, optionally tiered by card activity (Tier 1 means more than €1,200 spend or 20 or more transactions in both years) (guide pp. 17-21, 44-45).
- **`REFERENCE_DATA.MERCHANT_WEIGHTS`:** country weights per ticker KPI. **`FABLE.COMMON.COUNTRY_WTS`:** country and consumer-type weights [M].

### FABLE.COMMON (SRS-built) [S: sync-service `services/fable`]
- `PANELS_DATA`, `PANELS_SETTINGS`, `PANELS_METRICS` and `MERCHANT_HIERARCHY_MASTER` are S3 copies of Fable's rolling-panel aggregate files (bucket `fd-rollingpanelpanelizedaggs-v1`, 9 tickers: ABNB, AMZN, EBAY, ETSY, HFG, HMB, ITX, ROO, TKWY).
- `MACHINE_DATA_DAILY_ENHANCED_SRS_AGG_EU[_V2]` are built from **`SHARE_FABLE_DAILY_T7[_V2].FABLE_SIGNAL_DAILY[_V2].SIGNAL_DAILY[_V2]`** (Signal Daily aggregates, with `weights_input`) joined to VA calendars (`06_machine_data_daily_enhanced_srs_agg_eu.sql` lines 70-352).
- The `company_data` workflow reads `fable.common.machine_data_daily_enhanced_srs_agg_eu_v2` (srs `sync_raw_data_prepare.py:154-163`).
- **[I]** No production job reads the row-level `FABLE_SIGNAL.*_TXN` tables. Only the exploration notebooks do.

### Caveats [S]
- In the Muse work, Fable had zero agentic (`LINKAGNT*`) rows: "only `link.com*` (regular Link wallet)" (notebook cell 1).
- A v2 patch touched 76 merchant tags (#vendor-changes 2026-07-27).
- The FR v2 → v3 level change and the FRv2 panel shrink through Q4 2026 mean France needs a series switch.

---

## 5. SRS-internal `EARNEST.<TICKER>.TXNS`

### How it is built [S: sync-service, `services/earnest-PDD/config.py` and `sqls/post_processing/02_load.sql`, read via `gh api`; same pattern in the other services]
1. **Source.** These are **not** read from the Snowflake share. `config.py` finds the newest month under `s3://earnest-spend-279-us-east-1/prime-snapshots/` for `spend_279_transactions`.
2. **Load.** It reads parquet from `prime-snapshots/{yyyy/mm}/*/spend_279_transactions/v3.0/parquet/` filtered by a **parent_merchant / merchant path regex**, into `raw_snapshot_monthly`.
3. **Apply changes.** It loads `prime-incremental/.../spend_279_transactions_log` into `raw_incrementals_daily`, keeps the latest change per (parent_merchant, merchant, earnest_transaction_id) in `raw_changeset`, then MERGEs (applying D/U/N).
4. **Build `TXNS`.** `TXNS` = `raw_snapshot_monthly` plus:
   - `SCALARS` (from `earnest.common.trickle_scalars`, default 1);
   - `CS_PANEL_2019` (2019 consistent_shopper, `production_cs_panel`);
   - `CS_PANEL_2022` (2022 consistent_shopper members with a `member_weights` method ending in `v2`);
   - `WEIGHT` (that v2 weight).
5. **Columns [M].** The 279 columns plus `COBRAND_ID`, `CHANGE_DATE`, `SCALARS`, `CS_PANEL_2019`, `CS_PANEL_2022`, `WEIGHT`.
6. **Schedule.** Daily at 03:00 UTC for most services.

**Panel population.** The panel is effectively Earnest **PRIME** (Omega-equivalent), not Tau [I: the `prime-snapshots` prefix, not `prime-snapshots-tau`].

| Schema | Service | Filter (regex on S3 path) | Notes [M] |
|---|---|---|---|
| PDD | earnest-PDD | parent_merchant = pinduoduo_inc\|shein\|etsy_adjusted\|amazon_adjusted\|walmart_adjusted\|chewy_adjusted\|bytedance_adjusted\|ulta | 4.39B rows. **Not PDD-only** (also writes `USER_OVERLAP`) |
| UBER | earnest-UBER | uber, lyft, doordash (+driver pay), waymo | 1.06B |
| NFLX / SPOT / ETSY / CHWY / RBLX / DIS / DUOL / TSLA / LIF / YOU | same template | netflix / spotify_adjusted / etsy_adjusted / chewy_adjusted / roblox / disney_plus / duolingo / tesla / life360 / clear_me | refreshed 2026-10-15/16 |
| WBD | earnest-WBD | merchant = hbo \| discovery_plus | |
| AIRLINES | earnest-LUV | southwest, delta, united, american, jetblue | also `DAILY_AGG` |
| LMND, ROKU | earnest-LMND / -ROKU | **direct-snapshots/** prefix | last altered 2025-10 (stale, Direct feed ended) |
| DPZ | earnest-DPZ | direct-snapshots, weekly | |
| DASH, META, TMUS, LAD | — | — | `TXNS` last altered 2022–2024 (stale). earnest-DASH now writes `DASH.MARKETPLACE_TXNS` directly from `SHARE_EARNEST_279.PRIME` |
| CAVA, HIMS, TPR, PLNT, PYPL | earnest-CAVA/-HIMS/-TPR/-PLNT-new/-PYPL | SQL over `SHARE_EARNEST_279.PRIME` (not S3) | write `CAVA_TXNS`, `HIMS_TXNS*`, `TPR.SPEND_279_TRANSACTIONS`, …, not `TXNS` |
| EAT, FIVE, ULTA | not found in sync-service | — | created 2026-05/08. Origin unknown (see gaps) |

**Related [S]:** srs `workflows/jobs/company_data/artifacts/sync_raw_data_prepare.py:89-123` builds `SRS_MCP.<ticker>.EARNEST_TXNS` from `SHARE_EARNEST_279.PRIME` (backtest-limit flag, CS 2019/2022 members, legacy-method weights). sync-service is being retired into srs workflows (issue SRSfund/srs#2231: "slice-* and earnest-* are about 78 near-identical share → SQL services"; PR #2549 ported earnest-new-customer).

### Caveats [S]
- **Never full-scan.** "PDD.TXNS = 274 GB / 4.1B rows". Weight sales with `* scalars` and pin `cs_panel_2022` or `cs_panel_2019` (dataset-knowledge `earnest.md`).
- **Possible fan-out.** The double-count bug after 1 July 2026 affected "all ~16 earnest-<TICKER> services". Pinned-to-legacy filters (earnest-HIMS, earnest-TPR) were "now silently empty" (#vendor-changes 2026-07-27). **[I]** The current `cs_panel_2022` CTE groups by (member, production_cs_panel, weight) with `ENDSWITH(method,'v2')`. A member with more than one v2 weight would still fan out, so check `COUNT(DISTINCT earnest_transaction_id)` against `COUNT(*)`.
- **Secrets.** The sync-service `earnest-*` configs and the Notion *Earnest/Yodlee / Data Notes* page contain plaintext AWS keys for the Earnest bucket. They are not reproduced here and should probably be rotated or moved to a secrets store.

---

## 6. `EARNEST.COMMON.CE_PRIME_OMEGA_PANEL_TXNS` (Josh Singer) and the consistent-shopper panels

### What it is [S: srs `scripts/sql/earnest_ce_prime_omega_panel_txns_view.sql`, on master via PR #2513 (085ced2b) and PR #2522 (a47f1510), branch `feat/earnest-prime-omega-view` (f2083af0)]
- A row-level **view**, not a table ("the transaction table is too large to copy", lines 50-51), over the 2822 Omega share. It joins:
  - TRANS
  - MID (MERCHDESC)
  - CARD (deduplicated with QUALIFY)
  - CARDLINK_INCOME and CARDLINK_HOME_LOCATION (date-ranged)
  - MID_MATCH, BRAND, INDUSTRY_LIST
  - SYMBOL_BRAND (end date exclusive) and SYMBOL_DETAIL
  - a one-time pivot of CARDLINK_PANEL.

  Every join is a LEFT JOIN (lines 21-48, 174-249).
- **Two views in the master DDL** (PR #2522, lines 7-14, 109-265):
  - `CE_PRIME_OMEGA_TXNS`: **every** cardholder, with the `IN_AGG_CS2019` / `IN_AGG_CS2022` flags and the weights.
  - `CE_PRIME_OMEGA_PANEL_TXNS`: `WHERE in_agg_cs2019 OR in_agg_cs2022`.
- **[M] What is deployed.** Snowflake has **only** `CE_PRIME_OMEGA_PANEL_TXNS`, created 2026-10-14 08:42 PT, owner SRS_TABLE_OWNER. It carries the PR #2513-era comment ("…with CER symbol/brand, channel and the 2019/2022 aggregate-consistent-shopper panel weights; replaces SHARE_EARNEST_279…"). **`CE_PRIME_OMEGA_TXNS` does not exist yet**, so the master DDL (PR #2522) has not been applied.
- **Filters:**
  - `TRANS_DATE >= 2019-01-01` (the earliest panel start).
  - Excludes `PRIME_OMEGA_STATIC.AFFECTED_ACCOUNTS_092026` via NOT EXISTS (lines 99-102, 250-255).
- **Panels** (lines 54-78):
  - Only `aggregate_consistent_shopper_2019_v2` (about 0.5M cards) and `_2022_v2` (about 3.6M cards) are exposed. This was a "team decision, 2026-10-14: the other 20 panels are not used downstream".
  - Chuxi Wang in Slack: "let's only keep 2019_v2 and 2022_v2".
  - Each panel has one `PANEL_START_DATE` (1 January). The layout is horizontal: one `WEIGHT_*` / `PANEL_START_DATE_*` pair per panel.

### Key columns [S: column comments in the DDL]
- **Ids:** `TRANSID` ("Unique per transaction; a row repeats only when the brand maps to several CER symbols"), `PARTNER_TRANSID`, `CARDLINKID`, `CARDID`, `MERCHID`.
- **Dates:** `TRANS_DATE`.
- **Descriptor:** `MERCHDESC` ("Raw merchant descriptor for MERCHID … The way to find merchants CER has not tagged (NULL brand), such as Stripe Link / Meta Pay descriptors").
- **Panel and weight:** `IN_AGG_CS2019`, `IN_AGG_CS2022`, `WEIGHT_AGG_CS2019`, `WEIGHT_AGG_CS2022`, `PANEL_START_DATE_AGG_*`.
- **Brand and ticker:** `SYMBOL`, `BRAND_NAME`, `CHANNEL`.
- **Card, income and home:** card/income/home attributes.
- **Amount:** `TRANS_AMOUNT` ("Positive for debit, negative for credit"), `CURRENCY`.

### How to use and caveats
- **[S] Josh's usage note** (Slack C0C8FNZGQMD, 2026-10-14 17:09 BST):
  - "Always filter `symbol` and a `trans_date` range. It's big: about 2.5 min per symbol-week."
  - Filter `weight_agg_cs2022 IS NOT NULL` and weight by that same column.
  - Add `currency = 'USD'`.
  - "Don't sum across symbols: acquired brands map to both their old and new ticker."
- **[S] Grain.** One row per transaction per matching symbol, so use `COUNT(DISTINCT TRANSID)` or filter `SYMBOL` (DDL lines 88-97). Brands with no symbol keep NULL `SYMBOL`. A filter on `SYMBOL` therefore drops untagged merchants.
- **[M]** Dec-25: 418M of 1,939M Omega transactions (about 22%) are in the two panels. MIN/MAX over the view does not finish (`status.md:17,27,50`).
- **[S]** Fintan, Slack 2026-10-13: the consistent-shopping panels look like "a clean subset of the table i was using".
- **[I] Missing user-score filter.** The view does **not** apply the card-type / avg-user-score exclusion seen in the CER MIGRATION validation SQL. Totals may therefore differ from legacy 279 production series.

### Provenance of the request [S: Slack C0C8FNZGQMD, 2026-10-13/14]
Chuxi Wang asked for "a 'production' 279 table to handle all the join/logic for rest of us to use". Joshua Singer built it as a view in `EARNEST.COMMON` ("where we store all 'shared' earnest tables etled from upstream"). Josh also shared a SharePoint *Data Dictionary - Orion Prime Enriched.xlsx*, which was not accessible to this search. Chuxi asked whether "symbol/brand are available for earnest daily enhanced and machine data daily". CE says those aggregates are "NOT changing yet. maybe Oct." (2026-08-03 call).

---

## 7. Gaps: nothing found explains these

1. **Yodlee feeds 1–6.** What each feed number is (FI/cobrand/source), why there is no feed 5, and the official reason feeds 1 and 2 stopped on 2025-09-15. The link to the Yodlee Direct sunset (29 Oct 2025) and the 5640 outage is inference.
2. **"PRIME_EX_TAU" and "201".** No document defines either name. The ex-Tau meaning is inference.
3. **Omega and Tau provenance.** Which upstream sources make up Tau. Why Tau TRANS has rows from 2013 when CE said "2024 Jan 1" and 279 PRIME_TAU starts 2023-03-28. Whether Tau has CE-recommended weights. Ben (CE) owed "a recap of panel sizes … for Omega, Tau, and the new CE Transact" (2026-08-03 action item); no follow-up was found.
4. **2822 data dictionary.** The Notion attachment is the *279* Orion Prime Enriched dictionary (Oct 2025). The 2822/v1_0 dictionary Josh referenced is on SharePoint and was not reviewed. There are no CE docs for `CARDLINK_PANEL` methodology (how `aggregate_consistent_shopper_*_v2` differs from `consistent_shopper_YYYY`, or how weights are derived), for `NORMALIZER_PANEL` methods, or for `USER_SCORE`.
5. **Id equivalence across 279 and 2822.** `CARDLINKID = member_id` and the TRANSID ↔ `earnest_transaction_id` relationship are not verified. Whether 279 PRIME = Omega ∩ (some filter) and 279 PRIME_TAU = Tau is also unverified.
6. **The user-score exclusion.** The meaning and current status of the `avg_user_score between -4.98225 and 0` card exclusion (CER MIGRATION validation SQL). It is not documented elsewhere.
7. **AFFECTED_ACCOUNTS_092026 and IMPACTED_MEMBER_LIST_20260618 / SYNTHETIC_TRANSACTIONS_20260122** (279 PRIME_STATIC). Reason, scope and whether history was corrected. Only the #vendor-changes "~2.5% affected members, historical data not corrected" note exists.
8. **EARNEST.EAT/FIVE/ULTA.TXNS.** The builder was not found in sync-service. No owner is documented.
9. **Fable row-level tables.** No Snowflake column comments and no row-level data dictionary (the PDF covers the rolling-panel aggregate product). Sign conventions for SPENDIN/SPENDOUT, the meaning of `RECORDSTATUS`/`CAPPEDAMOUNT`/`SIGNALSELECTFLAG`, and the difference between `*_SIGNAL` views and `*_TXN` are inferred.
10. **Fable FRv3 vs FRv2 overlap.** Whether users and transactions overlap between them is undocumented.
11. **Vendor-change Notion entries.** The pages behind the #vendor-changes links (e.g. FRv3 `36ec595f…`, double-count `397c595f…`) return 404 to this Notion integration.

---

## Source list

**Repos (local)**
- srs `scripts/sql/earnest_ce_prime_omega_panel_txns_view.sql`:
  - lines 1-107: header, upstream tables, panels, grain, filters
  - lines 109-172: CE_PRIME_OMEGA_TXNS with column comments
  - lines 260-265: PANEL_TXNS
  - History: commits 7752578f → 52003321 (22 panels, with sizes) → 085ced2b (#2513) → a47f1510 (#2522); branch `feat/earnest-prime-omega-view`.
- srs `workflows/jobs/company_data/artifacts/sync_raw_data_prepare.py:89-123` (EARNEST template), `:154-163` (FABLE template).
- srs `apps/mcp/skills/public/dataset-knowledge/references/earnest.md` and `consumer-panel.md` (branch `origin/feat/dataset-knowledge-skill`, commit 79abb25d; also `.claude/rules/datasets/` in c5672655).
- srs-meta-muse:
  - `workflows/jobs/meta/artifacts/load/card_txns.sql:1-22, 60-185`
  - `workflows/jobs/meta/CLAUDE.md:41-49, 68-70, 94-101`
- exploration:
  - `meta/app/README.md:30-37, 50-54, 64`
  - `meta/app/METHODOLOGY.md:139, 150, 224`
  - `meta/app/sections.py:43, 100-132, 199, 344-346, 614-617`
  - `meta/investigations/card_linkagnt_coverage.ipynb` (cell 1 status; cells 9-12 mirror and overlap checks)
  - `meta/investigations/PLAN.md:14, 36`
  - `card_datasets_inv/status.md:5-55`

**sync-service (GitHub SRSfund/sync-service, read via `gh api`)**
- `services/earnest-PDD/config.py`, `services/earnest-PDD/sqls/post_processing/02_load.sql` and `02_post_run.sql`
- `services/earnest-{CHWY,DIS,DUOL,ETSY,LIF,LMND,LUV,NFLX,RBLX,ROKU,SPOT,TSLA,UBER,WBD,YOU,DPZ}/config.py` (merchant filters)
- `services/earnest-CAVA/sqls/post_processing/02_create_cava_txns.sql`, `services/earnest-DASH/sqls/post_processing/02_create_dash_txns.sql`
- `services/fable/config.py`, `services/fable/sqls/post_processing/05-07_*.sql`
- GitHub SRSfund/srs issue #2231; PRs #2513, #2522, #2549, #1705; sync-service PR #2269 (referenced).

**Snowflake metadata (role DATA_TEAM, 2026-10-15/16)**
- INFORMATION_SCHEMA.SCHEMATA, TABLES and COLUMNS comments for: SHARE_CE_PRIME_ENRICHED_OMEGA_2822 / _TAU_2822, SHARE_CE_SPEND_201_PRIME_EX_TAU, SHARE_EARNEST_279, SHARE_FABLE, FABLE, EARNEST.
- MANIFEST and DATADELIVERED_V3_0 tables.
- SHOW DATABASES (origins, e.g. SHARE_EARNEST_279 ← `XW17098.PW55959.SPEND_279_FINANCIAL_DIRECT`).
- SHOW VIEWS IN EARNEST.COMMON.
- GROUP BYs on 279 MEMBER_WEIGHTS methods and MEMBER_PANELS.
- Scripts and outputs: session scratchpad `meta1.py`, `meta2.py`, `meta3.py`.

**Notion**
- CER / Data Notes: https://app.notion.com/p/31ec595f49108144a630e2179ba3173f
- CER Change over call 2026-08-03 (Omega / Tau definitions): https://app.notion.com/p/3b1c595f491080d4b5ace6b9c147ef91
- CER MIGRATION (279 → 2822 validation SQL): https://app.notion.com/p/3b8c595f4910803298fbd05e1eb5deaf
- CER (Earnest Orion renewal call) 2026-02-20: https://app.notion.com/p/30dc595f4910809c9bb9f986e64725d4
- Earnest/Yodlee (index): https://app.notion.com/p/c8acaf149f234b4299241abddcea05fe
- Updates 2025-07-16: https://app.notion.com/p/232c595f491080909315f20d1b94912d
- Earnest Update Call 2025-10-03: https://app.notion.com/p/281c595f4910808daa4dcdf1c3c5c338
- Direct to Prime Migration: https://app.notion.com/p/29ac595f49108018a664e55b6331f0ee
- Yodlee 5640 Outage: https://app.notion.com/p/1eac595f49108088afc7d4d715783e86
- Earnest Data Dictionary (attachments `Orion_Prime_Enriched_Data_Dictionary_v2 (12).xlsx` and `S3_Access_Points_Spend_Orion_Query_Aggregate (8).xlsx`): https://app.notion.com/p/29cc595f491080b7a86dc573bca585f5
- Fable data (attachment `Fable_Data_Rolling_Panel_Aggregate_Product_Guide.pdf`): https://app.notion.com/p/9b79dfc6e3ef4b51b6acef46cf30477b
- Fable Resources: https://app.notion.com/p/d847c9d8fff6463cb5a39fca50a4717e
- Fable Call 2025-07-31: https://app.notion.com/p/241c595f491080418a2de105319e6f26
- Vendor-change database: https://www.notion.so/61b48ce1cfd94e3ab3d5c397a73612b1

**Slack**
- Group DM C0C8FNZGQMD (Josh Singer, Chuxi Wang, Fin Creedon), 2026-10-13 17:44 → 2026-10-14 20:12 BST. Covers the 2822 production tables, "OMEGA is the old cpanel", the panel choice, the view announcement and usage notes.
- #vendor-changes (C0B1D12LABZ), Christopher Chang's digests, 2026-06-01 → 2026-10-12. Covers the Orion Prime v2 panels and double-count bug, Orion Prime 2.0 schema, the Sep 22 recomposition, and Fable FRv3 / v2 patch. Examples: https://srsfund.slack.com/archives/C0B1D12LABZ/p1786378582563139, https://srsfund.slack.com/archives/C0B1D12LABZ/p1791216742887619

**SRS MCP**
- `skills_manager` has no data-source skill for these vendors. `srs-bootstrap` exists only as a foundation bundle skill covering documents and KPIs. `srs_documents` was not applicable: it covers company filings and broker notes, not vendor data dictionaries.
