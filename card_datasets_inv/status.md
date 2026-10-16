## Status

_Run completed 2026-10-15. Small warehouse for metadata and most probes, LARGE for the slow December counts._

**Coverage**
- 23 databases match the prefixes. 18 are reachable, giving 3,404 tables / views.
- Not reachable:
  - Four healthcare-claims shares and `SHARE_EARNEST_RETAIL_PRICING` have been revoked.
  - `SHARE_EARNEST_327`, `CALLOUTS` and `FOOT_TRAFFIC` errored.
  - `SHARE_FABLE.CLIENT_VIEW.SIGNAL_DAILY_V2_SPOTIFY_PATCH` is not authorised for DATA_TEAM.
- About 1,400 objects are exact mirrors and are not counted separately. Their `mirror_of` column points to the copy that was probed:
  - the four `*_279` databases are mirrors of `SHARE_EARNEST_279`;
  - `TAU_2822` mirrors `OMEGA_2822`;
  - the three Fable databases are identical;
  - the three `TRANSACT_USA` databases are identical.
- Every December 2025 count completed.
- `EARNEST.COMMON.CE_PRIME_OMEGA_PANEL_TXNS`: its own MIN/MAX would not finish, so the date range was derived from `TRANS_V1_0`. The derivation keeps the view's panel join, its 2019-01-01 floor and its affected-accounts exclusion. All its other joins are LEFT JOINs.

**Row-level transaction sources, December 2025 distinct transactions**

| Source | Object | Descriptor | Data from → to | Dec-25 txns |
|---|---|---|---|---:|
| Prime Omega | `OMEGA_2822.PRIME_OMEGA.TRANS_V1_0` | merchant-level only, via `MID_V1_0.MERCHDESC` | 2000 → 2026-10-13 | 1,939M |
| Prime Omega (Tau panel) | `TAU_2822.PRIME_TAU.TRANS_V1_0` | merchant-level only | 2013 → 2026-10-13 | 822M |
| Yodlee feed 3 bank | `SPEND_201_PRIME_EX_TAU.FEED3_PANELS.FEED3_BANK_PANELS_V1_0` | `DESCRIPTION` | 2005 → 2026-10-14 | 759M |
| 279 Tau | `SHARE_EARNEST_279.PRIME_TAU.SPEND_279_TRANSACTIONS_V3_0` | `BILLING_DESCRIPTION` | 2023-03-28 → 2026-10-14 | 432M |
| Josh's view (CS 2019 / 2022 panels) | `EARNEST.COMMON.CE_PRIME_OMEGA_PANEL_TXNS` | `MERCHDESC` (merchant-level) | 2019-01-01 → 2026-10-14 | 418M |
| 279 Prime | `SHARE_EARNEST_279.PRIME.SPEND_279_TRANSACTIONS_V3_0` | `BILLING_DESCRIPTION` | 2015-02-26 → 2026-10-14 | 278M |
| Yodlee feed 6 bank | `FEED6_BANK_PANELS_V1_0` | `DESCRIPTION` | 2001 → 2026-10-16 | 246M |
| Fable FR v3 / FR v2 / UK / ES / IT / DE | `SHARE_FABLE.FABLE_SIGNAL.*_TXN` | `DESCRIPTION` | → 2026-10-12/14 | 71 / 55 / 53 / 26 / 13 / 11M |
| Yodlee feed 3 / 4 / 6 card | `FEED{3,4,6}_CARD_PANELS_V1_0` | `DESCRIPTION` | → 2026-10-14/15 | 36 / 27 / 18M |
| Yodlee feed 4 bank | `FEED4_BANK_PANELS_V1_0` | `DESCRIPTION` | → 2026-10-14 | 29M |
| Earnest ticker extracts | `EARNEST.<TICKER>.TXNS` (PDD, UBER, DASH, NFLX, …) | `BILLING_DESCRIPTION` | → 2026-10-13/14 | 0.1–40M each |

**Early observations, for the follow-up overlap analysis**
- Several tables are just versions of one dataset:
  - `PRIME_SNAPSHOTS*` tables match their current table to within 0.1% for December.
  - The 279 `PRIME_INCREMENTAL*` change logs match to within 0.5%.
  - The Prime Omega `PRIME_INCREMENTAL_*` logs are much smaller (214M and 1.7M), so they hold only the changed rows.
  - Fable `*_SIGNAL` views equal their `*_TXN` tables.
  - Use the current table unless point-in-time history is needed.
- Some sources have stopped:
  - the 279 `DIRECT*` and `SIGMA` tables;
  - Yodlee feeds 1 and 2, which ended September 2025.
  - None of these has any December 2025 data.
- Prime Omega `TRANS_V1_0` is the largest US source, but has no per-transaction descriptor. The descriptor is per merchant (`MERCHID` → `MID_V1_0.MERCHDESC`).
- Per-transaction descriptors come from three places: 279 (`BILLING_DESCRIPTION`), Yodlee (`DESCRIPTION`) and Fable (`DESCRIPTION`).
- 279 `PRIME` has about 1.4 rows per distinct transaction (390M rows vs 278M ids), so deduplicate on the transaction id.
- 279 `PRIME_TAU` is larger than `PRIME` (432M vs 278M), but only starts on 2023-03-28.
- Josh's view restricts Prime Omega to the two consistent-shopper panels: 418M of the 1,939M December transactions, about 22%.

**Next:** a subset and overlap notebook to find out:
- whether 279 PRIME / PRIME_TAU are subsets of Prime Omega / Tau;
- how they overlap with Yodlee feeds 3, 4 and 6;
- whether per-merchant `MERCHDESC` is good enough to identify agentic (`LINKAGNT*`) transactions, compared with per-transaction descriptors.
