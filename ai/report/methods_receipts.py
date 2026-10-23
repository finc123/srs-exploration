"""Methods and caveats text for the e-receipt report (summarised from filters_receipts/*_report.md)."""

PANEL_NOTES = {
    "us": "US: NIQ Slice (SRS_SLICE.COMMON.ITEMS_LIVE), mailboxes active today (a mailbox that has left is removed from history). Denominator: NIQ 84-day active mailboxes. Direct web billing is visible for ChatGPT (sign-up receipts only) and Claude; direct X Corp, xAI, Perplexity, Cursor and Muse web receipts are absent, so those providers are app-store only here.",
    "eu": "Europe total is the sum of five Fox country panels (unweighted). Fox has cancellation emails only for ChatGPT direct, so other churn comes from renewal receipts stopping.",
    "uk": "UK: NIQ Fox. A user with no receipt of any kind for 90 days has left the panel; their subscriptions are removed.",
    "de": "Germany: NIQ Fox.", "fr": "France: NIQ Fox.", "es": "Spain: NIQ Fox.", "it": "Italy: NIQ Fox.",
}

ROWS = [
    ("ChatGPT", "Apple `ChatGPT : ChatGPT <plan> (Monthly)`; Google Play `ChatGPT <plan> (ChatGPT)…OpenAI`; EU PayPal (payee openai) and Stripe; direct `Chat GPT` / `chatgpt` sign-up receipts. Cancels: Chat GPT / iTunes / Google Play Cancellation (US), Fox email_type cancel (EU direct).",
     "Go, Plus (M/A), Pro 100, Pro 200, Pro 500",
     "Direct sends sign-up receipts only: churn is modelled from ChatGPT's Apple / Google Play / PayPal survival curve in the same panel (unmodelled line shown). US direct 'Payment' rows are API credits (excluded). Business/Team, credits, Sora and third-party 'powered by ChatGPT' apps excluded."),
    ("Claude", "US direct `Anthropic` 'Payment' at list prices; EU `anthropic` and Stripe (plan named); Apple and Google Play (plan named); EU PayPal/Klarna. Cancels: Anthropic / iTunes / Google Play Cancellation (US only).",
     "Pro M/A, Max 5x, Max 20x",
     "US $200 Pro annual vs Max 20x by repeat within 25–40 days, confirmed by Anthropic's unpriced Pro/Max subscription items. Bursts of 3+ list-price payments within 20 days are usage top-ups (excluded). EU direct shifts to Stripe in Sep 2026 (no effect on subscriptions)."),
    ("Gemini", "Google Play `Google AI Pro (5 TB) (Google One)` etc. (Google One web purchases bill through Play); Apple (Gemini, Gmail, Photos, Drive apps); EU PayPal to Google. Cancels: Google One / Google Play / iTunes Cancellation (US only).",
     "AI Pro (incl. AI Premium), AI Plus, AI Plus 2 TB (from 27 Jan 2026), Ultra, Ultra 5x",
     "Storage-only plans, welcome emails, trials, credits and partner bundles (Best Buy, Verizon, Fios, T-Mobile) excluded. Unnamed Play cancels take the plan of the user's latest Google One charge; storage and unresolvable ones excluded."),
    ("Grok (xAI)", "Apple `Grok AI : SuperGrok (Monthly)`; Google Play `SuperGrok (Grok AI)`; EU Stripe `grok xai : supergrok`. Cancels: iTunes / Google Play Cancellation (US).",
     "SuperGrok, Lite, Heavy, Plus (M/A), 3-month Apple offer (quarterly), The X Subscription from 12 Oct 2026",
     "Credits and trials excluded. No US direct xAI receipts."),
    ("X Premium+", "Apple `X : X Premium Plus`; Google Play `Premium+ (X)`; EU Stripe.",
     "Premium+ M/A",
     "Basic and Premium excluded (106k US, 24k EU charges). Unnamed 'Twitter Inc' Play cancels apply to Premium+ holders only."),
    ("Muse", "Apple bare 'Power Plan' / 'Maximum Plan' and 'Power Plan : Power Plan (Monthly)' from 7 Sep 2026; Google Play 'Power/Maximum Plan (Muse from Meta)'.",
     "Power, Maximum (monthly)",
     "Unpriced 'Muse from Meta … /month' Apple rows are confirmations. Web billing (Meta Pay) sends no receipt. US only."),
    ("Cursor", "Apple `Cursor : Pro / Pro+ / Ultra (Monthly)` from 29 Jun 2026; EU PayPal, Klarna, Apple.",
     "Pro, Pro+, Ultra",
     "Direct (Stripe) receipts are absent, so receipts show only a handful of payers: use the card panel for Cursor."),
    ("Perplexity", "Apple `Perplexity … : Perplexity Pro/Max`; Google Play `Perplexity Pro/Max (…)`; Samsung.",
     "Pro M/A, Max M",
     "Direct sign-ups arrive only as unpriced 'Welcome to Perplexity Pro' emails (mix of paid, trial and partner promos), so direct is absent: use the card panel for web subscribers."),
]

RULES = """
<h3>Subscriber rules</h3>
<ul>
<li><b>Gross add:</b> the first paid receipt of a subscription. Receipt history from before a mailbox joined the panel is used, so no tenure rule is needed and recent history revises slightly as mailboxes join.</li>
<li><b>Continuation:</b> the next paid receipt within 75 days of a monthly charge (135 quarterly, 400 annual), with no cancellation email in between. 75 days tolerates one missed renewal email.</li>
<li><b>Churn:</b> the earlier of a cancellation email (dated on the email day) or renewals stopping (dated one month after the last payment). Cancellation emails alone capture only 20–85% of churners, unevenly by channel, so they are not used on their own.</li>
<li><b>Sign-up-only channels:</b> ChatGPT direct follows the survival curve of ChatGPT's renewing channels in the same panel.</li>
<li><b>Panel exit:</b> US mailboxes that are now inactive are removed. In Europe, a subscription that lapses after the user stopped sending any receipts (90 days quiet) is removed from history.</li>
<li><b>Channels:</b> Apple, Google Play, PayPal, Stripe and direct where visible. Channels with no paid receipts in a panel are left out and disclosed per provider.</li>
<li><b>Rows flagged spam in Fox are excluded; deleted and trashed receipts are kept.</b></li>
</ul>
"""

OPEN = """
<h3>Open decisions</h3>
<ul>
<li><b>Coverage by channel differs from the card panel:</b> receipts see app-store billing (invisible on cards) but miss most direct web billing for X, Grok, Perplexity, Cursor and Muse. Combine the two sources, or read each provider from the source that sees its main channel.</li>
<li><b>Perplexity direct:</b> use 'Welcome to Perplexity Pro' emails as a sign-up proxy (they mix paid, trial and partner promos), or leave direct out (current).</li>
<li><b>ChatGPT direct:</b> modelled churn (current) vs the unmodelled line.</li>
<li><b>The X Subscription:</b> own provider line or within Grok (current).</li>
</ul>
"""


def html() -> str:
    t = "<div class='panel scroll'><table><thead><tr><th>Provider</th><th>Receipts matched</th><th>Plans</th><th>Exclusions and rules</th></tr></thead><tbody>"
    for r in ROWS:
        t += "<tr>" + "".join(f"<td style='white-space:normal;text-align:left;min-width:160px'>{c}</td>" for c in r) + "</tr>"
    return t + "</tbody></table></div>" + RULES + OPEN
