# Grok receipts filter (`grok`, `grok_x`)

## Matched patterns
| channel | US (NIQ Slice) | EU (Fox) |
|---|---|---|
| Apple | `Grok AI : SuperGrok (Monthly)`, `Grok - AI Chat & Video : …`, `X : X Premium Plus (Monthly)` | `grok - ai assistant \|\| supergrok (mensuel)`, `x \|\| x premium plus (monthly)` |
| Google Play | `SuperGrok (Grok AI) Auto-renewing subscription`, `Premium+ (X) …` | `supergrok (grok - assistant ia)de xai`, `premium+ (x)(by x corp.)`. PayPal-funded Play (seller `google`) maps to google_play |
| Stripe / PayPal | none | Stripe `grok xai : supergrok`, `xai, llc : supergrok`, `x : x premium plus (per period)`. PayPal payee `twitter` uses price bands |
| Cancels | `iTunes Cancellation` (`Grok AI SuperGrok (1 month)`, `X X Premium Plus (Monthly) (1 month)`) and `Google Play Cancellation` (`…from X.AI CORP. / SpaceXAI LLC / Twitter Inc on Google Play will be canceled on <date>`) | none for Grok/X |

Plans come from the text first. Cadence uses Monthly / Annual / (1 month) / (1 year) and the local-language equivalents. If neither is present, the amount is compared with the tier's monthly price.

- **Plans found:** supergrok, lite, heavy (`supergrokpro` = heavy) and plus, each M/A, plus premium_plus M/A.
- **X Subscription:** in-app Play `Plus/Premium/Super (Grok)` from 2026-10-12 maps to `xsub_*` (US: 87 rows).
- **Apple `SuperGrok (3 Months)`:** this is the $30-for-3-months retention offer. It is coded `supergrok_M` with `period_months=3`.

## Exclusions (rows; US / EU)
- **X basic/premium (`x_non_plus_tier`):** charges 106,106 / 23,818; cancels 10,131 / 0.
- **Trials and $0:** 19,288 / 1,797. **Unpriced Apple confirmations** (`SuperGrok $30.00 /month`): 7,282 / 0.
- **Credits** (Grok Credits, Extra Usage Credits, xAI prepaid): 5,884 / 2,587. **`credits_or_unknown`** (`payment to grok xai` not near $30/$10, Grackle AI): 49 / 617.
- **X creator / Super Follow subs:** 3,425 / 826.
- **US `Twitter : Payment`:** 5,003 rows. These are unpriced, with ordertotal ranging from $0 to $170k (X Money and tips), so they are not counted.
- **Stripe proration** ("unused/remaining time"): 0 / 234. **Fox `is_spam`:** 467. Deleted and trash rows are kept.
- **Duplicates:** 434 / 849.
- **Not matched at all:** false hits such as ITVX, Roblox, Deezer/AccuWeather `premium+`, HelloFresh `1 x premium recipe`, ONGROK, groksi, Grok Bot, Grokio and udemy.

## Monthly unique payers (kept charges)
| month | US grok (apple / play) | US grok_x (apple / play) | EU grok (apple / play / stripe) | EU grok_x |
|---|---|---|---|---|
| 2025-01 | 0 | 488 (405 / 83) | 0 | 39 |
| 2025-07 | 924 (782 / 142) | 143 | 149 (49 / 28 / 72) | 18 |
| 2026-01 | 2,008 (1,601 / 407) | 210 | 535 (268 / 161 / 107) | 39 |
| 2026-04 | 3,318 (2,394 / 924) | 194 | 838 (391 / 265 / 184) | 24 |
| 2026-07 | 3,499 (2,510 / 989) | 200 | 894 (392 / 291 / 216) | 32 |
| 2026-09 | 3,844 (2,734 / 1,111) | 226 (178 / 48) | 846 (339 / 301 / 208) | 31 (stripe 23) |

October is partial.

**Renewal visibility** (July payers who are seen paying in August; August payers seen paying in September):

| | Apple | Play | Stripe |
|---|---|---|---|
| US grok | 64% / 69% | 70% / 57% | — |
| US grok_x | 77% / 79% | 75% / 70% | — |
| EU grok | 45% / 53% | 58% / 47% | 68% / 60% |
| EU grok_x | — | — | 86% / 62% |

The other EU grok_x channels have fewer than 10 payers. `renews=True` is set for every channel.

**Cancels** (US, unique uids per month, 2026-09): grok Apple 1,546 and Play 559; grok_x Apple 16 and Play 208. Play cancels give `end_date` in 76–86% of rows. Apple cancels never do.

## Caveats
- US direct xAI / X Corp paid receipts do not exist, so US covers Apple and Google Play only.
- The US Play cancel text "X subscription from Twitter Inc" does not name a tier. It is kept as `grok_x unknown_M` (5,589 rows), but most of these are Basic/Premium cancels.
- EU xAI Stripe receipts start in 2025-07. Earlier EU web payers are missing.
- EU grok_x is small (about 30 per month) and mostly Stripe.

## Prefilter miss
`RECEIPT_KEYWORDS` misses the X-app X Subscription sold on Play, `Plus (X) Auto-renewing subscription`. A Snowflake check found 20 rows from 2026-10-12 to 10-19. It also misses the post-launch `Premium (X)` rows (801 since 09-15, mostly the legacy Premium). To fix this, add `'% (x)%'` / `'%(x)%'`. `classify()` already maps `Plus/Super/Ultra (X)` from 2026-10-10 to `grok xsub_*`.

## Open questions
1. Should the X Subscription (`xsub_*`) stay inside `grok` or become its own line?
2. Has Play `Premium (X)` become the X Subscription Premium tier (which includes Grok) after 10-12? Prices are still $11 so far.
3. The engine has no quarterly cadence for the 3-month SuperGrok offer (kept charges: 893 US, 199 EU).
