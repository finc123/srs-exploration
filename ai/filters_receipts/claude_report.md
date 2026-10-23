# Claude e-receipt filter: report (2026-10-19)

`filters_receipts/claude.py` reuses the card filter's bands and its Pro-annual vs Max 20x repeat rule (25–40 days). It adds a `note` column.

## Senders and patterns
| Panel | Channel | Pattern | Plan from |
|---|---|---|---|
| US | direct | `Anthropic` / `Payment` | Exact pre-tax list price: $20, $10 promo, $100, $200, $216 |
| US | apple | `iTunes` `Claude by Anthropic : Claude Pro - Monthly (Monthly)` | Text (Pro M $19.99, Max 5x $124.99, Max 20x $249.99, Pro A $214.99) |
| US | google_play | `Claude Pro Subscription (Claude by Anthropic) …`, `Claude Max (…)` | Text, then price (Max under 8x Pro = 5x) |
| EU | direct / stripe | `anthropic` `claude pro`, `max plan - 5x/20x`; `stripe` `anthropic ireland, limited : …` | Text; `claude pro` at 6x Pro or more = annual |
| EU | apple | `claude by anthropic \|\| claude pro - monthly (mensuel)` (localised period) | Text, then price |
| EU | google_play | Play receipt, plus PayPal receipts with seller `google` | Text, then price |
| EU | paypal / other | PayPal / Klarna with seller `anthropic` or `claude` | Price only |

US `$200` payments:
- Repeat → `max20_M` (20.5k rows).
- One-off → `pro_A` (11.6k).
- Pending → 0.8k.
- The unpriced `Pro subscription` / `Max subscription` items within 3 days confirm the plan: 97% of `$200` payments next to a `Pro subscription` item are one-offs. A Max item converts 454 one-offs to Max 20x. A Pro item settles 494 pending rows as annual.

EU direct needs no collision rule, because the plan is named.

## Exclusions (rows)
**US**
- direct, non-list amount (credits, usage, prorations): 168.9k
- direct, unpriced `Pro/Max subscription` items: 107k
- list-price rows in usage bursts (3+ payments within 20 days): 27.6k
- Apple unpriced `$20.00 /month` confirmations: 16.5k
- Apple `Usage Credits`: 373
- duplicates: 1.2k

**EU**
- extra usage / credits: 49.6k
- Stripe duplicate receipts: 16.8k
- team: 742
- gifts: 134
- spam (`is_spam` only): 843
- PayPal / Klarna receipts duplicating a merchant receipt: 275
- out of band: 290

## Monthly payers (unique uids, charges)
| | US apple | US direct | US GP | **US total** | EU apple | EU direct | EU stripe | EU GP | EU PP+Klarna | **EU total** |
|---|---|---|---|---|---|---|---|---|---|---|
| 2025-01 | 310 | 3,782 | 63 | **4,149** | 53 | 495 | 0 | 18 | 0 | **566** |
| 2025-06 | 410 | 4,572 | 120 | **5,086** | 63 | 723 | 0 | 44 | 1 | **831** |
| 2025-12 | 692 | 7,518 | 256 | **8,448** | 100 | 1,807 | 0 | 82 | 4 | **1,989** |
| 2026-03 | 3,946 | 23,494 | 800 | **28,079** | 819 | 6,757 | 200 | 340 | 13 | **8,121** |
| 2026-06 | 7,259 | 36,879 | 1,535 | **45,392** | 1,855 | 12,457 | 1,833 | 917 | 45 | **17,082** |
| 2026-08 | 7,809 | 39,738 | 1,730 | **49,032** | 1,925 | 13,836 | 1,716 | 1,042 | 52 | **18,544** |
| 2026-09 | 7,546 | 40,474 | 1,722 | **49,500** | 1,998 | 12,174 | 4,151 | 997 | 47 | **19,333** |

**September 2026 by plan:**
- US direct: Pro M 31.6k, Max 5x 6.0k, Max 20x 3.1k, Pro A 0.9k.
- US Apple: Pro M 6.9k, Max 5x 524.
- EU direct + Stripe: Pro M 14.0k, Max 5x 1.9k, Max 20x 678.
- EU by country: FR 8.6k, DE 3.1k, UK 3.0k, IT 2.5k, ES 2.2k.

## Renewal visibility (July monthly payers also seen in August)
| Panel | Rates |
|---|---|
| US | direct 88%, Apple 79%, GP 84% |
| EU | direct 86%, Stripe 88%, GP 78%, Apple 69%, Klarna 77%, PayPal 56% (n=18) |

`renews` is True for every channel.

## Cancellations (US only; Fox has none for Claude)
Monthly uids, Sep 2026:
- `Anthropic Cancellation`: 3.4k Pro (`pro_M`; the cadence is not stated) and 577 Max (`unknown_M`, multiplier not stated)
- iTunes: 1.26k, plan named
- Google Play: 545; 52% have a parsed "will be canceled on" end date

## Caveats
- **EU direct falls in September (13.8k → 12.2k) while Stripe jumps (1.7k → 4.2k).** This looks like a Fox parser or sender migration. Use direct + Stripe together; the same uid rarely appears in both in the same month (21 uid-months).
- **US `Payment` has no product text.** Prorated upgrades and Pro charges with tax folded into the item are dropped. A $20 credit purchase that is not in a burst would be counted as Pro.
- **October is partial** (data runs to 2026-10-18). There are 792 pending `$200` rows.
- **EU PayPal / Klarna are small and plan comes from price only.** Klarna includes instalment and noise lines.

## Open questions
1. Should Anthropic Max cancellations be assigned 5x vs 20x from the uid's last charge? That is an engine-level join.
2. US promo $10: keep it as `pro_M` (5.4k rows)? Some may be $10 credit purchases.
3. Should EU gifts (`gift pro - N months`, 134 rows) be counted as a recipient sign-up?
