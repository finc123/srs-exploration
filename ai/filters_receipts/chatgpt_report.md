# ChatGPT e-receipt filter (filters_receipts/chatgpt.py)

## Matched senders / patterns
| Panel | Channel | Charges | Cancels |
|---|---|---|---|
| US | apple | iTunes `chatgpt : chatgpt <plan> (monthly/annual)`, `chatgpt : chatgpt pro 5x/100` | `iTunes Cancellation` `chatgpt chatgpt <plan> (1 month/1 year)` |
| US | google_play | `chatgpt <plan> (chatgpt) auto-renewing subscription` | `Google Play Cancellation` "...subscription from OpenAI (OpCo), LLC ... will be canceled on <date>" / "chatgpt (chatgpt plus) ... will end on <date>" |
| US | direct | `Chat GPT` `chatgpt <plan> subscription` (sign-up only, renews=False) | `Chat GPT Cancellation` `chatgpt <plan> subscription/plan cancellation` |
| EU | apple | `chatgpt \|\| chatgpt <plan> (<period, local language>)`, bare `chatgpt` (parser change from Jun 2026, plan by amount) | Apple rows with a tail "cancellation date / date de (la) resiliation / data di annullamento / annullato il giorno / fecha de cancelacion" (end date parsed) |
| EU | google_play | `chatgpt <plan> (chatgpt)(by/de/di/von openai)`, plus PayPal payments to Google for ChatGPT | none |
| EU | paypal | seller `openai` (plan text or amount) | none |
| EU | stripe | OpenAI LLC / OpCo / Ireland `chatgpt <plan> subscription` (negligible, about 40 payers ever) | none |
| EU | direct | merchant `chatgpt` `chatgpt <plan> subscription` (sign-up only, renews=False) | `email_type='cancel'`, unpriced, plan `unknown_M` |

Plan from the text first (pro 5x/100 = pro100, pro 20x/200 = pro200, 25x/500 = pro500, bare "pro" by amount), cadence from the period word; amount bands per currency are the fallback. Plans found: go_M, plus_M, plus_A (Apple only, rare), pro100_M, pro200_M, pro500_M (US, 15 receipts).

## Exclusions (rows; US / EU)
- API prepaid "Payment" from Chat GPT (US): 83.5k. Apple credits, Codex "usage reset" and Sora: 3.5k US, about 90 EU.
- Apple unpriced confirmations (`... usd 19.99 /month`): 149k US. Apple renewal notices ("se renueva"): 172 EU.
- Business/Team: 5.8k US, 1.1k EU. Free-plan, trial-end and voided-purchase cancels: 690 US.
- Trial or zero: 630 US, 1.1k EU. Implausibly small amounts (VAT fragments): 600 US, 210 EU. Unmapped amounts (PayPal FX lines): 830 EU.
- Third-party "powered by ChatGPT" apps, resellers (G2A/Kinguin/Etsy) and "HU Openair" camping: 41k US, 10.7k EU.
- Fox spam flag: 5.6k EU. Deleted and trash rows are kept, per the coordinator's correction.
- Duplicates: 1.7k US, 5.7k EU (mostly a Google Play receipt plus a PayPal-to-Google payment on the same day).

## Monthly payers (distinct uid, kept charges)
| Month | US apple | US google_play | US direct | US total | EU apple | EU google_play | EU paypal | EU direct | EU total |
|---|---|---|---|---|---|---|---|---|---|
| 2025-01 | 12.8k | 2.0k | 3.4k | 18.2k | 3.9k | 1.3k | 51 | 1.0k | 6.3k |
| 2025-07 | 29.1k | 5.9k | 4.8k | 39.7k | 7.3k | 3.7k | 1.0k | 1.1k | 13.1k |
| 2026-01 | 39.6k | 8.3k | 5.5k | 53.3k | 9.9k | 5.2k | 2.1k | 3.7k | 20.7k |
| 2026-07 | 48.0k | 12.2k | 9.0k | 69.0k | 10.7k | 6.5k | 2.5k | 2.5k | 22.2k |
| 2026-09 | 46.1k | 14.3k | 10.1k | 70.3k | 12.6k | 6.8k | 2.7k | 2.6k | 24.6k |

October 2026 is partial. Direct counts are sign-ups only, not the stock of payers. In September 2026, Go was 17% of US payers and 38% of EU payers.

## Renewal visibility and cancels
- Same-channel payers seen paying the next month, Jul to Aug 2026: US apple 84%, google_play 89%, direct 0%. EU apple 79%, google_play 86%, paypal 87%, direct 0%.
- Cancels in September 2026: US direct 6.5k, apple 3.9k, google_play 2.4k. EU direct 2.0k and apple 70 (Apple tail rows only). There are no EU Google Play cancels.
- End dates are parsed for 84% of US Google Play cancels and for all EU Apple cancels. US iTunes and direct cancels state no date.

## Caveats
- Web subscribers in the EU appear twice: once as a direct sign-up and again as monthly PayPal payments. 57% of September PayPal payers also have a direct receipt, so the engine should count payers at uid level.
- Fox direct and PayPal amounts are often net of VAT (EUR 19.2, GBP 16.7). The plan comes from the text, so this does not affect plan assignment.
- The EU bare Apple `chatgpt` rows (from June 2026) are mapped by amount, and EUR 229 is read as pro200, not plus_A.
- A bare "pro" cancel with no price after 2026-04-09 is `unknown_M`.

## Open questions
- Should US direct cancellations (which carry the plan) be matched to Apple or Play payers who also cancel by email? Some users may get both emails.
- Should an EU PayPal or Stripe payer's direct sign-up receipt be merged into the PayPal spell?
- The RECEIPT_KEYWORDS prefilter missed no ChatGPT sender that I could see.
