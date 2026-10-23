# Grok filter report (`grok` = xAI direct, `grok_x` = X Premium+)

Rules applied: refunds, amounts under 1.5 and same uid/day/amount duplicates are dropped. Fable usertype B is dropped. The reportdate-vs-dt filter is **not** applied, per the user's decision. Google Play billing is kept (`channel='google_play'`) and Apple billing is excluded.

## Descriptors (rows in the extract)
| family (regex, lowercased) | omega | uk | de | fr | es | it |
|---|---|---|---|---|---|---|
| xai web: `grok ?xai\|xai llc\|x\.ai/` | 55,170 | 5,488 | 5,600 | 10,910 | 2,970 | 2,199 |
| xai Play: `google.{0,4}grok` | 24,181 | 6 | 40 | 130 | 22 | 6 |
| X web: `x ?corp\.? ?paid\|twitter paid\|corp\.? ?paid fea…` | 29,317 | 13,969 | 9,491 | 20,926 | 7,715 | 4,213 |
| X Play: `google.{0,4}(twitter\|x corp)` | 35,730 | 38 | 62 | 114 | 18 | 1 |
| excl. `paypal *x corp` (other merchant; amounts like €11.99/23.99) | 0 | 3,043 | 5,884 | 50,719 | 771 | 880 |
| excl. ads / dev platform | 3,908 | 911 | 681 | 535 | 1,301 | 179 |
| excl. ngrok / grokio / grokker / groke | 5,858 | 2,248 | 168 | 785 | 174 | 189 |
| excl. `twitter inc` (payouts to creators) | 1,303 | 13 | 0 | 88 | 9 | 0 |

**Prefilter miss (omega, serious):** Omega masks the token "X". From 2024-06-27, `X CORP. PAID FEATURES` appears as `CORP. PAID FEATURES ABOUT. .COM TX`, which `%x corp%` does not match. A Snowflake check (MID join, panel) found **117k transactions across 7.9k masked descriptors from 2024-06-26 to 2026-10-17**. The extract has only 86 of them. `grok.py` already matches the masked forms. `keywords.py` needs `%corp. paid f%`, `%corp paid f%` and `%corp. pa 865%` added. Omega `GOOGLE TWITTER` (Play) also stops on 2025-09 (5.1k rows/qtr down to 0.6k). This is probably the same masking of a new `GOOGLE *X…` descriptor. Until the extract is re-run, **omega `grok_x` is unusable after 2024-06**.

## Amount bands
**xAI** bills round USD. US rows carry no sales tax until the X Subscription. Europe shows no added VAT: UK $30 is £22.2–23.6. European rows are converted to USD using the USD amount printed in the descriptor where present (UK, ~30% of rows), otherwise a monthly rate from the $30 cluster (UK 0.74–0.80, DE 0.85–0.96). Bands are list price to +11% (US) or ±7% (Europe).

| USD | plan | evidence |
|---|---|---|
| 30 / Play 29.99 | supergrok_M (from 2025-02) | 85% of gaps 25–35d |
| 9.90 | supergrok_M promo | sequences `9.9 9.9 9.9 30` (US) |
| 300 | heavy_M if gap 20–320d or another subscription follows within 300d; supergrok_A if gap 320–410d or before 2025-07-10; otherwise **ambiguous** | 185 monthly vs 58 annual gaps |
| 99 / Play 99.99 | heavy_M promo | `99 99 99 300` sequences |
| 3000 | heavy_A | 6 payers |
| 10 / Play 9.99 | lite_M from 2026-03-25 (Play from 2025-10) unless the same amount repeats within 20d | 91% monthly gaps |
| 100 | plus_M if monthly gap from 2026-05; lite_A if gap ~1y; otherwise ambiguous or credits | 98% monthly |
| 5, 20, 50, 4.5, 7, 16, 25… | api_credits (keep=False) | gaps <20d, several per day |

**X Corp** bills fixed local prices. EU/UK prices include VAT and were reset to round amounts in 2025-07. Exact match ±0.015 in Europe; US is list to +11% for sales tax.

| region | Premium+ M | Premium+ A |
|---|---|---|
| US web | 16 → 22 (12-21) → 40 (2025-02-18) | 168 / 229 / 395 |
| US Play | 22 → 30 (2025-01) → 50 (2025-02-18) | — |
| UK | 19.20 → 20.40 → 37.20 → **31.00 (2025-07)**; 15.50 promo (2026) | 201.60 / 375.60 / 313; 120.96 (40% off, Oct-24) |
| EU | 19.04–19.52 → 24.99–25.62 → 45.22–46.36 → **38.00 (2025-07)**; 19.00 promo | 199.92–204.96 / 260.61–267.18 / 448.63–459.94 / 377; 0.6× promo |

Basic (3/3.57–3.66/4) and Premium (8/9.52–9.76/11 Play/84/114.99) are set to `x_non_plus_tier`. Volumes: omega 42.7k, UK 9.8k, DE 6.8k, FR 15.2k, ES 5.8k, IT 3.1k. Other X amounts (creator subscriptions, Verified Orgs) go to `x_other_amount`.

**The X Subscription (from 2026-10-10)** bills on the *xAI* descriptor (`GROK XAI`), not X Corp. US amounts carry sales tax: $8 → 8.48–8.69 (plus), $15–16.7 (premium at 50% off) / $30.xx, $50–55 or $100.xx (super), $200 (ultra). Europe bills round local prices: UK £7/£13/£45/£90/£180, EUR €8/€15.50–16/€52.50/€105. Through 10-17: omega 470 payments (plus 119, premium 316, super 35), UK 35, DE 23, FR 50, IT 10, ES 2. No SpaceX or X Corp descriptor carries it.

## Exclusions and quality
- Credits on the xAI descriptor: omega 15.4k, UK 1.1k, FR 2.6k.
- Duplicates: omega 11.9k, mostly $5 credits and the same $30 paid on 2–3 cards by one uid.
- UK business users are 9% of matched payments (`business_user`). Usertype B does not appear in the other EU panels.
- Ambiguous ($300 or $100 singles, unmapped X Subscription amounts): 1–2% of grok candidates.
- FR `auth` 1.2k rows are €1.00–1.50 bank fee lines.

## Sanity: unique kept payers, 2026-09 (web / Play)
| panel | grok | of which web / Play | grok_x |
|---|---|---|---|
| omega | 5,178 | 3,210 / 2,003 | 7 (masking) |
| uk | 247 | 244 / 3 | 37 |
| de | 345 | 338 / 7 | 19 |
| fr | 506 | 499 / 7 | 26 |
| es | 175 | 172 / 3 | 13 |
| it | 146 | 146 / 0 | 7 |

Omega supergrok_M payers: 446 (2025-04), 889 (2025-07), 1,291 (2025-10), 2,261 (2026-01), 3,356 (2026-04), 4,109 (2026-07), 4,060 (2026-09). lite_M: 288 → 980 (2026-04 → 09). heavy_M: 34 → 239 → 189. FR supergrok_M: 67 (2025-04) → 395 (2026-04) → 341 (2026-09). UK/EU Premium+ is flat to slightly down (UK 25–38 per month; FR 74 in 2024-04, 26 in 2026-09).

## Breaks to flag
- Omega X web stops 2024-06-27 and omega X Play stops 2025-09. Both are masking or prefilter issues (above).
- `XAI LLC` ends 2026-03-20 and `GROK XAI` replaces it. Classification continues across the change, so this is not a break.
- Omega xAI credits jump in 2026-07 ($5/$20 ×10). These are excluded but inflate the raw counts.
- Fable data ends 10-14/15, so October is partial everywhere.

## Open questions
1. Should `keywords.py` add the masked X Corp patterns and re-extract omega? This is needed for any US X Premium+ series after 2024-06.
2. Should the X Subscription be its own provider line? Its Premium and above tiers bundle X Premium, Grok and Cursor. It is currently `grok` with `xsub_*` tiers.
3. Is $99/$99.99 Heavy-promo or Plus? Web sequences say Heavy promo, but Plus at $100 launched 2026-08.
4. Single $300 payments (about 250 in omega) are left `ambiguous` (Heavy month vs SuperGrok annual). Should they be allocated pro-rata?
5. EU Play X prices are unpriced (about 300 rows, mostly €1–4). They are left as `x_other_amount`.
