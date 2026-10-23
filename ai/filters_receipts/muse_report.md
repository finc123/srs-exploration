# Muse from Meta (`muse`): e-receipt filter report

Data: NIQ US `us_ai_items.parquet` (through 2026-10-18) and Fox EU `eu_ai_items.parquet`. Muse launched in the US on 2026-09-08 and is monthly only. Filter: `filters_receipts/muse.py`.

## Matched patterns (US)

| Channel | Pattern | Kind | Rows / uids | Read |
|---|---|---|---|---|
| apple | `iTunes`, item `Power Plan` / `Maximum Plan` (bare) | charge | 273 / 266 | $20.00 / $100.00, kept |
| apple | `Power Plan : Power Plan (Monthly)` | charge (renewal) | 4 / 4 | $20.00, kept; all 4 uids had an earlier bare charge |
| apple | `Muse from Meta Power Plan $20.00 /month` (and $28 / Max $100 / $139) | confirmation | 352 / 351 | unpriced, rejected |
| google_play | `Power Plan (Muse from Meta) Auto-renewing subscription` (also Max $100) | charge | 137 / 135 | kept |
| google_play | `Maximum Plan (Muse from Meta)` without "Auto-renewing", $31 to $72 | charge | 5 / 5 | rejected as `upgrade_proration` (likely Power to Max upgrades) |
| apple | `iTunes Cancellation`: `Muse from Meta Power/Maximum Plan (1 month)` | cancel | 28 / 28 | no end date in the text |
| google_play | `Google Play Cancellation`: "…will be canceled on Nov 12, 2026" / "(Power Plan) subscription will end on Oct 22" | cancel | 15 / 15 | end date parsed (the year is inferred when absent); plan is `unknown_M` for 12 |

**Bare-plan control.** On iTunes from 2025-01 to 2026-08, there are no bare `Power Plan` or `Maximum Plan` items. The only near-miss is the "Power Planner" app at $2.99 to $4.99, which the anchored regex excludes. After launch, every bare item is exactly $20.00 or $100.00. No other app uses these names. Pre-launch in-band rows are rejected as `pre_launch` (there are none).

## Plans and exclusions

Plans found: `power_M` and `max_M`. Exclusions: 352 unpriced Apple confirmations and 5 Play prorations. There were no trials, out-of-band rows, duplicates or pre-launch rows. The $28 / $139 confirmations (10 uids) are Canadian accounts in the US panel. No CAD-priced charge appears.

## Monthly unique kept payers

| Panel / channel | ≤ 2026-08 | 2026-09 | 2026-10 (to 10-18) |
|---|---|---|---|
| US apple power_M | 0 | 79 | 182 |
| US apple max_M | 0 | 6 | 10 |
| US google_play power_M | 0 | 52 | 84 |
| US google_play max_M | 0 | 1 | 0 |
| **US total (unique)** | 0 | **135** | **273** |
| EU (all countries) | 0 | 0 | 0 |

Cancellations (unique uids, Sep / Oct): Apple 3 / 25, Google Play 6 / 9.

## Renewal visibility

The sample is tiny. Of the Apple payers from 09-07 to 09-17, 4 of 10 are seen paying again in October, and the second receipt uses the `Power Plan : Power Plan (Monthly)` form. On Google Play, 2 of 2 are seen again. The `renews` column is True for apple and google_play. Re-measure in November.

## Web billing (METAPAY)

Muse web billing sends no consumer-plan receipt. In a Snowflake check of `merchant_name ILIKE 'meta%'` from 2026-08 onward, Meta's own receipts cover only Quest content, an "Age confirmation on Muse" (unpriced) email, API token metering (`Muse Spark 1.x / Wonder 1.0 - … Tokens`) and **Muse Code** welcomes at $5 / $15 / **$50** from 2026-09-01. No Muse web Power or Max plan appears. Channel `direct` is therefore absent from this panel (disclosed, not imputed). These Meta rows are not in the extract (`RECEIPT_KEYWORDS` lacks `muse`), which is correct, because none are consumer Muse plans.

## EU

There are no Muse rows. The `power plan` hits are unrelated: the "Frank" AI app on Apple IT at €23, a PayPal "power plan per month/3 month", and Amazon or QVC products. `classify(df, 'eu')` returns an empty frame. Any future hit would be marked `region_not_launched`.

## Caveats

- About 351 uids received Apple confirmations, but only 262 of them ever show a priced charge. The bare charge receipt is missing for roughly 25% of Apple subscribers, so Apple charge counts understate starts. Confirmations could serve as a start proxy.
- The series is six weeks long, and October is partial.

## Open questions

1. Should Apple confirmations be used as a supplementary start signal for uids that have no charge receipt?
2. The Muse Code $50 welcome receipts from 2026-09-02 likely explain the ~$50 `METAPAY META.COM` card cluster (open question 1 in the card report). Should this be confirmed in the card filter?
3. Should Play `upgrade_proration` rows move the uid to `max_M` from that date?
