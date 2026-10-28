# inv2: Roblox payers x GTA VI pre-orderers (NIQ Slice)

Written 2026-10-27. Read-only. Code: `penetration/inv2_roblox.sql` (pull, ~4 min, 8.5M rows, cached to `.cache/roblox_rows.parquet`) and `penetration/inv2_roblox.py` (classification and all tables; CSVs in `penetration/inv2_roblox_out/`). GTA VI = `.cache/gta6.parquet` (base-game orders, cancellations excluded; a mailbox counts from its first pre-order date). Panel = `6_12_12_Month_Aging` active panel (1.08M mailboxes). No prior Roblox Slice filters existed in `exploration/roblox` (that folder holds CCU/Rotrends and MSc/Yipit bookings files only), so the rules below are new.

## Bottom line
- **Yipit basis (Roblox payers, 6m to 11 Oct → % pre-ordered GTA VI): 1.85% on the active panel, 1.66% on all mailboxes vs Yipit 1.65%.** It matches. By 26 Oct the rate is 2.13% (panel).
- **Spend: GTA pre-orderers spend more on Roblox, but the gap is smaller than Yipit's.** Mean 6m spend is $74 vs $61 (panel, 1.21x) and $72 vs $56 (all, 1.28x). Yipit has $112 vs $85 (1.32x). A 12m window gives levels close to Yipit's ($103 vs $88 panel; $97 vs $78 all). Medians are identical ($19.99), so a fat tail drives the gap. The GTA rate barely moves across spend quintiles (1.8–2.3%).
- **MScience basis (GTA VI pre-orderers → % with Roblox spend): it depends on the window.** In the active panel the figures are 10% any channel / 5% console over 6m, 14% / 7% over 12m, 18% / 10% over 24m, and **24% / 13.8% over all history**. MSc's ~22% / ~13% are reproduced only by an all-history look-back. "Historically" therefore means multi-year, not 6–12 months.
- **"Nearly a third of Roblox spenders have a PS/Xbox purchase" (MSc): reproduced.** 36% of 6m Roblox payers in the panel are current-gen console owners (flag B from `console_owners.md`). 68% have any PlayStation/Xbox evidence (flag C). Only 15% pay for Roblox on console.
- **Channel is what drives the overlap.** Console Roblox payers pre-order GTA VI at 6–9% (PSN 8.7%), while mobile-only payers do so at about 1%. That gap is 7–9x the panel base rate of about 0.8%. Most Roblox payers are mobile or direct, which explains why the payer-side rate is low (2%) while the pre-orderer-side rate is high (24% historically).

## 1. Roblox paying transactions by channel
Rules (case-insensitive, rows with price > 0; exact-duplicate rows dropped; `* Cancellation` merchants excluded):

| Channel | Merchant / rule | Notes |
|---|---|---|
| direct | `Roblox` (all except `Credit Redemption`, `PSPLUSITEM`), `Xsolla` with roblox text | Price = item_price, else order_total. Includes Robux, Premium, Roblox Plus, game subscriptions and `Payment` rows (not duplicates: <5% match a same-day same-amount item) |
| apple | `iTunes` with `robux`, `^roblox`, or `roblox premium/plus`; songs, books and guides excluded | Apple receipts are bare (`1200 Robux`, `Premium 450 Robux`) but carry the word Robux, so the item is identifiable. Unpriced confirmations are excluded |
| google_play | `Google Play` with `(Roblox)` | Third-party apps (`Customuse`, `LDCloud … for Roblox`) are excluded |
| psn | `Sony Entertainment Network` with roblox/robux, priced | $0 `Roblox (Demo)`, `(Game)` and free add-ons are excluded (143k rows). Starts 2023, which is Roblox's PS launch |
| ms_xbox / ms_other | `Microsoft store` robux with or without "xbox" | `… Robux for Xbox` is console. Bare `400 Robux` / `Premium 450 Robux` is likely the Windows app, so it is shown as "any MS Store" and as a strict variant |
| other_app | Amazon (Appstore `Premium 450 Robux`), Samsung (Galaxy Store), Meta (Quest) | Counted as mobile |
| gift_card (separate) | Any retailer with gift/eGift/VGC/game card/digital code text, `CashStar` "Roblox Gift", Walmart "Robux for Xbox" codes | Purchase of a code; the redeemer is unknown |
| gc_redeem (separate) | `Roblox` "Roblox Credit Redemption" | Only from Aug 2025 |

Paid transactions (distinct order_id) by month. All mailboxes; Oct 2026 runs through 27 Oct:

| Month | direct | apple | google_play | other_app | psn | ms_xbox | ms_other | gift_card | gc_redeem |
|---|---|---|---|---|---|---|---|---|---|
| 2025-01 | 2,134 | 36,548 | 29,001 | 1,558 | 5,661 | 5,233 | 1,633 | 3,807 | 0 |
| 2025-03 | 1,940 | 27,922 | 26,218 | 1,402 | 5,148 | 4,147 | 1,446 | 3,335 | 0 |
| 2025-05 | 2,123 | 29,315 | 25,812 | 1,266 | 6,106 | 4,660 | 1,554 | 3,090 | 0 |
| 2025-07 | 3,250 | 49,458 | 39,172 | 2,381 | 9,461 | 7,139 | 2,790 | 4,615 | 0 |
| 2025-09 | 2,757 | 34,970 | 26,226 | 1,998 | 5,485 | 4,027 | 1,437 | 3,608 | 136 |
| 2025-10 | 2,834 | 33,008 | 25,446 | 1,730 | 5,105 | 3,547 | 1,294 | 3,709 | 161 |
| **2025-11** | **37,110** | 28,863 | 22,128 | 2,038 | 4,934 | 3,837 | 1,330 | 4,068 | 163 |
| 2025-12 | 52,718 | 30,014 | 23,094 | 2,169 | 7,137 | 5,147 | 1,703 | 8,172 | 552 |
| 2026-01 | 47,886 | 27,671 | 20,333 | 2,194 | 5,861 | 4,432 | 1,639 | 3,553 | 280 |
| 2026-03 | 39,411 | 18,510 | 21,125 | 1,466 | 4,871 | 3,052 | 1,147 | 3,551 | 238 |
| 2026-05 | 37,653 | 15,057 | 19,570 | 1,178 | 4,269 | 3,249 | 1,330 | 2,613 | 259 |
| 2026-07 | 46,016 | 18,761 | 21,961 | 1,447 | 4,766 | 3,842 | 2,063 | 2,771 | 243 |
| 2026-08 | 41,596 | 16,220 | 19,865 | 1,248 | 4,250 | 3,203 | 1,601 | 2,300 | 179 |
| 2026-09 | 35,684 | 13,643 | 17,295 | 940 | 4,002 | 2,675 | 1,438 | 2,017 | 164 |
| 2026-10* | 33,486 | 11,392 | 14,880 | 809 | 3,685 | 2,647 | 1,441 | 1,963 | 159 |

The full monthly series, plus mailboxes and $, is in `inv2_roblox_out/t1_*.csv`.

Coverage reads:
- **Direct has a step change in Nov 2025, from about 2.5k to 37k transactions a month (about 15x).** Before then, roblox.com receipts are barely captured. Any look-back before Nov 2025 under-counts direct payers. This mostly affects the 12m+ and all-history windows.
- **Apple falls by roughly half from 2025 to 2026, while direct rises.** This is consistent with Roblox steering iOS users to web checkout. Mobile vs direct shares are therefore not stable over time.
- PSN, Xbox and Google Play look stable. Seasonality (Jul, Dec peaks) is visible in every channel. Gift cards peak in December.

## 2. Roblox payers (6m) → % pre-ordered GTA VI

| Base / as-of | Roblox payers | GTA pre-ordered | % | Avg Roblox $ GTA vs non | Median $ |
|---|---|---|---|---|---|
| Panel, 11 Oct | 43,177 | 798 | **1.85%** | $73.95 vs $61.11 | 19.99 / 19.99 |
| All mailboxes, 11 Oct | 81,383 | 1,347 | **1.66%** | $71.81 vs $56.23 | 19.99 / 19.97 |
| Panel, 26 Oct | 43,355 | 924 | **2.13%** | $78.63 vs $61.67 | 19.99 / 19.99 |
| All mailboxes, 26 Oct | 80,958 | 1,529 | **1.89%** | $73.80 vs $56.79 | 19.99 / 19.97 |
| Panel, 11 Oct, incl. gift-card buyers | 46,016 | 829 | 1.80% | $75.38 vs $62.99 | |

Split by Roblox channel (panel; 11 Oct / 26 Oct, % pre-ordered):

| Segment | Payers (26 Oct) | 11 Oct % | 26 Oct % | Avg $ GTA vs non (26 Oct) |
|---|---|---|---|---|
| All Roblox payers | 43,355 | 1.85 | 2.13 | 79 vs 62 |
| Any console (PSN/MS) | 6,320 | 5.92 | 6.88 | 56 vs 57 |
| PSN | 3,291 | 7.69 | 8.72 | 56 vs 55 |
| MS Store / Xbox | 3,077 | 4.15 | 5.00 | 57 vs 62 |
| Any mobile (Apple/GP/other) | 21,536 | 1.17 | 1.37 | 117 vs 64 |
| Any direct | 22,592 | 1.52 | 1.75 | 124 vs 83 |
| Console only | 4,780 | 6.00 | 6.88 | 40 vs 37 |
| Mobile only | 15,326 | 0.89 | 1.00 | 45 vs 37 |
| Direct only | 16,468 | 1.37 | 1.56 | 79 vs 63 |
| Multi-channel | 6,781 | 2.26 | 2.71 | 174 vs 133 |

- The overall spend premium comes from mix. GTA pre-orderers are over-represented among multi-channel, high-spend households. Within console payers there is no spend premium.
- Spend quintiles (panel, 11 Oct): Q1–Q5 GTA rates are 1.83, 1.75, 2.00, 1.77 and 1.89%. The rate is flat.
- Window sensitivity (11 Oct, all payers, % / avg $ GTA vs non):

| Window | Panel % | Panel $ | All-mailbox % | All-mailbox $ |
|---|---|---|---|---|
| 3m | 1.83 | 56 vs 44 | 1.76 | 53 vs 41 |
| 6m | 1.85 | 74 vs 61 | 1.66 | 72 vs 56 |
| 12m | 1.78 | 103 vs 88 | 1.44 | 97 vs 78 |
| 24m | 1.76 | 131 vs 110 | 1.23 | 123 vs 92 |

## 3. GTA VI pre-orderers → % with Roblox spend (MSc basis, as of 26 Oct)

Active panel, n = 8,995 pre-orderers:

| Window | Console (PSN + any MS) | Console strict | PSN | Mobile | Direct | **Any paying channel** | Any incl. gift cards |
|---|---|---|---|---|---|---|---|
| 6m | 4.8% | 4.5% | 3.2% | 3.3% | 4.4% | **10.3%** | 10.6% |
| 12m | 7.1% | 6.6% | 4.6% | 5.1% | 5.9% | **14.0%** | 14.6% |
| 24m | 10.1% | 9.5% | 6.6% | 8.0% | 6.0% | **18.0%** | 19.0% |
| All history (2015+) | **13.8%** | 12.6% | 7.9% | 12.8% | 7.8% | **23.9%** | 25.3% |

- All mailboxes (n = 14,084) give almost the same figures: all-history console 14.1%, any 24.0%; 6m 5.4% / 10.9%.
- As of 18 Oct (MSc's console/mobile data cut), the panel shows the same: all-history 13.9% console, 24.0% any.
- Restricting to mailboxes with tenure before the window start barely changes the 6–24m figures (24m: 17.3% vs 18.0%).

## 4. Comparison and verdict

| Claim | Theirs | Ours (closest basis) | Verdict |
|---|---|---|---|
| Yipit: % of Roblox payers pre-ordered GTA VI (thru 10/11) | 1.65% | 1.66% all mailboxes / 1.85% panel (6m) | **Match** |
| Yipit: Roblox spend, GTA pre-orderers vs others | $112 vs $85 (1.32x) | 6m $72–74 vs $56–61 (1.21–1.28x); 12m $97–103 vs $78–88 | Same direction, smaller gap; level implies Yipit uses a ~12m window or a heavier-spend panel |
| MSc: % of GTA pre-purchasers with a Roblox console txn | ~13% | 13.8% all history (12.6% strict); 4.8% 6m; 7.1% 12m | **Match only on an all-history window** |
| MSc: % across all channels | ~22% | 23.9% all history; 10.3% 6m; 14.0% 12m | **Match on all history** |
| MSc: Roblox spenders with a PS/Xbox purchase | "nearly a third" | 36% current-gen console owners (68% any PS/Xbox evidence) | Match |

Why the two vendors' numbers look so different (2% vs 22%) even though both are right:
- **Direction.** Yipit divides by Roblox payers, of whom about 85% are mobile or direct and rarely console gamers. MSc divides by GTA pre-orderers, a console cohort. Both rest on the same roughly 1k overlapping households.
- **Window.** MSc's "historically" works only as a multi-year look-back. A 6m window halves it (10%). Because the Roblox–GTA overlap partly comes from households whose kids paid for Roblox years ago, "historically" overstates the current-spender headwind. For RBLX Q4 bookings, the relevant figure is the 6m one: about 10% of pre-orderers, about 2% of payers.
- **Channel coverage.** PSN Robux exists only from Oct 2023 (Roblox's PS launch). Direct roblox.com receipts are thin before Nov 2025. Both depress our long windows on console/direct, which suggests MSc's "probably understated" applies to us as well. Apple Robux receipts are bare but still say "Robux", so Apple is not the blind spot here. The blind spots are gift cards and redemptions (not linkable to a channel; adds only about 0.3–1.4pp) and kids' own accounts on a different email.
- **Household vs person.** Receipts land in the account-holder mailbox. Parents buying Robux for kids and the parent or older sibling pre-ordering GTA create "overlap" that is household-level. Both vendors carry the same bias.
- **Panel.** Yipit uses a fixed Edison panel; we use the 6_12_12 active panel. The all-mailbox base lands closer to Yipit (1.66%), while the active panel runs slightly higher (1.85%) because its mailboxes have fuller receipt coverage.
- **Cancellations/gift cards.** We exclude GTA cancellations from the pre-orderer set, and retail gift-card purchases from Roblox payers by default. Including them moves the figures by less than 1pp.

## Caveats
- Unweighted panel counts.
- `ms_other` (bare "Robux" in the MS Store) may be Windows PC rather than Xbox. The strict console figures exclude it.
- Spend excludes gift cards. iTunes amounts are item prices; Apple `order_total` is the whole email and is not used.
- For multi-item Roblox and Xsolla emails, order_total is used only when item_price is null.
- 27 Oct is partial and not used. The 26 Oct as-of date includes all GTA rows dated on or before 26 Oct.
