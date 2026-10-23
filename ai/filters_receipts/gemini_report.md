# Gemini (Google One AI tiers): e-receipt filter report

Receipts name the plan, so the tier comes from the text. The card filter had to infer it from the amount.

## Matched patterns
- **Google Play.**
  - US: `Google AI Pro (5 TB) (Google One) (by Google LLC) Auto-renewing subscription`.
  - EU: `google ai plus (400 gb) (google one)(di google llc)`.
  - Google One web purchases are billed through Play.
- **Apple.**
  - US: `Google Gemini : Google AI Pro (2 TB) (Monthly)`.
  - EU: `google ai plus || google ai plus (al mese)`.
  - The Gmail, Photos, Drive and NotebookLM apps sell the same plans.
- **EU PayPal** (seller `google`, product truncated, e.g. `google ai pro (2 t…`).
  - 9.5k PayPal rows duplicate a Play receipt for the same uid, plan and amount within 3 days. They are dropped.

**Tiers**

| tier | receipt names |
|---|---|
| ai_pro | AI Pro 2/5/10 TB, One AI Premium |
| ai_plus | AI Plus, AI Plus 200/400 GB |
| ai_plus_2tb | AI Plus (2 TB), plus bare "2 TB"/"Premium" from 2026-01-27 |
| ultra | AI Ultra 30 TB |
| ultra_5x | AI Ultra 20 TB |

- **Bare "2 TB" in the EU.** Play still sold it as bare "2 tb (google one)" at about 5k/month until May 2026, then renamed it "Google AI Plus (2 TB)". Counting the bare label from 2026-01-27 keeps the series continuous.
- **Cadence** comes from the period text first (`(Monthly)`, `(1 year)`, `jahrliches`…). If there is none, an amount ≥ 60 for ai_pro, ≥ 25 for ai_plus or ≥ 45 for ai_plus_2tb means annual.

## Exclusions (rows)
| reason | US | EU |
|---|---|---|
| storage-only (100/200 GB, 30 GB, 5 TB, 2 TB before 2026-01-27) | 7.48M chg + 331k cxl | 2.42M |
| `Google One` welcome emails (unpriced) | 795k | - |
| trials / $0 / unpriced | 126k | 54.9k |
| Apple unpriced confirmations (`$19.99 /month`, `free trial`) | 8.5k | in above |
| partners: Best Buy 14.5k (G1 100 GB promo), Verizon Cancellation 4.1k, Fios 488, Google Store 315, T-Mobile 118 | 19.7k | - |
| AI credits / Home add-on / DAZN false match | 1.8k | 366 |
| Klarna / PayPal 'google one' with no plan | - | 6.4k |
| grey-market keys (G2A, Driffle…) | - | 55 |
| spam flag | - | 32k |

Gemini Trust and other generic "gemini" products (pizza, Pixel phones, Tesla rims) fail the Google One/AI text match and are never returned.

## Cancels (US only; Fox has none for Google)
**Kept:** `Google One Cancellation` ("Google AI Pro plan has ended/has been canceled", "Google AI plan has ended" → unknown_M), `Google Play Cancellation` and `iTunes Cancellation`.

**Excluded:** trial endings (6.2k).

**End dates.** 60% of Play cancels state an end date ("will be canceled on Sep 30, 2026" or "will end on Sep 30" with the year inferred), and 99% of those parse.

**Plan-less Play cancels.** "Your Google One subscription … will be canceled" takes the plan of the uid's latest Google One charge in the prior 400 days:
- 141k resolve to storage (excluded).
- 68.7k have no visible charge (`no_plan_no_history`, excluded).

Kept cancels per month: about 5–6k on Play and about 200–270 on Apple.

## Monthly AI payers (unique uids, kept charges)
| month | US Play | US Apple | US total | EU Play | EU Apple | EU PayPal | EU total |
|---|---|---|---|---|---|---|---|
| 2025-01 | 4,077 | 109 | 4,186 | 476 | 10 | 0 | 486 |
| 2025-09 | 8,251 | 248 | 8,496 | 1,547 | 60 | 73 | 1,678 |
| 2026-01 | 16,214 | 765 | 16,971 | 4,906 | 419 | 245 | 5,558 |
| 2026-02 | 37,203 | 778 | 37,960 | 9,271 | 393 | 409 | 10,061 |
| 2026-09 | 51,968 | 2,174 | 54,086 | 12,879 | 721 | 562 | 14,129 |

**Sep-26 payers by tier**

| panel | ai_pro | ai_plus | ai_plus_2tb | ultra | ultra_5x |
|---|---|---|---|---|---|
| US | 17.9k | 10.4k | 25.7k | 180 | 168 |
| EU | 4.2k | 4.8k | 5.3k | 9 | 27 |

EU by country: FR 4.0k, UK 3.8k, IT 2.6k, ES 2.3k, DE 1.4k.

The Jan→Feb 2026 step is the 2 TB plan entering ai_plus_2tb. Excluding it, US AI Pro rose from 13.1k to 17.9k (Jan to Sep).

**Renewal visibility** (monthly plans, July payers also seen in August):

| channel | US | EU |
|---|---|---|
| Play | 93% | 91% |
| Apple | 78% | 77% |
| PayPal | - | 84% |

`renews=True` for all three.

## Caveats / open questions
- **History lookup.** The plan-less cancel lookup uses the latest charge. A uid that holds both storage and AI plans may be mis-assigned.
- **US Play cancels.** "has been canceled" emails (about 40%) carry no date.
- **Amounts.** EU item_price is rounded to 0.1, so amounts are approximate.
- **Possible prefilter miss.** Apple rows for the bare 2 TB plan sold through the Drive or Photos apps (e.g. `Google Drive : 2 TB (Monthly)`) contain no "google one" or "google ai" text, so RECEIPT_KEYWORDS would miss them if they exist. Not verified.
- **Unconfirmed tiers.** "Google AI Pro (5 TB) with YouTube Premium" (US ~$8.99–15.49, EU €11–13) is kept as ai_pro_M, but it may be a bundle add-on. It needs confirming.
- **Low 2025 counts.** 2025 levels are low against 2026, which is consistent with the panel backfill depth. The engine's denominator should handle this.
