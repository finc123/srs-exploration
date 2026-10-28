# Inv 3: gaming-spend cohorts and GTA VI / BF6 penetration (NIQ Slice e-receipts)

Written 2026-10-27. All Snowflake queries were read-only.
- Code: `penetration/inv3_spend_cohorts.py`. Run `python inv3_spend_cohorts.py` for the full pipeline, or add `analyse` / `extras` to re-run only the tables.
- SQL: `penetration/inv3_spend_cohorts.sql`.
- Outputs are in `penetration/inv3_out/`: per-cohort CSVs, `tables.md`, `extras.md`, `dq.md`, and the per-mailbox features in `features_GTA6.parquet` and `features_BF6.parquet`.

## Setup
- **Base.** Unchanged from `gta6_penetration.py`: explicit PS5/Series X|S owners in the 6_12_12 panel who joined before pre-order open.
  - GTA VI: n = 82,830, of whom 3.92% bought by 26 Oct 2026. This reproduces the headline.
  - BF6: n = 74,347, of whom 0.46% bought by 17 Sep 2025 (L-23, the same days-to-launch as GTA today) and 4.22% by 30 Nov 2025.
- **Spend window.** The 12 months before open, [open−365d, open−2d]:
  - GTA VI: 25 Jun 2025 – 23 Jun 2026.
  - BF6: 31 Jul 2024 – 29 Jul 2025.
- **Spend definition.** `item_price × qty`, pre-tax, in USD, summed over gaming items, by channel:
  - **PSN** (`Sony Entertainment Network`) and **MS** (`Microsoft store`, gaming items only).
  - **PC**: Steam, Epic, EA/Origin, Ubisoft, Blizzard, Riot, GOG, Humble, GMG, Square Enix.
  - **Nintendo** eShop.
  - **Roblox** direct.
  - **Rockstar** store.
  - **Retail**: GameStop and Sony direct software and accessories, plus PS/Xbox-labelled items at Best Buy, Target, Walmart, Amazon and others, using the console_owners candidate rows.
  - Console hardware is excluded everywhere.
- **Derived features.**
  - Transactions: distinct paid orders.
  - Active months.
  - Recency: days from the last paid purchase to open.
  - AAA: paid full-game items priced $59–150, excluding virtual currency, add-ons and subscriptions.
  - GTA franchise signals: GTA V / Online / Shark Cards / GTA+.
  - Subscriptions: PS Plus tier, Game Pass tier, other.

## Data quality (what was found, what was done)
| Issue | Finding | Treatment |
|---|---|---|
| item_price vs order_total | PSN: 41% of orders are $0/$0 claims; paid orders have total = items or items + tax. Steam: total = items (+tax) in 95% of orders. MS: order_total null in 36% of orders | Use item_price × qty (pre-tax). Ignore order_total except for Epic |
| **Epic free-game claims** | 71% of Epic orders have order_total = 0 but carry list price. 478k rows worth $12.5M across the panel, e.g. Hogwarts Legacy at $59.99 | Set to $0. Without this, PC spend would be inflated about 3x |
| $0 claims | 41% of PSN rows are $0: PS Plus monthly games, free-to-play titles, apps (YouTube, Netflix), demos and betas. **6.6% of the GTA base have PSN/MS rows but only $0 rows** | Excluded from $. Kept as a visibility flag ("store $0 rows only" tier) |
| **Wallet top-ups and gift cards** | **Steam Wallet funds**: 397k rows, $769k in the GTA base/window (vs $3.4M of Steam item $). Steam items bought with wallet funds still appear at their price, so counting both would double count. Also Epic "Account Balance"/"Wallet Funds", "USD xx credit to Microsoft account", "Xbox Variable Load POSA Gift Card" ($0), GameStop/retail PSN, Steam and eShop gift cards, Battle.net Balance, and Roblox "Credit Redemption" (null price). **No PSN wallet-funding rows exist**: PSN items show their price whatever the payment method | All funding rows excluded, so spend is consumption-based. This understates people who top up a wallet and then spend it on things that never appear as items (Steam Market, in-game) |
| Non-gaming at gaming merchants | MS Store: Microsoft 365, Windows, Copilot and similar are **33% of MS Store $** (panel-wide, 2024–26). Sony direct sells cameras and headphones. GameStop sells protection plans and Pokémon TCG | Excluded by regex |
| Refunds and cancellations | `* Cancellation` merchants are almost all subscription-expiry or "has been cancelled" notices with null price, not refunds. MS Store Cancellation has 9.7k priced rows ($0.46M panel-wide, about 2% of MS gaming $). There are almost no explicit "refund" items (29 rows) | Gross, not netted. Treat as a ~2% upward bias on MS $ |
| Currency | 0.7% of base mailboxes have SKU prices 1.2–1.6x the SKU's modal price at a merchant: CAD storefronts (GTA VI $109.99/$139.99, V-Bucks $11.99 vs $8.99, PS Plus) | Deflated by the mailbox × merchant median price ratio (when there are at least 3 rows on SKUs with 200+ rows) |
| PSN truncated descriptions | About 40% of PSN rows lose the closing ")" ("(Virtual Currency"), until a parser change in May 2026. These are not duplicates: the rate of mixed truncated/untruncated same-day pairs (46%) matches random (45%). Same-day identical repeats are 3.9% of paid PSN rows and look like genuine repeat V-Bucks or Robux buys | No action |
| Outliers / resellers | The max gaming $ is $98k: a retail mailbox with 161 AAA titles. 31 GTA-base mailboxes have retail ≥ $5k or ≥ 30 AAA. 15 mailboxes exceed $12k, mainly PSN/MS virtual currency (e.g. $20k of V-Bucks / NBA VC). Marketplace rows (eBay, Mercari, TikTok, Whatnot) and Redbox rentals are excluded from retail | Rank-based cohorts are robust, and removing the 31 moves mean $ from 240 to 234. Use buckets or deciles, not means |
| Coverage drift | Roblox direct receipts barely exist before Q4 2025: 539 rows in Q3 2024 vs 47–67k a quarter from Q4 2025. Roblox is therefore in the GTA window but not the BF6 window. PSN rows fall in 2026 (393k in Q1 2026 vs 458k in Q4 2025) | Do not use Roblox for cross-game comparisons. Roblox is only 1% of $ |
| Tenure | 97.8% of the GTA base (90% of BF6) had a full 12 months in panel. Restricting to full-tenure mailboxes leaves the tables unchanged to ±0.1pp | No action |
| Retail prices | Walmart item_price is always null, so Walmart PS/Xbox items add transactions but $0. Target pickup orders are about 30% unpriced | Retail $ is understated. This argues for count-based measures (AAA count) alongside $ |

## Distribution (GTA VI base, 12m to 23 Jun 2026)
- **Share of the base with any spend:**
  - Any gaming $: 63.8%.
  - PSN/MS $: 42.2%. A further 6.6% have only $0 store rows, and 51.2% have no PSN/MS row in the window.
  - By channel: PSN 29.9%, MS 16.4%, PC 19.9%, Nintendo 19.3%, Retail 21.3%, Roblox 4.1%.
- **Spend among spenders (gaming $):**
  - Percentiles: p10 $30, p25 $75, **median $189**, p75 $431, p90 $845, p95 $1,275, p99 $2,820.
  - Mean is $376 among spenders and $240 across the whole base.
  - PSN/MS $ among spenders: median $169, p90 $652.
- **Mix of $:**
  - By channel: PSN 39%, PC 23%, MS 15%, Retail 12%, Nintendo 10%.
  - By category: full games 53%, virtual currency 23%, PS Plus 8%, Game Pass 3%, other subs 4%, accessories 5%.
- **The BF6 base looks almost identical:** 64.0% any $, median $200, p90 $851.
- **Stability:** across the two windows the Spearman rank correlation is **0.80**. Of mailboxes that were $1000+ in the BF6 year, 63% stay $1000+ and 89% stay $500+. Of $0 mailboxes, 78% stay $0.

## GTA VI penetration by cohort (base 3.92%; BF6 by 30 Nov 4.22% shown for comparison)
**All-channel gaming $ (12m)**
| Bucket | % of base | GTA VI pen | lift | BF6 pen (30 Nov) | BF6 pen (L-23) |
|---|---|---|---|---|---|
| $0 | 36.2 | 0.49% | 0.12 | 0.31% | 0.01% |
| $1–50 | 11.2 | 1.48% | 0.38 | 1.10% | 0.05% |
| $50–100 | 9.7 | 1.91% | 0.49 | 1.92% | 0.18% |
| $100–250 | 16.7 | 4.26% | 1.09 | 4.18% | 0.30% |
| $250–500 | 12.9 | 7.68% | 1.96 | 8.07% | 0.79% |
| $500–1000 | 8.5 | 10.68% | 2.72 | 12.73% | 1.56% |
| $1000+ | 4.8 | 16.14% | 4.12 | 18.25% | 2.83% |

Deciles of spenders (D0 = $0, 36%) rise monotonically from 1.3% (D1, ≤$30) to 14.9% (D10, ≥$845). The BF6 deciles run from 0.9% to 17.2%.

**PSN + MS Store $ (12m)**
| Bucket | % of base | GTA VI pen | lift | BF6 pen (30 Nov) |
|---|---|---|---|---|
| no store row | 51.2 | 0.58% | 0.15 | 0.39% |
| store $0 rows only | 6.6 | 1.66% | 0.42 | 0.67% |
| $1–50 | 8.0 | 3.50% | 0.89 | 2.02% |
| $50–100 | 6.4 | 4.96% | 1.27 | 3.70% |
| $100–250 | 12.5 | 7.01% | 1.79 | 6.31% |
| $250–500 | 8.8 | 10.64% | 2.71 | 11.82% |
| $500–1000 | 4.5 | 15.47% | 3.95 | 17.96% |
| $1000+ | 2.0 | 20.62% | 5.26 | 27.91% |

**Other dimensions (GTA VI pen, with % of base in brackets)**
- **Transactions (paid orders):** 0 → 0.49% (36%); 1–2 → 1.85% (17%); 3–5 → 4.2%; 6–12 → 6.4%; 13–25 → 8.5%; 26+ → 11.3% (10%).
- **Active months (of 12):** 1–2 → 2.2%; 3–5 → 5.1%; 6–9 → 8.0%; 10–12 → 10.3% (10%).
- **Recency of last paid purchase:** ≤30d → 8.6% (27%); 31–90d → 5.7%; 91–180d → 3.7%; 181–365d → 2.2%; none → 0.5%.
- **AAA full-price games:** 0 → 1.7% (71%); 1 → 5.9% (14%); 2 → 9.4% (6.5%); 3–4 → 13.2% (5.1%); 5+ → 19.2% (3.3%). BF6 shows the same shape: 1.5% → 21.2%.
- **GTA franchise:**
  - GTA+ subscriber: **25.5%** (1.3%, lift 6.5).
  - Shark Cards without GTA+: 16.9% (0.5%).
  - Other paid GTA V/Online: 12.6% (1.9%).
  - $0 GTA row or Rockstar account: 7.2%.
  - No GTA signal: 3.4% (95.5%).
  - For BF6 the GTA+ group shows 17.6% (lift 4.2). So GTA+ is partly a generic heavy-gamer marker, with roughly 1.5x of GTA-specific excess on top.
- **Subscriptions:**
  - PS Plus + Game Pass: 12.9%.
  - PS Plus Extra/Premium: 12.1% (11%).
  - PS Plus Essential: 8.6% (10%).
  - Game Pass Ultimate: 7.1%.
  - Other Game Pass tier: 4.0%.
  - Other sub only: 3.0%.
  - No paid sub: 1.3% (60%).
- **Platform:** PS5 4.3%, Xbox Series 2.4%, both 7.6%. Xbox trails PS5 in every PSN/MS $ bucket for GTA VI, e.g. 11.3% vs 16.0% at $500–1000. For BF6 Xbox matched or beat PS5. This points to a GTA-specific Xbox gap (or weaker MS Store capture), not a spend effect.
- **Prior-year spend (BF6 window) still predicts GTA VI:** $0 → 0.6%; $250–500 → 7.6%; $1000+ → 14.6%. Prior-year AAA 5+ → 17.5%. BF6 console buyers pre-ordered GTA VI at 15.5% (lift 3.9).

## Predictive power (AUC, GTA VI by 26 Oct / BF6 by 30 Nov; "visible" = has a PSN/MS row before open)
| Metric | Coverage | GTA AUC | GTA AUC (visible only) | BF6 AUC | BF6 L-23 AUC |
|---|---|---|---|---|---|
| **PSN+MS $** | 42% | **0.81** | **0.76** | **0.85** | **0.88** |
| PSN+MS+retail console $ | 52% | 0.81 | 0.76 | 0.84 | 0.88 |
| All-channel gaming $ | 64% | 0.79 | 0.74 | 0.82 | 0.85 |
| PSN/MS transactions | 42% | 0.79 | 0.73 | 0.84 | 0.86 |
| Game $ only (excl. VC, subs) | 52% | 0.78 | 0.73 | 0.79 | 0.83 |
| All transactions / active months | 64% | 0.77 | 0.71 | 0.80 | 0.82 |
| Recency | 64% | 0.75 | 0.69 | 0.78 | 0.80 |
| PSN $ alone | 30% | 0.75 | 0.71 | 0.73 | 0.75 |
| AAA count | 29% | 0.74 | 0.71 | 0.76 | 0.81 |
| Any paid sub | 40% | 0.71 | 0.65 | 0.72 | 0.74 |
| Virtual-currency $ | 32% | 0.68 | 0.64 | 0.74 | 0.79 |
| Store-visible flag alone | 71% | 0.64 | – | 0.64 | 0.65 |
| MS $ / PC $ alone | 16% / 20% | 0.58 / 0.57 | | 0.64 / 0.54 | |
| GTA engagement | 4.5% | 0.57 | 0.57 | 0.55 | 0.55 |

- Combining store $ with AAA rank adds only marginally (0.817 GTA / 0.851 BF6).
- Excluding virtual currency from gaming $ gives 0.796 (GTA). Kid-driven V-Bucks and Robux do not hurt the measure.
- PC spend has essentially no predictive value for a console title.

## Recommendation: how to define "high spenders"
1. **Primary statistic: 12-month PSN + MS Store gaming $** (pre-tax, excluding funding, non-gaming and $0 claims; CAD deflated).
   - It has the best AUC for both games (0.81 / 0.85) and still ranks well within the store-visible subset (0.76 / 0.81), so it is not only a visibility proxy.
   - It is monotonic across every bucket, and the thresholds behave the same for GTA VI and BF6.
   - **Tiers:**

   | Tier | GTA base n (%) | GTA pen | lift | % of GTA buyers | BF6 n (%) | BF6 pen | lift |
   |---|---|---|---|---|---|---|---|
   | High: store $ ≥ $500 | 5,359 (6.5%) | 17.1% | 4.35 | 28% | 5,600 (7.5%) | 21.1% | 5.0 |
   | Mid: $250–500 | 7,283 (8.8%) | 10.6% | 2.71 | 24% | 7,425 (10.0%) | 11.8% | 2.8 |
   | Light: $1–250 | 22,310 (26.9%) | 5.5% | 1.40 | 38% | 19,970 (26.9%) | 4.5% | 1.07 |
   | Store $0 rows only | 5,428 (6.6%) | 1.7% | 0.42 | 3% | 5,229 (7.0%) | 0.7% | 0.16 |
   | No store row | 42,450 (51.2%) | 0.6% | 0.15 | 8% | 36,123 (48.6%) | 0.4% | 0.09 |

   - "High spender" = store $ ≥ $250: 12,642 mailboxes (15.3%), 13.4% penetration, lift 3.4, 52% of buyers. BF6: 17.5%, 15.8%, lift 3.75.
2. **Visibility-neutral alternative: all-channel gaming $ with fixed tiers.**
   - Use this when the cohort must not be defined by the same store that records the outcome.
   - It covers 64% of the base with AUC 0.79.

   | Tier | GTA n (%) | GTA pen | lift | % buyers | BF6 pen | lift |
   |---|---|---|---|---|---|---|
   | High ≥ $500 | 11,084 (13.4%) | 12.7% | 3.23 | 43% | 14.7% | 3.49 |
   | Mid $250–500 | 10,677 (12.9%) | 7.7% | 1.96 | 25% | 8.1% | 1.91 |
   | Light $1–250 | 31,055 (37.5%) | 2.8% | 0.72 | 27% | 2.7% | 0.65 |
   | None $0 | 30,014 (36.2%) | 0.5% | 0.12 | 4.5% | 0.3% | 0.07 |
3. **Behavioural secondary flag: AAA count ≥ 2 in 12 months.**
   - Size: 12,253 (14.8%), 12.9% penetration, lift 3.28, 49% of buyers. BF6: 14.4%, 3.42.
   - It is channel-agnostic: it includes retail discs and codes, and it is not distorted by virtual-currency whales or kids' spend.
   - It reads most directly as "buys full-price releases". AAA ≥ 3 gives 8.3% of the base at 15.5% penetration.
4. **Use as overlays, not cohorts:**
   - GTA+ / Shark Cards: highest lift (6.5x), but only 1.8% of the base.
   - Subscriptions: PS Plus Extra/Premium is 12%. It adds little beyond spend.
5. **Do not use** MS $ alone, PC $ alone or Roblox $.
   - MS $ and PC $ have weak AUC.
   - Roblox is not captured before Q4 2025, so it breaks the BF6 comparison.
6. **For the GTA/BF6 comparison:**
   - Compute each game's cohort on its own 12-month pre-open window. The thresholds above hold for both, and the cohort shares are within 1–2pp.
   - Compare at matched days-to-launch. At L-23, BF6 penetration is only 0.46%, but lifts are steeper: store $1000+ is 9.9x and AAA 5+ is 8.5x. Heavy spenders pre-order earlier, so cohort lifts depend on timing.

## Biases and caveats
- **Store visibility is entangled with the outcome.**
  - 92% of GTA VI pre-orders are recorded via PSN/MS, so a mailbox with no PSN/MS row (51% of the base) can only register a retail purchase.
  - Store-$ cohorts therefore partly measure "we can see this person's console account".
  - The visible-only AUCs (0.76 / 0.81) and the all-channel tiers show that spend matters beyond visibility. Even so, the true gap between "no store row" and "high" is smaller than the 0.6% vs 17% observed.
- **Household vs person.** A mailbox is an email account, often shared by a household.
  - Virtual-currency spend (V-Bucks, Robux, NBA VC) is often a child's spend, while the GTA VI pre-order may be a parent's. Both land in the same mailbox, which inflates spend for "family" mailboxes. The VC-excluded measure performs equally well.
  - Multi-mailbox households are double-counted (`user_id` was not used).
- **Retail is under-measured.**
  - Walmart has no prices, Target pickups are partly unpriced, and Amazon descriptions are truncated.
  - In-store cash purchases are invisible.
  - Retail-heavy gamers fall into lower $ tiers than their true spend.
- **Funding exclusion.** Steam Market and in-game purchases paid from wallet balance do not appear as items, so PC spend is understated. This is immaterial for a console title.
- **Gross, not net.** Refunds and cancellations are rarely visible (MS about 2%). Ever-owned console bases include resold consoles.
- **Unweighted panel counts.** The 6_12_12 panel is NIQ's definition. Penetration levels are panel-internal, and cohort lifts transfer better than levels.
