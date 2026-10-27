"""Finding notes for card_gross_adds.ipynb, written after reading the executed results (data to 2026-10-21)."""
FINDINGS = {
    "panel": """
**Finding: the panel is fixed.** All 3,614,559 members share one start date (2022-01-01) and one static weight. Nobody joins later. After `TXNS_CORE` drops 8,778 affected accounts, the denominator is **3,605,781** members (weighted: 6.12M).

The active base is also close to fixed: 99.9% of members had a transaction in the trailing 35 days at every month-end since 2023. That is survivor-like, as in the earlier card work. So "% of panel" here is effectively "% of active card users in the panel", which is directly comparable over time. It is not "% of the US population": the panel skews toward heavy card users, so treat it as a read-across.
""",
    "claude": """
**Finding: the hypothesis holds; bare `ANTHROPIC` is not a plan.**
- Bare `ANTHROPIC` rows come about 3 times per member-month, with a median gap of 1 day. Only 2% are 26-35 days apart, and the common amounts are $5 / $10 / $11 / $45: API credit top-ups and auto-reloads.
- The subscription descriptors (`CLAUDE.AI SUBSCRIPTION`, then `ANTHROPIC* CLAUDE SUB` / `ANTHROPIC* CLAUDE` from 2026-05-30) are about 96% on $20 / $100 / $200 plus tax, with a 30-day median gap.
- Most bare-`ANTHROPIC` payers (15.0k of 19.7k) also pay a subscription, so counting bare rows would double count members and create false adds. They are excluded, except about 1% that sit on an exact list price and repeat monthly.
- `Team` descriptors (median $133) are excluded.
- Google Play (`GOOGLE *CLAUDE BY ANTH…`, unbranded) behaves like a subscription and is kept.
""",
    "chatgpt": """
**Finding.**
- `CHATGPT SUBSCR` and Google Play `GOOGLE *CHATGPT` are clean subscription families: 98-99% on price, about 90% recurring.
- Bare `OPENAI` is mixed. It is mostly API credits ($12 median, 30% recurring), but since late 2025 some ChatGPT subscriptions post under it. Those rows are kept only when the member repeats a plan price 25-35 days apart, which keeps 57% of the rows.
- `CHATGPT (other)` mixes credit packs, Business seats and Sora, and is filtered row by row.
""",
    "gemini": """
**Finding.**
- There is no Gemini-specific descriptor. AI plans and storage both bill as `GOOGLE ONE`, so the plan is read from the amount, and price collisions are resolved by each member's payment rhythm. Only 32% of `GOOGLE ONE` rows are AI-tier payments; the rest are storage.
- The 2024-25 `GOOGLE ONE AI PREMIUM` descriptor is AI-only (100% kept).
- From 2026-09-15 Google bills with SKU codes (`G1AI101M` / `G1SK003M`, unbranded). Most of those rows are $1.99-2.99 storage.
- The Aug-Sep 2026 dip in Gemini subscribers coincides with that descriptor transition and also shows in the earlier keyword extract. It is likely a billing or descriptor artefact, not real churn.
""",
    "perplexity": """
**Finding.**
- Web (`WWW.PERPLEXITY.AI`) and Google Play are subscription families: about 80-90% on price, about 75% recurring.
- From 2026-06-08 to 10-04 the Stripe descriptor dropped the brand (`PRO WWW.PERPLEX…`, unbranded). The patch recovers most of it, but the generic forms (`PRO, SAN FRANCISCO, CA`, bare `PRO`) can't be matched safely. This leaves a ~20% dip over that window.
- Credits / API and Enterprise rows are excluded.
""",
    "muse": """
**Finding: Muse is barely visible on cards.**
- Brand 11021 is Facebook ad spend and in-app purchases. Its `GOOGLE *FACEBOOK` Play rows are mostly under $3 and can't be told apart from other Facebook purchases.
- Muse's own descriptors are tiny in this panel: `METAPAY META.COM` has 195 rows (about a third are pre-Muse Meta One look-alikes), and `GOOGLE *MUSE FROM META` has 31 rows from 2026-10-07.
- About 90 TR30 subscribers is too few to read. Most Muse billing is likely Apple, or not yet in the panel. The e-receipt data is the better source for Muse.
""",
    "crosscheck": """
**Finding: with the patch, the brand pull matches the earlier keyword extract.**
- Claude and Perplexity agree at a ratio of 1.00 (Perplexity is 0.93 in Jul-Sep 2026, the brandless-descriptor window). ChatGPT is 1.00 to Sep 2025, then 1.01-1.02: the brand pull now also matches the truncated `GOOGLE *CHATGP` descriptor (fixed 2026-10-26), which the Oct-19 keyword extract missed.
- Gemini shows about 2x more AI Pro payments in 2024. The brand pull catches `GOOGLE *ONE AI PREMIUM…` descriptors that the old keyword prefilter missed, so the new series is the better one.
- Without the patch, ChatGPT would be about 3% of its true level, Claude about 57% before 2025, Perplexity about 10% in Jun-Sep 2026, and Gemini about half from mid-September 2026. The brands need these merchants mapped before `TXNS_CORE` can be used on its own.
""",
    "provider": """
**Findings (TR30, data to 2026-10-21; the last ~10 days are still filling).**
- **ChatGPT:** about 200k members, 5.5% of the panel, up from 95k a year ago. Gross adds stepped up sharply in Aug-Sep 2026 (TR30 adds peaked at about 37k).
- **Claude:** 36.6k, 1.0% of the panel, up about 8x on the year. Most of the growth came in Feb-May 2026, when TR30 adds peaked at about 10k.
- **Gemini:** 57k, 1.6% of the panel. **Most of that comes from the 2TB plan, counted as AI Plus from 2026-01-27** (an earlier decision). That rule also creates a one-off spike of about 28k "gross adds" in Feb 2026, when existing 2TB subscribers were reclassified rather than signing up. Excluding 2TB, Gemini is about 24k (0.7%).
- **Perplexity:** about 1.8k (0.05%). **Muse:** too small to read on cards.
- **Share of TR30 subscribers:** ChatGPT about 68%, Gemini 19%, Claude 12%. Excluding Gemini's 2TB plan: ChatGPT about 76%, Claude about 14%, Gemini about 9%.
- Weighted and unweighted panel shares are within about 0.2pp of each other.
""",
    "plan": """
**Findings by plan.**
- **ChatGPT Plus:** about 164k members, 4.4% of the panel.
- **ChatGPT Go:** about 35k, 0.9% of the panel. It launched 2026-01-16, so roughly 1 in 6 paying ChatGPT members on cards is on Go.
- **Claude Pro (monthly):** 31k, 0.87%. Max 5x is 3.9k and Max 20x is 1.3k.
- **Gemini:** AI Pro (monthly) is 14k and AI Plus (monthly) is 10k.
- **Annual plans:** each is under 1k TR30 payers, because annual subscribers only appear in the month they pay. A subscriber count for annual plans would need a 365-day window.
""",
}
