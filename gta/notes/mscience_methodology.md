# M Science GTA VI pre-purchase tracking: methodology review

Prepared 2026-10-27. Read-only review. Pre-orders opened 25 Jun 2026; launch 19 Nov 2026.

## 1. Sources reviewed

| Source | Date | Where | Read? |
|---|---|---|---|
| "TTWO FQ2 '27 Preview + GTA VI Update and Online Thoughts" (Corey Barrett) | 2026-10-19 | Outlook (to srsdata@). Report email is a link only ("View Full Report"). | Teaser only |
| Same report, account-team summary (Daniella Miller) | 2026-10-19 | Outlook. Has the bullet summary; Figure 1 is "First 7 Day Presales as % of First 30 Days". The image did not come through. | Full text |
| "@M Science 10/19 … TTWO + GTA VI Deep Dive" daily digest (Team Megan) | 2026-10-19 | Outlook | Full text |
| "The Sunday Sauce" weekly | 2026-10-25 | Outlook | Full text (GTA and RBLX passages) |
| "@M Science 10/12" digest, which includes the 10/11 Sunday Sauce | 2026-10-12 | Outlook | Full text |
| "Video Game Industry Update: September 2026" | 2026-10-08 | Outlook. Teaser only, no body text. | Teaser only |
| "SONY FQ2 '26 Preview" | 2026-10-13 | Outlook. Teaser only: "remain optimistic on GTA VI in FQ3". | Teaser only |
| "RBLX Early Q4 Observations + Updated GTA Overlap" | 2026-10-22 | Outlook. Teaser only, plus Fin's analysis reply. | Teaser only |
| **Call with M Science (Carter, Megan) on RBLX Q4 and the GTA overlap**, with transcript | 2026-10-22 | Notion meeting notes | Full transcript |
| SRS internal call "Roblox Q4 Bookings Analysis: Data Review & GTA Headwind" | 2026-10-22 | Notion | Summary |
| Slack #internet_games_travel_data: Michal K. on the MSc "Comp Days Units" dashboard for GTA VI precedent curves | 2026-10-26 | Slack | Read |
| Snowflake `SHARE_MSCIENCE.API` | 2026-10-27 | SRS MCP | Table and column list only |

**What I could not access or found nothing in:**
- **Full M Science reports.** Every report email is a "View Full Report" link to portal.mscience.com. No PDFs are attached. The figures, exhibit footnotes and methodology appendix were not available, and those are where the data source would normally be stated.
- **M Science MCP.** Only `authenticate` is exposed, and it needs `/mcp` → "claude.ai M Science" to be run by the user. Not done.
- **Video Games Dashboard.** The "cumulative" and "run-rate" presale compares are portal-only and were not reviewed.
- **Snowflake share.** `SHARE_MSCIENCE.API` has `VIDEO_GAMES_V3_COMPARABLEDAYS` with columns COUNTRY, DATE, DAYSSINCERELEASE, EVENT, GAME, MERCHANT, METRIC_NAME, METRIC_TYPE, RELEASEDATE, **SOURCE_DATA**, …. It also has `VIDEO_GAMES_V3_PURCHASES`, `_UNIQUEPAYERS` and `VIDEO_GAMES_HARDWARE_V1_DOMESTIC_PACKAGED_SOFTWARE`. Every row query timed out or errored, so I could not read SOURCE_DATA, MERCHANT or EVENT for GTA VI. **Retry this first.** It should settle the data-source and merchant questions directly.
- **Earlier reports (Jun–Sep).** The mailbox only holds M Science mail from about 8 Oct. Earlier GTA notes, such as the presale launch read, are not there.
- **AlphaSense.** 0 documents for "M Science" + GTA VI. M Science is not syndicated there.
- **Local files.** `roblox/investigations/mscience_*` hold RBLX bookings data only. Nothing on GTA.

## 2. Data source verdict: e-receipts very likely, not yet confirmed in writing for GTA VI

None of the GTA text we can read names the panel. The evidence points strongly to M Science's email-receipt panel, with a US panel and a separate European panel:

- **M Science's own words on the 22 Oct call.** They said the GTA cohort is built from the panel they use for console and mobile, and that panel is e-receipts:
  - *"our daily mobile and console view, which is based on e-receipt data"* (Carter, M Science)
  - *"we basically took the cohort of users that we see pre-purchasing GTA 6, and we looked at … what percentage of those users had purchased or made a Roblox transaction on console specifically … that's the 13%. … also on mobile and direct channel, which we have a separate visibility into direct channel **within that e-receipt panel** … that percentage overlap was near to 22%."*
  - So the GTA pre-purchaser cohort is user-linked in the same panel as the Roblox console, mobile and direct receipts. That panel is the e-receipt panel.
- **Item-level detail.** They report **units** (*"cumulative GTA VI units have outpaced Modern Warfare II by 3.2x"*, *"as many as 50mm units"*) and **edition mix** (*"a strong Ultimate Edition mix"*). Card data cannot see edition or unit counts. Receipts can.
- **Geography.** *"in the U.S. and Europe data combined"* and *"even greater strength in Europe than we observe in the U.S."* M Science has a European receipt panel. Our 22 Oct internal notes say it covers *"only … 5 Western European countries"* and that it *"backtested poorly against reported EMEA figures"* for RBLX.
- **Card or clickstream inputs.** No mention for GTA VI. Card data could still feed the dollar or merchant-level series. The Snowflake SOURCE_DATA column will confirm.
- **Physical retail.** There is a separate `VIDEO_GAMES_HARDWARE_V1_DOMESTIC_PACKAGED_SOFTWARE` table (by MERCHANT, MODEL, GAME). It may be a different source for physical or retail software. Whether it feeds the GTA presale read is unknown.

**Verdict:** e-receipt (US + Western Europe), with roughly 85–90% confidence on the reads above. Ask M Science to confirm in writing, and check `SOURCE_DATA` in Snowflake.

## 3. Methodology (what is stated vs. not)

**Stated:**
- **Metric.** Observed presale **units**, cumulative and run-rate, from the start of presale availability. They use a days-since-presale-open alignment: *"Through the first 110 days of presale availability…"*. The dashboard is "Comp Days Units", backed by the `COMPARABLEDAYS` table with `DAYSSINCERELEASE` and `EVENT`.
- **Benchmarks.** These are **pre-release presale curves of other titles**. GTA V and RDR2 are **not** cited, probably because the panel history is too short (unconfirmed):
  - *"Based on a compare vs. Modern Warfare II prior to its beta release, cumulative GTA VI units have outpaced Modern Warfare II by 3.2x in the U.S. and Europe data combined."* The MWII cut-off is its beta, which avoids the beta-access pre-order spike.
  - *"GTA VI has outpaced Hogwarts Legacy and Marvel's Spider-Man 2 by more than 13x and 6x, respectively, in our U.S. and Europe data."*
  - Figure 1: "First 7 Day Presales as % of First 30 Days". This compares how front-loaded the presale curve is across titles.
- **Editions.** Ultimate Edition mix is called "strong" and "healthy". No mix percentages or price points are given in the available text.
- **Breadth.** *"Demand for GTA VI to-date is notably broad, including across traditionally more casual gamers"*. This implies they segment buyers by past gaming spend, which needs a user-level panel.
- **Cross-title cohort work.** They do user-level overlap with Roblox spend (13% console-only, about 22% multi-channel). The Sunday Sauce says *"roughly 22% of U.S. GTA VI pre-purchasers have historically spent on Roblox"*.
- **Scaling to 50mm.** *"We continue to see data supporting an outlook for as many as 50mm units"*, later *"through the December quarter"*. The bridge from panel multiples to 50mm is not shown. It is presumably the MWII multiple × MWII's known launch units. Not confirmed.
- **Pull-forward.** The 19 Oct deep dive *"seek[s] to quantify the impact of a potential pull-forward of GTA VI unit sales"*. The details are in the full report, which we don't have.

**Not stated in anything we could read:**
- The merchant/storefront list (PlayStation Store, Microsoft Store, Rockstar Store, Steam/Epic, Amazon, Walmart, Target, Best Buy, GameStop).
- How GTA VI items are identified (description string, SKU, price).
- Digital vs physical split.
- How cancellations and refunds are handled.
- Pre-order vs deposit handling. This matters for GameStop/Amazon physical pre-orders, which charge at ship.
- Panel normalisation (fixed panel, active-user or share-of-wallet scaling) and US/EU weighting.

## 4. Headline figures

| Claim | Date | Source |
|---|---|---|
| "data supporting an outlook for as many as 50mm units" (through the Dec quarter) | 19 Oct; repeated 25 Oct | TTWO FQ2 preview; Sunday Sauce |
| GTA VI cumulative units **3.2x** Modern Warfare II (pre-beta), US+EU combined | 19 Oct | TTWO FQ2 preview summary |
| **>13x** Hogwarts Legacy, **>6x** Spider-Man 2, first 110 days of presale, US+EU | 19 Oct | same |
| Europe stronger than US ("even greater strength in Europe") | 8 Oct, 11 Oct, 19 Oct, 25 Oct | Industry update; Sunday Sauce; digest |
| "strong Ultimate Edition mix" | 19 Oct | digest |
| ~13% of GTA VI pre-purchasers made a Roblox console transaction; ~22% multi-channel | 22 Oct | MSc call; Sunday Sauce 25 Oct |
| "nearly a third" of Roblox spenders in panel have a PlayStation/Xbox purchase, so the overlap is "probably understated" | 22 Oct | MSc call |
| Context: NBA 2K27 units "pacing down mid-teens Y/Y"; non-mobile bookings outlook "roughly 25% Y/Y decline" vs consensus high-teens | 19 Oct | TTWO FQ2 preview summary |
| Dashboard "now approximately 5 weeks from release in our data" | 19 Oct | same |

## 5. Blind spots

**Stated or caveated by M Science:**
- On the Roblox overlap: *"we fundamentally believe that these are probably understated"*. They also said it *"isn't something that we're going to be able to have a really firm view on until we progress through release"*.
- Data lag differs by channel. Console and mobile receipts ran to about 17–18 Oct, while the direct channel ran only to 11 Oct. They *"recommend … look[ing] into our mobile and console views separately"* when working with partial data.
- Nothing GTA-specific caveated in the text available. Their exhibit footnotes are in the portal reports.

**Inferred by SRS (not stated by M Science), assuming an e-receipt panel:**
- **Console-store pre-orders with no emailed receipt.** PSN and Xbox purchases made on the console are usually emailed, but receipt-panel coverage of Sony and Microsoft senders varies. Some regions or settings also suppress the email.
- **Wallet funds and gift cards.** Wallet top-ups, PSN/Xbox gift cards bought at retail, and redeemed gift cards all hide the GTA item. The receipt may show only the wallet load, or no game line at all.
- **Physical in-store pre-orders.** GameStop, Walmart, Target and Best Buy in-store pre-orders and deposits produce no e-receipt or only a partial one. Also, many US retailers (Amazon, Best Buy) **charge at shipment**. Pre-order confirmations may be counted as orders even though some are later cancelled or never charged.
- **Cancellations and refunds.** PS Store and Xbox allow pre-order cancellation. It is unknown whether cancellation emails are netted out. Cancellations around launch could inflate cumulative pre-launch units.
- **Bundles.** Console + GTA VI bundles (PS5/Xbox) may not itemise the game. Mis-attribution between units and dollars is possible.
- **International.** "Europe" is likely only about 5 Western European countries, per our RBLX notes. Japan, LatAm and APAC are not covered. Extrapolating the US+EU multiple to 50mm worldwide assumes the global mix matches the panel.
- **Buyer vs player.** The cardholder or account email is often a parent. This affects the RBLX overlap reading (Chris Wang, 22 Oct: *"you are likely picking up parents who buy for their kids"*).
- **Comparator distortion.** MWII had a beta-access incentive (hence the pre-beta cut-off). Hogwarts and Spider-Man 2 are much smaller franchises, so 13x and 6x multiples overstate how informative the comparison is. With no GTA V or RDR2 in the panel, there is no like-for-like Rockstar curve.
- **Units vs dollars.** A heavy Ultimate Edition mix raises dollars per unit. Check whether "units" counts editions equally and how upgrade DLC purchases are treated.
- **Panel drift.** Over a 5-month presale window, the panel's composition can change. Cumulative multiples vs titles measured years ago (Hogwarts, Feb 2023) are sensitive to how panel size is normalised.

## 6. Open questions for M Science (Corey Barrett / Carter)

1. Please confirm the data source for the GTA VI presale series. Is it US and EU e-receipts only, or are card or other inputs blended in? What is `SOURCE_DATA` in `VIDEO_GAMES_V3_COMPARABLEDAYS`?
2. What is the merchant list behind "units": PlayStation Store, Microsoft Store, Rockstar Store, Amazon, Walmart, Target, Best Buy, GameStop, Steam/Epic? What are the shares by merchant and the digital vs physical split?
3. How is GTA VI identified (item-description match, SKU, price)? How are editions and upgrades classified, and what are the edition and price-point mix figures?
4. Are physical pre-orders counted at order confirmation or at charge/shipment? Are deposits (e.g. GameStop) included?
5. Are cancellations and refunds netted? How do PS Store and Xbox pre-order cancellation emails appear in the panel?
6. How are wallet-funded and gift-card-funded purchases handled? Do PSN/Xbox receipts paid with wallet funds still itemise GTA VI?
7. What panel normalisation is used across a 5-month window and vs 2022–23 comparators: fixed cohort, active-user scaling, or something else? How are US and EU weighted in the "combined" multiples?
8. What is the bridge from panel multiples (3.2x MWII) to "as many as 50mm units"? Which MWII unit base, and what geography and channel grossing-up is assumed?
9. Which countries does the EU panel cover? Is there any visibility into Japan, LatAm or APAC?
10. Can we get the cumulative and run-rate presale series (Comp Days Units) and the Figure 1 data via Snowflake or the API, plus the 19 Oct full report PDF?
11. Why are no GTA V or RDR2 comparisons shown? How far back does the panel go?
12. On the RBLX overlap (13% / 22%): what is the look-back window for "historically spent on Roblox"? Can it be weighted by Roblox spend rather than counted by user?
