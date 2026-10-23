# AI consumer subscriptions from e-receipts: final method spec (Phase 1, 2026-10-20)

This is implementation-ready: every rule and parameter needed to reproduce the index. The reference implementation is
`phase1/t7c_stockflow.py`, together with `common.py`, `t2_mailbox.py`, `t7_stockflow.py` and `t7b_stockflow.py`.
Evidence is in `phase1/RESULTS.md`.

## 1. Inputs

| Region | Receipts | Member id | Panel membership |
|---|---|---|---|
| US | NIQ Slice. Phase 1 used `SRS_SLICE.COMMON.ITEMS_LIVE` with `mailbox_status='ACTIVE'`. Production plan: `srs_slice.common.items_v` + hard-coded merchant_ids (see §11) | mailbox_id | Only currently active mailboxes. A mailbox that exits is removed from all history. |
| EU (UK, DE, FR, ES, IT) | `SHARE_NIQ.SRS.FOX_TRANSACTION_ITEMS`; exclude rows where `order_attributes` has `order_is_spam = 1`. Country comes from `FOX_MAILBOXES.customer_country`. | user_id | A user is active while sending any receipt. A user with no receipt for 90 days has left (§9). |

**Classification.** Run `filters_receipts/{provider}.py: classify(raw, region)` for chatgpt, claude, gemini, grok,
perplexity and muse. Keep rows with `keep = True`. Each row has `kind` (charge or cancel), `channel` (apple,
google_play, direct, paypal, stripe, other), `plan` (tier_cadence, e.g. `plus_M`), `cadence` (M/Q/A; a 3-month offer is
Q) and `renews`.

**Providers.** Fold `grok_x` (X Premium+) into `grok`. Cursor is out of scope.

**Paid receipt.** A row with `kind = 'charge'`. Keep one per uid × provider × channel × day, preferring the highest amount.

## 2. Scope exclusions

- **ChatGPT direct is excluded entirely.** It sends sign-up receipts only. Its charges create no subscriptions and its
  cancels are ignored. ChatGPT = Apple + Google Play + PayPal + Stripe.
- Only charges with `renews = True` enter subscriptions. ChatGPT direct is the only non-renewing provider × channel.
- **Muse is included** (US Apple and Google Play). It has had no churn so far; rates come from its own cells once they
  hold ≥ 100 active (§7).

## 3. Lapse windows W (days)

W is used both to split subscriptions (gross add) and to detect churn. It depends on the billing channel and cadence
of the receipt being continued from, i.e. the previous paid receipt.

| Cadence | W |
|---|---|
| A (annual) | 400 |
| Q (quarterly) | 135 |
| M (monthly) | from the table below |

**Monthly W.** This is the p99 of continuing renewal gaps in the reliable subset: missed-email gaps on the billing
anchor are kept, and chance-aligned resubscribes are removed. It is `out/final_windows.csv`, column `W_monthly`.

| Region | Provider | Apple | Google Play | Direct | PayPal | Stripe | Other |
|---|---|---|---|---|---|---|---|
| US | ChatGPT | 42 | 40 | (excluded) | – | – | – |
| US | Claude | 43 | 42 | 41 | – | – | – |
| US | Gemini | 44 | 40 | – | – | – | – |
| US | Grok | 60 | 91 | – | – | – | – |
| US | Perplexity | 59 | 58 | – | – | – | 58 |
| US | Muse | 42 | 40 | – | – | – | – |
| EU | ChatGPT | 43 | 42 | (excluded) | 61 | 43 | – |
| EU | Claude | 42 | 43 | 43 | 43 | 43 | 43 |
| EU | Gemini | 43 | 42 | – | 42 | – | – |
| EU | Grok | 87 | 87 | – | 87 | 87 | – |
| EU | Perplexity | 43 | 43 | – | – | 44 | – |

**Fallback for unlisted or small cells.** A cell with fewer than 2,000 subset gaps falls back as follows:
1. The provider pooled across channels in that region (if ≥ 2,000 gaps): US ChatGPT 42, Claude 41, Gemini 40, Grok 60,
   Perplexity 58; EU ChatGPT 43, Claude 43, Gemini 42, Grok 87.
2. Otherwise the channel pooled across providers: US Apple 42, Google Play 40, direct 41; EU Apple 43, Google Play 43,
   direct 43, PayPal 59, Stripe 44.
3. Otherwise 62.

Round W up to whole days. Grok's long windows (60–91 days) are kept, with a caveat: its churn is detected 2–3 months
after the last payment.

## 4. Subscriptions and gross adds

A subscription is uid × provider with channels pooled. Sort that provider's paid receipts by date. A receipt **starts a
new subscription (gross add, dated at that receipt)** if any of the following holds:

1. It is the first paid receipt for that uid × provider.
2. The gap to the previous paid receipt exceeds W of the previous receipt (its channel and cadence).
3. **Cancel split**: a cancel event (§5) for the same uid × provider, on any channel, is dated after the previous paid
   receipt and on or before this receipt.

**Plan and channel.** A subscription's plan, cadence and channel are those of its first receipt. Plan changes and
channel switches within a subscription do not create a new one.

## 5. Churn (dated at detection)

| Case | Churn date | Notes |
|---|---|---|
| Lapse | last paid receipt + W (of the last receipt) | Only once that date ≤ data end; until then the subscription is open (active). |
| Cancel split (§4 rule 3) | the date of the payment that starts the next subscription | Churn and gross add on the same day: the stock is unchanged, tenure resets. |

**Cancel event.** A row with `kind = 'cancel'` for the provider on any included channel. Keep only the first per
uid × provider × channel within 45 days, because Google Play sends "will be canceled" and "has ended". A cancel with no
later payment has no effect: the subscription churns by lapse.

There is no settled month. Recent subscriptions are simply open until W passes. Cancellation emails are not used to
date churn: no channel reaches 95% presence (RESULTS §3 and §6).

## 6. Reliable subset R (used for churn rates on the channels listed in §7)

**Reference senders.** Paid (price > 0), monthly receipts:

| Sender | US match | EU match |
|---|---|---|
| iCloud+ | `merchant_name = 'iTunes'` and descr ILIKE `icloud%icloud+%` and contains `(Monthly)` | `merchant_name = 'apple'` and product_name ILIKE `icloud%`; not annual (`annual\|yearly\|jährlich\|annuel\|anual\|annuale`); price < 35 |
| YouTube Premium | descr ILIKE `%youtube premium%` with merchant in (iTunes `(Monthly)`, Google Play price < 12, `Youtube Premium` price < 40). The Google Play price cap excludes most Google Play YouTube receipts in practice. | product_name ILIKE `%youtube premium%`, not annual, price < 35 |
| Spotify | `merchant_name = 'Spotify'`, descr ILIKE `premium%`, not trial, price < 40 | `merchant_name = 'spotify'`, product_name ILIKE `premium%`, price < 35 |
| Another AI provider | any paid AI receipt (any channel, including ChatGPT direct sign-up receipts) from a provider other than the subscription's own | same |

Google One storage is **not** a reference sender.

**present(u, m, p)** is true when, in calendar month m, member u has a receipt from a reference sender, or a paid receipt
from an AI provider other than p.

**Membership rules:**
- **Entry.** The subscription is in R if present(u, start month, p).
- **Follow.** For each month m from start + 1 to min(churn-detection month, H), where H is the last non-held month
  (§8): if present(u, m, p) is false, the subscription is **censored** at the first day of m.
- **One-month tolerance.** A missing month is treated as present if present(u, m − 1, p) and present(u, m + 1, p) are
  both true and m + 1 ≤ H.
- **Churn in R.** A churn counts in R only if the subscription is not censored at or before its detection month.

## 7. Churn-rate source by channel

A channel uses **full-panel** rates if its all-user renewal capture is ≥ **97.5%** and it is not Apple. Otherwise it
uses **R** rates.

| Region | Full panel | Reliable subset R |
|---|---|---|
| US | ChatGPT Google Play, Claude direct, Claude Google Play, Gemini Google Play | all Apple; Grok Google Play; Perplexity Google Play and other; Muse |
| EU | ChatGPT Google Play, Claude direct, Claude Stripe, Gemini Google Play | all Apple; ChatGPT PayPal and Stripe; Claude Google Play, PayPal and other; Gemini PayPal; all Grok; all Perplexity |

Capture is re-measured on each refresh (`capture_all` in `final_windows.csv`). Channels crossing 97.5% switch source.

## 8. Held months

**Landing share** for month m: among members with a reference-sender receipt (iCloud+, YouTube or Spotify) in both
m − 1 and m − 2, the share that also have one in m.

**Rule.** Month m fails if landing(m) < 0.95 × median(landing over the 6 months before m), or if m is the partial
data-end month. **Held months** are the trailing run of failing months ending at the data end. No churn rate is computed
for a held month and the stock is not advanced into it. A failing month followed by passing months is a capture dip,
not held; the one-month tolerance bridges it.

On 2026-10-18 only October 2026 is held (H = Sep 2026). US landing is about 0.97 and EU about 0.96.

## 9. Exits and denominators

- **US.** Mailboxes that are no longer active are absent (removed retroactively). Denominator: active mailboxes per
  `SRS_SLICE.COMMON.NORMAL_ACTIVE` (`84d_active`).
- **EU.** Activity spells are any receipt, with a gap of ≤ 90 days. If a subscription would lapse (not cancel-split)
  after the user's last receipt, and that last receipt is more than 90 days before the data end, it is a **panel exit**:
  remove the subscription entirely. Denominator: users with a receipt in the trailing 90 days.

## 10. Stock-flow model

**Tenure band.** age = t − start month (calendar months).

| Band | m1 | m2–3 | m4–6 | m7–12 | m13+ |
|---|---|---|---|---|---|
| age | 0–1 | 2–3 | 4–6 | 7–12 | ≥ 13 |

**Monthly churn rate** for month t, cell (region, provider, channel, plan, cadence, band), using the source from §7:
- active(t) = subscriptions with start month < t, not churn-detected before month t, and (R only) not censored before
  month t;
- churned(t) = those whose churn-detection month = t and (R only) that are not censored at or before t;
- rate = churned / active.

**Pooling.** A cell is used only if active ≥ 100. Otherwise use the first of the following that qualifies:
1. (provider, channel, plan)
2. (provider, channel, cadence, band)
3. (provider, channel, cadence)
4. the R rate pooled across channels at (provider, plan, band), then (provider, plan), (provider, cadence, band),
   (provider, cadence), (provider)
5. (provider, cadence) summed over the trailing 6 months
6. 0

Annual plans therefore only ever take annual (A) rates.

**Recursion.** Cohorts are keyed by (provider, channel, plan, cadence, start month). For each month t = t0 … H:

```
n_c(t) = n_c(t-1) × (1 − rate(t, cell(c, age = t − start_c)))   for existing cohorts
n_new(t) = gross adds in month t (§4), all included channels, full panel
subs(t, provider[, plan]) = Σ_c n_c(t)
```

**Initial stock** at t0 is the observed full-panel active subscriptions at the end of t0 − 1. These are subscriptions
started by then whose churn was not detected by then, keyed by their actual start month.

**Outputs.** Per region × provider (× plan): subs(t), gross adds(t), churn(t) = Σ n_c(t − 1) × rate, subs per 1,000
active members (§9), and share of tracked subscribers.

## 11. Parameters

| Parameter | Value |
|---|---|
| Window percentile | p99 of continuing gaps in R |
| Minimum gaps for an own-cell window | 2,000 |
| Annual / quarterly W | 400 / 135 days |
| Cancel-event de-duplication | 45 days |
| Full-panel capture threshold | 97.5%, never Apple |
| Minimum active for a rate cell | 100 |
| Held-month threshold | landing < 0.95 × median of prior 6 months; trailing run only |
| Reference-gap tolerance | 1 month, bridged both sides |
| EU quiet period | 90 days |
| Model start | 2024-01 (initial stock at end 2023-12) |

**Re-derive on each refresh, or whenever the source changes** (e.g. ITEMS_LIVE → items_v):
- W: re-run t1 → t2b, swapping in t2c (storage excluded);
- capture by channel and the §7 lists;
- the held months.

## 12. Validation (Phase 1) and caveats

- **Back-test** (modelled vs observed full-panel stock, non-Apple channels, 2025-07 start, month 6 / month 12):
  - full-panel channels: 0% (in-sample);
  - channels on subset rates: EU ChatGPT PayPal 0% / +1%, EU Gemini PayPal +11% / +2%, EU Claude Google Play −1% / +4%,
    US Grok Google Play +5% / +9%.
- **Apple** cannot be validated, because observed Apple loses about 6% of renewals to missed emails. The reliable
  subset retains about 4pp better at first renewal than the rest. This is disclosed, not adjusted.
- **Open items with NIQ** (`NIQ_QUESTIONS.md`):
  - the May–June 2026 Google One storage receipt drop;
  - the July 2025 step up in Apple cancellation emails;
  - the fall from July 2025 in ChatGPT direct sign-up receipts relative to cancellations.
- **Not covered by receipts.** Direct web billing for Grok/X, Perplexity, Muse and Cursor (cards cover these), and
  ChatGPT direct (excluded).
