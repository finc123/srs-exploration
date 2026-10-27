# GTA VI pre-purchases in Slice items (SRS_SLICE.COMMON.ITEMS_V)

Written 2026-10-27. All queries were read-only. The SQL is in `slice_items_gta6.sql`.

## Bottom line
- Slice captures GTA VI pre-orders well. The two first-party digital stores are both visible at item level: **PlayStation Store** (merchant `Sony Entertainment Network`) and **Microsoft Store** (merchant `Microsoft store`). Together they make up 92% of matched rows.
- Retail is visible at Best Buy, Amazon, GameStop, Target, Sam's Club and Costco. Every retail SKU is the **$79.99 Standard "code in box"**; we found no disc SKU.
- The main blind spot is **Walmart**. Walmart is in the panel with item descriptions, but no GTA VI *order* rows exist. Only Walmart *cancellation* emails show up. Rockstar Store, Steam and Epic have no game rows, which is expected because the game is console-only.
- Data is fresh. The latest `email_sent_time` / `last_updated` is 2026-10-27 07:xx UTC, and GTA rows run through 2026-10-27.

## Table and access notes
- `ITEMS_V` is defined as `share_niq.srs.items_extended` LEFT JOIN `mailboxes_enhanced`, `active_panel_users` (`active_panel = '6_12_12_Month_Aging'`, exposed as `PANEL`) and `quality_merchants` (exposed as `QUALITY` / `QUALITY_MERCHANT_NOTES`). There is no weight column.
- Key columns: `ORDER_ID`, `USER_ID`, `MAILBOX_ID`, `MERCHANT_NAME`, `MERCHANT_ID`, `ORDER_DATE` (user-local date), `EMAIL_SENT_TIME` (UTC), `LAST_UPDATED`, `DESCRIPTION`, `ITEM_PRICE`, `ITEM_QUANTITY`, `ORDER_TOTAL`, `TAX`, `SHIPPING_COST`, `ORDER_DISCOUNT`, `STATUS`, `CATEGORY_NAME`, `DIGITAL_GOOD`, `SHIP_TO_ZIP`, plus the mailbox and panel fields.
- Free-text scans on `ITEMS_V` time out in the SRS MCP tool for windows longer than a few days, because of the view joins. Use the base table `share_niq.srs.items_extended` for searching, and join back on `order_id, item_id` when you need `PANEL` or `QUALITY`. The full Jun–Oct base-table scan took about 1–5 minutes through the local connector (key-pair JWT, `connection_name="default"`).
- Freshness: the max `order_date` is 2026-11-03, because some rows carry future dates. The max `last_updated` is 2026-10-27 07:59 and the max `email_sent_time` is 2026-10-27 07:44. The week of 26 Oct contains only 2 days.

## Recommended filter (base game)
```sql
where order_date >= '2026-06-24'
  and description ilike '%grand theft auto%'
  and regexp_like(description, '.*GRAND THEFT AUTO[^A-Z0-9]{0,3}VI([^A-Z0-9].*|$)', 'is')
  and not regexp_like(description,
        '.*(UPGRADE|DUALSENSE|CONTROLLER|ALBUM|VINYL|\\bCD\\b|POSTER|SHIRT|\\bTEE\\b|UNOFFICIAL|COVER ART).*', 'is')
  and merchant_name not in ('eBay','Etsy','Temu','TikTok','Mercari','Whatnot')
-- orders:        merchant_name not ilike '% Cancellation'
-- cancellations: merchant_name ilike '% Cancellation'   (net these off separately)
```
- The `VI([^A-Z0-9]|$)` boundary is required. Without it, "Grand Theft Auto **Vi**ce City" matches.
- Short forms (`GTA 6`, `GTA6`, `GTA VI`, `GTAVI`) were tested. They appear only on marketplace merch such as posters and t-shirts, never on a real game SKU, so the filter does not need them.
- Things the filter excludes, plus GTA-adjacent items you can track separately if useful:
  - The Ultimate Edition Upgrade add-on ($20; 101 PSN rows, 69 MS rows). 83% of upgrade buyers already have a Standard row.
  - GTA VI DualSense controllers ($84–85; about 1,050 rows across Sony direct, Best Buy, Target and GameStop, from 10 Sep).
  - The GTA VI soundtrack album (vinyl/CD; about 270 rows, mostly the Shopify store, from 17 Sep).
  - Noise: GTA V/Enhanced, GTA Online, Shark Cards, GTA+, Trilogy, and `%gta%` false hits such as FrogTape.

## Merchant table (orders, 24 Jun – 27 Oct 2026, unweighted)
| Merchant | Rows | Orders | Users | Units | $ (item price × qty) | First date | Launch-week share* | Ultimate % | PS5 / Xbox |
|---|---|---|---|---|---|---|---|---|---|
| PlayStation Store (`Sony Entertainment Network`) | 9,786 | 9,786 | 9,701 | 9,786 | 960,222 | 2026-06-24** | 48% | 88% | 100 / 0 |
| Microsoft Store (`Microsoft store`) | 3,552 | 3,552 | 3,438 | 3,552 | 346,224 | 2026-06-25 | 46% | 87% | 0 / 100 |
| Best Buy | 526 | 519 | 498 | 534 | 42,483 | 2026-06-25 | 32% | 0% | 78 / 22 |
| Amazon | 274 | 271 | 255 | 286 | 22,875 | 2026-06-25 | 72% | 0% | 81 / 19 |
| GameStop | 153 | 150 | 141 | 156 | 12,638 | 2026-06-25 | 31% | 0% | 81 / 19 |
| Target | 118 | 117 | 112 | 122 | 9,759 | 2026-06-24** | 22% | 0% | 81 / 19 |
| Sam's Club | 27 | 26 | 25 | 27 | 2,157 | 2026-06-25 | 56% | 0% | 74 / 26 |
| Costco | 20 | 20 | 19 | 21 | 1,680 | 2026-06-26 | 50% | 0% | 100 / 0 |
| Shopify / QVC / P.C. Richard | 4 | 4 | 4 | 4 | 324 | Jul–Oct | – | – | – |
| **Total** | **14,460** | | ~14,150 | | **1,398,362** | | | 81% | |
| Walmart (cancellations only) | 40 | 38 | 34 | 43 | n/a (no prices) | 2026-06-24 | – | – | 27 / 13 |
| Target Cancellation | 32 | 31 | 29 | 35 | n/a | 2026-06-25 | – | – | |
| Microsoft store Cancellation | 8 | 8 | 7 | 8 | 720 | 2026-06-25 | – | – | |

\* Launch-week share is the share of rows dated on or before 1 Jul.
\*\* The 24-Jun rows are a timezone artefact. `order_date` is the user-local date, and all PSN rows dated 24 Jun have `email_sent_time` from about 04:00 UTC on 25 Jun (midnight ET). Pre-orders effectively opened at 00:00 ET on 25 Jun.

**Inflection: yes, for every merchant.** No base-game rows exist before 24/25 Jun at any merchant. The only earlier GTA VI hit is a single unofficial Amazon guide in May. Each merchant goes from zero to its peak on launch day. Launch day (24+25 Jun) rows were PSN 3,262, MS 965, Best Buy 132, Amazon 121, GameStop 28 and Target 19.

## Trend (all merchants, base game rows)
| Month | Rows | $ |
|---|---|---|
| Jun (24–30) | 6,632 | 647k |
| Jul | 1,726 | 166k |
| Aug | 1,568 | 150k |
| Sep | 1,781 | 171k |
| Oct (1–27) | 2,753 | 263k |

- The launch week (22 Jun) produced 4,343 PSN rows and 1,487 MS rows. Activity then decayed to about 120–160 PSN rows a week by late July.
- Activity spiked in the weeks of 24 Aug and 31 Aug (PSN 489 and 461 rows), which was probably a marketing beat.
- Activity has ramped steadily through October (PSN 452, 528 and 626 rows in the weeks of 5, 12 and 19 Oct), heading into launch.

## Edition and price mix
- **Ultimate $99.99 accounts for 81% of rows**, but only on the digital stores (PSN 88%, MS 87%). Retail sells Standard only, at $79.99. Amazon also shows $79.97, and Best Buy has a few discounted rows at $67.20 / $71.99.
- PSN prices of $109.99 (Standard, 16 rows) and $139.99 (Ultimate, 101 rows) are almost certainly non-USD (likely CAD) storefronts. Exclude these or convert them if you need US dollars.
- Platform: PS5 accounts for about 79% of retail rows. Combined with PSN, PS5 is 74% of all rows and Xbox 26%.
- Format: digital is 92% (`DIGITAL_GOOD = 'Y'` on PSN and MS); retail code-in-box is 8% (`DIGITAL_GOOD = 'N'`). Retail descriptions read "Code in Box, Delivers 11/12/26, Playable 11/19/26". This SKU is a code in a box, not a disc.

## Pre-order vs charged, and dedupe
- `STATUS` is always `I` and `CATEGORY_NAME` is always `Electronics & Accessories`. These fields do not separate states.
- PSN descriptions carry `(Pre-Order)` explicitly. PSN and MS both charge at purchase, so these rows are effectively charged. Retail rows are order confirmations. Best Buy, Target and Amazon typically charge at shipment, around 12 Nov.
- Cancellations arrive as a separate merchant name, `<Merchant> Cancellation`, with mostly NULL prices. Only 34 of 81 cancellation rows match an observed order from the same user and merchant, so the original order email is often missing (Walmart in particular). Track cancellations as their own series rather than netting them row by row.
- `order_id` + `item_id` is unique. The base table is already one row per receipt item.
- Soft duplicates: 170 user × merchant × description combinations have more than one `order_id`, adding about 198 excess rows (1.4%). Examples are identical totals minutes apart at Amazon and PSN. These may be genuine double purchases or repeat emails. Use `count(distinct user_id)` per merchant and edition (about 14.1k users vs 14.5k rows) as the conservative count.
- After launch, watch for shipped or delivered receipts and day-one digital purchases being added. We could not yet test whether retail shipping emails create new item rows.

## Panel coverage
- 64% of matched rows fall in the `6_12_12_Month_Aging` active panel (`PANEL` not null), consistently across merchants.
- All matched merchants are flagged `QUALITY = TRUE`.
- Quality notes:
  - Amazon: truncated descriptions and item details removed on some confirmations. The "Grand Theft Auto VI - PlayStation..." truncation still matches the filter, but Amazon is likely under-counted.
  - Target: about 30% of items have no price on pickup orders.
  - Sam's Club: limited descriptions on pickup orders.

## Blind spots
| Store | In Slice at all? | GTA VI rows? | Read |
|---|---|---|---|
| PlayStation Store | Yes. About 17.9k item rows on 25–26 Jun, all priced, with full titles | **Yes** | Covered |
| Microsoft Store | Yes. 8.6k rows on 25–26 Jun, titles shown as "… by: Rockstar Games" | **Yes** | Covered |
| Sony Direct (`Sony`) | Yes, but small | Controllers only | Fine |
| **Walmart** | Yes. About 294k rows on 25–26 Jun with descriptions; **`ITEM_PRICE` is always NULL**; GTA V and other console games appear | **Cancellations only (40)** | Pre-order confirmation emails appear not to be parsed or captured. This is a material retail blind spot, and Walmart dollars would have no prices anyway |
| Rockstar Games store | Yes, about 110 rows a day, mostly "Welcome to Rockstar Games" and GTA+ payments | No | Expected; no console game sales there |
| Steam / Epic | Yes, with item-level data | No | Expected; no PC version at launch |
| Nintendo | Yes | No | Not on Switch |

## Caveats
- All figures are raw panel counts with no weights. They show relative merchant mix and trend, not absolute units.
- The panel is US-centric. A small slice of PSN rows looks like CAD pricing.
- Retail is about 8% of rows. Physical code-in-box sales at Walmart and at stores outside the panel (independents, in-store walk-ins without an email receipt) are not visible.
- Amazon is under-counted because of its receipt-detail removal.
- Add-on upgrades, controllers and the album are excluded from base-game counts. They are worth tracking as engagement or attach signals.
