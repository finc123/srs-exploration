# Perplexity filter report (`filters/perplexity.py`)

Panels: omega (US), uk/de/fr/es/it. Amounts are classified on a USD-equivalent (`usd_eq`) using monthly GBP/EUR rates embedded in the module. GBP rates come from the "usd X vrate R" text in UK descriptors; EUR rates come from the DE/FR Pro cluster.

## 1. Biggest issue: brandless descriptors, 2026-06-08 to 2026-10-04
From about 8 June 2026, Perplexity's Stripe descriptor dropped the brand. Examples: US `PRO WWW.PERPLEXIT CA`, `MAX SAN FRANCISCO CA`, `ENT PRO …`, `CREDITS …`, `COMPUTER …`; UK `pro san francisco ca`; FR `cb pro`; ES `compra pro, san francisco, tarjeta …`. From about 5 October 2026 it reads `PERPLEXITY PRO` / `PERPLEXITY CREDITS`. The `%perplexity%` prefilter misses these rows. On the extract alone, kept payers collapse in Jul–Sep 2026 (US 1,668 → 149; DE 622 → 1).

I pulled the missed rows into the scratchpad as evidence (US 9.7k MID rows from 2026-05; Fable superset from 2026-06). `classify()` recognises them by token residual: strip bank noise, numbers and `WWW.PERPLEXIT`; what remains must be PRO/MAX/ENT PRO/CREDITS/COMPUTER. Guards: date ≥ 2026-06-01; non-round GBP/EUR amount; uid has a branded Perplexity payment (or MCC 5815/5734). Without these guards, the same forms matched 30–115 payers/month in FR/IT in Jan–May 2026, none with Perplexity history. With them, the noise is 0.
**Action: widen `keywords.py` and re-extract.** Suggested patterns: `% www.perplex%`, `pro`, `cb pro%`, `% pro san franc%`, `max san franc%`, `ent pro%`, `credits san franc%`, `computer%`. Classify filters the rest.

## 2. Descriptors and exclusions (extract + missed rows, row counts)
| reason | US | UK | DE | FR | ES | IT |
|---|---|---|---|---|---|---|
| ok | 26,781 | 3,568 | 9,186 | 9,818 | 2,199 | 2,569 |
| Computer usage credits | 2,881 | 436 | 898 | 698 | 243 | 234 |
| API/credits (descr + $5/$10 top-ups) | 1,268 | 332 | 441 | 12,601* | 154 | 238 |
| Enterprise (ENT descr + $40/$325 multiples) | 942 | 138 | 319 | 244 | 101 | 50 |
| refunds | 224 | 624 | 435 | 831 | 100 | 122 |
| duplicates (uid+day+amount) | 872 | 153 | 185 | 815 | 115 | 49 |
| unmatched amount | 1,825 | 258 | 343 | 1,085 | 113 | 103 |
| business users | – | 578 (14% of matched) | 0 | 0 | 0 | 0 |

*FR bare `api` is another merchant. Other exclusions:
- Collisions removed by regex: Tour Perplexity Games, HighPerplexity, Perplexity Supply/PROSHOP (merch), PerplexAI Limassol (from Aug 2026, round EUR top-ups, zero overlap with Perplexity payers), payroll/ACH credits.
- Samsung Galaxy Store: 105 US rows, excluded.
- Google Play is kept (`channel='google_play'`): US Sep-2026 payers are 139 Play vs 1,618 web. EU Play is about 0.
- Ambiguous $200: 23 US rows, all in the last 75 days of data.

## 3. Amount bands (usd_eq)
| plan | list | US band | EU/UK band |
|---|---|---|---|
| pro_M | $20 ($10 promo months) | 19.70–22.30 | ×1.0 or ×(1+VAT), −8%/+10% |
| pro_disc_M | $4.99 | 4.92–5.56 | same rule |
| pro_A / max_M | $200 | 197–223 | same rule |
| max_A | $2,000 | 1,970–2,230 | same rule |

**VAT.** EU charges move from $20 to $20+VAT in Aug 2024 (DE €18.5 → €21.5). UK moves from $20 to $24 in Oct 2025 (£14.9 → £18.0); descriptors confirm "usd 20.00" switching to "usd 24.00". There is no sign of a $204 annual price.

**$4.99 tier.**
- In the US it is recurring monthly: 737 of 772 gaps fall in 25–35 days.
- It is billed under the "Pro" product (`PERPLEXITY PRO` at $4.99).
- Exact $5.00 is credits: 0–7 day gaps.
- There is a Nov-2024 one-month cohort and a 2026Q1 multi-month cohort.

## 4. Monthly vs annual evidence (gap between same-plan payments, days)
| | 0–20 | 27–33 | 330–400 |
|---|---|---|---|
| US pro_M | 688 | 16,425 | 16 |
| US pro_A | 20 | 0 | 135 |
| US max_M | 16 | 285 | 0 |
| DE pro_A | 5 | 0 | 42 |

**How $200 charges are resolved after 2025-07-02:**
1. The descriptor word (MAX/PRO) decides first.
2. Otherwise the uid's gaps: 24–45 days = max_M, 330–400 days = pro_A.
3. Otherwise no repeat within 75 days = pro_A.

Result: US 560 pro_A vs 477 max_M rows.

## 5. Sanity series: unique kept payers by month (all plans, extract + missed)
| | US | UK | DE | FR | ES | IT |
|---|---|---|---|---|---|---|
| 2024-01 | 66 | 17 | 15 | 28 | 11 | 9 |
| 2024-07 | 227 | 41 | 87 | 164 | 20 | 18 |
| 2025-01 | 409 | 83 | 139 | 288 | 35 | 37 |
| 2025-07 | 741 | 115 | 246 | 321 | 63 | 52 |
| 2026-01 | 1,122 | 151 | 327 | 356 | 89 | 132 |
| 2026-05 | 1,672 | 233 | 622 | 495 | 144 | 185 |
| 2026-07 | 1,502 | 168 | 659 | 303 | 95 | 165 |
| 2026-09 | 1,755 | 117 | 705 | 257 | 79 | 232 |
| 2026-10 (partial) | 988 | 77 | 335 | 156 | 39 | 84 |

Plan mix, Sep 2026: US pro_M 1,521 / pro_disc 157 / max_M 59 / pro_A 30; DE 486 / 185 / 20 / 15. Annual payers appear only in their payment month.

## 6. Partner-promo conversion waves (first-ever kept payment, vs ~2025H2 baseline)
- **DE:** Jan–Mar 2026 = 128 / 170 / 219, against a baseline of about 55. About half are discounted ($4.99 or $10 + VAT). This matches the Telekom Magenta free year (from 2025-01-29) plus the 50% retention offer.
- **FR:** Mar 2026 = 190, against about 85. This matches Bouygues.
- **UK:** Jan–May 2026 = 43–77, against about 28. This matches Revolut.
- **IT:** Jan 2026 = 72, then Aug–Sep 2026 = 66–79, against about 22. The second wave matches TIM.
- **ES:** Mar 2026 = 56, against about 25. A weak match to Movistar.
- **US:** Mar–Apr 2026 = 320–400 (Xfinity tail), and **Sep 2026 = 434**. The September spike matches the PayPal/Venmo wave (redemptions from Sep 2025).

## 7. Caveats
- During Jun–Sep 2026, EU/UK new payers with no branded history are rejected. Gross adds in that window are understated unless the payer is still paying in October.
- Existing UK/FR/ES subscribers fall 40–50% from May to Sep 2026. Lost UK/FR users show no Perplexity-like charges, so this looks like real churn, but it is unconfirmed.
- FR bank data shows `cb pro` with MCC 5411, so the MCC cannot be used to filter there.
- US Oct 2026 is a partial month (data runs to about Oct 17).

## 8. Open questions
1. Widen the prefilter as in section 1?
2. Should Samsung Galaxy Store billing be kept?
3. Should the $4.99 and sustained-$10 users stay a separate `pro_disc` tier, or merge into `pro`?
4. Should "Computer" usage be excluded as usage-based (current treatment)?
