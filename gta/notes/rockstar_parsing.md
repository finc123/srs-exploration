# Rockstar Games / Take-Two in Slice items and SUPRA

Written 2026-10-27. All queries were read-only. The SQL is in `rockstar_parsing.sql`.

## Bottom line
- **Slice does parse the Rockstar Store, and it does more than welcome emails.** Merchant `Rockstar Games` (id 3325, mapped to TTWO) is on the quality-merchant list. Since Jan 2025 it has 29.4k rows: welcome/account emails (86%), GTA+ payments (10%), and a small set of real purchases (Shark Cards, Red Dead Online Gold Bars, PC games). This corrects the earlier note, which said it had only welcome emails and GTA+.
- **No GTA VI rows exist at Rockstar,** and no pre-order deposits or merch either. This is expected: GTA VI is console-only, so pre-orders go through PSN, Xbox and retailers (see `slice_items_gta6.md`). The Rockstar Store sells merch on a separate storefront that is not parsed under any merchant name we found.
- **Purchase parsing appears to have broken around 1 Oct 2025, and the break has not been reported.** Rockstar Store purchase rows (Shark Cards, Gold Bars and PC games) fell from about 100 a month (Jan–Sep 2025) to about 4 a month from Oct 2025, a 96% drop overnight. Over the same period, Steam Shark Card rows fell only about 20%, with no step. GTA+ payment and welcome-email parsing kept working. `MERCHANTS_WITH_ISSUES` has only a June 2025 layout issue, marked "Fixed" on 2025-08-28.
- **Rockstar is not a SUPRA domain.** SUPRA covers 23 quality domains plus 3 non-quality ones, and none of them is rockstargames.com, socialclub or take2. The only GTA VI signals in SUPRA are indirect: Netflix's *"Grand Theft Auto VI: An Extended Look"* (Aug 2026) and a few ChatGPT tasks tracking pre-orders. SUPRA has no purchase signal at all around 25 Jun.

## A. Slice items: Rockstar Games (merchant_id 3325)

Merchant discovery: `%rockstar%`, `%take%two%`, `%2k%` and `%social club%` return only `Rockstar Games` (3325). `2K` (1783) has no rows since 2023. Zynga (20224) is the only other TTWO-mapped merchant, and it is mobile.

Quality and issue lists:
- `QUALITY_MERCHANTS`: Rockstar Games 3325 is present, with a null note.
- `MERCHANTS_WITH_ISSUES`: "In June 2025, a decline in parsing rate was observed due to modifications in the merchant's receipt layout and subject field…" The status is Fixed (first reported and updated 2025-08-28). Nothing has been logged for the Oct 2025 break.
- `ORDER_TOTAL_ONLY_MERCHANTS`: not listed.

### What is parsed, Jan 2025 – 27 Oct 2026
| Class | Rows (= orders) | Users | Priced | $ (item price) | Typical descriptions / prices |
|---|---|---|---|---|---|
| Welcome / account | 25,417 | 25,385 | 0 (NULL price) | – | "Welcome to Rockstar Games" (the "…Social Club" variant appears only in 2024) |
| GTA+ subscription | 3,053 | 765 | all | 25,031 | "Payment for GTA+ Membership" $7.99 (2,168); "GTA+ Subscription Confirmation" $7.99 (799); "Buy 2 Get 1 Free" $15.98 (79, Dec 2025–Jan 2026) |
| Shark Cards (GTA Online, PC) | 436 | 179 | all | 15,503 | Great White $19.99, Bull $9.99, Whale $49.99, Tiger $4.99, Megalodon $99.99; "(PC)" and "GTA+:" variants |
| RDO Gold Bars | 137 | 80 | all | 4,013 | 25 / 55 / 150 bars at $9.99 / $19.99 / … |
| PC game / bundle | 396 | 377 | all | 13,080 | GTA V $29.99 (233), RDR2 $59.99, GTA IV CE $19.99, Trilogy, RDR, Bully, Max Payne 3, L.A. Noire |
| **GTA VI** | **0** | – | – | – | none |
| Merch (Rockstar Store apparel etc.) | 0 | – | – | – | none at 3325 or under any Rockstar-like merchant name |

Notes:
- Every row has one item per order (rows = orders), `DIGITAL_GOOD = 'N'` and `STATUS = 'I'`.
- Categories are noisy. Gold Bars are tagged "Grocery & Gourmet Food" and some Shark Cards are tagged "Office Products".
- Descriptions are never null. NULL prices occur only on welcome emails, which is expected because those are not orders. Purchase rows have `order_total`, and usually `tax`.

### Monthly rows by class
| Month | Welcome | GTA+ | Shark | Gold Bars | PC game |
|---|---|---|---|---|---|
| 2025-01 | 2,042 | 0 | 74 | 21 | 81 |
| 2025-02 | 1,394 | 0 | 35 | 24 | 49 |
| 2025-03 | 1,579 | 118 | 94 | 14 | 67 |
| 2025-04 | 1,583 | 100 | 21 | 10 | 36 |
| 2025-05 | 1,737 | 112 | 45 | 9 | 46 |
| 2025-06 | 1,409 | 128 | 52 | 12 | 31 |
| 2025-07 | 1,305 | 143 | 31 | 18 | 28 |
| 2025-08 | 995 | 149 | 33 | 11 | 24 |
| 2025-09 | 738 | 139 | 26 | 6 | 20 |
| **2025-10** | 773 | 135 | **0** | **1** | **1** |
| 2025-11 | 1,184 | 147 | 0 | 0 | 1 |
| 2025-12 | 1,860 | 207 | 0 | 0 | 2 |
| 2026-01 | 1,788 | 168 | 1 | 0 | 2 |
| 2026-02 | 879 | 142 | 5 | 0 | 0 |
| 2026-03 | 956 | 185 | 7 | 1 | 0 |
| 2026-04 | 757 | 183 | 4 | 2 | 1 |
| 2026-05 | 836 | 180 | 2 | 0 | 1 |
| 2026-06 | 951 | 168 | 2 | 5 | 2 |
| 2026-07 | 1,013 | 181 | 4 | 1 | 0 |
| 2026-08 | 569 | 168 | 0 | 0 | 1 |
| 2026-09 | 617 | 167 | 0 | 2 | 1 |
| 2026-10 (1–27) | 452 | 133 | 0 | 0 | 2 |

GTA+ parsing at Rockstar starts in Mar 2025; there are no GTA+ rows in 2024 or Jan–Feb 2025. Before that, PC GTA+ was either not sold direct or not parsed.

### Parse-break evidence (Oct 2025)
- The last regular run of Shark Card, Gold Bar and PC-game rows ends on 1 Oct 2025, after 2–5 rows a day through 30 Sep. From then on there are about 4 rows a month in total.
- Demand did not collapse. Steam (the other PC channel) logged Shark Card rows of 137, 101 and 130 in Sep, Oct and Nov 2025. The average was about 200 a month in Jan–Sep 2025 and about 160 a month in Oct 2025 – Oct 2026, a decline of about 20% with no step. PSN and Xbox Shark Card rows also show no step at Oct 2025.
- GTA+ payments ("Payment for GTA+ Membership") and welcome emails from the same sender kept parsing normally. This points to a template change in the Rockstar purchase-receipt email, consistent with the June 2025 issue, and not to a loss of the sender.
- We cannot measure the parse rate against raw email volume, because rockstargames.com is not a SUPRA domain (see B). The step change is the best evidence available.

### GTA VI-adjacent signal at Rockstar
- **Welcome / account creations rose after pre-orders opened.** They averaged about 28 a day in mid-June and about 42–64 a day from 25 Jun to early July. Weekly counts went from about 180 (Jun) to 301 and 340 in the weeks of 22 and 29 Jun, then decayed to about 100–130 a week by October. A smaller bump appeared in the week of 31 Aug (198), around the Netflix *Extended Look* release.
- Welcome emails are an engagement signal, not a purchase signal. Console pre-orders do not require a Rockstar account. The 2026 level is about 40% below 2025 year-on-year, which partly reflects panel shrinkage.

### Context: where Rockstar monetisation actually shows up in Slice (Jan 2025 – Oct 2026)
Rockstar-branded items at other merchants number 129.6k rows, against about 4k purchase rows at the Rockstar Store:

| Merchant | Rows | Users | $ |
|---|---|---|---|
| PlayStation Store (`Sony Entertainment Network`) | 70,093 | 12,383 | 1.05M |
| Microsoft Store | 45,271 | 19,960 | 1.11M |
| Steam | 5,084 | 3,047 | 132k |

Most of these rows are GTA+ (PSN "GTA+ (Subscription)" 44.8k; Xbox renewals and cancellations), Shark Cards, GTA V/Online, RDR2 and GTA VI (PSN/MS, covered in `slice_items_gta6.md`).

## B. SUPRA email headers

Tables in `SHARE_NIQ.SRS`:
- `SUPRA_QUALITY_MERCHANT_EMAIL_HEADER`: 400M subject rows, 23 domains. Columns: subject_id, subject (redacted "__"), domain, top_level_domain, from_addr, aux_data (hash tokens). There is no date column.
- `SUPRA_QUALITY_MERCHANT_EMAILS`: one row per email. Columns: email_id, subject_id, email_sent_date, user_id, mailbox_id, email_type. The latest `email_sent_date` is 2026-10-20, so there is about a 1-week lag.
- `SUPRA_NON_QUALITY_MERCHANT_EMAIL_HEADER` / `_EMAILS`: 54k subjects covering invisalign.*, currentbody.com and 360incentives.com.

Quality domains: google, etsy, netflix, airbnb, duolingo, spotify, wayfair, chewy, lululemon, roblox, westelm, openai, potterybarn, potterybarnkids, planetfitness, coachoutlet, tesla, global-e, fivebelow, coach, rh, rivian and aligntech.

**Rockstar verdict: not covered.** No rockstargames.com, socialclub, take2 or take-two domain or sender exists. The only `%rockstar%` sender hits are rockstargo.com (filed under netflix) and teamrockstars.nl (under google), and both are false positives. We therefore have no subject templates, weekly counts or mailbox counts for Rockstar's own emails, and no 25 Jun inflection can be measured in SUPRA.

### GTA VI mentions in other SUPRA domains (bonus)
A subject search for rockstar / grand theft / GTA / GTA VI / GTA 6 / red dead / shark card across all domains returns 6.4k subject templates. Emails since 2024 for the relevant groups:

| Group | Emails | Mailboxes | When | What it is |
|---|---|---|---|---|
| Netflix: *Grand Theft Auto VI: An Extended Look* | 484,743 | 272,242 | 6 Aug – 20 Oct 2026; 483k in Aug | Netflix title marketing. The main blast ran 9–28 Aug ("Grand Theft Auto VI: An Extended Look" 458k emails to 257k mailboxes, plus localised variants). Viewing nudges followed: "Don't forget to finish…" (1,051), "What did/do you think of…" (866) and "Termina de ver…" (73). These are a rough proxy for viewers who started the title. |
| Netflix: other GTA (Netflix Games) | 200 | 108 | Aug 2026 | GTA Trilogy on Netflix Games |
| OpenAI: ChatGPT task updates on GTA VI | 340 | 39 | Jan 2025 – Oct 2026; peak Oct 2025 (62) | Examples: "[Task Update] GTA 6 pre-order status update", "GTA VI preorder deal watch: Target student discount…", "GTA 6 Countdown". These are users' scheduled tasks; the sample is too small to use. |
| Google / Spotify / Roblox misc. | 12 | 7 | Jun–Sep 2026 | Google Forms ("Target/Walmart GTA VI Collector's Edition Pre-Order – Multiple Checkout", 25 Jun); Calendar ("GTA 6 digital pre order @ Thu Jun 25, 2026"); Spotify "'Grand Theft Auto VI: The Album' Launch" |
| Google: Rockstar Games account / GTA Android installs | 1 | 1 | – | Templates exist (e.g. "Rockstar Games Social Club now has access to __ Google Account", "Grand Theft Auto: San __ installed on __ device"), but the email rows predate 2024 |

25 Jun inflection: SUPRA shows only a handful of hits on 25 Jun (Google Forms and Calendar pre-order reminders). Nothing in SUPRA is a usable GTA VI purchase series.

## Caveats
- Counts are unweighted rows from `items_extended` (the base of `ITEMS_V`), with no panel or aging filter. The welcome-email trend partly reflects panel shrinkage: 2026 is about 40% below 2025 year-on-year in every month.
- The parse-break call rests on a step change plus a flat Steam control. We have no raw Rockstar email counts to compute a true parse rate.
- `US_MERCHANT_EMAILS` (`feed_description = 'PROMOTIONAL_EMAILS'`, 12B rows, with domain, ticker, subject and from_addr in DATA) might contain Rockstar promo emails. Scanning it is very slow: a 0.5% row-sample probe ran for more than 15 minutes and was stopped, so this feed is still unchecked.
- SUPRA subjects are redacted ("__"). The header table has no dates, so all dating comes from the email table, which has a 1-week lag (latest 2026-10-20).

## Recommendations
1. **Do not use the Rockstar Store for GTA VI.** Track pre-orders at PSN, Microsoft Store and retail, as in `slice_items_gta6.md`. Rockstar direct is PC-only and, today, mostly GTA+.
2. **Raise the Oct 2025 Rockstar purchase-receipt parse break with NIQ.** Cite merchant 3325, the Shark Card / Gold Bar / PC-game rows dropping from about 100 a month to about 4 from 1 Oct 2025, and the flat Steam control. This matters if GTA VI comes to PC through the Rockstar Launcher later, and for any GTA Online PC monetisation work.
3. To get Rockstar email volumes (welcome, newsletter, purchase receipts), ask NIQ to add rockstargames.com to SUPRA, or run a targeted (non-sampled) `PROMOTIONAL_EMAILS` pull filtered on `data:ticker = 'TTWO'` overnight.
4. Optional engagement proxies for the launch narrative:
   - Rockstar welcome-email weekly counts (+70–90% in the pre-order weeks).
   - Netflix *Extended Look* "finish/what did you think" nudges.
