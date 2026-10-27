# GTA VI at Amazon / Walmart in NIQ email-header feeds (SUPRA and EMAIL_HEADER)

Written 2026-10-27. All queries were read-only. The SQL is in `supra_amzn_wmt_gta6.sql`. Companion to `slice_items_gta6.md`.

## Bottom line
- **SUPRA cannot help here. Production SUPRA does not carry Amazon or Walmart.** `SUPRA_QUALITY_MERCHANT_EMAIL_HEADER` covers 23 allow-listed domains (google, etsy, netflix, airbnb, duolingo, spotify, wayfair, chewy, roblox, openai and others). `SUPRA_NON_QUALITY_*` covers 3 (currentbody, 360incentives, invisalign). Amazon (940M subjects) and Walmart (58M) appear only in the `TRIAL-THROUGH-2025-12-31` schema, which ends on 2025-12-31, six months before pre-orders opened.
- The usable header source is **`SHARE_NIQ.SRS.EMAIL_HEADER`**. This is the subject and sender header for every email that Slice parsed into an order, keyed by `ORDER_ID`. It does carry GTA VI subjects for Amazon and Walmart, but it is **not incremental** to Slice items:
  - **Amazon:** 201 orders with a GTA VI game subject. All 201 already have a GTA VI item row in `items_extended`, so 0 mailboxes are incremental. The header actually sees *fewer* orders than Slice (201 of 271), because 69 Slice orders have a NULL subject, including all 53 Xbox orders.
  - **Walmart:** the only GTA VI subjects are 38 `Canceled:` emails. These are the same 38 orders as the 40 Slice "Walmart Cancellation" rows. No Walmart order, pre-order, "Thanks for your preorder", shipped or delivered email mentions GTA VI. **No Walmart subject from May to October contains "preorder" or "pre-order" at all.** Walmart's pre-order confirmation template is not ingested anywhere we can see.
- So the Walmart blind spot and the Amazon under-count are upstream ingestion or parsing gaps. No header table we can access works around them.

## 1. Inventory
| Object | Type | Grain / key columns | Amazon? | Walmart? | Dates |
|---|---|---|---|---|---|
| `SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAIL_HEADER` | view | one row per distinct subject: `SUBJECT_ID, SUBJECT, DOMAIN, TOP_LEVEL_DOMAIN, FROM_ADDR, AUX_DATA` (hashed redacted tokens) | No | No | n/a |
| `SHARE_NIQ.SRS.SUPRA_QUALITY_MERCHANT_EMAILS` | view | one row per email: `EMAIL_ID, SUBJECT_ID, EMAIL_SENT_DATE, USER_ID, MAILBOX_ID, EMAIL_TYPE(+confidence)` | No | No | 2018-11-11 to **2026-10-20** |
| `SHARE_NIQ.SRS.SUPRA_NON_QUALITY_MERCHANT_EMAIL(S/_HEADER)` | views | same as above | No | No | 3 domains only |
| `SHARE_NIQ."TRIAL-THROUGH-2025-12-31".SUPRA_QUALITY_*` | views | same as above | Yes (940M) | Yes (58M) | to **2025-12-31** |
| `SRS_SLICE.{ALGN,RIVN,ROKU}.*_SUPRA` | tables | derived, company-specific | n/a | n/a | n/a |
| **`SHARE_NIQ.SRS.EMAIL_HEADER`** (not SUPRA-named) | view | one row per message × order: `MESSAGE_ID, ORDER_ID, MERCHANT_NAME, ORDER_DATE, EMAIL_SENT_DATE, SEQUENCE, SUBJECT, SUBJECT_KEYWORDS, LOCAL_PART, DOMAIN` | Yes | Yes | to **2026-10-26** |
| `SHARE_NIQ.SRS.EMAIL_HEADER_FTA(_BANKING)` | views | same as `EMAIL_HEADER` | not checked (FTA subsets) | | |
| `SHARE_NIQ.SRS.US_MERCHANT_EMAILS(_FLATTEN)` | views | one row per email: `MESSAGE_ID, USER_ID, MAILBOX_ID, EMAIL_SENT_DATE, SUBJECT, DOMAIN, EMAIL_TYPE, TICKER` | Yes (about 5.6M per week), but marketing / `NOT_A_RECEIPT` mail | **No** (not in the domain list) | to **2026-10-19**; very slow (a one-week scan takes 30–40 min) |

In production SUPRA, "grand theft / gta / rockstar" subjects exist only under unrelated domains (google 8.6k, netflix 812 and others). These are noise.

### EMAIL_HEADER coverage, 2026 (rows per week)
- **Amazon:** a steady 4.2–4.9M rows per week, with a spike of 6.1M in the week of 22 Jun (Prime Day). 73–94% of rows have a non-null subject (about 75% in H1, about 87% from mid-July).
- **Walmart:** 430–530k rows per week, and 100% of rows have a subject.
- **Freshness:** rows run to 2026-10-26 (partial day). Subjects back-fill with a lag: the latest week is only 74% (Amazon) and 85% (Walmart) populated, and 26 Oct has 0%. The last GTA VI subjects found were Amazon on 19 Oct and Walmart on 21 Oct. Treat the last 5–7 days as incomplete.
- **Speed:** a scan takes about 36 s per day, or about 8–13 min per month for a regex scan. Pull month by month in parallel. An `ORDER_ID IN (...)` lookup over Jun–Oct takes about 2.5 min.

## 2. Subject search (May–Oct 2026, `grand theft | theft auto | \bGTA | rockstar`)
- "Rockstar" is mostly noise: Rockstar energy drinks and "Rockstar Romance" Kindle books. Drop it.
- **Amazon subject templates** (`LOCAL_PART`):
  - `auto-confirm`: `Ordered: "<title> __` or `Ordered: N "<title> __ and N more items`
  - `shipment-tracking`: `Shipped: "<title> __`
  - `order-update`: `Delivered: "<title> __`
  - `digital-no-reply`: `Amazon.com order of <full title>.`
- **Truncation and redaction (Amazon):** physical-order subjects show only the first 3–4 title words before a `__` redaction token. GTA VI always reads `Ordered: "Grand Theft Auto VI __`, so **the platform (PS5/Xbox) is never visible**. All 201 GTA VI subjects are redacted after "VI". `"Grand Theft Auto VI: __` (with a colon) is the **soundtrack album**, not the game (4 orders in Sept). Bare `"Grand Theft Auto __` / `"Grand Theft Auto: __` subjects exist, but all are Shipped or Delivered, and GTA VI has not shipped yet. These are GTA V, Trilogy or Vice City.
- **Walmart subject templates:** Walmart truncates the item name itself at about 22 characters, followed by `...`, e.g. `Canceled: delivery of Grand Theft Auto VI, P... 🔴`. The letter after the comma gives the platform (**P = PS5 26, X = Xbox 12**). Other templates (`Shipped:`, `Delivered:`, `Picked up at h:mm:`) appear only for GTA V, Trilogy, San Andreas and pre-owned discs.
- **Amazon "Your Amazon.com order of "Grand Theft…""**: only 1 subject in this template (`Your Amazon.com order of Grand Theft __ and 1 more item.`), and it is not GTA VI.

## 3. True GTA VI subjects
| Domain | Template | Subjects (rows) | Orders | Users / mailboxes* |
|---|---|---|---|---|
| Amazon | Order confirmation (`Ordered: "Grand Theft Auto VI __`, incl. qty / multi-item) | 201 | 201 | 195 / 195 |
| Amazon | Shipped / delivered / cancelled | 0 | | |
| Walmart | Pre-order / order confirmation | **0** | | |
| Walmart Cancellation | `Canceled: delivery of Grand Theft Auto VI, P/X...` (+ `Canceled: … item from delivery`) | 38 | 38 | 34 / 34 |
| *(excluded)* Amazon album | `Ordered: N "Grand Theft Auto VI: __` | 4 | 4 | |

\* `EMAIL_HEADER` has no user or mailbox column. These counts come from joining `ORDER_ID` to `items_extended`; every header order resolved.

**Inflection (Amazon order confirmations, by `email_sent_date`):** 0 in May through 24 Jun. **99 on 25 Jun**, then 21, 12, 10, 5 and 2 over 26–30 Jun.

| Month | Amazon `Ordered:` GTA VI | Walmart `Canceled:` GTA VI | Slice Amazon game orders (for ref.) |
|---|---|---|---|
| Jun (25–30) | 149 | 11 | 194 |
| Jul | 24 | 7 | 32 |
| Aug | 7 | 5 | 16 |
| Sep | 8 | 5 | 13 |
| Oct (to ~21) | 13 | 10 | 19 |
| **Total** | **201** | **38** | **274** |

## 4. Overlap with Slice items (join key `ORDER_ID`)
- `EMAIL_HEADER.ORDER_ID` = `items_extended.ORDER_ID`. This is a direct 1:1 link and needs no mailbox mapping.
- **Amazon:** all 201 header GTA VI game orders have a GTA VI item row in Slice, so 0 are incremental (0 incremental mailboxes out of 195). In the other direction, 271 Slice Amazon GTA VI orders (255 users) produce:
  - 201 orders whose header subject names GTA VI;
  - 69 orders whose `auto-confirm` subject is **NULL**. These comprise **all 53 Xbox orders** and 16–19 PS5 orders. The `|` in "Xbox Series X|S" is the likely cause of the dropped subject;
  - 1 multi-item order whose subject names another item first.
  - Every Slice order has at least one header row.
- **Walmart:** the 38 `Canceled:` header orders are exactly the 38 Slice "Walmart Cancellation" orders (34 users), so we **gain 0 mailboxes**. No Walmart GTA VI order or pre-order emails exist in any header table we can query.
- **Implication:** `EMAIL_HEADER` is a header view over the *same parsed receipts* as Slice. It cannot recover emails that Slice failed to ingest. For Amazon, item rows are the better source (they carry the platform and capture Xbox). Header subjects are useful only as a cross-check.

## Recommended filter
Use Slice items (`slice_items_gta6.md`) as the primary source. If you want header subjects as a cross-check:
```sql
from share_niq.srs.email_header h
where h.email_sent_date >= '2026-06-24'
  and h.domain in ('amazon', 'walmart')
  and h.subject like '%Grand Theft Auto VI%'
  and regexp_like(h.subject, '.*Grand Theft Auto VI( __|,).*', 's')   -- excludes 'VI:' album
-- template: Ordered: / Canceled: / Shipped: / Delivered:  (prefix)
-- Walmart platform: regexp_substr(subject, 'Grand Theft Auto VI, ([PX])', 1, 1, 'e')
```

## Caveats and limitations
- **No SUPRA coverage** for Amazon or Walmart after 2025. To get Walmart pre-orders, NIQ would have to add walmart.com to the SUPRA quality allow-list, or parse Walmart's pre-order template into Slice. Raise this with NIQ.
- **Redaction:** Amazon subjects are tokenised and redacted (`__`) after the first few words, so platform, edition and price are lost. Walmart truncates natively (`...`), but the first platform letter survives.
- **Missing subjects:** about 13–27% of Amazon header rows have NULL subjects, and GTA VI Xbox orders are systematically NULL.
- **Lag:** rows are fresh to 26 Oct, but subjects back-fill over about a week. Production SUPRA itself ends on 20 Oct.
- **No prices or quantities** in headers, apart from Amazon's leading "N" for quantity. All counts are unweighted panel counts.
- **Post-launch:** GTA VI `Shipped:` / `Delivered:` subjects should appear from about 12 Nov. These could help confirm Amazon Xbox orders and fulfilment, but they would still be the same parsed orders.
- `US_MERCHANT_EMAILS_FLATTEN` (a non-SUPRA feed with user and mailbox ids) was checked for the launch week (24 Jun–1 Jul). It has **0 Walmart rows** and **0 Amazon subjects containing "Grand Theft"**. Its Amazon rows are promotional mail ("Last call for Prime Day" and similar, `EMAIL_TYPE = NOT_A_RECEIPT`), so it adds nothing for order confirmations.
