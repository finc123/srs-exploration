# Cursor (`cursor`): e-receipt filter report

**Bottom line:** neither receipt panel shows a usable direct Cursor charge series. The only clean paid receipts are from Apple in-app purchases in the Cursor iOS app (from 2026-06-29). That leaves 14 US payers and up to 9 EU payers a month (2026-09). For Cursor, use the card panels (`filters/cursor.py`) as the main source.

## Where paid receipts are (and are not)
**US (NIQ items):**

| sender / pattern | rows | treatment |
|---|---|---|
| `Cursor`: `Cursor Pro plan`, `Cursor`, `Cursor Ultra[ plan]`, `plan for Cursor` | 11.7k | Never priced (item_price and ordertotal both null, 2023-08 to 2026-02). These are plan welcome/change emails, so they are dropped as `unpriced_confirmation`. |
| `Cursor`: `free plan for Cursor`, `Business`/`Team plan`, `Your Teams plan is now active` | 9.4k | `non_consumer_or_free` |
| `Cursor Cancellation`: `canceled your subscription` | 2,455 (no plan stated) | `channel_no_paid_receipts`: the direct channel has no paid receipts, so it is left out |
| iTunes `Cursor : Pro / Pro+ / Ultra (Monthly)` at $25.99 / $77.99 / $259.99 | 41 | **charge (kept)** |
| iTunes `Cursor Pro $25.99 /month` (unpriced Apple confirmation) | 26 | `unpriced_confirmation` |
| iTunes Cancellation `Cursor Pro (1 month)` | 12 | **cancel, pro_M (kept)** |

There is no Stripe, Anysphere or cursor.com paid receipt anywhere in ITEMS_LIVE. I checked this in Snowflake for 2023-01 to 2026-10, as well as the full extract. The keyword prefilter is not the cause: `%cursor%` / `%anysphere%` already catch every sender.

**EU (Fox):** the merchant name never contains "cursor". Every Cursor row comes through `seller_name = 'cursor'`.

| channel | pattern | rows | treatment |
|---|---|---|---|
| stripe | `cursor : cursor pro` (€17.9–18.3, £15.1–15.7, annual €171.6) | 35 | All but one are in 2024-07 to 2024-08, which looks like a Fox parser window, and none renew. Excluded as `stripe_parser_window`. |
| paypal | payment-direct_payment*, €17–21.7 | 16 | charge, pro_M |
| klarna (`other`) | payment-bnpl. DE line items are the USD amount (`kaufbetrag`) plus an FX line (`wechselkurs`); the EUR amount is order_total. | 69 | One row per order. FX lines, snoozes and returns are dropped. |
| apple | `cursor \|\| pro (monthly/mensuel)` £25 / €30; bare `cursor` €30 / €90 | 9 | charge (tier from text, else amount) |

**False matches excluded by pattern:**
- The Amazon "Cursor" fitness brand (treadmills), about 3.1k EU rows.
- Jak & Daxter "Precursor", Medcursor, Quick Cursor (Google Play), Cursorblade and Steam cursor packs.
- The unrelated iOS "Cursor Pro" app at $14.99 (2022–25), "Cursor AI - Assistant Guide" and Cursor Highlighter.

## Plans and bands
- **Apple:** the plan comes from the text.
- **EU paypal/klarna:** the plan comes from the amount, converted to USD at a fixed rate (EUR 0.90, GBP 0.78):
  - pro_M: $15–31.5, plus the $10 promo from 2026-03.
  - Team: $34–50, excluded.
  - proplus_M: $50–95.
  - $160–320 is pro_A before 2025-06-16 or below $199.5; otherwise ultra_M.

## Exclusions (EU)
| reason | rows |
|---|---|
| stripe parser window | 35 |
| Klarna FX lines | 21 |
| order duplicates | 9 |
| out of band | 6 |
| Klarna non-payment emails | 4 |
| small or unpriced | 3 |
| spam flag (only `order_is_spam`; deleted and trash rows are kept) | 2 |
| team | 1 |

## Monthly payers (kept charges, unique uids)
| month | US apple | EU apple | EU paypal | EU klarna |
|---|---|---|---|---|
| 2025-01 to 2026-03 | 0 | 0 | 0 | 0–1 |
| 2026-04 | 0 | 0 | 1 | 1 |
| 2026-06 | 1 | 1 | 1 | 0 |
| 2026-07 | 7 | 1 | 2 | 1 |
| 2026-08 | 11 | 3 | 2 | 3 |
| 2026-09 | 14 | 3 | 3 | 3 |
| 2026-10 (partial) | 7 | 1 | 0 | 0 |

**Renewal visibility.** In US Apple, 5 of 7 July payers were seen in August, and 5 of 11 August payers in September. EU numbers are too small to measure. `renews=True` is set for apple, paypal and klarna.

**Cancellations.** US Apple: 3 in Aug, 5 in Sep and 4 in Oct. US direct `Cursor Cancellation` peaked at 190–250 a month in Jul–Oct 2025 and has run at 46–71 a month in 2026; it is left out because there are no direct charges to anchor it. The EU has no cancellation emails.

## Caveats
- The panels capture direct Cursor billing only as unpriced US plan emails, and those stop after 2026-02. The receipt panels cannot measure Cursor web subscribers.
- The brief's "about 450 EU direct payers a month" does not reproduce in Fox: there are at most about 20 Cursor-seller uids a month. That figure most likely comes from the card panels (DE about 583, FR about 459 in 2026-09).
- Fox rows flagged deleted or trash are kept, by coordinator decision; only `order_is_spam` rows are excluded.
- The EU rows before 2026-06 were counted before this change and may now be slightly higher.

## Open questions
1. Should the US unpriced `Cursor Pro plan` / `Cursor Ultra` emails (about 3.5k uids, 2023-08 to 2026-02) be used as a sign-up signal (gross adds), even though they carry no price or renewals?
