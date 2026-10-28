# inv1: why our GTA VI / Battlefield 6 multiple (8.5x) is above Yipit (3.7x) and M Science (3.2x MWII)

Written 2026-10-27. Read-only Snowflake (`share_niq.srs.items_extended`, `mailboxes_enhanced`, `active_panel_users`) plus the existing caches.
Code: `penetration/inv1_ratio.py` (`python inv1_ratio.py pull` re-pulls; `python inv1_ratio.py` runs everything), SQL in `penetration/inv1_ratio.sql`.
Outputs: `penetration/inv1_grid.csv`, `inv1_yipit_backtest.csv`, `inv1_channel.csv`, `inv1_franchise_monthly.csv`, `inv1_volume_fixed.csv`, `inv1_titles.csv`, `inv1_title_curves.csv`. New caches are `.cache/inv1_*.parquet`.

## Bottom line
- **The gap is definitional, not a data problem.** Starting from our 8.5x and changing one step at a time reproduces Yipit's 3.7x almost exactly (3.72x):
  - **BF6 PC (about x0.5).** This is the largest factor. In this panel about half of BF6 units are PC (Steam, EA app, Epic). GTA VI has no PC SKU. Yipit divides console GTA by all-platform B6 units, then scales by B6's all-platform reported units.
  - **Panel shrink (x0.82).** Receipt-active mailboxes fell 18% between Jul 2025 and Jun 2026. Raw unit counts are not normalised for this; penetration is.
  - **Explicit-owner base (x1.05).** Requiring prior console ownership adds only 5%.
- **The channel shift is real but small, so it is not the driver.**
  - The digital share of annual-franchise console units rose by about 3–4pp a year: 87% (2024), 91% (2025), 94% (2026).
  - Per-member PSN and MS Store game-purchase rates are flat to slightly down. There is no sign that parse coverage rose in 2026.
  - The **retail-only** GTA/BF6 ratio (19x, but only n=56 BF6 units) is *higher* than the digital ratios (PSN 10.2x, MS Store 4.6x).
- **Alignment matters by up to about 1.7x.** "Same days to launch" (our default) compares 123 days of GTA pre-orders with 47 days of BF6. On the same definition the multiple is:
  - 8.5x at L-24;
  - 7.3x at the same % of the window;
  - 5.1x at the same days since open (day 47).
- **Base composition is not a factor.** The BF6 owner base is a strict subset of the GTA base. Using a fixed common cohort gives 8.7x vs 8.5x.
- **Our own multiples on M Science's basis** (raw US units, console, same days since open) are in the same range as theirs. MSc's figures are US+EU, and they say GTA is stronger in Europe.

  | Comparison | Our multiple | Panel-normalised | MSc |
  |---|---|---|---|
  | MWII pre-beta | 2.6–3.1x | 3.7–4.3x | 3.2x |
  | Hogwarts Legacy, 110 days | 8.2x | 11.7x | >13x |
  | Spider-Man 2, 110 days | 3.4x | 5.0x | >6x |

- **Recommendation.** Keep penetration of console owners as the headline (it controls for panel shrink and PC), but report it at **same days since open** as well as days to launch. Always label the comparable's platform scope. For a Yipit/MSc-comparable number, quote "GTA console units ÷ comparable all-platform units", which comes to about 3.6x B6 on our data.

## 1. Decomposition at our alignment (GTA thru 26 Oct = L-24; BF6 at L-24 = 16 Sep 2025, day 47)
| Step | Definition | GTA n | BF6 n | Multiple | Step factor |
|---|---|---|---|---|---|
| 0 | **Ours**: explicit PS5/XSX owners (active 6_12_12 panel, joined pre-open), first console base-game order, % of base | 3,247 / 82,830 | 342 / 74,347 | **8.52x** | |
| 1 | Drop ownership requirement: all active-panel members joined pre-open, % of base | 8,982 / 1.076m | 975 / 1.048m | 8.97x | x1.05 |
| 2 | Raw buyers in the current active panel (no base) | 8,982 | 1,002 | 8.96x | x1.00 |
| 3 | Raw buyers, all mailboxes (no panel-size normalisation) | 14,064 | 1,928 | 7.29x | x0.81 (panel shrink 1.218 explains it: 8.97 / 1.218 = 7.36) |
| 4 | Raw units (mailbox x merchant x date x SKU) | 14,344 | 1,968 | 7.29x | x1.00 |
| 5 | **Add BF6 PC units** (Steam, EA app/Origin, Epic, retail PC codes) | 14,344 | 3,859 | **3.72x** | x0.51 |
| | Yipit Vol. 17 (thru 10/18) | | | 3.7x | |

Other cells (full grid in `inv1_grid.csv`):
- Our base with BF6 PC added: 5.68x.
- Active-panel penetration with PC: 4.78x.
- Raw buyers, all mailboxes, with PC: 3.93x.

Survivorship: only 55% of BF6 console pre-orderers are still in the *current* active-panel snapshot, against 64% of GTA pre-orderers. The base is drawn from the same snapshot, so penetration is unaffected. Raw active-panel counts, however, carry this tilt.

## 2. Alignment sensitivity (GTA/BF6, same definition across columns)
| Definition | L-24 (ours) | Same % of window (BF6 day 59) | Yipit cut: GTA 10/18 vs BF6 77% (day 56) | Same days since open = 47 | = 30 | = 7 | GTA to date vs BF6 full window (L-1) | vs BF6 L+7 |
|---|---|---|---|---|---|---|---|---|
| Ours (owners, console, %) | **8.52** | 7.29 | 7.07 | 5.05 | 5.17 | 9.04 | 3.28 | 1.31 |
| Owners, console + BF6 PC, % | 5.68 | 4.91 | 4.74 | 3.37 | 3.54 | 6.27 | 2.05 | 0.84 |
| All mailboxes, raw units, console | 7.29 | 6.39 | 6.23 | 4.38 | 4.48 | 8.30 | 3.05 | 1.15 |
| All mailboxes, raw units, console + BF6 PC | **3.72** | 3.27 | 3.17 | 2.23 | 2.32 | 4.23 | 1.47 | 0.56 |

- BF6 was back-loaded. Of its pre-launch console buyers in the owner base, 61% came in the last 24 days: 0.46% at L-24, 1.19% at L-1.
- GTA still has its last 24 days to run. "GTA to date vs BF6 full window" (3.3x) is therefore a floor, not a like-for-like comparison.
- A 147-day window (GTA) against a 71-day window (BF6) means no single alignment is neutral:
  - Days since open favours BF6, because it is near launch at the same day count.
  - Days to launch favours GTA, because GTA has had more days of accumulation.

**Yipit back-test** (raw units, console GTA vs all-platform BF6):

| Yipit date | GTA day | Yipit | Ours, same % of window | Ours, same days to launch | Ours, same days since open | Ours, % window, console-only BF6 |
|---|---|---|---|---|---|---|
| 6/28 | 3 | 10.0x | 13.0x | n/a | 7.6x | 25.7x |
| 7/12 | 17 | 6.0x | 3.8x | n/a | 2.5x | 7.4x |
| 7/26 | 31 | 3.4x | 2.8x | n/a | 2.3x | 5.4x |
| 9/27 | 94 | 3.4x | 3.0x | 3.7x | n/a | 5.9x |
| 10/4 | 101 | 3.4x | 3.0x | 3.5x | n/a | 6.0x |
| 10/11 | 108 | 3.5x | 3.1x | 3.5x | n/a | 6.1x |
| 10/18 | 115 | 3.7x | 3.2x | 3.6x | n/a | 6.2x |

- Yipit's series is reproduced within about ±0.4x by "GTA console ÷ B6 all-platform raw units", using % of window early and days to launch late.
- The console-only BF6 variant is roughly twice Yipit throughout. **Yipit's B6 denominator includes PC.**

## 3. Channel shift (hypothesis 1)
**Per-channel GTA/BF6 multiple at L-24** (owner base, first purchase in channel; raw all-mailbox units):

| Channel | GTA pen % | BF6 pen % | Penetration multiple | GTA units | BF6 units | Unit multiple |
|---|---|---|---|---|---|---|
| PSN | 2.85 | 0.28 | 10.2x | 9,767 | 1,136 | 8.6x |
| MS Store | 0.76 | 0.16 | 4.6x | 3,502 | 776 | 4.5x |
| Retail | 0.36 | 0.02 | 18.9x | 1,075 | 56 | 19.2x |
| PC | – | 0.24 | – | 0 | 1,891 | – |

At the same % of window: PSN 8.8x, MS Store 4.1x, retail 11.5x. Retail is not lower than digital, so a shift into digital stores cannot be what inflates GTA.
- Unit mix at L-24:
  - GTA: PSN 68%, MS Store 24%, retail 7.5%.
  - BF6: PC 49%, PSN 29%, MS Store 20%, retail 1.5%.
- PS share of console units: GTA 74%, BF6 60%. BF6 skews to Xbox, which explains PS5 10.5x vs Xbox 4.9x.

**Digital share of console base-game units, annual franchises** (CoD, Madden, NBA 2K, College Football, EA FC; Jul–Nov launch season, 2026 = Jul–26 Oct):

| Franchise | 2024 | 2025 | 2026 |
|---|---|---|---|
| CoD | 84.7% | 88.4% | 96.3% |
| Madden | 82.6% | 89.4% | 92.9% |
| NBA 2K | 88.5% | 93.7% | 96.3% |
| College Football | 93.3% | 93.1% | 95.3% |
| EA FC | 93.1% | 95.9% | 94.6% |
| All (calendar year) | 87.0% | 91.0% | 94.0% |

From 2025 to 2026 the retail share fell from about 9% to about 6%. Even if the whole change went into digital, it would lift a digital-store count by only about 3–4%.

**Per-member volume, fixed cohort** (active panel, joined before 2024; Jul–Oct averages):

| Metric | 2024 | 2025 | 2026 |
|---|---|---|---|
| Receipt rows per member | 38.2 | 41.2 | 38.8 |
| % members with any PSN receipt | 4.64 | 4.22 | 3.88 |
| % with a PSN paid game ≥$20 ("(Game)") | 1.06 | 1.03 | 0.99 (incl. GTA) |
| % with any MS Store receipt | 3.56 | 3.22 | 3.06 |
| % with MS Store ≥$20 | 1.32 | 1.31 | 0.78* |
| % with Steam/EA/Epic | 3.18 | 3.51 | 3.59 |

\* The July 2026 step-down is "subscription to Xbox Game Pass / Microsoft 365 renewal" receipts disappearing from MS Store. Game SKUs are unaffected: GTA, CFB, NBA 2K and Madden all appear normally.

There is no evidence of improving PSN or MS Store coverage. If anything, PSN coverage drifts down. That would bias GTA *down*, not up.

## 4. Base effects (hypothesis 4)
| | GTA base | BF6 base |
|---|---|---|
| Size (explicit owners, active panel, joined pre-open) | 82,830 | 74,347 |
| PS5-only / XSX-only / both | 59.6 / 32.9 / 7.5% | 58.1 / 34.2 / 7.6% |
| Median console age at open | 3.5y | 2.7y |
| Console bought in prior 12m | 9.6% | 16.5% |
| Median panel tenure | 4.0y | 3.2y |

- The BF6 base is a strict subset of the GTA base: 74,347 of 82,830.
- On the common cohort, GTA is 3.99% and BF6 0.46%, which gives **8.68x** against 8.52x on the full bases.
- The 8,483 GTA-only owners (newer consoles or newer joiners) pre-order GTA at 3.29%, below the 3.99% of older owners.
- Overlap: 16% of BF6 console pre-orderers have pre-ordered GTA VI. 5.2% of GTA pre-orderers pre-ordered BF6.

## 5. Our own multiples on M Science's basis (hypothesis 5)
Method:
- Units are counted pre-launch, at the same days since the pre-order open, across all mailboxes.
- "Norm" divides each side by the receipt-active mailboxes in its open month: 2.62m for MWII (Jun 2022), 2.66m for Hogwarts (Aug 2022), 2.78m for Spider-Man 2 (Jun 2023), 1.87m for GTA (Jun 2026).
- Our data is US only. MSc's is US+EU.

| Comp | Open (from data) | Window | Console units x | Console norm x | All-platform units x | All-platform norm x | MSc |
|---|---|---|---|---|---|---|---|
| MWII | 8 Jun 2022 | day 95 (11 Sep, before the beta ramp) | 3.05 | 4.26 | 1.90 | 2.66 | |
| MWII | | day 99 (15 Sep, day before PS early-access beta) | 2.62 | 3.67 | 1.63 | 2.29 | 3.2x |
| Hogwarts Legacy | **25 Aug 2022** (not May) | first 110 days | 8.24 | 11.69 | 6.22 | 8.82 | >13x |
| Spider-Man 2 | **16 Jun 2023** (not 6 Jun) | first 110 days | 3.38 | 5.01 | 3.38 | 5.01 | >6x |
| BO6 (context) | 9 Jun 2024 | first 110 days | 2.88 | 4.05 | 1.48 | 2.08 | |
| BO7 (context) | 19 Aug 2025 | day 70 | 7.66 | 9.18 | 4.67 | 5.60 | |
| BF6 (context) | 31 Jul 2025 | day 47 / day 70 | 4.38 / 2.15 | 5.33 / 2.62 | 2.23 / 1.04 | 2.72 / 1.26 | |

Notes on the comparison titles:
- **MWII pre-orders ramp from about 13 Sep** (daily console rows: 90, 187, 356 on 13–15 Sep, then 440 on 16 Sep). The "pre-beta" cut-off is therefore sensitive by about 15%.
- MWII PC (Battle.net and Steam) is 38% of all-platform units. Battle.net appears as merchant `Blizzard Entertainment`.
- MS Store MWII rows may include some PC purchases made through the Xbox app.
- Hogwarts and Spider-Man 2 have no meaningful pre-orders before the dates shown. If MSc started Hogwarts from an earlier listing date, their >13x would be mechanically higher.
- Retail GTA excludes Walmart, which has no parsed GTA order rows. In 2022–23 Walmart was also tiny for the comps, so this is a small effect.

How our figures line up with M Science:
- MSc's 3.2x / >13x / >6x sit between our raw and panel-normalised console multiples. That is consistent with:
  - (a) some panel normalisation on their side;
  - (b) Europe adding strength, as MSc says it does.
- On GTA vs CoD comparables (MWII, BO6), our console multiple is about 2.6–3.1x raw, or 3.7–4.3x normalised.
- BF6 is the outlier comparable. It is PC-heavy (52%), Xbox-skewed and back-loaded.

## 6. Recommendation
1. **Headline: keep penetration among explicit console owners.** It is immune to the 18% panel shrink and to PC mix.
   - Add a "same days since open" column next to "same days to launch" in the artifact.
   - On BF6, quote **5.1x (day 47) to 8.5x (L-24)**, with 7.3x at the same % of window, as the honest range.
2. **For comparability with Yipit and MSc, add one external-style line:** "GTA console units ÷ comparable all-platform units".
   - On our data this is 3.2x (same % of window) to 3.7x (days to launch) vs B6, and 1.6–1.9x vs MWII pre-beta.
   - It is the right ratio only when it is multiplied by the comparable's *all-platform* reported units.
3. **Prefer CoD comparables (MWII, BO6) over BF6 for scaling.** BF6's US-panel mix (half PC, a short back-loaded window) makes it the least stable comparable. Against CoD comparables GTA runs about 3–4x on a console, panel-normalised basis.
4. Do not attribute the gap to a digital-channel shift. It is worth at most about 3–4%, and the retail-only ratio is higher, not lower.

## Caveats
- The BF6 retail count is small: 56 units at L-24. The retail ratio is noisy.
- Panel-size normalisation uses all receipt-active mailboxes. Gamer coverage may not have shrunk proportionally. The fixed-cohort PSN game rate is flat, which supports using penetration rather than raw units.
- The comparison-title regexes:
  - Exclude upgrades, bundles, points, Blackcell, guides, merch, consoles and controllers.
  - Keep cross-gen and Vault/Deluxe editions.
  - Accept prices of $35–140 or null.
  - Treat Steam, EA app, Epic, Battle.net, GMG and Humble as PC.
  - Count gross pre-orders; cancellations are not netted.
