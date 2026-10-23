# Claude (Anthropic) card filter: report

Revision 2 (2026-10-19), on the re-extracted Fable files: 2-month collision rule, no reportdate filter, Google Play kept. `filters/claude.py` adds a `note` column (how each plan was assigned).

## 1. Descriptors and regex
- **Candidate:** `ANTHROPIC|CLAUDE ?\.?AI\b|CLAUDEAI|CLAUDE BY|<NAME>\.AI SUBSCRI|CLAU AI PRO`. Never bare `CLAUDE`; `PHILANTHROP|MISANTHROP|ANTHROPICS\b` excluded.
- **Web:** `CLAUDE.AI SUBSCRIPTION` (to 2026-06), any `ANTHROPIC*` (from 2026-05-30), `ANTHROPIC CLAUDE`, plus truncations and Fable's masked `<NAME>`.
- **Team:** `TEAM`, `CLAUDE TE`, `CLAUDE T`.
- **Google Play:** `GOOGLE *CLAUDE BY ANTH`, `GOOGLE ANTHROPIC`. These are now kept.
- **Fees:** overdraft/NSF, FR `FRAIS…/COMMISSION CB`.
- **Bare `ANTHROPIC`** is treated as API. It becomes web at (a) an exact GBP/EUR list price or (b) a list-band amount the uid repeats 26–35 days apart.

| rows / uids | omega | uk | de | fr | es | it |
|---|---|---|---|---|---|---|
| web | 314k / 61k | 60k / 16k | 111k / 30k | 215k / 50k | 47k / 11.7k | 56k / 15.8k |
| google_play | 10k / 2,814 | 83 / 32 | 58 / 27 | 353 / 88 | 20 / 12 | 13 / 6 |
| api (excluded) | 114k / 19.6k | 19k / 4.7k | 27k / 7.9k | 64k / 14.6k | 19k / 4.1k | 16k / 3.9k |
| team (excluded) | 3,048 / 544 | 122 / 49 | 482 / 168 | 520 / 105 | 845 / 154 | 72 / 21 |

## 2. Amount bands (from the histograms)
| Plan | USD web (+tax) | GBP | EUR |
|---|---|---|---|
| pro_M | 19.99–23.00 | 14.5–19.5 | 17.0–23.9 |
| pro_M promo (from 2025) | 9.99–11.20 | 8.5–9.5 | 8.5–11.5 |
| max5_M | 99.99–111.5 | 89.5–90.5, 74.5–75.5 net | 104–113.5, 89.5–90.5 net |
| collision | 199.99–240 | 179.5–180.5, 149–151 net | 210–226, 179–181 net |
| prorated → Max 5x / 20x | 75–100 / 111.5–200 | 60–89.5 / 90.5–179.5 | 60–104 / 113.5–210 |
| **Google Play** | Pro 19.5–23, Max5 124.5–140, Pro A 200–240, Max20 249–285 | Pro 14.5–21, Max5 85–110 | Pro 16.5–24, Max5 100–135 |

What the histograms show:
- **US web:** $20 / $21 / $22 = 128k / 87k / 35k rows.
- **Prorated upgrade peaks:** $80 = 100−20, £72, €85.68.
- **FR:** the bank folds its FX fee into the charge line (€23.66 = 21.60×1.029+1.40).
- **ES:** €18 net = 6.3k rows.
- **Google Play (US):** $19.99, $124.99 and $249.99 plus tax, and about $215 annual. Play has no collision.

## 3. Monthly vs annual
- **Do descriptors separate the collision?** No. Same descriptor families and Omega merchids, no `MAX` text; mix differences track the descriptor-change date, not the plan.
- **Rule used:**
  - an in-band repeat by the same uid 25–40 days before or after → `max20_M`;
  - a one-off → `pro_A`;
  - a one-off in the last 40 days of data → `pro_A` provisional (`note=pending`, keep=True);
  - before 2025-04-09 → `pro_A`.

| collision rows | omega | uk | de | fr | es | it |
|---|---|---|---|---|---|---|
| repeat → max20_M | 8,097 | 731 | 1,271 | 2,253 | 828 | 373 |
| one-off → pro_A | 7,828 | 796 | 2,709 | 3,140 | 743 | 692 |
| **pending** (pro_A provisional) | **1,203** | **139** | **500** | **400** | **152** | **194** |

- **pro_M gaps of 26–35 days:** 90 / 90 / 89 / 83 / 86 / 86%.
- **Annual renewals:** 52% of US one-off payments from Apr–Sep 2025 renewed 330–400 days later.

## 4. Exclusions (rows)
| | omega | uk | de | fr | es | it |
|---|---|---|---|---|---|---|
| kept | 310,114 | 55,929 | 109,696 | 193,422 | 45,652 | 55,043 |
| refund | 3,597 | 1,576 | 1,916 | 3,347 | 1,706 | 959 |
| duplicate (same day, or same band ≤3d) | 11,845 | 1,115 | 622 | 18,109 | 1,089 | 233 |
| business user | – | 6,600 | 0 | 0 | 0 | 0 |
| fee / auth ≤1 | 71 / 183 | 0 / 68 | 0 / 147 | 2,181 / 3,473 | 0 / 102 | 0 / 54 |
| out of band | 1,164 (0.4%) | 86 | 180 | 1,543 (0.8%) | 128 | 35 |

## 5. Sanity series: unique kept payers per month (web + Google Play)
| | 2024-07 | 2025-01 | 2025-07 | 2026-01 | 2026-03 | 2026-06 | 2026-09 | Sep: web / GP |
|---|---|---|---|---|---|---|---|---|
| omega | 678 | 2,248 | 3,650 | 6,897 | 16,440 | 30,461 | **36,423** | 35,003 / 1,446 |
| uk | 242 | 475 | 666 | 1,148 | 2,746 | 6,076 | **6,400** | 6,389 / 11 |
| de | 209 | 474 | 849 | 1,878 | 5,144 | 12,755 | **15,614** | 15,607 / 7 |
| fr | 383 | 1,225 | 2,061 | 4,630 | 11,805 | 21,380 | **19,245** | 19,211 / 37 |
| es | 105 | 207 | 409 | 778 | 2,531 | 5,454 | **5,648** | 5,642 / 6 |
| it | 149 | 271 | 530 | 1,035 | 2,797 | 6,464 | **7,536** | 7,534 / 2 |

US September 2026 by plan: Pro M 30,986, Max 5x 3,828, Max 20x 1,307, Pro A 982 (mostly pending).

**The prefilter patch fixed the pre-June gaps.** Payers in 2025-01 before and after the patch: UK 171 → 475, ES 2 → 207, IT 0 → 271. The UK step at June 2026 is now ordinary growth (4,872 in May, 6,076 in June).

## 6. Panel caveats
- **FR falls from June to September** (21.4k → 19.2k). With the reportdate filter gone, late-reported FR rows (median lag 2 days, mean 16) now land in earlier months, so the latest FR months may still fill in.
- **ES MCC-8299 masking.** From June 2026, some ES Claude charges post as "schools and educational services" (MCC 8299, merchant unknown). These rows are not captured. See section 7.
- **FR double-posts charges** (descriptor variants, with and without the FX fee). The near-duplicate rule handles these.
- **Only the UK extract has B users** (6.6k rows excluded). DE includes about 8% Austrian users.

## 7. ES MCC-8299 test (proposal only, not implemented)
In ES, MCC 8299 / `schools and educational services%` users paying exactly **€21.78** rose from 2–10 a month (Oct-25 to Apr-26) to 208 / 529 / 517 / 456 in Jun–Sep 2026. **€108.90** tripled over the same period (about 15 → 60). UK, DE, FR and IT show no step at their own Claude prices.

Cohort test: of 2,930 Claude-named €21.78 payers in Apr–May 2026, 254 continue **only** in the 8299 bucket, 89% on the same billing day ±3. 62% of the 694 bucket users at €21.78 (Jul–Sep) also have Claude-named payments; 93% of bucket gaps are 26–35 days.

**Proposed rule:** ES, MCC 8299, that description, dt ≥ 2026-05-15, amount exactly 21.78 / 108.90 / 217.80 / 10.89, and either a same-amount repeat 26–35 days apart or a prior Claude-named payment. Treat as web Claude, de-duplicated against named rows within 3 days.

Estimated false positives about 2–5% (pre-switch base under 10 users a month against about 500, plus 32 Cursor payers). It would add about 450–500 ES payers a month (+9%).

## 8. Open questions
1. Adopt the ES MCC-8299 rule?
2. Keep the bare-`ANTHROPIC` recurrence rescue (US about 900 rows)?
3. Should pending pro_A be revisited automatically once 40 days have passed?
