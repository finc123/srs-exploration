# Perplexity e-receipt filter (`filters_receipts/perplexity.py`)

## Matched senders and patterns
| panel | channel | pattern | kind |
|---|---|---|---|
| US | apple | `iTunes`: `Perplexity - AI Search & Chat : Perplexity Pro (Monthly)`, `… Pro (Annual/Yearly)`, `… Perplexity Max (Monthly)`, `Pro for Mac`, Comet app | charge |
| US | apple | `iTunes Cancellation`: `… Perplexity Pro (1 month / 1 year)`. These rows are priced, but they are cancels and carry no end date | cancel |
| US | google_play | `Perplexity Pro/Max (Perplexity - Ask Anything) Auto-renewing subscription` ($19.99 / $199.99) | charge |
| US | google_play | `Google Play Cancellation` "… will be canceled / will end on <Mon D>". End date parsed for 85% of rows | cancel |
| US | direct | `Perplexity AI Cancellation`: "subscription has been canceled", "plan has been canceled", "Pro subscription Cancellation" | cancel |
| US | other | `Samsung`: `Perplexity Pro Monthly` | charge |
| EU | apple | `app \|\| perplexity pro (mensuel/monatlich/…)` at EUR 22 / GBP 20, annual EUR 229 / GBP 200 | charge |
| EU | google_play | Google Play, plus PayPal rows with seller `google` (Play billed via PayPal). EUR 22–23 / GBP 19.5 | charge |
| EU | stripe | `perplexity ai, inc: perplexity pro` (1 user) | charge |
| EU | other | Samsung Galaxy Store | charge |

Plans found: pro_M, pro_A, max_M (US Apple/GP; EU 1 user). Education Pro appears only as unpriced "Welcome" emails, so there are no pro_edu charges. Cadence comes from the text, with amounts as a fallback (≥100 → annual).

## Direct channel findings
- **US direct paid receipts: none.** All 116.6k `Perplexity AI` rows are unpriced "Welcome to Perplexity" emails: 82.6k sign-ups, 31.6k "Welcome to Perplexity Pro" (25.7k users), 1.0k "via Samsung Galaxy", 0.7k Max, 0.4k Enterprise and 0.4k Education. No Stripe or Link sender carries Perplexity. A direct Snowflake check for Jun–Sep 2026 found the same. These Welcome emails mix trials, partner promos (PayPal/Venmo, Xfinity, Samsung) and paid sign-ups, so they are not charges. US direct is therefore cancel-only and left out of the paid panel.
- **US direct cancels:** 23.1k rows. I excluded 11.0k "Perplexity Pro trial has ended" rows. The kept 12.0k (10.5k users) spike in Nov 2025 (917) and Sep 2026 (1,642), which matches the 12-month PayPal/Venmo promo expiring. Many are probably cancels of free promo subscriptions, not paid churn.
- **EU direct `perplexity`:** 9.6k rows from 6.7k users, all unpriced (`perplexity pro`, `… for education`), UK/FR/DE only. The median user has 1 row with 0-day span, so the emails do not recur. They spike in Sep–Oct 2025, matching promos. They are activation emails, not charges (`unpriced_confirmation`).

## Exclusions (rows)
| reason | US | EU |
|---|---|---|
| unpriced (Welcome / Apple `$20.00 /month` confirmations) | 116.2k | 6.0k + 45 |
| trial / $0 promo (Apple "1 week free trial", GP $0, Bouygues "offert 12 mois") | 1.2k | 6 + Bouygues 124 (unrelated) |
| trial-ended cancels | 11.0k | – |
| credits (500–25,000 credit packs) | 3.0k | 273 |
| enterprise | 342 | 0 |
| Fox spam flag (deleted/trash rows kept) | – | small |
| resold keys (G2A, Kinguin, Gamivo, eBay) | – | 39 |
| unrelated (books, Logitech/Udemy, courses) | 530 | 197 |

## Monthly payers (unique uids with a kept charge)
| month | US apple | US GP | US other | **US** | EU apple | EU GP | EU other | **EU** |
|---|---|---|---|---|---|---|---|---|
| 2025-01 | 334 | 56 | – | 390 | 47 | 19 | – | 66 |
| 2025-07 | 461 | 81 | – | 542 | 61 | 15 | – | 76 |
| 2026-01 | 703 | 123 | – | 826 | 74 | 23 | – | 97 |
| 2026-05 | 1,295 | 199 | 16 | 1,510 | 88 | 33 | 1 | 122 |
| 2026-09 | 1,044 | 159 | 19 | 1,222 | 84 | 31 | 5 | 120 |

US peaked in May 2026 and has declined about 19% since.

## Renewal visibility (monthly-plan payers in m seen in m+1, Mar–Aug 2026)
US: Apple 66–73%, GP 72–82%. EU: Apple 60–70%, GP 66–79%. `renews` = True for apple, google_play, paypal, stripe and other; False for direct.

## Cancellations (users, Sep 2026)
US: direct 1,642, Apple 278, GP 49. EU: none, because Fox has no Perplexity cancel emails.

## Caveats and open questions
- Web/Stripe subscribers, the main channel in the card data, are invisible in both receipt panels. The receipt panel covers app stores only. Use card data for direct.
- Direct cancels are mapped to `pro_M` (the text names Pro but not the cadence) and cannot be matched to any direct charge.
- Should "Welcome to Perplexity Pro" (US) be used as a sign-up proxy? It cannot separate paid from promo.
- The keyword prefilter is sufficient: there is no evidence of missed senders.
