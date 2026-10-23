"""Builds ai_subs_methodology.html: a bookmarkable explainer of how the ai_consumer job measures gross adds,
churn and subscribers from e-receipts. Data tables are embedded from:
  - srs-ai-consumer/.../engine/params/lapse_windows.csv (windows, capture, churn-rate source)
  - docs/plan_channel.csv (receipt_events: paid receipts by region x provider x plan x channel, Oct 2025 - Oct 2026)
Run: python build_methodology_html.py
"""
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
WINDOWS = HERE.parents[2] / "srs-ai-consumer/workflows/jobs/ai/consumer/artifacts/engine/params/lapse_windows.csv"

w = pd.read_csv(WINDOWS)[["region", "prov", "channel", "capture_all", "capture_R", "W_monthly", "W_source", "rate_source"]]
p = pd.read_csv(HERE / "plan_channel.csv")
p.columns = [c.lower() for c in p.columns]
p["cur"] = p.cur.str.upper()

# Per-provider receipt patterns and exclusions (from METHODOLOGY.md and filters_receipts/*_report.md).
PROVIDERS = {
    "chatgpt": dict(
        name="ChatGPT",
        us="Apple <code>ChatGPT : ChatGPT &lt;plan&gt; (Monthly/Annual)</code>; Google Play <code>ChatGPT &lt;plan&gt; (ChatGPT) Auto-renewing subscription</code>.",
        eu="Apple <code>chatgpt || chatgpt &lt;plan&gt; (&lt;period&gt;)</code> (bare <code>chatgpt</code> from June 2026, plan from the amount); Google Play (including PayPal payments to Google); PayPal with payee <code>openai</code>; Stripe OpenAI invoices.",
        plans="Go, Plus (monthly, annual), Pro 100, Pro 200, Pro 500. Plan from the receipt text, else from the amount band for the currency.",
        excluded="<b>Direct ChatGPT</b> (US sender <code>Chat GPT</code>, Fox <code>chatgpt</code>): sign-up receipts only, with 0–4% renewals, so churn can't be measured. Also excluded: API prepaid <code>Payment</code>, credits, Codex, Sora, Business/Team/Enterprise, unpriced Apple confirmations, trials, and third-party “powered by ChatGPT” apps.",
        note="Understated: about 33% of tracked US subscribers, against about 46% with direct included."),
    "claude": dict(
        name="Claude",
        us="Direct <code>Anthropic</code> <code>Payment</code> at list prices ($20, $10 promo, $100, $200, $216). A $200 that repeats monthly is Max 20x; a one-off $200 is Pro annual. Apple <code>Claude by Anthropic : Claude Pro - Monthly</code>; Google Play <code>Claude Pro Subscription (Claude by Anthropic)</code>.",
        eu="<code>anthropic</code> and Stripe <code>anthropic ireland</code> with the plan named; Apple; Google Play; PayPal/Klarna (price only).",
        plans="Pro (monthly, annual), Max 5x, Max 20x.",
        excluded="Direct amounts that aren't list prices (credits, usage, prorations), bursts of 3+ payments within 20 days (usage top-ups), unpriced <code>Pro/Max subscription</code> items, Apple confirmations, EU extra usage, team plans, gifts.",
        note="In September 2026 EU direct fell and Stripe rose, because of a Fox sender migration. Read them together."),
    "gemini": dict(
        name="Gemini",
        us="Google One AI plans: Google Play <code>Google AI Pro (5 TB) (Google One) … Auto-renewing subscription</code> (Google One web purchases bill through Play); Apple <code>Google Gemini : Google AI Pro (2 TB) (Monthly)</code>.",
        eu="Google Play; Apple; PayPal with payee <code>google</code> (Play duplicates dropped).",
        plans="AI Pro, AI Plus, AI Plus 2 TB (the bare 2 TB plan from 27 Jan 2026), Ultra, Ultra 5x (each monthly or annual).",
        excluded="Storage-only Google One (100 GB–5 TB before 27 Jan 2026), unpriced Google One welcome emails, trials, partner promos (Best Buy, Verizon, Fios), add-ons.",
        note="The Jan–Feb 2026 step is the 2 TB plan moving into AI Plus 2 TB. The 20 Oct meeting asked for Gemini shown with and without this storage-bundled tier."),
    "grok": dict(
        name="Grok (incl. X Premium+)",
        us="Apple <code>Grok AI : SuperGrok (Monthly)</code>, <code>X : X Premium Plus</code>; Google Play <code>SuperGrok (Grok AI)</code>, <code>Premium+ (X)</code>; the X Subscription in-app (<code>Plus/Super (X)</code>) from 12 Oct 2026.",
        eu="Apple; Google Play; Stripe <code>grok xai : supergrok</code> (from July 2025); PayPal with payee <code>twitter</code>.",
        plans="SuperGrok, Lite, Heavy, Plus (monthly, annual), X Premium+ (shown in plan detail), and Apple's SuperGrok 3-month offer (quarterly).",
        excluded="X Basic/Premium, trials, Apple confirmations, credits, creator subscriptions, US <code>Twitter : Payment</code> (X Money). No direct xAI or X web receipts exist.",
        note="Renewals arrive irregularly, so the lapse windows are long (60–91 days) and churn shows up 2–3 months after the last payment."),
    "perplexity": dict(
        name="Perplexity",
        us="App stores only: Apple <code>Perplexity - AI Search &amp; Chat : Perplexity Pro (Monthly)</code>; Google Play <code>Perplexity Pro/Max (…)</code>; Samsung Galaxy Store.",
        eu="Apple; Google Play.",
        plans="Pro (monthly, annual), Max (monthly).",
        excluded="Direct web billing: <code>Perplexity AI</code> sends only unpriced “Welcome to Perplexity (Pro)” emails. Only 11% of them are followed by a payment, because they mix trials and partner promos. Credits, enterprise and trial-ended cancels are also excluded.",
        note="Most Perplexity subscribers (web) are not visible in receipts."),
    "muse": dict(
        name="Muse",
        us="From 8 Sep 2026: Apple bare <code>Power Plan</code> / <code>Maximum Plan</code> at $20 / $100, and <code>Power Plan : Power Plan (Monthly)</code> renewals; Google Play <code>Power Plan (Muse from Meta) Auto-renewing subscription</code>.",
        eu="Not launched.",
        plans="Power, Maximum (monthly).",
        excluded="Unpriced Apple confirmations (<code>Muse from Meta Power Plan $20.00 /month</code>), Play upgrade prorations. Web billing (Meta Pay) sends no receipt.",
        note="Churn becomes observable once its first cohorts pass their window (from late October 2026)."),
}

w = w.astype(object).where(w.notna(), None)
p = p.astype(object).where(p.notna(), None)
DATA = dict(windows=w.to_dict("records"), plans=p.to_dict("records"), providers=PROVIDERS)

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Subscriptions Method</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=Fraunces:opsz,wght@9..144,600&display=swap">
<style>
:root {
  --bg: #f6f7f6; --surface: #ffffff; --fg: #16191c; --muted: #5b6268; --line: #dde1df; --accent: #1f5f8b;
  --accent-soft: #e6eef5; --good: #1d7a4f; --warn: #8a5a00; --warn-bg: #fff4dc; --code-bg: #eef1ef;
  --f-display: "Fraunces", Georgia, serif; --f-body: "IBM Plex Sans", system-ui, sans-serif; --f-mono: "IBM Plex Mono", ui-monospace, monospace;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #121514; --surface: #1a1e1d; --fg: #eceff0; --muted: #a1a8a6; --line: #2e3432; --accent: #7db6e0;
  --accent-soft: #1d2a33; --good: #5fc796; --warn: #f3cf85; --warn-bg: #3a2c0d; --code-bg: #232826; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #121514; --surface: #1a1e1d; --fg: #eceff0; --muted: #a1a8a6; --line: #2e3432; --accent: #7db6e0;
  --accent-soft: #1d2a33; --good: #5fc796; --warn: #f3cf85; --warn-bg: #3a2c0d; --code-bg: #232826; color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.6 var(--f-body); }
.wrap { max-width: 1040px; margin: 0 auto; padding-inline: 16px; padding-block: 32px 80px; display: grid; gap: 36px; }
header { display: grid; gap: 8px; }
.eyebrow { font: 500 11px/1 var(--f-mono); letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
h1 { font: 600 clamp(28px, 4.2vw, 38px)/1.15 var(--f-display); margin: 0; text-wrap: balance; }
h2 { font: 600 22px/1.3 var(--f-display); margin: 0 0 10px; text-wrap: balance; }
h3 { font: 600 16px/1.4 var(--f-body); margin: 18px 0 6px; }
p, li { max-width: 74ch; }
.lede { color: var(--muted); font-size: 16px; margin: 0; }
nav.toc { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 13.5px; }
nav.toc a { color: var(--accent); text-decoration: none; }
nav.toc a:hover { text-decoration: underline; }
section { display: grid; gap: 10px; min-width: 0; }
.panel { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 18px; min-width: 0; }
.formula { font: 500 15px/1.6 var(--f-mono); background: var(--accent-soft); border-left: 3px solid var(--accent); padding: 12px 16px; border-radius: 4px; overflow-x: auto; }
.note { background: var(--warn-bg); color: var(--warn); border-radius: 6px; padding: 10px 14px; font-size: 14px; }
code { font: 12.5px var(--f-mono); background: var(--code-bg); padding: 1px 5px; border-radius: 3px; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; font-variant-numeric: tabular-nums; }
th, td { text-align: right; padding: 7px 9px; border-bottom: 1px solid var(--line); vertical-align: top; }
th:first-child, td:first-child, th.l, td.l { text-align: left; }
th { font: 500 11px var(--f-mono); letter-spacing: .05em; text-transform: uppercase; color: var(--muted); white-space: nowrap; }
tr.total td { font-weight: 600; border-top: 2px solid var(--line); }
.pill { display: inline-block; font: 500 11px var(--f-mono); padding: 2px 7px; border-radius: 999px; white-space: nowrap; }
.pill.full { background: color-mix(in srgb, var(--good) 16%, transparent); color: var(--good); }
.pill.sub { background: color-mix(in srgb, var(--accent) 16%, transparent); color: var(--accent); }
.steps { counter-reset: s; display: grid; gap: 14px; padding: 0; margin: 0; list-style: none; }
.steps > li { counter-increment: s; display: grid; grid-template-columns: 34px 1fr; gap: 12px; max-width: none; }
.steps > li::before { content: counter(s); font: 600 14px/34px var(--f-mono); text-align: center; width: 34px; height: 34px; border-radius: 50%; background: var(--accent); color: var(--surface); }
.steps > li > div { min-width: 0; }
.controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.seg { display: inline-flex; border: 1px solid var(--line); border-radius: 999px; overflow: hidden; }
.seg button { font: 500 13px var(--f-body); color: var(--fg); background: var(--surface); border: 0; padding: 6px 14px; cursor: pointer; }
.seg button + button { border-left: 1px solid var(--line); }
.seg button[aria-pressed="true"] { background: var(--accent); color: var(--surface); }
.seg button:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.prov-card { display: grid; gap: 6px; }
.prov-card dl { display: grid; grid-template-columns: minmax(90px, 140px) 1fr; gap: 6px 14px; margin: 0; }
.prov-card dt { color: var(--muted); font-size: 13px; }
.prov-card dd { margin: 0; min-width: 0; }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
.muted { color: var(--muted); }
footer { color: var(--muted); font-size: 13px; }
</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="eyebrow">ai_consumer job · e-receipt panels · method as of 20 Oct 2026</div>
  <h1>How we count AI subscribers from e-receipts</h1>
  <p class="lede">Gross adds, churn, net adds and the subscriber index for ChatGPT, Claude, Gemini, Grok, Perplexity and Muse, in the US (NIQ Slice) and Europe (NIQ Fox: UK, DE, FR, ES, IT). In one line: <b>gross adds from everyone; churn rates from the inboxes we trust; subscribers = last month + adds − rate × last month.</b></p>
  <nav class="toc" aria-label="Contents">
    <a href="#sources">1 · Sources</a><a href="#gross">2 · Gross adds</a><a href="#churn">3 · Churn</a>
    <a href="#index">4 · Subscribers &amp; net adds</a><a href="#example">5 · Worked example</a>
    <a href="#filters">6 · Filters by provider × plan</a><a href="#caveats">7 · Caveats</a><a href="#where">8 · Where it lives</a>
  </nav>
</header>

<section id="sources">
  <h2>1 · Sources and panels</h2>
  <div class="panel scroll"><table>
    <thead><tr><th>Region</th><th class="l">Receipts</th><th class="l">Member</th><th class="l">Panel rule</th><th class="l">Denominator (per 1,000)</th></tr></thead>
    <tbody>
      <tr><td>US</td><td class="l"><code>srs_slice.common.items_v</code>: NIQ <code>items_extended</code> plus mailbox status, entry/exit dates and panel flags; filtered to fixed <code>merchant_id</code>s</td><td class="l">mailbox</td><td class="l">Active mailboxes only; a mailbox that leaves is removed from all history</td><td class="l">84-day active mailboxes (<code>normal_active</code>), about 1.79M</td></tr>
      <tr><td>Europe</td><td class="l"><code>share_niq.srs.fox_transaction_items</code> (spam excluded)</td><td class="l">user</td><td class="l">No receipt of any kind for 90 days means the user has left</td><td class="l">Users with a receipt in the last 90 days, about 750k</td></tr>
    </tbody></table></div>
  <p>Both panels backfill a mailbox's history when it joins, so recent history revises slightly as the panel changes.</p>
  <p class="muted">We also checked NIQ's separate <code>CANCELLATION_ITEMS</code> view. 99.3–99.9% of its AI cancellation rows are already in <code>items_extended</code>; the rest come from mailboxes that have left the panel (only 74 active-mailbox rows since 2022). It adds nothing for these providers.</p>
</section>

<section id="gross">
  <h2>2 · Gross adds</h2>
  <div class="panel"><ol class="steps">
    <li><div><b>Keep paid receipts only.</b> Each provider's filter keeps priced charges, such as “ChatGPT Plus (Monthly) $19.99” from Apple, and drops welcome emails, unpriced confirmations, trials, credits and business plans. One receipt per member × provider × channel × day.</div></li>
    <li><div><b>Line up each member's receipts by date.</b> A subscription starts at the first receipt, and again after any gap longer than the lapse window <i>W</i> (see section 3).</div></li>
    <li><div><b>Gross add = the first paid receipt of a subscription</b>, counted in the month it lands. A payment after a cancellation email also starts a new subscription (one churn, then one gross add).</div></li>
  </ol></div>
  <p>Gross adds use <b>every</b> panellist on every visible channel. Welcome emails are never counted as adds: only 11% of direct Perplexity welcomes and 54% of Google One AI welcomes are followed by a payment.</p>
</section>

<section id="churn">
  <h2>3 · Churn</h2>
  <div class="panel"><ol class="steps">
    <li><div><b>A subscription churns when no paid receipt arrives within the window <i>W</i></b> after the last one. <i>W</i> is the 99th-percentile gap between consecutive renewals, measured per provider × channel (40–91 days for monthly plans; 135 for quarterly, 400 for annual). Churn is dated when <i>W</i> runs out, not backdated.</div></li>
    <li><div><b>Cancellation emails don't date churn.</b> Even with every NIQ table combined, they cover only 56–88% of real lapses (Apple 62%, Google Play 75–84%, Claude direct 57%), and in Europe there are almost none.</div></li>
    <li><div><b>Problem: missed renewal emails look like churn.</b> On some channels the panel misses renewal receipts. Apple captures about 94% for ChatGPT, so about 1 in 16 is missing. One missing monthly receipt opens a gap of about 60 days, longer than <i>W</i>, so a subscriber who is still paying is counted as churned.</div></li>
    <li><div><b>Fix: measure churn rates only where emails are reliable.</b>
      <ul>
        <li><span class="pill full">full panel</span> Channels capturing ≥ 97.5% of renewals (ChatGPT, Claude and Gemini on Google Play; Claude direct; EU Claude Stripe) use <b>everyone</b>.</li>
        <li><span class="pill sub">reliable subset</span> Everything else, and Apple always, uses only members whose inbox <b>received another regular subscription email that same month</b> (iCloud+, YouTube Premium, Spotify, or another AI app). That proves the inbox was working, so a missing AI receipt is a real stop. In this group Apple captures 99.1% of renewals.</li>
        <li>The check also covers the months after the last payment. A single month without a check email is tolerated if the months either side have one. Members whose inbox stops showing them are dropped from the rate, not counted as churn.</li>
      </ul></div></li>
    <li><div><b>Split into buckets and compute each bucket's rate every month:</b> provider × channel × plan × tenure (1st month, 2–3, 4–6, 7–12, 13+). Rate = churns detected in the month ÷ subscriptions live at the start of the month, in the trusted population. Buckets with under 100 live subscriptions borrow the rate of a broader group.</div></li>
  </ol></div>
  <p>Tenure matters most: new subscribers churn at 15–24% a month, long-standing ones at 2–4%. The rates are applied to <b>all</b> subscribers in each bucket in section 4.</p>
  <div class="controls"><span class="muted">Lapse windows and rate source:</span><div class="seg" id="seg-win" role="group" aria-label="Region"></div></div>
  <div class="panel scroll"><table id="tbl-win"></table></div>
  <p class="muted">Capture = share of expected renewal receipts seen, for all members and within the reliable subset. Where a cell lacks enough renewal gaps, its window is pooled across the provider's channels.</p>
</section>

<section id="index">
  <h2>4 · Subscribers, net adds, share</h2>
  <div class="formula">churn(t) = Σ over buckets [ subscribers in bucket at end of t−1 × bucket's churn rate in t ]<br>subscribers(t) = subscribers(t−1) + gross adds(t) − churn(t)<br>net adds(t) = gross adds(t) − churn(t)</div>
  <ul>
    <li><b>Subscribers</b> (modelled) is the headline. It is built cohort by cohort from January 2024, starting from the observed stock.</li>
    <li><b>Observed subscribers</b>: simply counting open subscriptions in the full panel. Shown as a check. It sits below the modelled count wherever missed Apple emails drop live subscribers.</li>
    <li><b>Share</b> = a provider's subscribers ÷ the total across tracked providers. <b>Per 1,000</b> = subscribers ÷ active panel members × 1,000.</li>
    <li><b>Held month</b>: if the check emails behind the reliable subset haven't arrived yet, that month shows gross adds only (in October 2026, the current month).</li>
  </ul>
</section>

<section id="example">
  <h2>5 · Worked example: ChatGPT, US, September 2026</h2>
  <div class="panel"><ol class="steps">
    <li><div><b>Receipts.</b> Apple and Google Play ChatGPT charges. Direct chatgpt.com is excluded (sign-up receipts only, no renewals).</div></li>
    <li><div><b>Windows.</b> Apple 42 days, Google Play 40 days. Example member: Apple Plus receipts on 29 Jan, 29 Feb, 29 Mar and 29 Apr 2024, then nothing until 31 Oct 2024. The gap of 185 days is more than 42, so their first subscription churned on 10 Jun 2024 (29 Apr + 42 days) and a new one, a gross add, started on 31 Oct.</div></li>
    <li><div><b>Gross adds.</b> Subscriptions whose first receipt falls in September: <b>9,392</b>.</div></li>
    <li><div><b>Churn rates for September</b>, a sample of buckets:
      <div class="scroll"><table>
        <thead><tr><th>Bucket</th><th>Source</th><th>Live at 1 Sep</th><th>Stopped in Sep</th><th>Rate</th></tr></thead>
        <tbody>
          <tr><td>Apple · Plus monthly · 1st month</td><td><span class="pill sub">subset</span></td><td>2,616</td><td>388</td><td>14.8%</td></tr>
          <tr><td>Apple · Plus monthly · months 2–3</td><td><span class="pill sub">subset</span></td><td>5,226</td><td>785</td><td>15.0%</td></tr>
          <tr><td>Apple · Plus monthly · months 7–12</td><td><span class="pill sub">subset</span></td><td>8,479</td><td>340</td><td>4.0%</td></tr>
          <tr><td>Apple · Plus monthly · 13+ months</td><td><span class="pill sub">subset</span></td><td>6,929</td><td>176</td><td>2.5%</td></tr>
          <tr><td>Apple · Go · months 2–3</td><td><span class="pill sub">subset</span></td><td>1,653</td><td>219</td><td>13.2%</td></tr>
          <tr><td>Google Play · Plus monthly · 1st month</td><td><span class="pill full">full panel</span></td><td>1,823</td><td>359</td><td>19.7%</td></tr>
          <tr><td>Google Play · Plus monthly · 13+ months</td><td><span class="pill full">full panel</span></td><td>2,306</td><td>96</td><td>4.2%</td></tr>
          <tr><td>Google Play · Go · 1st month</td><td><span class="pill full">full panel</span></td><td>791</td><td>189</td><td>23.9%</td></tr>
        </tbody></table></div>
      <p class="muted">Channel totals in the trusted populations: Apple subset 35,196 live, 2,668 stopped (7.6%); Google Play 13,594 live, 1,637 stopped (12.0%).</p></div></li>
    <li><div><b>Apply each rate to that bucket's modelled subscribers at the end of August</b> and add up. For example, if 9,000 Apple Plus-monthly subscribers were in months 2–3, they'd contribute 9,000 × 15.0% ≈ 1,350. By plan:
      <div class="scroll"><table>
        <thead><tr><th>Plan</th><th>Subscribers, end Aug</th><th>Churn in Sep</th><th>Effective rate</th><th>Gross adds in Sep</th><th>Subscribers, end Sep</th></tr></thead>
        <tbody>
          <tr><td>Plus monthly</td><td>70,880</td><td>5,189</td><td>7.3%</td><td>7,148</td><td>72,839</td></tr>
          <tr><td>Go</td><td>12,378</td><td>1,398</td><td>11.3%</td><td>2,151</td><td>13,132</td></tr>
          <tr><td>Pro 200</td><td>119</td><td>9</td><td>—</td><td>16</td><td>125</td></tr>
          <tr><td>Pro 100</td><td>78</td><td>11</td><td>—</td><td>66</td><td>133</td></tr>
          <tr><td>Plus annual</td><td>70</td><td>2</td><td>—</td><td>11</td><td>79</td></tr>
          <tr class="total"><td>ChatGPT total</td><td>83,524</td><td>6,609</td><td>7.9%</td><td>9,392</td><td>86,307</td></tr>
        </tbody></table></div>
      September's new subscribers aren't at risk until October.</div></li>
    <li><div><b>Result.</b> 83,524 + 9,392 − 6,609 = <b>86,307 subscribers</b>; <b>net adds +2,783</b>; <b>churn rate 7.9%</b>. That is 38.6% of tracked US subscribers and 48.2 per 1,000 active mailboxes.</div></li>
    <li><div><b>Check.</b> Counting open subscriptions directly gives <b>65,670</b>. The gap is mostly Apple subscribers whose renewal emails went missing. Counting churn directly from everyone would put ChatGPT's monthly churn about 3–5 points higher (for example 18% against 14% in Aug 2025).</div></li>
  </ol></div>
</section>

<section id="filters">
  <h2>6 · Filters by provider × plan</h2>
  <div class="controls">
    <div class="seg" id="seg-region" role="group" aria-label="Region"></div>
    <div class="seg" id="seg-prov" role="group" aria-label="Provider"></div>
  </div>
  <div class="panel prov-card" id="prov-card"></div>
  <div class="panel scroll"><table id="tbl-plans"></table></div>
  <p class="muted">Paid receipts kept by the filters, October 2025 to October 2026 (members = distinct panellists). Typical amount = the most common charge, in local currency. Cells with fewer than 20 receipts are hidden.</p>
</section>

<section id="caveats">
  <h2>7 · Caveats</h2>
  <ul>
    <li><b>Channels receipts can't see:</b> direct ChatGPT (excluded; ChatGPT understated), Grok/X web, Perplexity web, Muse web (Meta Pay). The card panel sees web billing; it is kept separate.</li>
    <li><b>The reliable subset is slightly optimistic:</b> its first-renewal rate is about 4 points above everyone else's. This is disclosed, not corrected.</li>
    <li><b>Apple can't be validated directly.</b> The observed Apple count loses about 6% of renewals to missed emails, so modelled and observed differ most for Apple-heavy providers (ChatGPT, Grok, Perplexity).</li>
    <li><b>Grok churn lags 2–3 months</b> because of its long windows.</li>
    <li><b>Gemini includes AI Plus 2 TB</b> (storage-bundled) from late January 2026. A split without it is planned.</li>
    <li><b>Open NIQ questions:</b> the May–June 2026 drop in Google One storage receipts, the mid-2025 step in Apple cancellation emails, and the fall from July 2025 in direct ChatGPT sign-up receipts.</li>
  </ul>
</section>

<section id="where">
  <h2>8 · Where it lives</h2>
  <div class="panel scroll"><table>
    <thead><tr><th>What</th><th class="l">Where</th></tr></thead>
    <tbody>
      <tr><td>Job (branch <code>feat/ai-consumer-subs</code>)</td><td class="l"><code>workflows/jobs/ai/consumer/</code>: <code>consumer.yaml</code>, <code>METHODOLOGY.md</code></td></tr>
      <tr><td>Receipt filters</td><td class="l"><code>artifacts/engine/filters/*.py</code>, <code>classify.py</code></td></tr>
      <tr><td>Churn, subset, stock-flow</td><td class="l"><code>artifacts/engine/model.py</code>, <code>params/lapse_windows.csv</code></td></tr>
      <tr><td>Output tables</td><td class="l"><code>srs_mcp.ai_consumer</code>: <code>receipt_events</code>, <code>subs_monthly</code>, <code>churn_rates</code>, <code>subs_daily_adds</code>, <code>switching</code></td></tr>
      <tr><td>Step-by-step notebook</td><td class="l"><code>exploration/ai/notebooks/ai_subs_receipts_walkthrough.ipynb</code></td></tr>
      <tr><td>Research behind the rules</td><td class="l"><code>exploration/ai/phase1/FINAL_SPEC.md</code>, <code>RESULTS.md</code></td></tr>
    </tbody></table></div>
</section>

<footer>Built by <code>exploration/ai/docs/build_methodology_html.py</code> from the job's parameter files and <code>receipt_events</code>. Rebuild after a method change.</footer>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const PROV = ["chatgpt", "claude", "gemini", "grok", "perplexity", "muse"];
const CH = { apple: "Apple", google_play: "Google Play", direct: "Direct", paypal: "PayPal", stripe: "Stripe", other: "Other" };
const TIER = { go: "Go", plus: "Plus", pro: "Pro", pro100: "Pro 100", pro200: "Pro 200", pro500: "Pro 500", max: "Max", max5: "Max 5x", max20: "Max 20x",
  ai_pro: "AI Pro", ai_plus: "AI Plus", ai_plus_2tb: "AI Plus 2 TB", ultra: "Ultra", ultra_5x: "Ultra 5x", supergrok: "SuperGrok", lite: "Lite",
  heavy: "Heavy", premium_plus: "X Premium+", xsub_plus: "X Subscription Plus", xsub_premium: "X Subscription Premium", xsub_super: "X Subscription Super", power: "Power" };
const CAD = { M: "monthly", A: "annual", Q: "quarterly" };
const PLAN = p => { const m = p.match(/^(.*)_([MAQ])$/); return m ? `${TIER[m[1]] || m[1]} · ${CAD[m[2]]}` : p; };
const pct = v => v == null || isNaN(v) ? "—" : (100 * v).toFixed(1) + "%";
const num = v => Number(v).toLocaleString("en-US");
const st = { win: "us", region: "us", prov: "chatgpt" };
try { Object.assign(st, JSON.parse(localStorage.getItem("ai-method-state") || "{}")); } catch (e) {}
const save = () => { try { localStorage.setItem("ai-method-state", JSON.stringify(st)); } catch (e) {} };

function seg(id, opts, key, render) {
  const el = document.getElementById(id); el.innerHTML = "";
  for (const [v, label] of opts) {
    const b = document.createElement("button"); b.textContent = label; b.setAttribute("aria-pressed", st[key] === v);
    b.onclick = () => { st[key] = v; save(); seg(id, opts, key, render); render(); };
    el.appendChild(b);
  }
}
function renderWin() {
  const rows = D.windows.filter(r => r.region === st.win);
  let h = "<thead><tr><th>Provider</th><th>Channel</th><th>Capture (all)</th><th>Capture (subset)</th><th>Window W (days)</th><th>Window source</th><th>Churn-rate source</th></tr></thead><tbody>";
  for (const r of rows) h += `<tr><td>${D.providers[r.prov].name}</td><td>${CH[r.channel] || r.channel}</td><td>${pct(r.capture_all)}</td><td>${pct(r.capture_R)}</td><td>${r.W_monthly}</td><td>${r.W_source}</td><td>${r.rate_source === "full_panel" ? '<span class="pill full">full panel</span>' : '<span class="pill sub">reliable subset</span>'}</td></tr>`;
  document.getElementById("tbl-win").innerHTML = h + "</tbody>";
}
function renderFilters() {
  const P = D.providers[st.prov];
  document.getElementById("prov-card").innerHTML = `<h3 style="margin:0">${P.name} · ${st.region === "us" ? "US" : "Europe"}</h3><dl>
    <dt>Receipts kept</dt><dd>${st.region === "us" ? P.us : P.eu}</dd><dt>Plans</dt><dd>${P.plans}</dd>
    <dt>Excluded</dt><dd>${P.excluded}</dd><dt>Note</dt><dd>${P.note}</dd></dl>`;
  const rows = D.plans.filter(r => r.region === st.region && r.provider === st.prov);
  const w = Object.fromEntries(D.windows.filter(r => r.region === st.region && r.prov === st.prov).map(r => [r.channel, r]));
  let h = "<thead><tr><th>Plan</th><th>Channel</th><th>Typical amount</th><th>Paid receipts</th><th>Members</th><th>Window W</th><th>Churn-rate source</th></tr></thead><tbody>";
  if (!rows.length) h += `<tr><td colspan="7" class="l muted">No paid receipts kept in this region.</td></tr>`;
  for (const r of rows) {
    const ww = w[r.channel], cad = r.plan.slice(-1);
    const W = cad === "A" ? 400 : cad === "Q" ? 135 : ww ? ww.W_monthly : "—";
    const src = !ww ? "—" : ww.rate_source === "full_panel" ? '<span class="pill full">full panel</span>' : '<span class="pill sub">reliable subset</span>';
    h += `<tr><td>${PLAN(r.plan)}</td><td>${CH[r.channel] || r.channel}</td><td>${Number(r.typical_amt).toFixed(2)} ${r.cur}</td><td>${num(r.n)}</td><td>${num(r.members)}</td><td>${W}</td><td>${src}</td></tr>`;
  }
  document.getElementById("tbl-plans").innerHTML = h + "</tbody>";
}
const REG = [["us", "US"], ["eu", "Europe"]];
seg("seg-win", REG, "win", renderWin); renderWin();
const renderAll = () => { seg("seg-prov", PROV.map(p => [p, D.providers[p].name.split(" (")[0]]), "prov", renderFilters); renderFilters(); };
seg("seg-region", REG, "region", renderAll); renderAll();
</script>
</body>
</html>
"""

out = HERE / "ai_subs_methodology.html"
out.write_text(HTML.replace("__DATA__", json.dumps(DATA, default=str, allow_nan=False).replace("</", "<\\/")), encoding="utf-8")
print("wrote", out)
