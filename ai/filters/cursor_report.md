# Cursor (`cursor`) — card-panel filter report

Data runs to 2026-10-13..17, depending on the panel. No reportdate-vs-dt filter is applied: all late-reported payments are kept (user decision).

## Descriptors and regex
Matching is on the lowercased `descr` with backslashes stripped (FR writes `cursor\, ai`). Precedence: usage, then BNPL, then subscription. Rows that match none of these are dropped as unrelated.

| class | regex | omega | UK | DE | FR | ES | IT |
|---|---|---|---|---|---|---|---|
| usage (excluded) | `cursor usage\|cursor usag\b\|cursor,? (mid )?<mon>\b\|cursor mid\b` | 11.8k | 2.2k | 2.8k | 5.7k | 1.9k | 1.1k |
| subscription | `cursor,? ?ai ?power\|cursor, ai\b\|cursor, power\|cursor usa\b\|cursor\.com\|cursorcom\|httpscursor\|cursor\.so\b\|^cursor usd\b\|^cursor$\|pwp cursor\|zilch \* cursor, a` | 33.3k | 7.4k | 12.0k | 32.3k | 6.5k | 5.0k |
| bnpl (Klarna, excluded) | `klarna\s?\*\s?cursor` | 6 | 6 | 0 | 1 | 2 | 0 |

- **Usage invoices** use `CURSOR USAGE [MID] <MON>` and sometimes only `CURSOR MID JAN`. Excluding by descriptor keeps $20 usage invoices out of Pro.
- **Anysphere** appears only as US ACH credits and payroll, never as a debit.
- **Unrelated `%cursor%` merchants (dropped):**
  - Precursor (Lima petrol stations, Precursor Ventures), MedCursor, Cursorocity, Cursor Machinery (Bangkok), Osteria il Cursore.
  - Hotmart and DodoPay resellers, Cash App and Square P2P, and Monzo "cursor from … pot" transfers.
  - Totals: omega 396 rows, UK 232.
- **Included edge cases:**
  - UK bare `cursor` (931 rows, behaves like Pro), Curve `crv*`, and Privacy.com `PWP CURSOR`.
  - US `$100–109` bursts on the main descriptor. These are overage invoices (median gap 1 day) and end up `unclassified_amount`.
- **App stores:** no Google Play or Apple Cursor rows exist in any panel.

## Amount bands
**US.** Bands are list price ×[0.995, 1.15]:
- Amounts were exact list prices until May 2025. After that, sales tax shows as $21.2–21.95.
- $23.00 and $69 recur from 2026, which looks like Canadian HST.

**Europe.** Cursor bills in USD, so amounts are converted back to gross USD:
- A monthly local-per-USD rate is the median of amount/$20 over the Pro cluster (amount/$20×VAT once VAT applies).
- GBP: 0.79 (2024) → 0.82 (Jan 25) → 0.74 (Jun 25) → 0.775 (Oct 26). EUR: 0.92 → 0.97 → 0.85 → 0.90.
- Bands are list ×[0.95, 1.075], with and without VAT.
- FR uses ×[0.95, 1.13] because French banks fold FX commission into the amount: a second cluster sits 5–13% above Pro.

**VAT arrival (from the data).** Pro moved €17.1 → €20.5–21.7 in **Jan 2026** in DE, FR, ES and IT. In the UK it moved £14.9 → £18.0–18.9 in **Mar 2026**. Some payers stay at the net price after that.

**Plans and rules:**
- **pro_M:** $20.
- **proplus_M:** $60, from 2025-07.
- **Teams:** a $40 seat (×1–3) or $384/yr → `team_amount`.
- **Promo:** a one-off $10 (€10.6–11) since about Apr 2026, about half followed by $20 Pro → mapped to pro_M from 2026-03.
- **Pro annual $192 vs Ultra $200**, resolved in order:
  1. Payments dated before 2025-06-16 are pro_A.
  2. The uid's own hi-zone gaps: 20–45d → ultra_M; 300–430d → pro_A.
  3. Nearest list price. In the US, $192–199.99 → pro_A; exactly $200.00 or >$213.12 → ultra_M.
  4. Anything left is `ambiguous`: 138 US rows, mostly $204–212.

## Monthly vs annual evidence (share of same-plan gaps that are 25–35d / 300–430d)
| panel | pro_M | proplus_M | ultra_M | pro_A |
|---|---|---|---|---|
| omega | 90% (n=20.5k) | 87% | 82% | 86% annual (n=88) |
| UK | 90% | 84% | 80% | 10/11 annual |
| DE | 89% | 81% | 74% | 94% annual |
| FR | 76% | 70% | 67% | 57% annual |
| ES / IT | 84% / 82% | 78% / 82% | 72% / 82% | small n |

## Exclusions (rows)
| reason | omega | UK | DE | FR | ES | IT |
|---|---|---|---|---|---|---|
| refund | 1,318 | 282 | 559 | 1,551 | 309 | 205 |
| team_amount | 767 | 92 | 135 | 766 | 99 | 29 |
| duplicate | 851 | 101 | 30 | 1,848 | 116 | 30 |
| auth ≤$1.6 | 58 | 39 | 9 | 1,642 (FR €1 checks, Q4 25) | 10 | 2 |
| business user | – | 705 (~10%) | 0* | 0* | 0* | 0* |
| unclassified | 946 (3%) | 81 | 144 | 588 | 124 | 56 |
| ambiguous | 138 | 0 | 0 | 0 | 0 | 0 |
| **kept rows / uids** | 29,331 / 5,027 | 6,130 / 1,541 | 11,256 / 2,520 | 25,945 / 5,174 | 5,820 / 1,201 | 4,713 / 1,116 |

*The EU extracts contain only usertype C rows.

## Sanity series — monthly unique kept payers (all plans)
| month | omega | UK | DE | FR | ES | IT |
|---|---|---|---|---|---|---|
| 2024-01 | 20 | 6 | 2 | 17 | 3 | 1 |
| 2025-01 | 367 | 90 | 137 | 542 | 120 | 72 |
| 2025-07 | 976 | 248 | 390 | 1,229 | 293 | 199 |
| 2026-01 | 1,400 | 330 | 612 | 1,285 | 322 | 248 |
| 2026-04 | 1,561 | 295 | 616 | 983 | 309 | 225 |
| 2026-07 | 1,593 | 273 | 600 | 620 | **44** | 227 |
| 2026-09 | 1,851 (pro+ 327, ultra 127) | 279 | 583 | 459 | **35** | 231 |

## The X Subscription (from 2026-10-12)
- **Cursor descriptor:** in 10-12..10-17 only legacy amounts appear ($20/21.x, $60/64, $200; EU equivalents). There is nothing at $8/$30/$100 and no new descriptor.
- **New payers:** first-time legacy payers still appear (omega 37, UK 5, against about 100 and 18 per week before). That is a partial week with posting lag, so I can't call it a stop yet.
- **Whole extract:** there is no "X Subscription" descriptor anywhere. Bundle signups probably bill as `GROK XAI WWW.GROK.CO`, where $30 collides with SuperGrok.
- **Implication:** from 10-12 the Cursor series will lose gross adds by construction.

## Panel caveats
- **ES: Cursor charges masked as MCC 8299 from June 2026 (the prefilter misses these rows).**
  - **How we know:** a longitudinal check on a cohort of 235 ES uids with a kept Cursor payment in both April and May 2026 (182 Pro, 36 Pro+, 16 Ultra, 1 Pro annual). For each uid we took its Apr–May Cursor amount and billing day-of-month.
  - **What the cohort pays by month:**

    | month | Cursor-named | MCC-8299 matching their amount (±3%) and billing day (±3d) |
    |---|---|---|
    | Jan–May | 131–235 | 0–1 |
    | Jun | 142 | 41 |
    | Jul | 32 | 106 |
    | Aug | 26 | 84 |
    | Sep | 22 | 70 |

  - **Switchers:** in Jul–Sep, 112 of 235 (48%) have matching 8299 rows and no Cursor-named row. Another 33 still pay under the Cursor name, and 90 show neither (churn or panel exit; 217 of the 235 were still active in the panel in Sep).
  - **Retention check:** named plus masked retention is 62%, in line with the same cohort definition elsewhere: DE 70%, IT 71%, UK 60%, FR 57%.
  - **Cutover:** sharp. The median gap from the last Cursor-named payment to the first 8299 payment is 30 days, and first 8299 payments fall in Jun (29) and Jul (78).
  - **Amounts:** match the uid's own converted EUR Cursor amount at a ratio of 0.976–1.030 (mean 1.006, n=326), drifting with FX like Cursor does.
  - **Cadence:** 187 of 196 gaps are 25–35 days.
  - **Descriptor:** always `schools and educational services ( not elsewhere classified)`, with merchant country, postcode and processor `unknown`.
  - **Why it is noisy:** MCC 8299 is a large bucket, about 47k ES uids a month. Its €17–23.5 slice jumps from about 2.4k to about 7k uids a month from June 2026, so other merchants were masked at the same time. €21.78 alone goes from about 10 to 500 uids a month; only 32 of the 694 Jul–Sep payers at that amount are known Cursor payers, and 14 are prior Claude payers.
  - **Finding new subscribers:** a candidate rule is MCC 8299 + the Cursor Pro gross band (USD 23.5–24.9 at the month's rate) + non-round cents + not €21.78 + a second payment 25–35 days later within ±4%.
    - Non-Cursor uids that pass this rule: about 21–31 a month in Jan–Jun, before Cursor was masked, so all of these are false positives.
    - In Aug–Sep: 58–61 a month, against 55–84 confirmed cohort uids.
    - Implication: about half of the new-subscriber candidates would be false positives. Not recommended without a better signal.
  - **Decision:** ES is unchanged for now.
- **FR:** shows no masking. Lapsed Cursor payers are partly paying Anthropic/Claude instead, and the panel shrinks (the Jan cohort's active users fall 1,070 → 622).
- **US:** the omega panel ramps steeply through 2024–25, so read payer counts as an index.
- **UK:** Pro payers fell after VAT was added in March 2026.

## Open questions
1. Should Cursor access through the X Subscription be counted under grok/grok_x, or does it need its own line?
2. ES: should we add a cohort-carry rule (count 8299 payments matching a known Cursor payer's amount and day as Cursor, but no new subscribers), or truncate ES at 2026-05?
3. Should the 138 ambiguous US $204–212 rows be split pro-rata between Pro annual and Ultra?
4. Are the $10 promo months and the Canadian-HST $23 payers acceptable as pro_M?
