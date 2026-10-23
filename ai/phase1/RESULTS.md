# Phase 1: renewal consistency, reliable subset and survival (AI subscriptions, e-receipts)

Run 2026-10-20. Data: `.cache/receipts/{us,eu}_classified.parquet` (US NIQ ITEMS_LIVE active mailboxes, data to 2026-10-18;
EU Fox UK/DE/FR/ES/IT, data to 2026-10-13), plus new Snowflake pulls (`pull.py`, ANALYST_L, temp table in SRS_MCP.SANDBOX):
monthly receipt activity per AI-subscriber mailbox and a set of **reference recurring senders**: iCloud+ (Apple), Google One
storage (Google Play), YouTube Premium, Spotify (monthly paid only). Gap and survival work runs locally on the classified
caches, about 10 minutes in total. The classifier is pandas-only, so the classified rows exist only locally.
Providers: chatgpt, claude, gemini, grok (X Premium+ pooled into grok), perplexity. Muse has too little history (started
Sep 2026, 151 R subscriptions, no renewals yet) and is not assessed. Unless stated otherwise, figures are for monthly plans.

Scripts (run in order): `pull.py` → `t1_gaps.py` → `t2_mailbox.py` → `t2b_windows.py` → `make_windows.py` → `t3_cancel.py`
→ `t5_survival.py` → `t4_repr.py`. Tables are in `out/`; intermediates (about 800 MB) are in `data/` (git-ignored).

## How gaps are read

Each gap is the time between consecutive paid receipts for a uid × provider × channel:
- **Renew**: the gap is ≤ 1.5 cycles.
- **Missed (aligned)**: the gap is longer but the next receipt lands within ±4 days of the billing anchor (d0 + k months).
  The subscription continued and k−1 renewal emails were not captured.
- **Break**: the gap is longer and the next receipt is off the anchor. This is a lapse followed by a resubscribe, or a
  billing-retry re-anchor.

Resubscribes land uniformly across the month, so some fall on the anchor by chance. **Capture** below is therefore
chance-corrected: off-anchor density × window is subtracted from each k. In the raw counts, capture looks 2–5pp worse,
mostly at the first renewal.

## 1. Renewal consistency (all users)

| Region | Provider | Channel | Subs ≥3 charges | Gap p50/p90/p95/p99/p99.5/max (d)¹ | Capture | Subs 100% captured | p99 continuing gap² |
|---|---|---|---|---|---|---|---|
| US | ChatGPT | Apple | 78,403 | 31/36/41/124/211/1068 | 93.9% | 77% | 92 |
| US | ChatGPT | Google Play | 18,894 | 31/31/35/90/150/947 | 98.6% | 86% | 43 |
| US | Claude | direct | 46,430 | 31/31/32/65/124/915 | 98.7% | 88% | 44 |
| US | Claude | Apple | 8,275 | 31/35/40/88/119/760 | 96.5% | 90% | 63 |
| US | Gemini | Google Play | 56,193 | 31/31/33/61/90/851 | 98.5% | 92% | 42 |
| US | Gemini | Apple | 2,368 | 31/35/40/92/152/515 | 94.8% | 89% | 89 |
| US | Grok | Apple | 3,684 | 31/37/41/152/242/849 | 93.3% | 79% | 92 |
| US | Perplexity | Apple | 1,767 | 31/35/40/119/162/549 | 93.5% | 85% | 92 |
| EU | ChatGPT | Apple / GP / PayPal | 18.6k / 10.6k / 4.0k | p99 123 / 92 / 62 | 96.6 / 97.9 / 97.1% | 79 / 84 / 87% | 61 / 45 / 61 |
| EU | Claude | direct / Stripe | 14.5k / 1.9k | p99 62 / 61 | 98.8 / 99.2% | 92 / 94% | 44 / 44 |
| EU | Gemini | GP / Apple | 14.6k / 0.8k | p99 61 / 150 | 97.8 / 91.6% | 91 / 82% | 57 / 120 |
| EU | Grok | Apple / GP / Stripe | 0.3k each | p99 92–126 | 92–95% | 79–87% | 90–95 |

¹ Within subscriptions with ≥3 charges, including missed-email gaps. ² From the chance-corrected distribution of
continuing gaps. Full table, including annual plans and EU countries: `out/t1_gap_dist.csv`.

- **Missed emails that then resume** (a long gap that comes back on the anchor) are about **2.2% of US Apple gaps**,
  0.6–0.8% of US Google Play and direct gaps, and 0.6–1.6% in the EU (`out/t1_missed_k.csv`). Most of these skip a single
  month (k=2), with a tail to k ≥ 5.
- **Stability over time** (`out/t1_by_quarter.csv`): Apple capture is slipping. US ChatGPT Apple was 97–99% in 2023–24
  and is about 92.6% in 2025Q4–2026Q4. Grok Apple fell from about 95% to 87–92%. Google Play and Claude direct are flat at
  about 98–99%.
- **By tenure** (`out/t1_by_tenure.csv`): the **first renewal has the worst capture** (US ChatGPT Apple 83%, Grok Apple
  84%), against 95–99% from the fourth renewal onwards. This is where survival is most sensitive.
- **By mailbox age** (`out/t1_by_mbx_age.csv`): backfilled pre-join history captures 2–5pp worse than post-join history.
  After joining, capture is flat by mailbox age.

## 2. Is a missed renewal a mailbox trait?

The month-level test is in `out/t2_month_level.csv`. In months where an AI renewal was missed (high-purity misses on the
anchor), the user's reference sender was also missing **17–27%** of the time on Apple and Google Play, against **1–3%** in
months where the AI renewal was captured (roughly 10–20x). The mailbox sent no receipts at all in only 1–11% of missed
months. Claude direct is the least mailbox-linked: 6% against 1.6%.

At user level (`out/t2_user_level.csv`), using US ChatGPT Apple: P(any AI miss) is 35% when the reference sender has a
miss and 18% when it does not. Pairs of AI providers show the same pattern.

**Conclusion:** missing emails is partly a mailbox trait, strongest for Apple (iCloud+ comes from the same sender). Most
misses are still specific to the month and sender. A user-level "clean history" filter therefore helps less than a
time-local check.

### Subset candidates (`out/t2_subset_eval.csv`, `out/t2b_windows.csv`)

| Candidate (none uses the AI subscription's own end) | US Apple capture / p99 | US GP capture / p99 | EU Apple capture / p99 | Share of US Apple gaps |
|---|---|---|---|---|
| All users | 94.1% / 92d | 98.6% / 42d | 96.6% / 61d | 100% |
| Has a reference sender (≥3 receipts) | 95.9% / 63d (ChatGPT) | 98.6% / 42d | 96.7% / 61d | 86% |
| Reference sender never missed (user level) | 97.3% / 58d | 99.0% / 40d | 98.5% / 43d | 66% |
| **live_any (time-local)**: a reference sender **or a different AI provider** has a captured receipt in every month the gap spans (for a lapse: every month from the last payment to last + W) | **98.5% / 44d** | **99.2% / 40d** | **99.0% / 43d** | **73%** (EU 79%) |

`live_any` reaches the ≥95% target in every cell except **Grok** (93–97%; p99 61–95 days) and EU Claude Google Play
(97%, p99 61). It covers 37–52% of Google Play, direct, Stripe and PayPal gaps. Those channels already capture 98–99%
without any subset, with p99 41–45 days.

## 3. Cancellation reliability (US; Fox has cancels only for ChatGPT direct and about 600 ChatGPT Apple rows)

Source: `out/t3_lapse_cancel.csv`. A confirmed lapse means no payment from the provider on any channel within W, W has
already elapsed, and the mailbox is still active. The cancel email must be from the same provider and channel, within
±45 days of paid-through.

| Provider × channel | Lapses | Cancel email present | ... in reliable lapses | Last payment → cancel email (p50) |
|---|---|---|---|---|
| ChatGPT Apple / GP | 95.8k / 17.7k | 61% / 79% | 75% / 84% | 15d / 15d |
| Claude Apple / direct / GP | 8.5k / 32.0k / 1.5k | 63% / 60% / 82% | 76% / 63% / 87% | 15 / 13 / 13d |
| Gemini Apple / GP | 2.7k / 30.3k | 56% / 74% | 61% / 71% | 15 / 19d |
| Grok Apple / GP | 7.6k / 1.8k | 72% / 88% | 78% / **92%** | 15 / 8d |
| Perplexity Apple / GP | 3.1k / 0.5k | 73% / 86% (95% any channel) | 80% / 90% | 15 / 13d |

**No provider × channel reaches 95%.** The best are Grok Google Play (92% in reliable lapses) and Perplexity Google Play.
Where a cancel email exists, it arrives a median 13–19 days after the last payment. Lapse detection only knows the churn
at last payment + W (40–90 days), so dating churn on the cancel email would be roughly 25–75 days earlier.

### What follows a cancellation (`out/t3_cancel_then_pay.csv`)

25–31% of ChatGPT and Claude Apple and Google Play cancels are followed by a paid receipt within W, a median of 17–25 days
later. For Gemini, Grok and Perplexity the figure is 9–17%. Of those payments:

| Channel | Has a sign-up / gross-add email within ±7 days (treat as churn + gross add) | Looks like a continuing renewal: same channel and plan, on the old anchor, no sign-up email | Continuing renewals as a share of all cancels |
|---|---|---|---|
| ChatGPT Apple | 48% | 19% | **5.0%** |
| ChatGPT Google Play | 7% | 45% | **11.9%** |
| Claude direct | 75% | 12% | 2.5% |
| Claude Apple / GP | 32% / 25% | 27% / 39% | 6.9% / 11.8% |
| Gemini GP | 60% | 17% | 2.6% |
| Grok Apple / GP | 16% / 0% | 22% / 23% | 3.6% / 3.9% |

### Telling a gross-add email from a renewal receipt (`out/t3_signup_marker.csv`)

| Channel | Gross-add marker | Present at a subscription start / at a renewal |
|---|---|---|
| ChatGPT direct (US, EU) | The paid receipt itself (sign-up only; renewals are not sent) | 100% / – |
| Apple (US) | Unpriced "App Plan $X /month" subscription confirmation; the paid receipt looks identical for first and renewal | ChatGPT 59%, Claude 68%, Perplexity 67%, Gemini 40%, Grok 32% / 1–3% |
| Claude direct (US) | Unpriced "Pro/Max subscription" welcome | 85% / 4% |
| Gemini via Google One (US) | "Welcome (back) to Google AI Pro…" (sent by Google One, not Play) | 32% (any channel) / 4% |
| Google Play (US, EU) | None. First and renewal receipts are identical. | 0–0.5% |
| EU Fox (all except ChatGPT direct) | None usable | ~0% |

So gross add = **first paid receipt after a gap > W** is the only rule that works on every channel. The confirmation email
is a supporting signal on Apple and Claude direct only.

## 4. Representativeness of the subset (`out/t4_mix.csv`, `out/t4_early.csv`, `out/t4_first_renewal_by_channel.csv`)

The subscription-level subset R used for survival enters R if a reference sender has a receipt in the start month. It
covers 52% of subscriptions for US ChatGPT, 39% for Claude, 22% for Gemini, 53% for Grok and 56% for Perplexity. In the EU
it covers 52%, 33%, 21%, 41% and 54%.

- **Channel mix skews to Apple**: +11 to +24pp in the US and +12 to +21pp in the EU. iCloud+ is the main reference.
  Channels are pooled within provider × plan for the index, so this matters only if survival differs by channel.
- **Plan mix** is within ±6pp; the largest gaps are US Grok SuperGrok (+8pp) and US Gemini AI Pro (−6pp). **Start-cohort
  mix** is within ±6pp by quarter.
- **Early survival** is compared within a channel where capture is the same for R and the rest (Google Play, direct,
  Stripe, PayPal). On those channels, R's first-renewal rate is **2–9pp higher** (median about 4pp). R is therefore mildly
  more retentive, which makes its survival curves a little optimistic. On Apple, the 15–46pp gap is mostly missed Apple
  emails among the rest, which is why the rest cannot be used.

## 5. Survival on R, churn dated when known (`out/t5_km.csv`, `out/t5_monthly_churn.csv`)

Method:
- A subscription is uid × provider with channels pooled. ChatGPT direct is excluded because it is sign-up only and
  modelled separately.
- A new subscription starts after a gap > W of the channel that billed it.
- **Churn is dated at last payment + W.** It is censored when the reference sender stops (from the first month without
  a reference receipt), at EU panel exit, or at the data end.
- Google One storage is not used as a reference for Gemini, because upgrading to a Gemini plan ends the storage plan.
- With this dating, S = 1 until age W.

| R, all plans | S(90) | S(180) | S(365) | Monthly churn, Jun–Aug 2026 |
|---|---|---|---|---|
| US ChatGPT (Plus 0.63/0.49/0.36; Go 0.63/0.50) | 0.63 | 0.49 | 0.36 | 9.3–9.6% |
| US Claude (Pro_M 0.72/0.56/0.39; Max5 0.77/0.63/0.43; Max20 0.81/0.65/0.49) | 0.75 | 0.61 | 0.45 | 7.8–8.2% |
| US Gemini (AI Pro 0.74/0.59/0.47; AI Plus 0.66/0.54/0.46) | 0.82 | 0.72 | 0.61 | 3.9–5.1% |
| US Grok (W 61–89) | 0.58 | 0.38 | 0.25 | 13.6–16.1% |
| US Perplexity (W 61) | 0.66 | 0.45 | 0.30 | 12.8–14.7% |
| EU ChatGPT | 0.55 | 0.40 | 0.26 | 11.0–12.4% |
| EU Claude | 0.67 | 0.53 | 0.35 | 10.1–11.6% |
| EU Gemini | 0.67 | 0.52 | 0.36 | 7.7–9.9% |
| EU Grok (W 91) | 1.00 | 0.32 | 0.17 | 13.3–17.1% |
| EU Perplexity (n 443) | 0.41 | 0.24 | 0.16 | 16–26% |

- **Lag between last payment and churn date** equals W for each provider × channel (`out/recommended_windows.csv`): 40–45
  days for most cells, 60–61 days for EU PayPal, US Grok Apple and US Perplexity, and 89–91 days for Grok on Google Play
  and in the EU.
- **The choice of W changes churn materially.** EU Grok monthly churn was 25–36% with the pooled 43-day window and is
  10–17% with Grok's own 91-day window.
- **Sep–Oct 2026 churn reads low** (US ChatGPT 6.7% in September). October is a partial month. September is probably an
  edge effect of requiring a reference receipt in the month the churn becomes known, while the latest receipts are still
  arriving. The rule should be relaxed for the last 1–2 months (see decisions).
- EU country curves are in `out/t5_km.csv`. DE is lowest and FR highest for ChatGPT and Claude.

**Back-test** (`out/t5_backtest.csv`, `out/t5_holdout_calibration.csv`): S (churn) and G (reference-loss censoring) are
trained on data up to T − 6 months. The model, Σ R gross adds × S(age) × G(age), is then compared with the observed R
actives.

| | US ChatGPT | US Claude | US Gemini | US Grok | US Perplexity | EU ChatGPT | EU Claude | EU Gemini | EU Grok |
|---|---|---|---|---|---|---|---|---|---|
| Error at month 6 | −10% | −8% | +13% | −2% | +15% | +2% | −20% | +20% | −3% |
| Hold-out churn observed / expected | 1.05 | 0.81 | 1.48 | 0.98 | 1.27 | 1.04 | 0.66 | 1.24 | 0.88 |

- The errors come from **non-stationary retention**, not from the method. Claude retention improved in 2026: in-sample,
  pooled S over-predicted 2024–25 Claude stock by 15–47%.
- **New plans with short histories** also drive errors. US Gemini AI Plus 2TB had 1,108 churns against 163 expected, and
  ChatGPT Go churned 1.6x more than expected.
- Neither trailing-12-month hazards nor curves by start half-year fixed this consistently; both are reported in
  `t5_backtest.csv`.
- The method works where retention is stable: ChatGPT within ±10%, and Grok within ±3% for US and EU.

## Recommended definition

1. **Lapse window W** = p99 of continuing gaps in the reliable subset, per region × provider × channel. Cells with fewer
   than 2,000 gaps fall back to the provider pooled across channels, then to the channel pooled across providers.
   Values are in `out/recommended_windows.csv`: mostly **40–45 days**; EU PayPal 60; US Grok Apple and US Perplexity
   Apple 61; US Grok Google Play 89; EU Grok 91.
2. **Reliable subset = time-local reference capture (live_any).** A subscription counts toward churn and survival only
   while the same mailbox shows a captured receipt from a different recurring sender (iCloud+, Google One storage except
   for Gemini, YouTube Premium, Spotify, or another AI provider) in each month. A lapse counts only if that holds from the
   last payment's month to the month of last + W. The subscription is censored when it stops holding. Churners are not
   excluded by construction. For the survival curves, use reference senders only, so that censoring is independent of AI
   churn.
3. **Churn date**: last payment + W (dated when known). Cancellation emails are not used: none reaches 95%.
4. **Gross add**: the first paid receipt after a gap > W, on any channel. A confirmation email is supporting evidence on
   Apple and Claude direct only.

## Decisions for the user

1. **Cancellation threshold.** No provider × channel reaches 95%. Options: (a) keep churn lapse-only, which costs 25–75
   days of timeliness; or (b) lower the bar so that cancel dating is allowed on Google Play for Grok and Perplexity
   (86–92%) and possibly ChatGPT and Claude Google Play (79–87%).
2. **Cancel followed by a renewal with no sign-up email** is 5% of ChatGPT Apple cancels, 12% of ChatGPT and Claude Google
   Play cancels, and 2.5–7% elsewhere. Google Play never sends a sign-up email, so this cannot be resolved there. Options:
   (a) void the cancel (no churn), (b) churn + re-add, or (c) void it only if the payment is on the old anchor. Option (c)
   is what the "continuing renewal" column measures.
3. **Subset scope.** Apply R to every channel (uniform, smaller n), or only to Apple. Google Play, direct, Stripe and
   PayPal already capture 98–99% with p99 ≤ 45 days on all users, except EU PayPal at 60.
4. **Grok.** Capture stays at 93–97% even in R, and W is 61–95 days. Accept the longer W, which makes churn visible later
   and slows the curve, or report Grok churn with a caveat. Churn is very sensitive to W here (EU 25–36% vs 10–17%).
5. **R is mildly optimistic.** First renewal is about 4pp better than the rest on comparable channels. Options: correct S
   (for example, scale the first-renewal hazard by the Google Play and direct gap), or disclose it.
6. **Non-stationary survival.** The 6-month back-test errors are −20% to +20% where retention shifted (Claude, Gemini,
   new plans). Options: estimate S by plan and start cohort with frequent re-estimation, or anchor the index to observed
   R actives and model only the not-yet-known tail.
7. **Edge months.** Relax the "reference receipt in month" requirement for the last 1–2 months of data, to avoid the low
   September and October 2026 churn reads.
8. **Muse.** It has too little history for any of this; it needs a separate rule (card data, or provisional curves from
   ChatGPT or Claude).
9. **Annual plans** (Claude Pro A, Gemini A, Perplexity A) have too few events for a curve. Options: use W = 400 days and
   pool annual plans by provider, or exclude them.

## 6. Churn from cancellation emails scaled by 1 / presence (US): `t6_cancel_scaling.py`

**Setup.**
- A cancel event is the first cancel email per uid × provider × channel within 45 days. Google Play sends both a
  "will be canceled" and a "has ended" email, so 30–40% of raw Google Play cancel emails are repeats; Apple and direct
  repeat 3–8%.
- **Presence** = the share of confirmed lapses (window crossed, mailbox active) that have a same-provider, same-channel
  cancel event within ±45 days of paid-through. It is measured by paid-through month, over the 24 months to Aug 2026.
  Sep 2026 is excluded because cancels can still arrive.
- **R** = the reliable subset (live_any). **All** = the full panel.

Outputs:
- `out/t6_presence_monthly.csv` and `out/t6_presence_summary.csv`
- `out/t6_presence_by_plan_tenure.csv`
- `out/t6_reenable_monthly.csv`
- `out/t6_backtest*.csv`
- `out/t6_timeliness.csv`
- `out/t6_chatgpt_direct.csv`

**Presence by quarter** (R / all; 2026Q3 = Jul–Aug):

| | 24Q4 | 25Q1 | 25Q2 | 25Q3 | 25Q4 | 26Q1 | 26Q2 | 26Q3 | 24m CV (R) | Last-12m CV / trend (R) |
|---|---|---|---|---|---|---|---|---|---|---|
| ChatGPT Apple | .60/.52 | .54/.46 | .61/.52 | .73/.61 | .77/.64 | .76/.64 | .76/.63 | .71/.57 | 13% | 3% / −5pp/yr |
| ChatGPT GP | .85/.85 | .86/.84 | .86/.83 | .87/.85 | .90/.85 | .85/.80 | .81/.76 | .77/.72 | 6% | 6% / −15pp/yr |
| Claude direct | .64/.59 | .57/.58 | .68/.63 | .68/.62 | .68/.62 | .55/.51 | .60/.54 | .63/.60 | 10% | 10% / −10pp/yr |
| Claude Apple | .66/.58 | .59/.60 | .63/.54 | .83/.75 | .79/.71 | .75/.64 | .73/.59 | .75/.64 | 19% | 7% / −11pp/yr |
| Gemini GP | .71/.75 | .71/.79 | .74/.82 | .82/.85 | .79/.83 | .77/.80 | .68/.72 | .65/.70 | 8% | 9% / −20pp/yr |
| Grok Apple | .59/.49 | .37/.35 | .59/.56 | .86/.77 | .84/.79 | .78/.75 | .77/.73 | .72/.68 | 29% | 8% / −17pp/yr |
| Perplexity Apple | .79/.63 | .52/.54 | .67/.62 | .80/.69 | .86/.77 | .82/.76 | .81/.77 | .80/.75 | 15% | 5% / −8pp/yr |

- **Apple has a level break in mid-2025** (ChatGPT +15–20pp; Claude, Grok and Perplexity similar). It is probably a
  parser or sender change for "iTunes Cancellation". Before and after the break the level is fairly flat (CV 3–8%).
- **Google Play and Claude direct are flat over 24 months** (CV 6–10%), but **all of them drift down in 2026**: ChatGPT
  GP 0.90 → 0.77 and Gemini GP 0.82 → 0.65 between 2025Q3 and 2026Q3.
- **Presence depends on mix.**
  - It falls with tenure: Claude direct 0.66 at 1 receipt vs 0.49 at 7+; ChatGPT GP 0.90 vs 0.78; Grok Apple 0.81 vs 0.59.
  - Plans differ: Claude Max 0.44 vs Pro 0.64; Gemini AI Plus 2TB on Apple 0.09.
  - So a single factor drifts as the tenure and plan mix shifts.
- **Re-enables** (a cancel followed by a payment within W) are steadier: ChatGPT Apple 0.23–0.29 (CV 10%), ChatGPT GP
  0.20–0.29. Gemini GP (0.07 → 0.30) and Grok GP (0.02 → 0.19) roughly tripled from 2025Q3.

**Back-test** of the scaling factor:
- The factor is estimated on a trailing window lagged 2 months (only data known at publication), applied to the month's
  cancel count, and compared with that month's observed lapses.
- Results are MAPE / bias over the last 12 months, with a 12-month window. The 6-month window is within ±3pp.
- The three factors:
  - (a) cancels × (1 − re-enable) / presence;
  - (b) cancels × Σ lapses / Σ cancels;
  - (c) as (a), counting only cancels with a payment in the prior 62 days.

| Pooled to provider | (a) R | (b) R | (c) R | (a) all | (b) all | (c) all |
|---|---|---|---|---|---|---|
| ChatGPT (Apple+GP) | 14% / +7% | **9% / −5%** | 13% / +2% | 35% / +34% | **11% / 0%** | 14% / +5% |
| Claude (Apple+direct+GP) | 28% / +27% | 16% / +4% | 23% / +20% | 53% / +53% | **11% / +3%** | 20% / +19% |
| Gemini | 99% | 30% / −16% | **26% / +5%** | 212% | 26% / −22% | **14% / +6%** |
| Grok | 106% | 42% | **31% / +22%** | 213% | 54% | **33% / +22%** |
| Perplexity | 41% | **22% / +12%** | 25% | 55% | **19% / +7%** | 23% |

- By cell, the best results are ChatGPT GP (a) in R at 7%, Claude direct (b) in all at 8%, and ChatGPT Apple (b) in R
  at 10% (all-panel 13%).
- Factor (a), the literal 1/presence, overshoots badly. Many cancels never become a lapse in our data: trial and
  non-subscriber cancels, and the 2.5–12% of cancels that continue as renewals (section 3). Factor (b) absorbs these;
  factor (c) removes most of them.
- For comparison, lapse-based churn is itself the observed truth here. The section 5 survival back-test erred by −10% to
  +20% at 6 months.

**Timeliness** (`out/t6_timeliness.csv`):
- A cancel event arrives a median of 14–15 days after the last payment. The spread is narrow on Apple (p10–p90 7–28
  days) and wide on Google Play and direct (0–34 days, many on the payment day).
- Lapse detection needs W days (40–44; Grok, Perplexity and Grok GP 61–89).
- Scaled-cancel churn is therefore available a **median 26–29 days earlier** for ChatGPT, Claude and Gemini, and 46–80
  days earlier for Grok and Perplexity. Allowing for the ±45-day matching, a month's cancel count is complete about 2
  weeks after month end, against about 6 weeks for lapses.

**ChatGPT direct** (no renewals; presence borrowed from ChatGPT Apple+GP, all-panel, trailing 12 months):
- Borrowed presence went from 0.55 to 0.66 because of the Apple break, so it is not stable enough to borrow as is. GP
  alone (0.72–0.87) is steadier but falling.
- Direct cancel events alone (6–12k a month in 2026) already exceed the modelled direct churn (sign-ups × the R survival
  of renewing channels: 4–6k a month), even at 100% presence. Scaled, direct churn is 8.5–17k a month, about **2–3x the
  modelled curve**.
- The share of direct cancellers with an earlier direct sign-up receipt fell from 93–95% before Jul 2025 to 61–73% after.
  This points to **sign-up receipt capture dropping in mid-2025**: direct gross adds, and the modelled base, are
  understated since then.
- Either way, the current modelled ChatGPT direct line looks too low on churn and too low on adds. It needs a review
  before it is used.

**Verdict.**
- No provider × channel has presence that is stable over 24 months (CV < 10% with no trend).
- Apple has a mid-2025 level break. ChatGPT GP (CV 6%), Claude direct (10%) and Gemini GP (8%) were flat until 2026 but
  have drifted 10–20pp since.
- The workable recommendation is factor (b), the raw lapses-per-cancel ratio on a trailing 6–12 months (lagged 2), for
  ChatGPT and Claude. It is within about 10% MAPE and ±5% bias against lapse churn, and about 4 weeks earlier.
- For Gemini and Grok use factor (c), at 14–33% MAPE. Use these as a **nowcast that lapse churn later replaces**, not as
  a substitute for it.

Additional decisions:
- (10) Adopt scaled-cancel churn as an early estimate for ChatGPT and Claude, revised to lapse churn when it becomes
  known.
- (11) Estimate factors by tenure band (and plan where the sample allows), so mix shifts do not move the factor.
- (12) Investigate the mid-2025 Apple cancel-email and ChatGPT direct sign-up capture changes with NIQ.
- (13) Rebuild ChatGPT direct, which is modelled 2–3x too low on churn.

## 7. Agreed rules (user decisions, 2026-10-20) and stock-flow back-test (`t7_stockflow.py`)

**Rules**
1. **Churn is lapse-only.** The window W is the p99 per provider × channel from `out/recommended_windows.csv`. Grok keeps
   its own long windows (61–91 days), with a caveat. Churn is dated at detection (last payment + W).
2. **Cancel emails only decide the split.** A cancel followed by any later payment is churn + gross add. The churn is
   dated at that payment, when it is detected, so the stock is continuous. Otherwise cancels are ignored.
3. **Reliable subset R** = a same-month reference-sender check, applied to all channels. A subscription enters R if a
   reference receipt falls in its start month, and is censored at the first month without one. Months whose reference
   receipts have not landed yet are **held**: no churn is computed for them, and the rule is not relaxed.
   - Held = the trailing run of months whose landing share is below 95% of the prior six-month median. Landing share is
     the share of users with a reference receipt in m−1 and m−2 who also have one in m.
   - On 2026-10-18 only **October 2026 is held** in both regions, so the latest non-held month is Sep 2026.
   - **June 2026 is a capture dip** in both regions (landing 0.90 against about 0.97 in the US and 0.95 in the EU), not
     a lag, because July–September landed normally. A single missing reference month bridged by receipts either side
     is counted as present, so the dip does not censor R permanently. This should be raised with NIQ.
4. **Subset optimism** (about 4pp better first renewal than the rest) is disclosed, not adjusted.
5. **Annual plans are in the stock**, with W = 400 days. Their rates come from their own plan cells (cadence-level
   pooling, never mixed with monthly plans).
6. **ChatGPT direct is excluded entirely.** ChatGPT = Apple, Google Play, PayPal and Stripe.
7. **Muse** uses its own lapse churn once observable. As of September 2026 there are 135 subscriptions and no churn yet.
8. Gross add = the first paid receipt after a gap > W on any included channel, or the first payment after a cancel.

**Back-test method**
- Model: subs(t) = subs(t−1) + adds(t) − churn_rate(t) × subs(t−1). It runs as monthly cohorts so tenure is tracked.
- churn_rate is R churn divided by R active at month start, per provider × region × plan × tenure band (m1, m2–3,
  m4–6, m7–12, m13+).
- Cells with fewer than 100 active subscriptions pool in this order: plan → cadence × band → cadence → provider, then a
  provider × cadence trailing-six-month pool.
- The initial stock is the observed stock at the month before the start.
- Comparison targets:
  - The **full panel on non-Apple first channels** (Google Play, direct, Stripe and PayPal capture 98–99%, so
    observed is reliable there).
  - The full panel on all channels. Its observed Apple stock is understated by missed emails, so it is not a fair target.
  - R's own stock, where the model also removes R's censoring rate. This is a consistency check.

**Error of the modelled stock (model / observed − 1)** (`out/t7_drift.csv`; the September 2026 value is the latest
non-held month):

| Full panel, non-Apple | Start 2024-01: month 6 / month 12 / Sep 2026 | Start 2025-07: month 6 / month 12 (Jun 2026) / Sep 2026 |
|---|---|---|
| US ChatGPT | +20% / +19% / +14% | +9% / +13% / +13% |
| US Claude | +14% / +14% / +10% | +6% / +8% / +9% |
| US Gemini | +19% / +23% / +10% | +7% / +7% / +9% |
| US Grok | −5% / +8% / −3% | −6% / −8% / −3% |
| US Perplexity (n about 270) | +20% / +13% / −3% | −11% / −1% / −3% |
| EU ChatGPT | +4% / −1% / +6% | +2% / +3% / +6% |
| EU Claude | +9% / +1% / +2% | −2% / +1% / +2% |
| EU Gemini | +9% / +6% / +1% | −5% / 0% / +1% |
| EU Grok | +24% / +10% / +1% | +5% / +1% / +1% |

- **R's own stock** is reproduced within ±1% (ChatGPT, Claude, Gemini) and within 2–6% (Grok, Perplexity) from either
  start. The bookkeeping is therefore consistent.
- **The EU fits well.** From the 2025-07 start, errors are within ±5% at month 6 and 0–3% at month 12 for the large
  providers, much better than the 8–20% of the survival-curve back-test in section 5.
- **The US drifts upward by about 1% a month on Google Play and direct** (+7–13% after 12 months for ChatGPT, Claude and
  Gemini). Running the model with rates from R's non-Apple subscriptions only did not close the gap (it widened it to
  +11–15%), so the cause is not channel mix. It is the R-vs-rest selection: R users renew better (US first-renewal gap
  +4–8pp on Google Play and direct). Missed-email false lapses in the observed panel account for perhaps 1–3pp.
  Under rule 4 this is disclosed, not adjusted. The size suggests the US index will overstate the stock by about 10%
  a year if the selection does not fade.
- The 2024-01 start is worse early on, because 2024 R cells are thin and rates pool to provider level.
- Full-panel comparisons on all channels show +10–32%. That mostly reflects the understated observed Apple stock, not
  model error.

**Share of tracked subscribers, Sep 2026 (latest non-held month)** (`out/t7_shares.csv`):

| | ChatGPT (ex direct) | Claude | Gemini | Grok | Perplexity | Muse |
|---|---|---|---|---|---|---|
| US model (full-panel adds × R rates) | 36.7% | 28.9% | 30.6% | 2.8% | 0.9% | 0.1% |
| US observed full panel | 32.8% | 30.3% | 32.7% | 3.1% | 1.0% | 0.1% |
| US R stock | 46.8% | 29.5% | 18.2% | 4.0% | 1.5% | 0.1% |
| EU model | 41.9% | 32.0% | 23.2% | 2.6% | 0.3% | – |
| EU observed full panel | 37.4% | 33.9% | 25.7% | 2.7% | 0.2% | – |
| EU R stock | 55.0% | 29.4% | 12.4% | 2.8% | 0.3% | – |

- The R stock alone must not be used for shares. It is Apple-heavy, which overweights ChatGPT, and it underweights
  Gemini, because Google One storage cannot serve as Gemini's reference.
- The model, which applies full-panel adds to R rates, sits between the two observed views. ChatGPT is 4pp above the
  observed full panel because the model restores the Apple renewals that the observed panel loses to missed emails.

**Open items from this run**
- (14) Whether to correct the US R optimism after all. The cost is about +1% a month of stock drift on US Google Play
  and direct.
- (15) Raise the June 2026 reference-receipt capture dip (−6 to −7pp in both regions) with NIQ.
- (16) The Grok caveat stands: it uses long windows, so its churn is detected 2–3 months late.

### 7b. Further decisions (2026-10-20) and re-run (`t7b_stockflow.py`)

**Decisions**
1. **Churn-rate source by channel.**
   - Channels with all-user renewal capture ≥ 98% use **full-panel** rates. On current data that is US ChatGPT Google
     Play (98.6%), US Claude direct (98.7%), US Gemini Google Play (98.6%), EU Claude direct (98.8%) and EU Claude
     Stripe (99.2%).
   - Apple and every channel below 98% use the reliable subset R. That includes EU ChatGPT Google Play (97.9%), EU
     Gemini Google Play (97.8%), all PayPal, and all Grok and Perplexity.
   - Rates are per provider × region × plan × tenure × channel. The cohort model runs per channel, so the
     provider-level rate is the channel rates weighted by each channel's share of the modelled stock.
2. **Cancel followed by a later payment** = churn and gross add, both dated at the payment (unchanged).
3. **Keep the one-month reference-gap tolerance.**
4. **NIQ questions** are in `NIQ_QUESTIONS.md`.

**What the June 2026 "dip" actually is.** It is not mailbox-wide. It comes entirely from **Google One storage receipts
on Google Play**:
- Landing share 0.96 (Apr) → 0.85 (May) → 0.71 (Jun) in the US; 0.94 → 0.87 → 0.76 in the EU.
- Monthly storage receipts fell by about a third (US 70k → 47k) and have not recovered.
- iCloud+ is flat (0.97–0.98).
- So the reference set loses Google One storage users from June 2026. With the one-month tolerance, they are censored
  rather than counted as churn. This is unaffected for Gemini, which never uses storage as its reference.

**Results: model / observed − 1, previous run (t7) → this run (t7b)** (`out/t7b_drift.csv`)

| Full panel, non-Apple | Start 2025-07, month 6 | Start 2025-07, month 12 | Start 2024-01, month 12 |
|---|---|---|---|
| US ChatGPT | +9% → **0%** | +13% → **0%** | +19% → −2% |
| US Claude | +6% → **0%** | +8% → **0%** | +14% → 0% |
| US Gemini | +7% → **0%** | +7% → **0%** | +23% → 0% |
| US Grok (R cells) | −6% → −6% | −8% → +11% | +8% → +8% |
| EU ChatGPT (R cells) | +2% → +7% | +3% → +11% | −1% → +5% |
| EU Claude | −2% → −4% | +1% → 0% | +1% → −1% |
| EU Gemini (R cells) | −5% → −1% | 0% → +4% | +6% → +6% |
| EU Grok (R cells) | +5% → +5% | +1% → +1% | +10% → +10% |

- On full-panel channels, the comparison is now **in-sample**: the model reproduces their own observed churn, so about
  0% is expected there.
- The **out-of-sample** check is the non-Apple channels that still use R (`full_nonapple_Rcells`):
  - US Claude Google Play: +15% / +7% (n about 2k)
  - US Grok Google Play: −6% / +11%
  - EU ChatGPT Google Play + PayPal: +7% / +11%
  - EU Gemini Google Play: −1% / +4%
  - EU Grok: +5% / +1%
- R-sourced Google Play and PayPal still overstate the stock by 0–1% a month. The R optimism is now confined to Apple
  (which cannot be checked) and the channels below 98%.
- **Sensitivity at a 97.5% threshold** (`out/t7b_*_cap975.csv`) adds EU ChatGPT Google Play, EU Gemini Google Play and
  US Claude Google Play to the full-panel list. EU ChatGPT non-Apple drift then falls to +1% / +2% at months 6 / 12
  (from +7% / +11%), and EU Gemini to −1% / 0%.

**Share of tracked subscribers, Sep 2026, t7 → t7b** (`out/t7b_shares.csv`):

| | ChatGPT (ex direct) | Claude | Gemini | Grok | Perplexity |
|---|---|---|---|---|---|
| US model | 36.7% → **38.1%** | 28.9% → **28.3%** | 30.6% → **29.6%** | 2.8% → 3.0% | 0.9% → 1.0% |
| US observed full panel | 32.8% | 30.3% | 32.7% | 3.1% | 1.0% |
| EU model | 41.9% → **42.3%** | 32.0% → **30.9%** | 23.2% → **24.0%** | 2.6% → 2.6% | 0.3% → 0.3% |
| EU observed full panel | 37.4% | 33.9% | 25.7% | 2.7% | 0.2% |

The modelled stocks for US Claude and Gemini fell by 8–10%, because full-panel churn replaced R churn on their main
channels. ChatGPT's share rises because its stock is mostly Apple, which is still on R. That is 5pp above the observed
panel: partly the Apple renewals the observed panel misses, and partly R optimism, which cannot be separated on Apple.

**Open item.** (17) Lower the threshold to 97.5%? It would put EU ChatGPT and Gemini Google Play (97.8–97.9%) on
full-panel rates, removing most of the remaining EU drift.

### 7c. Final Phase 1 re-run (`t7c_stockflow.py`; the spec is in `FINAL_SPEC.md`)

**Changes from 7b**
- **Reference senders** are now iCloud+, YouTube Premium, Spotify, and any paid receipt from a different AI provider.
  Google One storage is removed.
- **Full-panel churn threshold** is 97.5% all-user renewal capture.
- **Lapse windows** were re-derived with the new reference set: `out/t2c_windows.csv` → `out/final_windows.csv`.
- **The held-month rule and the one-month tolerance** are unchanged.

**Effects**
- **Windows** barely move: US ChatGPT Apple 43 → 42 days, US Grok Apple 61 → 60, US Perplexity Apple 61 → 59, EU Grok
  91 → 87. Reliable-subset capture is 99.1% for US Apple and 99.0% for EU Apple.
- **The June 2026 dip is gone.** Reference landing is 0.97–0.98 in the US and 0.96 in the EU for June–September 2026.
  Only October 2026 is held, so the latest non-held month is Sep 2026.
- **The reliable subset** now holds 42% of US and 40% of EU subscriptions.
- **Full-panel rate channels**: US ChatGPT Google Play, US Claude direct, US Claude Google Play, US Gemini Google Play,
  EU ChatGPT Google Play, EU Claude direct, EU Claude Stripe and EU Gemini Google Play.

**Drift of the modelled stock vs the observed non-Apple full panel**, start 2025-07, month 6 / month 12
(`out/t7c_drift.csv`):

| | US | EU |
|---|---|---|
| ChatGPT | 0% / 0% (in-sample) | 0% / 0% |
| Claude | 0% / 0% (in-sample) | −2% / 0% |
| Gemini | 0% / 0% (in-sample) | 0% / 0% |
| Grok (subset rates) | +5% / +9% | +3% / +2% |
| Perplexity (subset rates) | −5% / −5% | +10% / +5% (n about 50) |

Out-of-sample cells, which use subset rates on non-Apple channels:

| Cell | Month 6 / month 12 |
|---|---|
| EU ChatGPT PayPal + Stripe | 0% / +1% |
| EU Claude Google Play | −1% / +4% (+11% by Sep 2026) |
| EU Gemini PayPal | +11% / +2% |
| US Grok Google Play | +5% / +9% |

From the 2024-01 start, month-12 errors are within ±4% except Grok (+10% US, +8% EU) and Perplexity (US +20%, EU +15%, small n). The rate pooling never mixes cadences: there is no provider-only level, so annual plans take only annual rates.

**Share of tracked subscribers, Sep 2026** (`out/t7c_shares.csv`):

| | ChatGPT (ex direct) | Claude | Gemini | Grok | Perplexity | Muse |
|---|---|---|---|---|---|---|
| US model | 38.6% | 27.9% | 29.4% | 3.0% | 1.0% | 0.1% |
| US observed full panel | 32.8% | 30.3% | 32.8% | 3.1% | 1.0% | 0.1% |
| EU model | 41.8% | 31.8% | 23.5% | 2.6% | 0.3% | – |
| EU observed full panel | 37.5% | 33.8% | 25.9% | 2.6% | 0.2% | – |

The ChatGPT gap to the observed panel (+6pp US, +4pp EU) is on Apple, which cannot be validated. It combines the Apple
renewals the observed panel misses and the disclosed subset optimism.
