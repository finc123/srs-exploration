"""Finding notes for card_ereceipt_comparison.ipynb, written after reading the executed results (card data to 2026-10-21,
e-receipts to 2026-10-20; window Jan 2024 - Aug 2026). Correlations are of monthly levels unless marked MoM."""
FINDINGS = {
    "removed": """
**Finding: the subscription-state rule removes 13-46% of e-receipt cancellations, except for Claude.**
- **Claude:** direct 1.7%, iTunes 3.1%. Its sign-ups and cancellations are both well reported.
- **ChatGPT:** direct 32%, Google Play 30%, iTunes 16%. **Gemini:** 36-46%. **Grok:** 40-46%. **Perplexity direct:** 37%.
- These are cancellations with no sign-up or paid email since the previous cancellation: missed sign-up emails (ChatGPT direct ~16% per the NIQ missing-email study), cancelled free trials (Grok, Gemini), and repeated cancel emails more than 45 days apart.
""",
    "chatgpt": """
**Finding: card and e-receipts agree on ChatGPT's trend until mid-2026, then diverge; Yipit tracks the e-receipts.**
- **Level:** cards see 4.2x the e-receipt web adds and 6.2x on Google Play. The two panels differ in size, and direct e-receipts carry only the sign-up email.
- **Trend:** monthly levels correlate (adds 0.82 web / 0.96 Play; churn 0.90 / 0.89), but month-on-month changes much less (adds 0.54 / 0.41, churn about 0).
- **Churn diverges from Mar 2026:** card web churn climbs from 8k to 11-12k a month, while e-receipt direct cancellations stay flat at about 2.2k. Direct sends no renewal receipts, so a lapse without a cancellation email is invisible on e-receipts.
- **Card web adds jump Jul-Sep 2026** (Plus 12k → 21k → 26k → 27k; Go 2k → 7k). The adds look like real paying subscribers: 76-80% are new to ChatGPT in the panel, they pay full price, they renew within 40 days at the usual rate (83%), and under 1% came from Google Play.
- **E-receipt direct adds surge at the same time** (2.3k → 4.4k → 5.3k), while **iTunes adds fall** (5.3k → 2.9k). The share of direct adds with an earlier iTunes ChatGPT subscription rises from 12% to 21-22%, and the share that cancelled iTunes within 60 days doubles (4.5% → 9%). Roughly 30% of the extra direct adds had been iTunes subscribers; the rest are new sign-ups going to the web rather than the App Store.
- **So this is mostly a shift of channel, not extra subscribers.** E-receipt total adds rise only modestly, in line with Yipit (+30% Jun-Aug). Cards can't see Apple, so they record the move to the web as growth. A card-only ChatGPT series overstates growth whenever subscribers move from iTunes to the web.
- **Yipit vs e-receipt totals:** adds 0.97, churn 1.00. This is consistent with Yipit being an e-receipt panel. Card vs Yipit: 0.91 / 0.93.
""",
    "claude": """
**Finding: Claude is where the two sources agree. Both levels and trends match.**
- **Totals:** card / e-receipt = 1.09 on adds and 1.17 on churn. Correlation 0.98 / 0.96; month-on-month 0.94 / 0.48. Net adds correlation 0.98.
- **Web:** adds ratio 1.29, correlation 0.98 (MoM 0.92). The e-receipt panel sees direct payments monthly, so both sources measure the same thing.
- **Churn diverges from Apr 2026:** by Aug, card web churn is about 3.3k against 1.8k e-receipt cancellations. That is the gap between lapses (card) and cancellation emails, which grows after the Feb-Mar 2026 sign-up wave. On Google Play, card churn jumps in Aug 2026 (231 → 482). That matches the card's missing Google-billed charges (see Gemini) rather than a real change.
- **Yipit** matches the e-receipts almost exactly (correlation 1.00 / 1.00).
""",
    "gemini": """
**Finding: with the missing Google One descriptors added, card Gemini is continuous, but the 2TB subscribers enter the two sources at different times.**
- **The Jul-Aug 2026 card hole is closed.** Card paying accounts now run 51.0k (Jun) → 53.5k (Jul) → 54.0k (Aug) → 58.7k (Sep), and August churn falls from 15k to 5.3k. The missing charges were on the truncated `GOOGLE *GOOGLE MOUNTAIN VIE` (11-12k accounts a month in Jul-Aug) and untagged `GOOGLE ONE, …` merchids (added 26 Oct).
- **False-positive risk:** 6% of card Gemini accounts (6k of 100k) appear only under the generic `GOOGLE *GOOGLE MOUNTAIN VIE`. They are 14% of August adds and could be other Google charges at AI prices.
- **2TB timing:** cards add the 2TB subscribers in Jan-Feb 2026 (about 29k in Feb, the 27 Jan rule date). The e-receipts add them in May-Jun 2026 (Google Play 8.5k in Jun), when the receipt text changed to `Google AI Plus (2 TB)`. Yipit also shows them in Jun. So card and e-receipt adds correlate poorly (0.42), even though both count the same subscribers.
- **Card churn rises from Mar 2026** (about 1k → 5.3k a month by Aug). This is the larger 2TB base churning at storage-plan rates; e-receipt churn rises less (about 1.0k → 1.4k).
- **E-receipt vs Yipit** now match on adds (0.99, up from 0.82 before the rename was counted) and on churn (0.97).
""",
    "perplexity": """
**Finding: Perplexity is too thin and too promo-driven for either source to read cleanly.**
- **Direct adds:** e-receipts see 3x the card's adds (13.6k vs 4.4k). Direct welcome emails include promos and trials that never reach a paid charge, e.g. the Jul 2025 spike of 3.3k. Card adds are paid charges only.
- **Churn levels are similar** (card / e-receipt 1.04 on web), but monthly correlation is only 0.46.
- **Google Play** is under 60 adds a month on both sources: noise.
- **Yipit** correlates with e-receipt churn (0.93) but not with adds (0.41). Yipit's own adds are volatile (e.g. Sep 2025 660 a month).
""",
    "grok": """
**Finding: card and e-receipt Grok trends agree on Google Play, and each source has a channel the other can't see.**
- **Google Play:** card / e-receipt = 7.1x on adds and 6.9x on churn, with level correlations 0.99 and 0.94.
- **Cards alone see web billing** (~1k adds a month in 2026); **e-receipts alone see iTunes** (~500 a month). There's no Yipit series to check against.
- **Totals** (sum of channels) correlate 0.96 on adds and 0.90 on churn, but each total is built from a different channel mix.
""",
    "summary": """
**Summary for the web-app decision**
| Provider | Level agreement | Trend agreement | Main issue |
|---|---|---|---|
| Claude | Close (1.1-1.2x) | Strong (0.96-0.98, MoM adds 0.94) | Card churn runs ahead of cancel emails from Apr 2026 |
| ChatGPT | Card 4-6x | Levels 0.8-0.96, MoM weak | Direct e-receipts are sign-up only; cards miss iTunes, so the Jul-Sep 2026 iTunes → web shift reads as card growth |
| Gemini | Card 1.3x adds, 1.8x churn | Weak (0.42 adds) | 2TB subscribers enter cards in Feb 2026 but e-receipts and Yipit in Jun 2026; generic Google descriptor adds some false positives |
| Grok | Card 7x on Play | Strong on Play | Each source covers a channel the other doesn't (web vs iTunes) |
| Perplexity | Mixed | Weak | Small samples; promo-heavy direct welcomes |

- **Yipit tracks the e-receipts** wherever both exist (churn correlation 0.93-1.00), as expected for an e-receipt panel.
- **Card descriptor gaps read as churn.** The ChatGPT `CHATGP` and Gemini `GOOGLE *GOOGLE MOUNTAIN VIE` fixes both closed holes that had shown as churn followed by re-adds. The Claude Google Play churn jump in Aug 2026 (231 → 482) may be the same issue and is unchecked.
- **Cards miss Apple**, so a shift between iTunes and the web (ChatGPT, Jul-Sep 2026) reads as card growth or decline.
""",
}
