"""Methods and caveats text for the card-panel report (summarised from filters/*_report.md)."""

PANEL_NOTES = {
    "omega": "US: Consumer Edge 2022 consistent-shopper panel (3.6M members). 99.5% of members are still active at the data end, so panel exits are rare and the retroactive exit rule barely changes US history. Apple App Store billing is invisible (no app name); Google Play is included where the app is named.",
    "es": "Spain: from June 2026 some Cursor and Claude charges arrive under a masked merchant category (MCC 8299, 'schools and educational services'). Those charges are not captured, so Spanish Cursor and Claude subscribers are understated from June 2026 and their churn is overstated.",
    "eu": "Europe total is the sum of the five Fable country panels (unweighted). European Google Play charges usually lack the app name, so European counts are effectively web billing only, apart from Gemini (Google One is billed the same way on web and Play).",
    "uk": "UK: Fable panel. Google Play charges usually lack the app name, so counts are effectively web billing only.",
    "de": "Germany: Fable panel. Perplexity has a large discounted base from the Telekom free-year promotion (2025), which converted to paid in early 2026.",
    "fr": "France: Fable panel (FR_V3). Banks fold FX fees into USD-billed charges, and reporting lag averages about 16 days, so the latest month fills in late.",
    "it": "Italy: Fable panel.",
}

ROWS = [
    ("ChatGPT", "OPENAI *CHATGPT, CHAT GPT, PayPal OpenAI; Google Play GOOGLE *CHATGPT. Bare OPENAI kept only when a plan-band amount recurs monthly (otherwise API).",
     "Go, Plus, Pro 100, Pro 200, Pro 500 (all monthly; no consumer annual plan).",
     "Team/Business rejected by seat-multiple amounts; credit packs and Sora add-ons excluded; legacy USD billing in Europe mapped via FX."),
    ("Claude", "CLAUDE.AI SUBSCRIPTION (to June 2026), ANTHROPIC* CLAUDE SUB, masked '<name>.ai subscription' and claudeai in Fable; Google Play.",
     "Pro monthly and annual, Max 5x, Max 20x.",
     "$200 / £180 / €180+VAT is Pro annual or Max 20x: a repeat within 25–40 days means Max 20x, a one-off means Pro annual (provisional for the last 40 days). Bare ANTHROPIC is API unless a list price recurs monthly."),
    ("Gemini", "Google One / Google Storage descriptors, and from 15 Sep 2026 Google One SKU codes (G1AI…, G1SK…; masked as 'ttttt' in Fable).",
     "AI Pro (incl. AI Premium), AI Plus, Ultra, and the 2TB plan (counted as AI Plus 2TB from 27 Jan 2026).",
     "AI tiers only. Where an AI price equals a storage price (e.g. $19.99), SKU codes decide; otherwise a repeat within 25–40 days means monthly AI, a one-off means storage annual. The 2TB plan's existing subscribers enter as gross adds in Jan–Feb 2026 (~24k in the US), which inflates those months."),
    ("Grok (xAI)", "XAI LLC / GROK XAI, X.AI; Google Play.",
     "SuperGrok monthly and annual, Heavy, Lite, Plus, and The X Subscription (from 10 Oct 2026).",
     "$300 and $100 collisions resolved by payment gaps; credit top-ups excluded."),
    ("X Premium+", "X CORP. PAID FEATURES (masked in the US panel as 'CORP. PAID FEATURES' from June 2024); Google Play.",
     "Premium+ monthly and annual (price ladder 2023-10, 2024-12, 2025-02).",
     "Basic and Premium tiers excluded by price. PayPal *X CORP rows belong to another merchant and are excluded."),
    ("Muse", "METAPAY … META.COM (no '*'); Google Play GOOGLE *MUSE FROM META (from 7 Oct 2026).",
     "Power and Maximum, monthly.",
     "US only (no UK/EU launch). About 50 payers, so the series is very noisy. Meta One/Verified look-alikes excluded by price."),
    ("Cursor", "CURSOR, AI POWERED IDE family; usage invoices (CURSOR USAGE) excluded.",
     "Pro monthly and annual, Pro+, Ultra.",
     "Billed in USD everywhere; European amounts converted with monthly FX. Teams seats excluded. New sign-ups since 12 Oct 2026 move to The X Subscription and are counted under Grok."),
    ("Perplexity", "PERPLEXITY / WWW.PERPLEXIT, plus brandless descriptors used 8 Jun to 4 Oct 2026 (PRO SAN FRANCISCO, MAX …, cb pro).",
     "Pro monthly and annual, discounted Pro ($4.99/$10 promo), Max monthly and annual.",
     "Enterprise, API and Computer credits excluded. Partner promotions (Telekom, Bouygues, Revolut, TIM, PayPal/Venmo) create conversion waves about 12 months later."),
]

RULES = """
<h3>Subscriber rules</h3>
<ul>
<li><b>Gross add:</b> first payment of a subscription by a member whose current activity spell started more than 35 days earlier. Subscriptions from members new to the panel are excluded at both ends.</li>
<li><b>Lapse:</b> no renewal within 45 days of a monthly payment (365 + 35 days for annual). The churn is then dated at the end of the paid period, one month after the last monthly payment, so churn for the latest ~45 days is provisional. (A 35-day window was tested first: 3–6% of renewals post 36–66 days after the previous charge, which added roughly 3–6 points of false monthly churn.) A lapse is churn if the member transacted in the 30 days before it; otherwise it is a panel exit and the whole subscription is removed from history.</li>
<li><b>Reactivation:</b> a gross add by a member who previously churned from the same provider (or plan).</li>
<li><b>Plan level vs provider level:</b> at plan level, switching tier or cadence is a churn from one plan and an add to another; at provider level it is continuous.</li>
<li><b>Active panel members:</b> any transaction in the trailing 35 days. This is the denominator for subscribers per 1,000.</li>
<li><b>Channels:</b> web billing plus app-named Google Play. Apple App Store billing is invisible in both panels and is excluded everywhere.</li>
<li><b>No end cutoff:</b> all data is used. The latest month is partial, and recent churn, exits and gross adds will be revised as late data and renewals arrive.</li>
</ul>
"""

OPEN = """
<h3>Open decisions</h3>
<ul>
<li><b>Spain masking (Cursor, Claude):</b> adopt an MCC 8299 rule at exact Claude prices plus monthly recurrence or a prior Claude payment (estimated 2–5% false positives; about +450–500 Claude payers a month). New Cursor sign-ups can't be identified reliably there.</li>
<li><b>Gemini 2TB step:</b> treat the existing 2TB base as opening stock on 27 Jan 2026 rather than as gross adds.</li>
<li><b>The X Subscription:</b> keep under Grok, or report it as its own line now that it bundles Grok, Cursor and X Premium.</li>
<li><b>Bare OPENAI / ANTHROPIC recurrence rule:</b> keep (current) or exclude all bare rows as API.</li>
<li><b>Fill rates:</b> measure how late data arrives in each panel to decide how many recent days to treat as provisional.</li>
</ul>
"""


def html() -> str:
    t = "<div class='panel scroll'><table><thead><tr><th>Provider</th><th>Descriptors matched</th><th>Plans</th><th>Exclusions and rules</th></tr></thead><tbody>"
    for r in ROWS:
        t += "<tr>" + "".join(f"<td style='white-space:normal;text-align:left;min-width:160px'>{c}</td>" for c in r) + "</tr>"
    return t + "</tbody></table></div>" + RULES + OPEN
