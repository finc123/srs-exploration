The KMX/CVNA ABS work is the AutoABS bot pipeline. It is built, but it has been switched off since 2026-04-02. As a result, the Snowflake tables stop at December 2025 for KMX and CVNA, even though the vendor (72degree) is still delivering new files every month.

## Where it lives

| Layer | Location |
|---|---|
| Pipeline code | `C:\Users\chris.chang\github\sync-service\services\bot_autoabs\` (`config.py`, `src/fed_fund_rate.py`, five SQL files in `sqls/post_processing/`) |
| Raw vendor files | `s3://srs-vendors/72degree/AutoABS/{carmax,carvana,...}/` |
| Copied files | `s3://srs-72degreedata/AutoABS/data/` |
| Snowflake | `BOTS.AUTOABS`: one detail table per issuer, then `ABS_COMBINED`, then `ABS_COMBINED_PROCESSED` |
| Bot registry | The Notion SRS Bot Registry entry "AutoABS" (monthly ABS-EE loan-level filings from SEC EDGAR via BAMSec for CarMax, Carvana and other issuers) |

The dataset covers seven issuers, not just KMX and CVNA: Ally, Bridgecrest, Capital One, CarMax, Carvana, Exeter and Santander.

## What's been done

Feb 2026 (Joshua Singer): set up the service, made the columns consistent across issuers, and built the combined `ABS_COMBINED` table.

Mar 5–12, 2026 (you, PRs #2200, #2201, #2204, #2209, #2210):
- Added the daily fed funds rate from FRED, joined at each loan's origination date, giving a rate spread over fed funds and spread bins.
- Built `ABS_COMBINED_PROCESSED`, which removes duplicate loans (keeping the latest record per trust, period and loan) instead of relying on a hardcoded exclusion list.
- Added derived columns:
  - Prime vs subprime: CarMax Select and Carvana N trusts count as subprime.
  - FICO bins, loan-to-value, and trust period/year labels.
  - Flags for loan extensions, prepayments, and loans that suddenly paid off while 60+ days delinquent (excluding charge-offs and repossessions).
  - Previous-period balance and delinquency status.
- Fixed `ABS_COMBINED` so it rebuilds on every run, and fixed SQL formatting errors. You also tried normalizing Capital One interest rates but reverted it.

Sept 28, 2026: the bot-management routine asked Will in Private channel for the AutoABS bot spec documentation.

## Current state (checked just now)

| Issuer | Rows | Last filing | Last period |
|---|---|---|---|
| carmax | 37.3M | 2026-01-15 | 2025-12-31 |
| carvana | 17.2M | 2026-01-15 | 2025-12-31 |
| others | — | Feb–Mar 2026 | 2026-01-31 |

72degree's latest files are `carmax_detail_2026-09-16.csv` and `carvana_detail_2026-09-16.csv`, so about nine months of KMX and CVNA data are sitting in S3 but haven't been loaded into Snowflake.

## Open issues before turning it back on

1. **Why it was disabled:** Joshua turned it off on 2026-04-02 because a Santander file (`santander_detail_2026-03-16.csv`) was missing the `mostRecentServicingTransferReceivedDate` column. That shifted every later column by one and broke the load. He tried a date-format fix and reverted it, so the missing column was never handled.
2. **New CarMax files would be skipped:** the file filter in `config.py` matches files named `bamsec_detail_`, which is how CarMax files used to be named, but not the new `carmax_detail_` names. If the sync were simply re-enabled, CarMax files would probably still not load. This comes from reading the filter, not from a test run. The fix is to add `carmax` to the pattern.
3. **Hardcoded key:** the FRED API key is written directly into `fed_fund_rate.py` (commit 9f366f66). It should be moved into config or a secret.

I found no dashboard or notebook built on these tables. If one exists, it isn't in these repos.
