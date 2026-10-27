# YipitData GTA VI pre-order tracker: methodology review

Prepared 2026-10-27. Read-only review. Pre-orders opened 25 Jun 2026; launch 19 Nov 2026.

## 1. Sources reviewed

| Source | Date | Where |
|---|---|---|
| "Take-Two (TTWO) – Weekly Tracker (GTA VI and NBA 2K27)", Vol. 14 (data thru 9/27) | 2026-10-01 | Outlook (to srsdata@), full text read |
| Same, Vol. 15 (data thru 10/4) | 2026-10-08 | Outlook, full text read |
| Same, Vol. 16 (data thru 10/11) | 2026-10-15 | Outlook, full text read |
| Same, Vol. 17 (data thru 10/18), latest | 2026-10-22 | Outlook, full text read |
| "Roblox (RBLX): Hours, Steal An Egg, and GTA Overlap – Data Thru 10/11" | 2026-10-15 | Outlook, full text read (gives the panel name) |
| "YD Key Reports" weekly digest thread from Max Florsheim (Yipit), 2 Jul to 2 Oct, forwarded by J. Durand / R. Rubin | 2026-10-05 (FW) | Outlook. Contains one-line summaries of Vol. 1, 2, (7/12), 5, 10, 11, 12, 13, 14 |
| "META (Muse), SPCX, TTWO, RDDT, SPOT, NYT" marketing note | 2026-10-23 | Outlook (insights@yipitdata.com) |

Exhibits are images and were not in the email bodies, so no exhibit values were available. Yipit says "the working XLS is available to clients". We do not have it.

**What I could not access or found nothing in:**
- YipitData MCP: only `authenticate` is exposed. I did not run the OAuth flow, so the portal and dashboard were not reviewed.
- Vol. 1 to 13 full texts are not in the mailbox. Only the digest one-liners are.
- Slack: no hits for Yipit + GTA.
- AlphaSense: 0 docs for YipitData + GTA VI.
- Local `roblox/investigations/yipit_data.xlsx`: Roblox sheets only, no GTA.
- Notion: no Yipit GTA notes. The 22 Oct meeting note "Roblox Q4 Data Review Call" covers GTA/Roblox overlap (13% console-only, ~22% multi-channel). It appears to be the **M Science** call, not Yipit, so it is excluded from the Yipit evidence below.

## 2. Data source verdict: e-receipts, confirmed

The source is a US email-receipt panel (Edison). The reports cite no card, clickstream or app inputs for GTA VI.

- Every volume says: *"We are tracking observed GTA VI unit sales (using our USA e-receipt panel; digital only, no in-store physical)"*.
- Every GTA exhibit is captioned *"Source: U.S. e-receipt data"*.
- The panel is named in the RBLX report (15 Oct), Exhibit 5: *"Source: Email receipt data (US Only) … GTA VI purchasers among a fixed panel of Edison users."*
- Yipit says *"Our panel begins in 2019, thus we cannot track/compare Red Dead Redemption 2 (released in October 2018)."*
- One adjacent caveat: the 4 Sep digest says *"This week we've transitioned our consumer coverage to the new transaction panel"*. It is unclear whether this touched the GTA series. The GTA exhibits still cite e-receipts afterwards.
- The only non-receipt inputs are calibration constants: comparables' **reported** unit sales (e.g. Battlefield 6 ">7m opening weekend") and a physical-to-digital mix adjustment. Neither is a data panel.

## 3. Methodology (as stated by Yipit)

**Unit of measure.** Observed GTA VI *unit* sales in the panel, plus SKU mix and blended ASP.

**Scaling is ratio-to-comparable, not panel ÷ coverage of GTA itself.**
1. Compute observed GTA VI units ÷ observed comparable-title units *"at the same point in time in the preorder window"*.
2. Multiply that ratio by the comparable's eventual reported units (or $ sell-thru) to get implied opening weekend, F3Q27 (Dec) and F4Q27 (Mar) units.
3. For the to-date estimate, take observed GTA units ÷ (comparable's panel units as % of its reported units). This is effectively a coverage ratio borrowed from the comparable.

Yipit gives its reason for the comparables: *"we expect similar geo mix, demos, genres, platforms, and brand awareness to translate to similar panel coverage."*

**Comparables.**
- CoD Modern Warfare II and Battlefield 6 through Vol. 16. Vol. 17 uses B6 alone.
- Other "post-Covid high-profile launches" sit in Exhibit 2, but they *"mostly point to higher implied GTA unit sales"*. Yipit attributes this to coverage differences.
- RDR2 is not possible (pre-2019).
- GTA V is used only for platform mix: *"51%/23%/26% PlayStation/Xbox/PC"* over the past year.
- Yipit dropped MWII on beta lapping: *"CoD MWII preorders increased +155% during the 2-week open beta … we would argue that B6 is the better comp."*

**Digital/physical adjustment.** *"We are adjusting for different mix of digital versus physical unit sales across comparable titles based on when they were launched (EXHIBIT 1 shows adjusted and unadjusted outputs)."* The size of the adjustment is not given in the text.

**Editions and prices.** *"$79.99 Standard Edition vs. $99.99 Ultimate Edition"*. Only these two SKUs are mentioned. No physical collector's edition and no bundles.

**Platforms observed.** PlayStation and Xbox only (e.g. *"72%/28% PlayStation/Xbox"*). The figures exclude PC, which is shown as a separate add-on scenario.

**Not stated anywhere in the material reviewed:**
- which merchants/storefronts are parsed (PS Store vs Microsoft Store vs Rockstar Store vs retailers such as Amazon/Walmart/Best Buy/GameStop online)
- how GTA VI line items are matched (description/SKU/price)
- treatment of cancellations or refunds
- de-duplication of pre-order confirmation vs charge/shipping receipts
- panel size and normalisation for panel churn

## 4. Headline figures (time series)

| Vol. / date | Data thru | Units to-date | Implied opening weekend | Other |
|---|---|---|---|---|
| Vol. 1 (2 Jul digest) | ~6/28 | — | 43–66m (MWII 5.2x, B6 10.0x) | 92% Ultimate, ASP $98.45; 60% of pre-orders from GTA V spenders since 2019 |
| Vol. 2 (10 Jul digest) | ~7% of window | — | 35–67m (console only) | ASP $88; Ultimate 43%; PS5 78% |
| (17 Jul digest) | 7/12, ~12% | — | 34–40m | 3.8x MWII, 6.0x B6; ASP ~$86 (78% Standard / 22% Ultimate) |
| Vol. 5 (31 Jul digest) | ~21% | — | 23–29m (console only) | 3.3x MWII, 3.4x B6 |
| Vol. 10 (4 Sep digest) | 8/31 | ~3.1m | ~21–25m | +9% in 5 days after 8/27 Netflix trailer |
| Vol. 11 (11 Sep digest) | — | — | 23–25m | |
| Vol. 12 (18 Sep digest) | ~54% | 3.45m | 23m | +3% W/W |
| Vol. 13 (25 Sep digest) | ~58% | ~3.55m | 23–24m | |
| Vol. 14 (1 Oct) | 9/27, ~64% | 3.66m (3.3–4.0m) | 22m (MWII) – 23m (B6) | 91% Ult, ASP $98.19; PS/Xbox 71/29; 3.4x B6, 2.5x MWII |
| Vol. 15 (8 Oct) | 10/4, ~69% | 3.85m (3.4–4.3m) | 20m (MWII) – 24m (B6) | ASP $98.15; 3.4x B6, 2.2x MWII |
| Vol. 16 (15 Oct) | 10/11, ~74% | 4.1m (3.7–4.6m) | 11m (MWII) – **25m (B6)** | 90.5% Ult, ASP $98.09; PS/Xbox 72/28; 3.5x B6, 1.3x MWII; W/W +7% |
| **Vol. 17 (22 Oct)** | **10/18, ~77%** | **4.9m** | **26m (B6 only)** | **43m at F3Q27 (Dec), 45m at F4Q27 (Mar)**, ex-PC; 89.75% Ult, ASP $97.94; 3.7x B6; W/W +6%; PC could add ~16m to Mar (GTA V mix) |

Other claims:
- Vol. 16 says the window is *"~74% … on a calendar basis (we estimate still less than 20% on a cumulative unit sales basis)"*.
- Yipit sees catalysts in the 10/15 trailer, TV ads from about 10/20, and early download from 11/12.
- RBLX overlap: 1.65% of Roblox payers have pre-ordered GTA VI (thru 10/11). Those payers spent $112 on Roblox, against $85 for payers who have not pre-ordered.

## 5. Blind spots

**Stated by Yipit:**
- USA only. *"Our panel is USA only"*, used as a caveat on ASP and on the comparable dispersion.
- Digital only, with *"no in-store physical"*.
- No PC SKU yet. The PC add-on is a scenario that *"should err too aggressive … as it assumes no PC cannibalization of console"*.
- Panel starts in 2019, so there is no RDR2 comparable.
- Sales curves are *"unlikely to exactly mirror other comparables"*. Outputs *"will update weekly (potentially meaningfully)"*.
- ASP *"may continue to moderate thru launch"*: the early skew is to the Ultimate Edition.
- The RBLX overlap excludes Roblox gift-card purchases.

**Inferred by us (not stated by Yipit):**
- **Wallet- or gift-card-funded console purchases.** PS Store and Xbox purchases paid from wallet balance may still send receipts, but users who buy PSN/Xbox cards at retail are a distinct, possibly younger cohort. Receipt capture probably depends on platform email behaviour.
- **On-console purchases** made with an account email that is not linked to Edison are invisible. Edison users are not representative of console-first gamers. The ratio-to-comparable method assumes coverage equals B6/MWII coverage, so any GTA-specific skew passes straight into the estimate (e.g. broader, more casual or younger audience, more physical, more gift cards).
- **Online physical pre-orders** (Amazon, Walmart, Target, Best Buy, GameStop) leave email receipts. It is unclear whether Yipit includes them or restricts to digital storefronts. "Digital only" suggests they are excluded, and that is a large channel for a holiday launch.
- **International**, roughly half or more of units, is assumed to scale as it did for B6. US share for GTA may differ (Rockstar's EU/LatAm strength).
- **Cancellations and refunds** are not mentioned. PS Store pre-orders can be cancelled until about 14 days before release, so gross pre-orders may overstate net.
- **Charge timing.** Some storefronts charge at or near release. If a confirmation receipt is counted while the charge comes later, double-counting or timing-shift risk exists.
- **Bundles.** Console bundles with GTA VI (e.g. a PS5 bundle) may not show a GTA line item, or may carry a $0/bundled price.
- **Edition mix instability.** Ultimate share moved 92% → 43% → 22% → ~91% between Vol. 1 and Vol. 14. That points to a classification or panel change, or a very small early sample. Yipit gives no explanation.
- **Comparable dependence.** Opening-weekend estimates swung from 11m to 25m depending on the comparable (Vol. 16). Vol. 17 rests on B6 alone, whose calibration point is ">7m opening weekend", a company "more than" figure rather than a precise number.
- **"Opening weekend" definition** drifted from *"first 3 days post launch"* (Vol. 14–16) to *"thru 11/22"* (Vol. 17). The game launches Thu 11/19, so 11/19–11/22 is 4 days.

## 6. Open questions to ask Yipit

1. Which merchants and storefronts are parsed: PS Store, Microsoft Store, Rockstar Store, Amazon/Walmart/Target/Best Buy/GameStop (digital codes and physical online)? Is online physical pre-order counted or excluded?
2. How is a GTA VI unit identified (item text, SKU, price)? How are confirmation, charge and shipping receipts de-duplicated?
3. Are cancellations and refunds netted? Is a PS/Xbox pre-order counted at order or at charge?
4. Is the panel a fixed Edison cohort? What is the panel size and normalisation? Did the 4 Sep "new transaction panel" transition affect the GTA series?
5. Why did Ultimate mix swing (92% → 43% → 22% → 91%) between Vol. 1 and Vol. 14?
6. What is the size of the digital/physical adjustment per comparable? Can we get the working XLS and Exhibit 1A/1B/2 values?
7. What exact B6 (and MWII) reported figures and windows calibrate the scale? How is ">7m" treated?
8. Is "opening weekend" 3 days or thru 11/22 (4 days)? Are the comparables' windows aligned?
9. How do they handle gift-card and wallet-funded purchases and bundles?
10. How will the post-launch window and PC release be tracked?
