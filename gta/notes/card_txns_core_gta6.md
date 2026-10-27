# GTA VI pre-purchases in EARNEST.COMMON.TXNS_CORE_V (2022 Consistent Shopper panel)

Run 2026-10-27, read-only. SQL: `card_txns_core_gta6.sql`.

## Verdict
**GTA VI pre-purchases are not observable in TXNS_CORE_V.** No descriptor mentions GTA or Rockstar, and no retailer in the table shows an inflection on or after 25 Jun 2026 in the expected price buckets. **Reliable channels: none. Estimated excess pre-orders: 0 (not estimable).**

The main reason is coverage. TXNS_CORE carries only the brands in `brand_selection.yaml` / `TXNS_CORE_SELECTION`. That list includes **no** PlayStation/Sony, Microsoft/Xbox, Rockstar/Take-Two, Steam/Valve, Epic or GameStop selector. These are the channels that charge at pre-order. The relevant retailers in the table are Amazon (symbol AMZN) and Walmart (brand 93718). Both charge pre-orders at shipment.

## Panel filter
`WEIGHT_AGG_CS2022 IS NOT NULL`. Every such row has `PANEL_START_DATE_AGG_CS2022 = 2022-01-01`, and the weight is static (26 distinct values). About 2.44M members transacted in TXNS_CORE brands in 1–7 Sep 2026. About 0.3% of rows have a null CS2022 weight. Purchases use `TRANSTYPE='debit'` (amount > 0). Credits are negative.

Key columns: `MEMID`, `TRANS_DATE`, `TRANS_AMOUNT`, `BILLING_DESCRIPTION`, `BRAND_ID/BRAND_NAME`, `DISTRIBUTION_BRAND_*`, `PAYMENT_BRAND_*`, `CHANNEL`, `WEIGHT_AGG_CS2022`.

## Descriptor search (since 2026-05-01)
I searched for GTA, GRAND THEFT, ROCKSTAR, TAKE TWO / TAKE-TWO / TAKETWO, PLAYSTATION, SONY, PSN, XBOX, MICROSOFT, STEAM, VALVE, EPIC GAMES, GAMESTOP and NINTENDO. **None of the hits is a game purchase.** They are substring false positives such as "DOORDASH STEAMSOUL", "STEAMBOAT SPR", DEPOP "…APSN" reference codes and "…GTA…" random IDs, plus bank-transfer memos ("XFER TO AMAZON XBOX"). Amazon/Walmart descriptors carry no item detail, apart from rare Amazon Fresh grocery strings.

## Per-retailer results
Average daily debit counts (unweighted) in the CS2022 panel. "Pre" = 4–24 Jun. "Wk1" = 25 Jun–1 Jul. Week-level unweighted, weighted and member counts are in SQL 3d.

| Retailer (brand id / pattern) | Bucket | 2026 pre | 2026 25-Jun | 2026 wk1 | 2026 2–22 Jul | 2025 pre → wk1 | Verdict |
|---|---|---|---|---|---|---|---|
| AMAZON.COM (10127) | $69.99 | 20.5 | 12 | 18.0 | 20.4 | 22.1 → 19.0 | Unreliable, no inflection |
| AMAZON.COM | $79.99 | 21.0 | 15 | 19.6 | 21.7 | 25.5 → 29.4 | Unreliable |
| AMAZON.COM | $99.99 / $129.99 | 14.6 / 6.6 | 14 / 7 | 18.6 / 5.1 | 14.5 / 6.3 | flat | Unreliable |
| AMAZON MARKETPLACE (23513) | $69.99 | 43.6 | 42 | 36.6 | 35.7 | 35.3 → 37.3 | Unreliable |
| AMAZON MARKETPLACE | $79.99 | 26.7 | 34 | 31.4 | 25.9 | 27.4 → 24.9 | Unreliable (+5/day is noise) |
| AMAZON (both) | tax-incl. $74–87.99 | ~14.4k | 16.9k | ~16.7k | ~12.8k | Prime Day mix | Unreliable: Prime Day confound |
| WALMART online (93718, ONLINE) | $69.99 / $79.99 | 4.5 / 3.6 | 0 / 7 | 3.7 / 4.7 | 4.3 / 3.2 | ~2 / ~2 | Unreliable |
| WALMART online | tax-incl. $74–87.99 | 3,536 | 2,648 | 3,509 | 3,597 | 1,836 → 1,858 | Unreliable, flat |
| WALMART stores (93718, OFFLINE) | $69.99 / $79.99 | 10.9 / 10.0 | 5 / 3 | 9.4 / 6.1 | 11.1 / 9.6 | flat | Unreliable |
| BEST BUY (10315) | any | ~2/day in $74–88 | — | — | — | — | Not usable: DoorDash delivery rows only |
| TARGET (12734) | any | ~31/day in $74–88 | — | — | — | — | Not usable: DoorDash delivery rows only |
| PSN, Xbox, Rockstar, Steam, Epic, GameStop | — | not in table | | | | | Not covered |

Weekly exact-price counts ($69.99/$79.99/$99.99/$129.99, weeks aligned to 25 Jun):
- **Amazon:** wk −4…−1 averages 1,141/wk (768 at $69.99/$79.99). Wk0 is 1,124 (739), which is −4%. The 2025 equivalent was 761 → 774.
- **Walmart:** wk −4…−1 averages 303/wk (201 at $69.99/$79.99). Wk0 is 277 (168). The 2025 equivalent was 185 → 193.
- Weighted counts and unique members move one-for-one with raw counts (members ≈ 0.95–0.99 × txns).

The Amazon $74–88 lift on 24–26 Jun 2026 (share of Amazon debits 3.0% → 3.26%) is a Prime Day mix effect, not GTA. Amazon's total debits rose at the same time (~480k → ~600k/day), and Prime Day 2025 (8–11 Jul) produced a larger share lift (3.0% → 3.65%).

## Timing implications
- **Amazon, Walmart, Best Buy and Target** authorize pre-orders but capture payment at shipment. Their GTA VI pre-orders should appear as card debits around **18–19 Nov 2026** (release-day ship/delivery), not from 25 Jun. A flat Jun–Oct series is expected, not evidence of weak demand. Retail physical pre-orders could still be tested here as a spike in exact or tax-inclusive buckets at Amazon/Walmart around 19 Nov, against the 2025 November baseline.
- **PS Store, Rockstar Store and Steam** charge at pre-order. **Xbox** charges about 10 days before release. These are the only channels where a 25-Jun inflection would exist, and none of them is in TXNS_CORE.

## Estimated excess pre-orders
None is attributable in any channel. The excess over baseline in the expected buckets is within ±5–10% weekly noise and ≤0 for wk0 at both Amazon and Walmart.

## Data freshness
`TRANS_DATE` runs to 2026-10-25 and `FILEDATE` to 2026-10-25. `BUILT_AT` is 2026-10-26.

## Caveats and next steps
- Exact-cent buckets are small (Amazon ~110/day, Walmart ~30/day), and tax-inclusive ranges are dominated by unrelated baskets. Even a real GTA signal at retail would be hard to isolate without item data.
- Physical GTA VI at Amazon/Walmart will be bundled into multi-item orders and taxed by state, which weakens price-bucket identification.
- To actually track GTA VI pre-purchases, add brand selectors for PlayStation Network/Sony, Microsoft/Xbox, Rockstar Games/Take-Two (and Steam/GameStop for completeness) to `brand_selection.yaml`, then rerun this test on the PSN/Rockstar descriptors. An alternative is the full Omega panel tables or e-receipts (NIQ), which carry item names.
