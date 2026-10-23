# Gemini (Google One AI tiers): filter report (rev 3)

## Rev 3: SKU descriptors from 2026-09-15 (supersedes the "data hole" below)
- **What happened.** From 2026-09-15 Google bills Google One under **SKU descriptors**, e.g. `GOOGLE *G1SK002M`, `GOOGLE G1AI101M 650- CA`. The old keyword prefilter missed them, which produced the apparent September "hole". There was no billing pause and no catch-up charges. `keywords.py` now includes these descriptors, and a re-extract has been requested.
- **What the codes mean** (read from amounts):

| code | plan | tier in the filter |
|---|---|---|
| AI101 | AI Pro (19.99 / 199.99) | ai_pro |
| AI102 | Ultra ($199.99) | ultra |
| AI103 | AI Plus (4.99, intro 1.29�2.99 / 49.99) | ai_plus |
| SK003 | 2TB (9.99 / 99.99) | ai_plus_2tb |
| SK008 | 19.99 / 199.99; looks like legacy AI Premium | ai_pro |
| SK001/002/004/005/006 | 10TB, 100GB, 20TB, 200GB, sub-$1 | storage |

  - The trailing `M`/`A` gives the cadence.
  - The SKU overrides the amount rules, and SKU-coded AI rows are kept even at promo amounts.
  - Truncated codes (`G1SK00`, `G1AI10`, bare `G1`) fall back to the amount rules.
- **Fable panels** mask the code as `google ttttt`. These rows are included only from 2026-09-01 to 2026-10-31, with the amount rules applied.
- **SKUs confirm the 25�40-day rule.** Among payers the rule had classed as `ai_pro_M`, the September SKU was G1AI101M for 5,037 and G1SK002A for 45 (238 were G1SK008M, legacy AI). Payers the rule had classed as storage annual mostly renewed as G1SK002A (3,431, against 342 AI).
- **New $19.99 payers with no history split about 50/50** (1,492 AI vs 1,551 100GB annual). So `pending` $19.99 one-offs without a SKU are now **excluded** (`tier='ambiguous'`, `reason='pending_19_99'`, keep=False). In the US test this covers 3.7k rows. Other pending collisions remain `pending_provisional`.
- **Back-fill.** No explicit back-fill was added. SKU-coded $19.99 rows join the same-price gap chain, so a prior one-off becomes monthly automatically when a SKU charge follows 25�40 days later.
- **Test (US, local extract + SKU pull): unique payers in Sep-26** (the pull did not exclude `AFFECTED_ACCOUNTS_092026`, so it may overstate):

| ai_pro M | ai_plus | ultra (+5x) | ai_plus_2tb |
|---|---|---|---|
| 14.3k | 8.5k | 230 | 34.6k |

  For comparison, Aug-26 is 10.1k ai_pro M, 4.9k ai_plus and 27.2k ai_plus_2tb. The sanity tables need re-running once the re-extract lands.


**What changed in rev 2 (user decisions):**
1. The 2TB-with-AI-Plus plan is now **counted** (`ai_plus_2tb_M/A`).
2. Shared prices are resolved by the **25–40-day repeat rule**, with `pending` for recent one-offs.
3. The **report-lag filter is removed**.

## Descriptors
- **Include** (case-insensitive): `GOOGLE\W*(GOOGLE\W*)?(ONE|STORAGE)`. ONE/STORAGE must end the token or run straight into a phone, URL or location fragment.
- **Exclude:** transfer memos (`TO LOAN|XFER TO|TO SHARE|DEPOSIT`).

| panel | rows | members | excluded: Play devs `ONEMT/ONESOFT…` | GEMINI TRUST crypto | Gemini-named Play apps | Workspace |
|---|---|---|---|---|---|---|
| omega | 11.70M | 680k | 35.8k | 88.5k | 95 | 70 |
| uk / de / fr / es / it | 1.63M / 0.55M / 2.17M / 1.03M / 0.85M | 172k / 65k / 258k / 125k / 87k | ≤219 | ≤157 | ≤24 | ≤12 |

The prefilter contains no `GOOGLE *CLOUD` rows. `channel='web'` for all rows, because Google One has no separate app-store descriptor.

**Can descriptors separate AI from storage at $19.99? Only partly.**
- The `GOOGLE STORAGE` → `GOOGLE ONE` change is a **time rename for every product**, not a product split.
  - $19.99 rows were 99.9% "STORAGE" up to Q2-24 and about 100% "ONE" from Q4-24.
  - Before AI existed (before 2024-02-08), the "storage" family had 40.4k annual-gap and 1.1k monthly-gap $19.99 rows.
  - From Feb-24 both families carry monthly AI rows.
- **`GOOGLE ONE AI PREMIUM`** (US Apr-24 to Mar-25: 7.5k rows, 2.6k uids; also UK/EU at £18.99/€21.99) is **AI-only**. Its $19.99 rows have monthly gaps 6,813 times and annual gaps 21 times. The filter forces it to `ai_pro`.
- No storage-only descriptor exists.

## Amount bands
- **US:** list price to +11.5% (sales tax).
- **UK/EU:** exact match ±0.01, since prices include VAT.

| tier | US | UK | EU | 
|---|---|---|---|
| ai_pro M | 19.99* | 18.99, 9.49 promo | 21.99, 10.99 promo, 6.99 promo (Nov-25 to Apr-26) |
| ai_pro A | 199.99* | 189.99* | 219.99* |
| ultra M | 249.99*, 124.99 intro, 199.99* (from 05-19) | 234.99, 119.99, 189.99* | 274.99, 139.99, 219.99* |
| ultra_5x M | 99.99* | 79.99* | 99.99* |
| ai_plus M / A | 3.99, 7.99, 4.99 / 49.99* | 3.49, 6.99, 4.49 / 44.99 | 3.99, 7.99, 4.99 / 79.99, 49.99 |
| **ai_plus_2tb M / A** (from 2026-01-27) | 9.99 / 99.99* | 7.99 / 79.99* | 9.99 / 99.99* |

\* = the price is shared with another plan.

The EU/UK AI Plus launch is visible from **Nov/Dec-25**. The US AI Plus annual price ($49.99) is inferred from a new single-payment cluster from Jun-26.

**Not mapped (open):**
- EU €5.49 recurring monthly from May-26 (~1.2–1.9k rows per panel).
- UK £4.79 and £23.99.

## Resolving shared prices (user rule)
- **Monthly:** a same-price payment by the same uid 25–40 days before or after.
- **One-off:** read as the annual plan. At $19.99 that is 100GB storage, so the row is excluded.
- **`pending_provisional`:** a one-off within 40 days of the **effective panel end**, with no prior annual renewal. It is kept, using the monthly reading.
  - Exception: where the monthly reading is storage or Ultra 5x ($49.99, $/€99.99, £79.99), pending takes the annual reading instead.
- **Ultra intro → full price** counts as monthly.
- **Legacy 20TB monthly payers** at $99.99 are storage.
- **NYE-promo one-offs** at $/€99.99 (AI Pro promo annual vs 2TB annual) stay `ambiguous`: 361 US rows, ≤65 per EU panel.
- **Effective panel end = 2026-09-13 in all panels.** Weekly volume falls to 2–9% of normal from 09-21 and only partly recovers by mid-October.
  - This is an extract hole or latency. Without this adjustment, Aug-26 monthly payers would read as one-offs.
  - The US also has a smaller dip (~0.6×) in the weeks of 07-27 and 08-03.
- **US $19.99 gaps (all periods):** 19–45d 132.7k; 329–400d 121.6k; other gaps 20k. Under the rule, 215.7k one-off rows are storage.

**Pending counts:**
- **US:** 11,555 rows / 11,286 uids (10,034 `ai_pro_M`, 720 `ai_plus_A`, 608 `ai_plus_2tb_A`, 193 `ultra_M`). About 5.6k of these are Aug-26 payers.
- **Each EU/UK panel:** 36–135 rows, mostly `ai_plus_2tb_A`.

## The 2TB step on 2026-01-27
| panel | 2TB monthly payers in the 35d before 01-27 | 2TB annual paid in the prior 365d | first `ai_plus_2tb` payment in Jan / Feb from pre-existing 2TB payers | new to 2TB, per month after |
|---|---|---|---|---|
| omega | 28,053 | 9,399 | 3,784 / 19,805 (then ~600 per month as annuals renew) | ~2.0–2.9k |
| uk | 4,763 | 777 | 619 / 3,249 | ~0.5k |
| de / fr / es / it | 1,079 / 5,374 / 2,352 / 1,380 | 861 / 1,443 / 790 / 377 | – | – |

Existing 2TB subscribers will look like a **one-off gross-add step of about 24k US payers in Jan–Feb-26**, plus a further ~9k annual payers spread over the next 12 months. Subscriber-index work should seed these as opening stock rather than as adds.

## Exclusions (candidate rows)
| panel | kept (ok + pending) | storage (one-off / 20TB) | ambiguous | dup | refund | business |
|---|---|---|---|---|---|---|
| omega | 438.1k | 215.7k | 361 | 5.1k | 3.1k | – |
| uk | 63.3k | 5 | 0 | 1.5k | 253 | 170 (B = 0.18% of all Google One rows) |
| de / fr / es / it | 27.0k / 103.2k / 48.1k / 30.3k | ≤47 | ≤65 | ≤1.9k | ≤492 | 0 |

## Sanity series: unique kept payers (Aug-26 = last month before the hole; it includes pending)
| panel | month | ai_pro M | ai_pro A | ai_plus M+A | ultra + 5x | ai_plus_2tb M+A |
|---|---|---|---|---|---|---|
| omega | 2026-01 | 8,598 | 30 | 151 | 131 | 4,402 |
| omega | 2026-07 | 9,937 | 69 | 4,536 | 167 | 27,796 |
| omega | 2026-08 | 13,097 (incl. ~3–4k pending) | 33 | 4,901 | 246 | 27,184 |
| uk | 2026-08 | 1,382 | 0 | 628 | 23 | 4,602 |
| de | 2026-08 | 972 | 2 | 866 | 22 | 876 |
| fr | 2026-08 | 2,158 | 3 | 2,254 | 29 | 4,332 |
| es | 2026-08 | 1,443 | 1 | 1,248 | 16 | 2,529 |
| it | 2026-08 | 870 | 1 | 1,165 | 13 | 1,010 |

US AI Pro monthly: 1.7k (Jan-25) → 8.6k (Jan-26) → 11.3k (May-26). Jul-26 dips to 9.9k, which coincides with the early-August data dip.

## Caveats
- **US half-price AI Pro promo** at $9.99 is the same price as 2TB, so promo months are either lost (before 2026) or counted as `ai_plus_2tb`.
- **One-month AI Pro subscribers at $19.99** are now excluded as storage, which understates gross adds and churn. This is the user's rule; before AI existed, isolated $19.99 payments ran at about 2.4k per quarter, versus 3.5–5.3k per quarter in 2025–26.
- **Fable:** with the lag filter removed, UK/FR/ES gain 13–17% of rows. FR/DE panel depth steps up in Nov-24 and Feb-25.

## Open questions
1. What are EU €5.49 and UK £4.79 / £23.99?
2. Should the subscriber index treat existing 2TB holders on 2026-01-27 as opening stock?
3. Should the earlier EU/UK AI Plus launch be fed back into `plans/gemini_prices.csv`?
