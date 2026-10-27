# Console-owning base in NIQ Slice e-receipts (for GTA VI pre-order scaling)

Written 2026-10-27. Read-only queries. Code and cached outputs:
- `console_owners.sql`: every Snowflake query that was run.
- `console_owners_rules.py`: the description rules.
- `console_owners.py`: builds the mailbox flags and all tables.
- `console_owners_supra_pull.py`: SUPRA pull.
- CSV outputs: `console_owners_all.csv`, `console_owners_pre2020.csv`, `console_owners_by_year.csv`, `console_owners_top_descriptions.csv`, `console_owners_gta_recall.csv`.
- Cached parquet: `gta/.cache/`. The mailbox-level flags are in `mb_console_flags.parquet`.

## Bottom line
- **Recommended base: the active `6_12_12_Month_Aging` panel (1,076,109 mailboxes), using the strict explicit + inferred flag (b): 199,970 mailboxes (18.6%).**
  - Sensitivity range is 17.4% (dropping $0 PSN claims) to 23.0% (adding cross-gen and multi-platform items).
  - Explicit console purchases alone (a) cover 7.8% of the panel. This captures only about a third of known owners, so it is too narrow to use as the base.
  - Model-agnostic PlayStation/Xbox (c) covers 42.0%. That includes PS4/Xbox One-only households and light PSN app users.
- **Recall check:** among GTA VI pre-orderers, we used only evidence dated before 24 Jun 2026 and excluded the GTA row itself. On that basis, 30% had an explicit console purchase, 76% are in (b) strict, 83% in (b) with cross-gen, and 96% in (c). Within the panel the figures are 36%, 80%, 86% and 97%.
- **Pre-June-2020 joiners:** their rates within the panel are almost the same as the full panel ((b) 18.6% vs 18.6%; (a) 8.8% vs 7.8%). The extra history adds little, because the console generation launched in Nov 2020, after they joined anyway. On the "all mailboxes" denominator the cohort looks far lower, because 57.5% of pre-2020 joiners exited before PS5 launched.
- **SUPRA adds almost nothing.** There is no playstation.com, sony, xbox.com or microsoft.com domain in the SUPRA quality or non-quality header tables. The only console signal is google.com "Xbox / PlayStation App installed" and "YouTube on Xbox Live / PlayStation Network now has access to your Google account" emails, covering 4.9k mailboxes. **No SUPRA subject references a console purchase, order or registration.**

## Denominators
| Base | Mailboxes | Use |
|---|---|---|
| All `mailboxes_enhanced` | 10,747,158 | Includes 57% of mailboxes that exited before Nov 2020 or never sent receipts. Understates the base heavily; reported for completeness only |
| Receipts since PS5 launch (any `items_extended` row on or after 2020-11-12) | 5,341,620 | Mailboxes that could have shown current-gen evidence |
| **Active 6_12_12 panel** (`active_panel_users`, `active_panel='6_12_12_Month_Aging'`) | **1,076,109** | **Recommended.** This is the panel the GTA pre-order counts are measured in: 64% of GTA rows, 9,006 of 14,100 pre-orderers. Its members have long, continuous history, so recall is highest |

The join date is `mailboxes_enhanced.ENTRY_DATE`, which runs from 2011-06-01 to 2026-10-27. Flags use all item history for each mailbox, from 2015 to 2026-10-27.

## (1) All mailboxes
| Group | All mailboxes n | % | Receipts post-launch n | % | **6_12_12 panel n** | **%** |
|---|---|---|---|---|---|---|
| **(a) Explicit PS5 or Series X\|S console** | 210,628 | 1.96 | 210,491 | 3.94 | **84,164** | **7.82** |
| PS5 console | 138,323 | 1.29 | 138,247 | 2.59 | 56,704 | 5.27 |
| Xbox Series X\|S console | 88,033 | 0.82 | 87,959 | 1.65 | 33,779 | 3.14 |
| PS5 only | 122,595 | 1.14 | 122,532 | 2.29 | 50,385 | 4.68 |
| Xbox Series only | 72,305 | 0.67 | 72,244 | 1.35 | 27,460 | 2.55 |
| Both | 15,728 | 0.15 | 15,715 | 0.29 | 6,319 | 0.59 |
| **(b) Explicit + inferred (strict)** | 530,471 | 4.94 | 529,864 | 9.92 | **199,970** | **18.58** |
| PS5 (explicit or inferred) | 402,026 | 3.74 | 401,479 | 7.52 | 153,126 | 14.23 |
| Series X\|S (explicit or inferred) | 169,718 | 1.58 | 169,643 | 3.18 | 64,358 | 5.98 |
| Sensitivity: + cross-gen titles ("PS4 & PS5") | 666,299 | 6.20 | 665,551 | 12.46 | 235,137 | 21.85 |
| Sensitivity: + cross-gen + multi-platform accessories | 698,800 | 6.50 | 698,013 | 13.07 | 247,177 | 22.97 |
| Sensitivity: strict, excluding $0 PSN claims | 480,011 | 4.47 | 479,404 | 8.97 | 187,010 | 17.38 |
| **(c) Model-agnostic PlayStation or Xbox** | 1,699,331 | 15.81 | 1,545,663 | 28.94 | **452,391** | **42.04** |
| PlayStation (any gen, PSN, PS Plus) | 1,214,760 | 11.30 | 1,113,310 | 20.84 | 326,681 | 30.36 |
| Xbox (any gen, Game Pass, Live) | 852,771 | 7.93 | 781,758 | 14.64 | 248,785 | 23.12 |
| Sensitivity: excluding multi-platform accessories | 1,682,642 | 15.66 | 1,530,040 | 28.64 | 447,490 | 41.58 |
| Sensitivity: + SUPRA app-install / account-link | 1,700,965 | 15.83 | 1,547,251 | 28.97 | 452,623 | 42.06 |
| *Denominator* | *10,747,158* | | *5,341,620* | | *1,076,109* | |

## (2) Mailboxes that joined before 2020-06-01
| Group | All pre-2020 joiners n | % | Pre-2020 joiners with receipts post-launch n | % | **6_12_12 panel ∩ pre-2020 n** | **%** |
|---|---|---|---|---|---|---|
| **(a) Explicit PS5 or Series X\|S console** | 35,339 | 0.73 | 35,231 | 4.14 | **13,674** | **8.78** |
| PS5 console | 21,944 | 0.45 | 21,885 | 2.57 | 8,755 | 5.62 |
| Xbox Series X\|S console | 16,253 | 0.34 | 16,195 | 1.90 | 6,035 | 3.87 |
| PS5 only / Xbox only / both | 19,086 / 13,395 / 2,858 | | 19,036 / 13,346 / 2,849 | | 7,639 / 4,919 / 1,116 | 4.90 / 3.16 / 0.72 |
| **(b) Explicit + inferred (strict)** | 75,547 | 1.56 | 74,979 | 8.81 | **28,985** | **18.60** |
| PS5 / Series X\|S | 54,052 / 27,921 | | 53,532 / 27,862 | | 21,171 / 10,610 | 13.59 / 6.81 |
| Sensitivity: + cross-gen | 95,591 | 1.98 | 94,911 | 11.15 | 33,543 | 21.53 |
| Sensitivity: + cross-gen + multi-platform | 99,442 | 2.06 | 98,726 | 11.60 | 35,082 | 22.52 |
| Sensitivity: excluding $0 PSN claims | 70,860 | 1.47 | 70,292 | 8.26 | 27,874 | 17.89 |
| **(c) Model-agnostic** | 411,669 | 8.52 | 266,611 | 31.33 | **68,510** | **43.97** |
| PlayStation / Xbox | 277,530 / 213,946 | | 182,676 / 145,795 | | 47,439 / 40,733 | 30.45 / 26.14 |
| *Denominator* | *4,830,124* | | *850,932* | | *155,801* | |

**Pre-2020 denominator.** I'd use the panel ∩ pre-2020 base (155,801), or the post-launch-receipts base (850,932) if a larger sample is needed. The all-joiners base (4.83M) is dominated by mailboxes that left before the consoles existed.

The longer history raises explicit-console recall only slightly: 8.8% vs 7.8% in the panel. It does nothing for (b). This is because PS5 and Series X|S launched in Nov 2020, so every panel member who joined before about Nov 2021 already covers the whole console generation. The pre-2020 effect matters more for the PS4/Xbox One part of (c): 44.0% vs 42.0%. The pre-2020 panel cohort also has a lower GTA VI pre-order rate (0.66% vs 0.84%), which suggests an older skew.

## Rules
The rules are applied to `merchant_name × description`, on 1.30M distinct descriptions covering 69M candidate rows. They are then mapped back to mailboxes through `hash(description)` on 11.7M candidate rows.

The candidate pre-filter is a description match on any of `ps5 / ps 5 / ps4 / ps3 / playstation / xbox / series x / dualsense / dualshock / psvr / game pass / psn / ps plus`, plus every row from PSN (`Sony Entertainment Network`), `Microsoft store` and `Sony`. The text is uppercased and stripped of ®, ™ and `?` before matching.

Exclusions applied everywhere:
- `* Cancellation` merchants.
- Negative prices.
- A junk list: gift cards and POSA, apparel, posters, toys and LEGO, cakes, fridges, prizes and sweepstakes, warranty and protection plans, trade-ins, rentals, repairs, empty boxes, books and guides, PlayStation Vue.
- `NFL Game Pass`.

**(a) Explicit console**
- The description must contain:
  - PS5: `PS5 / PlayStation 5` (not PS4).
  - Xbox: `Xbox` plus `Series X / Series S / Series X|S`.
- It must also contain the word `CONSOLE`, or start with a bare model name priced $230–1,500. Examples: "Xbox Series X" at Microsoft Store, "Sony PlayStation 5, Digital Edition".
- Accessory words veto the match: `for PS5…`, compatible, cover, skin, stand, disc drive, Portal/remote player, SSD, drive, expansion, headset, case, charging, controller-only, and similar. The veto is overridden for `Console Bundle / Bundle with / Gaming Console` at $230 or more.
- Price must be null, $0, or $150–2,000, checked at both description and row level. Walmart prices are always null. Verizon and Fios $0 bundle consoles are kept.
- Listings that name both PS5 and Xbox Series are dropped.
- Marketplace (used) purchases are kept: eBay, Mercari, StockX, OfferUp and Facebook make up 3.8% of explicit rows.

**(b) Inferred current gen (strict)**
- The description names PS5 / PlayStation 5 / DualSense, or Xbox + Series X|S.
- It does **not** also name PS4 / PS3 / DualShock / Xbox One / 360.
- It is not a multi-platform listing that also names PC / Switch / Steam / Mac / mobile. Sony first-party DualSense / PULSE / Access items are exempt from this test.
- Also included are `ASTRO's PLAYROOM` and `Live TV on PS5 Media Player` on PSN, which are PS5-only free titles.
- Main sources:
  - PSN PS5-version SKUs: "GTA Online (PlayStation 5)", "NBA 2K24 for PS5", "Apex Legends PS5", GTA+ PS5.
  - Microsoft Store "… Xbox Series X|S" SKUs, including GTA+ Series X|S.
  - DualSense and Xbox Series X|S controllers.
  - Expansion cards.
- **Cross-gen rule:** the main count includes a title only if it is current-gen only. "PS4 & PS5", "Xbox One & Xbox Series X|S" and similar go in the sensitivity line (+3.3pp on the panel).
- **Second sensitivity:** $0 PSN items (mostly PS Plus monthly PS5 claims, which can be added from the web without owning a PS5) are dropped (−1.2pp).

**(c) Model-agnostic**
- Any PSN purchase (836,759 mailboxes; mostly free app/game "purchases" plus PS Plus).
- Any row naming PlayStation, PS2–5, DualShock/DualSense, PSVR, PSN or PS Plus.
- Any row naming Xbox (Game Pass, Live Gold, Robux for Xbox, controllers, consoles), excluding PC Game Pass / "for PC".
- Plus everything in (a) and (b).
- Microsoft Store games without "Xbox" in the title are **not** counted, because they could be PC purchases.
- Multi-platform accessories (an item naming both PlayStation and Xbox) move the result by only −0.5pp.

## Sanity checks
**Explicit console purchases by year** (distinct mailboxes buying a console, per 100k receipt-active mailboxes that year; 2026 runs through 27 Oct):

| Year | PS5 | Series X\|S | PS5 share |
|---|---|---|---|
| 2020 (Sep–Dec, launch + pre-orders) | 508 | 406 | 56% |
| 2021 | 853 | 646 | 57% |
| 2022 | 781 | 554 | 59% |
| 2023 | 748 | 452 | 62% |
| 2024 | 698 | 324 | 68% |
| 2025 | 485 | 178 | 73% |
| 2026 YTD | 238 | 81 | 75% |

- **What matches the known US trend:** launch in Nov 2020; Xbox Series falling every year from 2021; PS5's share rising steadily; a sharp hardware drop in 2025, the year of price increases.
- **Where it diverges:** the panel peaks in 2021, whereas US PS5 unit sales peaked around 2023. The likely cause is the 2020–21 shortage. Shoppers placed many drop-day orders that were later cancelled, and cancellation emails are often missing (the GTA work found the same at Walmart), so the early years are inflated.
- I did not pull external unit figures. This comparison rests on the qualitative public trend, not an SRS data source.
- Raw explicit rows by year (PS5 / XSX): 2020 30.1k / 21.0k, 2021 60.8k / 38.0k, 2022 42.4k / 25.4k, 2023 32.6k / 19.6k, 2024 28.8k / 12.9k, 2025 17.3k / 6.1k.
- Merchant mix of explicit rows: Walmart 81k, Best Buy 69k, Target 61k, GameStop 33k, Sony direct 32k, Amazon 20k, eBay 9k, Costco 8k, Microsoft Store 7k. Median price is $499 throughout, as expected.

**Top matched descriptions per rule.** The full list, 15 per rule, is in `console_owners_top_descriptions.csv`.
- **Explicit PS5:** "PlayStation®5 Console" (Sony, 11.9k mailboxes, $499.99); "Sony - PlayStation 5 Console" (Best Buy, 11.0k); "Sony PlayStation 5 Video Game Console" (Walmart, 9.5k); "PlayStation 5 Console" (Target, 8.9k).
- **Explicit Xbox:** "Microsoft - Xbox Series X 1TB Console - Black" (Best Buy, 12.8k); "Xbox Series X Console" (Target, 7.3k); "Xbox Series S 512 GB All-Digital Console" (Best Buy, 5.9k, $299.99).
- **Inferred PS5:** ASTRO's PLAYROOM (PSN, 29.8k, $0); GTA Online (PlayStation 5) (PSN, 29.4k, $9.99); Ghostrunner PS5 (PSN, 18.7k, $0); Apex Legends PS5; DualSense controllers (Amazon, GameStop, Best Buy, Target).
- **Inferred Xbox Series:** GTA+ (Xbox Series X|S) (MS Store, 7.7k); Hogwarts Legacy Xbox Series X|S (4.8k); Madden / NBA 2K "Xbox Series X|S"; Xbox Series X|S Wireless Controller (Target).
- **Cross-gen additions:** Destiny 2 PS4 & PS5 (42k, $0); DIRT 5 PS4 & PS5; Miles Morales PS4 & PS5; EA FC "Xbox One & Xbox Series X|S".
- **Model-agnostic:** PSN app "purchases" such as YouTube (239k), Prime Video, Netflix and Fortnite; Xbox Game Pass Ultimate (244k); Xbox Live Gold (140k); Robux for Xbox.

**GTA VI pre-orderer recall.** This is the % of pre-orderers already in each group. Only evidence dated before 2026-06-24 is used, and the GTA VI row itself is never counted.

| Segment | n | (a) explicit | (b) strict | (b) + cross-gen | (c) agnostic |
|---|---|---|---|---|---|
| All pre-orderers | 14,100 | 30.4% | 76.1% | 83.1% | 96.3% |
| PSN buyers (PS5 by definition) | 9,701 | 31.7% | 80.7% | 87.9% | 97.4% |
| MS Store buyers (Series X\|S by definition) | 3,438 | 25.3% | 64.5% | 72.2% | 95.8% |
| Retail buyers | 1,042 | 36.9% | 72.7% | 75.7% | 88.3% |
| 6_12_12 panel pre-orderers | 9,006 | 36.1% | 80.1% | 86.3% | 97.2% |

- Implied GTA VI pre-order rate within each panel group: (a) 4.0%, (b) 3.8%, (b) + cross-gen 3.5%, (c) 2.0%. The panel overall is 0.84%.
- Xbox recall is weaker because Microsoft Store titles rarely say "Series X|S" (most are "Title By: Publisher").

## Caveats
- **Recall is below 100% and is biased upward.** GTA VI pre-orderers are heavy gamers with active PSN/MS accounts, so their 76–80% recall in (b) overstates recall for the average console owner. A console bought before a mailbox joined, bought in store, or used without digital purchases leaves no trace. Treat (b) as a floor on true current-gen ownership in the panel.
- **The flags are ever-owned, not currently owned.** Resold and gifted consoles still count, and so do scalpers. The median mailbox has 1 explicit console row, but 2,070 mailboxes have 10 or more and the maximum is 684. Marketplace purchases are 3.8% of explicit rows. Mailbox-level counts are robust to this, but row-level counts are not.
- **The 2020–21 explicit counts include orders that were later cancelled**, because cancellation coverage is incomplete.
- **Some evidence is weak:**
  - $0 PSN PS5 claims are a weaker signal; see the sensitivity line.
  - DualSense also works on PC.
  - Some "Xbox" model-agnostic users are PC-only Game Pass Ultimate or Robux buyers. PC Game Pass itself is excluded.
- **Amazon descriptions are truncated** ("PlayStation 5 Console - Ma…"). Rules match on the prefix, so some truncated accessories may slip through or be missed.
- **Unweighted panel counts.** `mailboxes_enhanced` mixes `app 1` and `app 2` panel sources, and the 6_12_12 panel definition is NIQ's.
- **Household vs mailbox.** A household with several mailboxes counts more than once. `user_id` was not used.
- **SUPRA has no console-retailer domains.** Header subjects in the 23 quality domains carry no console purchase, order or registration emails. If SUPRA coverage of playstation.com or xbox.com is wanted, it would need to be requested from NIQ.
