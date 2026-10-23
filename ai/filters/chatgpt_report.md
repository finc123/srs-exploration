# ChatGPT filter: report

Filter: `filters/chatgpt.py` (`classify(df, panel)`; it adds `note`, `dclass` and `usertype` as extra columns). ChatGPT has no annual consumer plan, so every kept payment is cadence M, and the panels agree (see the gap section).

**Change (2026-10-19): the Fable `reportdate - dt <= 7` lag filter has been removed and all data is used.** The filter dropped 13% of UK rows, 20% of FR and 19% of ES. The dropped rows were spread through each uid's monthly run, so they left holes that `subs.py` would read as churn. The lagged share was also not stable over time: in FR it rose from 16% in 2023 to 26% in 2025Q2, then fell to near 0 by 2026Q4. As a result the filter also distorted the trend. All tables below are without the lag filter and use the refreshed Fable extracts.

**Change (2026-10-19, user decision): Google Play billing is now kept alongside web.** These rows have `keep=True`, `channel='google_play'` and their own price bands. Apple billing stays excluded (it is invisible). The duplicate rules (same uid+day+amount, plus repeats within 3 days and 15% of the amount) absorb the extra pending/posted repeats.

## Descriptors (upper-cased; first match wins)
| class | rule | treatment |
|---|---|---|
| not OpenAI | no `CHAT ?GPT\|OPEN ?AI(?!R)` ("OPEN AIR" markets) | dropped |
| not a merchant charge | `XFER\|TRANSFER\|FROM SHARE\|TO LOAN\|PAYROLL\|DIRECT DEP\|DEPOSIT\|REPAY` | dropped |
| sora | `SORA` (Sora by OpenAI Play app/add-ons; US 635 rows at $4/$8/$12/$20) | rejected |
| google_play | `GOOGLE.{0,4}CHAT ?GPT` (incl. PayPal-funded "GOOGLE CHATGPT") | kept, `channel=google_play`, Play bands |
| third-party app | ChatGPT-named descriptor without `OPENAI` or an OpenAI subscription pattern: Sider, Superpower ChatGPT, ChatGPT Writer, ChatGPT Premium (HK), Gumroad, CHATGPTBUILDER… | dropped |
| credits | `CHATGPT CRED\|CHATGPT CR\b` (Codex/Sora packs: 10/20/40/90/160) | rejected |
| business | `CHATGPT (FOR )?BUSINESS\|CHATGPT TEAM` (44 US rows) | rejected |
| chatgpt | `CHAT ?GPT\|OPENAI ?\* ?CH\|OPENAIOPCO\|OPENAI - OPENAI\|PAYPAL.{0,20}OPENAI` | banded |
| openai_bare | any other `OPENAI` | banded, plus a recurrence test |

Rows / uids by class:

| class | omega | uk | de | fr | es | it |
|---|---|---|---|---|---|---|
| chatgpt | 2.63M / 303k | 326k / 54k | 540k / 64k | 828k / 119k | 276k / 35k | 195k / 35k |
| openai_bare | 110k / 30k | 43k / 13k | 23k / 10k | 105k / 28k | 24k / 7k | 10k / 5k |
| google_play | 248k / 42k | 382 | 1.6k | 7.1k | 385 | 180 |

How the classes were drawn:
- **PayPal counts as ChatGPT web.** PayPal-billed OpenAI charges ("PAYPAL *OPENAI", "OPENAIOPCOL") are almost all at Plus amounts, so they are treated as web billing.
- **Team and Business have no separate descriptor.** They bill under the same descriptor as consumer plans, so they are separated by amount.
- **Bare `OPENAI` is not purely API.** In omega, Plus-band amounts on the bare descriptor grew from about 300 per quarter in 2024 to about 9k in 2026Q3, and 74% of them repeat every 27–32 days. A bare row is kept only if its amount is in a plan band **and** the same uid pays that plan 25–35 days before or after. The rest (5/10/15/11/6…) are rejected as `api_bare_openai`.

## Amount bands
Bands were set from exact-amount-by-quarter histograms and start on each plan's launch date. An in-band amount before launch is rejected as `pre_launch`.

| plan | US (USD) | UK (GBP) | EUR |
|---|---|---|---|
| go | 7.95–9.00; $4 promo | 6.90–8.10 (£8 Jan–Mar 2026, then £7) | 7.50–8.50; 6.50–6.80 ex-VAT; €4 promo |
| plus | 19.50–23.05 | 14.40–20.60 | 16.50–25.90 |
| plus 50% retention | 9.95–11.30 | 8.70–10.10 | 9.00–12.50 |
| pro100 (from 9 Apr 2026) | 99.9–111 | 85–92 (£89) | 98–106 (€103) |
| pro200 (from 5 Dec 2024) | 199.9–222.1 | 160–201 | 180–246 |
| pro500 (from 29 Sep 2026) | 499.9–555 | 440–505 | 495–520 |
| **Google Play** go | 7.99–8.95 | 6.90–8.10 | 7.50–8.60 |
| **Google Play** plus | 19.99–22.30; 9.99–11.20 promo | 14.40–20.00 | 16.50–23.10 |
| **Google Play** pro100 / pro200 | 99.98–111.1 / 199.98–222.2 | 80–92 / 160–201 | 85–106 / 170–246 |

Google Play price points are set from the Play rows themselves:
- **US Play** charges $19.99 for Plus (53k of 247k rows are exactly 19.99; the rest is 19.99 plus sales tax: 21.19, 21.39…) and $8.00 for Go (8.48/8.56 with tax). There is a 2025 retention promo at $9.99–11.20. Pro 200 has about 80–95 Play payments a quarter, and Pro 100 starts in 2026Q2.
- **EU Play** amounts are mostly USD-priced: $19.99 at FX gives a drifting €16.9–18.3, plus some €22.74–22.99. UK Play is £18.99 plus USD-priced variants at £15–17.
- **Rejected Play amounts** (US $4.2–4.4, €4.2–5.6 in FR/DE, about 2–5k rows in total) are likely Codex/Sora credit packs or Play promos and stay `out_of_band`.
- **Play rows get no Team seat, proration or bare-descriptor logic.**
What the histograms show:
- **US Plus** is $20.00 (53%), with a sales-tax tail at 21.20–21.95.
- **$23.00 (since Jan 2026, ~1k payments a month)** comes from uids who previously paid $22.20 or $21.80. This looks like a local tax rise, so it maps to Plus.
- **Legacy USD billing in Europe** shows clearly:
  - UK Plus in 2023–24 is £18.3–19.9 and moves with FX. Descriptors often carry the original amount, e.g. `usd 24.00 @ 1.3415`.
  - £20.00 starts in 2025Q1, and legacy amounts of £17.5–18.3 persist into 2026.
  - DE/FR show USD 23.80–24.40 as €20.5–22.9. French cards add an FX commission, which reaches €25.6 in 2024Q4–2025Q1.
- **Ex-VAT amounts** (VAT-ID payers) are kept: £16.67 and €19.0–19.3 for Plus, €6.61–6.72 for Go.
- **Upgrade prorations** (Plus→Pro 100 $75–99, Plus→Pro 200 $170–199, Go→Plus $11.5–19.4) are mapped to the target plan only if the uid pays that plan within 40 days (`note=upgrade_proration`).

## Team / Business (`team_business`)
Seat multiples billed under the consumer descriptor:

| | Team (before 2 Apr 2026) | Business (from 2 Apr 2026) |
|---|---|---|
| US | $60–66 (2×30) | $50–55 (2×25), $75, $125 |
| US annual | $600 | $480 |
| UK | £56–60 | £36, £43 |
| EU | €56–75 (2×34) | €43–44, €51–53 |

The price cut is visible in the US: $60 payments fall from 2,523 in 2026Q1 to 62 in 2026Q2, while $50 jumps to 2,698.

Pro amounts that collide with seat multiples (Pro 100 = 4×25, Pro 200 = 8×25) are rejected as `team_business_collision` when the same uid paid a seat multiple within 62 days.

## Exclusions (rows)
| reason | omega | uk | de | fr | es | it |
|---|---|---|---|---|---|---|
| ok (all channels) | 2,775,907 | 335,781 | 532,010 | 770,597 | 263,654 | 190,735 |
| of which google_play ok | 242,158 | 305 | 1,089 | 2,907 | 266 | 173 |
| api_bare_openai | 66,755 | 14,559 | 18,929 | 41,488 | 15,271 | 8,357 |
| duplicate (uid+day+amount) | 57,795 | 4,493 | 2,055 | 18,667 | 6,625 | 603 |
| duplicate_near (≤3d, ±15%, same channel) | 29,995 | 1,537 | 1,666 | 36,771 | 3,865 | 210 |
| team_business (+collision) | 32,445 | 1,461 | 2,567 | 3,752 | 2,490 | 551 |
| refund | 11,282 | 4,638 | 2,481 | 3,654 | 2,353 | 2,127 |
| credits | 9,651 | 2,361 | 2,555 | 2,994 | 1,933 | 1,208 |
| sora | 635 | 0 | 0 | 2 | 0 | 0 |
| auth_small (<3) | 3,738 | 881 | 1,334 | **60,523** | 2,434 | 1,054 |
| business_user (B) | – | 4,149 (1.1%) | 0 | 0 | 0 | 0 |
| out_of_band + pre_launch (of which Play) | 12,244 (2,236) | 1,835 (67) | 4,552 (464) | 6,450 (1,231) | 3,918 (104) | 1,807 (5) |

Notes on the exclusions:
- **Unclassified share:** out_of_band plus pre_launch is 0.4–1.4% of clean subscription payments, web and Play combined.
- **FR `auth_small`** (including 2.9k Play rows) is mostly €1.00 and €1.50 card FX-fee lines posted under the OpenAI descriptor.
- **`duplicate_near`** catches FR pending/posted pairs: the same payment appears 1–3 days apart under two descriptor variants.
- **EU usertype** is C only in the extracts.

## Monthly vs annual (gaps between kept payments, same uid, channel and plan)
| | omega | uk | de | fr | es | it |
|---|---|---|---|---|---|---|
| 25–35 days | 90.5% | 92.8% | 92.4% | 86.8% | 89.3% | 86.0% |
| 330–400 days | 0.12% | 0.15% | 0.16% | 0.21% | 0.18% | 0.29% |

There is no annual cluster, so `ambiguous` is not used.

Removing the lag filter raised the 25–35-day share: UK from 91.3% to 92.8%, FR from 84.9% to 86.8%, ES from 84.0% to 89.3%. 70–100-day gaps in ES fell from 2.1% to 0.8%.

## Web vs Google Play: unique kept payers by month
| month | omega web / play | uk | de | fr | es | it |
|---|---|---|---|---|---|---|
| 2024-01 | 15,249 / 326 | 3,284 / 0 | 6,843 / 1 | 11,043 / 5 | 2,947 / 0 | 1,832 / 0 |
| 2025-01 | 38,492 / 2,051 | 6,241 / 2 | 14,961 / 19 | 18,788 / 49 | 6,205 / 1 | 4,221 / 4 |
| 2025-07 | 71,709 / 6,991 | 10,190 / 10 | 17,188 / 35 | 25,430 / 106 | 8,544 / 10 | 6,538 / 5 |
| 2026-01 | 100,182 / 10,284 | 13,467 / 16 | 17,374 / 48 | 26,844 / 123 | 8,960 / 13 | 8,254 / 12 |
| 2026-04 | 116,880 / 14,687 | 15,066 / 18 | 16,758 / 55 | 24,359 / 154 | 9,190 / 13 | 7,581 / 9 |
| 2026-07 | 141,500 / 17,309 | 16,030 / 25 | 18,810 / 68 | 24,474 / 156 | 11,234 / 17 | 8,626 / 7 |
| 2026-09 | 175,835 / 22,909 | 16,062 / 24 | 20,351 / 74 | 22,412 / 190 | 11,673 / 16 | 9,038 / 10 |

**US Google Play is 11.5% of kept payers in 2026-09**, up from 2.1% in 2024-01. Play mix in Sep 2026 is Go 4,575, Plus 18,271, Pro 100 141, Pro 200 39.

**In Europe, Play is under 1% of payers.** The prefilter only sees descriptors that name ChatGPT, and European Play charges mostly post as a generic "GOOGLE *Google Play" with no app name, so most EU Play subscribers are probably invisible, like Apple.

## Sanity series: unique kept web payers (go / plus / pro100 / pro200)
| month | omega | uk | de | fr | es | it |
|---|---|---|---|---|---|---|
| 2024-01 | 0/15,249/0/0 | 0/3,284/0/0 | 0/6,843/0/0 | 0/11,043/0/0 | 0/2,947/0/0 | 0/1,832/0/0 |
| 2025-01 | 0/38,367/0/176 | 0/6,217/0/29 | 0/14,928/0/42 | 0/18,746/0/61 | 0/6,191/0/18 | 0/4,215/0/8 |
| 2025-07 | 0/71,348/0/440 | 0/10,158/0/35 | 0/17,153/0/41 | 0/25,382/0/58 | 0/8,514/0/30 | 0/6,526/0/14 |
| 2026-01 | 2,710/97,168/0/511 | 341/13,103/0/27 | 1,021/16,298/0/75 | 3,310/23,552/0/54 | 103/8,826/0/36 | 1,269/6,989/0/14 |
| 2026-04 | 13,946/103,049/199/491 | 2,210/12,843/34/33 | 1,683/15,015/51/73 | 4,692/19,712/47/43 | 2,033/7,150/26/31 | 1,492/6,081/16/12 |
| 2026-07 | 20,200/121,059/907/511 | 2,673/13,257/106/46 | 2,181/16,427/222/86 | 4,843/19,522/221/64 | 2,641/8,538/88/51 | 1,831/6,773/38/21 |
| 2026-09 | 29,662/145,607/1,722/603 | 2,658/13,156/249/78 | 2,412/17,512/394/145 | 4,245/17,830/395/126 | 2,613/8,894/199/95 | 1,796/7,131/116/41 |

**Effect of removing the lag filter on the monthly series:**
- **Levels rise in FR, ES and UK.** In 2025-07, Plus payers rise 42% in FR (17.9k to 25.4k), 14% in ES and 19% in UK. DE and IT barely change.
- **The FR Plus trend changes most.** With the filter, FR Plus looked flat at about 16.5–18.8k from 2025-07 to 2026-09. Without it, FR Plus peaks at about 25k in mid-2025 and falls to about 17.8k by 2026-09. The filter had been removing the most rows exactly when the lagged share was highest.
- **The latest month is now provisional in the Fable panels.** Late-reported rows for September 2026 may still arrive.

Pro 500 payers in October 2026: omega 3, de 4, es 1.

## Caveats
- **The FR decline in Plus from mid-2025 needs checking against FR panel active members.** Plus→Go downgrades explain part of it.
- **US descriptor formats change with the bank feed.** "POINT OF SALE…" is replaced by "SXONG…" from Apr 2026, and "DC : PURCH" appears in Jun 2026. Counts at uid level are unaffected.
- **US Plus payers rise 37% from Jun to Sep 2026** across all descriptors. Check this against panel active members.
- **Apple billing is invisible in all panels.** EU Google Play is largely invisible too (generic descriptor). Because of this, the web/Play/Apple channel mix is a source of bias between panels.
- **Google Play charges have no plan detail.** Plan mapping relies on price points, and EU USD-priced Play amounts drift with FX.
- **EU Plus falls in Apr 2026** while Go rises, consistent with Plus→Go downgrades.

## Open questions
1. Should bare `OPENAI` rows be kept on the recurrence test (adds about 31k US / 18k UK / 49k FR rows), or should all of them be excluded as API (the prior-notebook rule)?
2. Should VAT-ID (ex-VAT) Plus and Go payers count as consumer?
3. Should the generic "GOOGLE *Google Play" EU rows be used at all? This would need a new prefilter keyword, and they cannot be attributed to an app.
4. Is there a better source for the UK £36/£43 and EU €44/€52 Business seat prices?
