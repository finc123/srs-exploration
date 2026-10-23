# AI subscriber tracker: e-receipt panels (record)

Built 2026-10-19. Report: https://claude.ai/artifact/Y5DsW5pwshCCjKuMgajBEj (v1, private). Card counterpart: `CARD_TRACKER.md`.
Per-provider detail: `filters_receipts/{provider}_report.md`; filter code `filters_receipts/{provider}.py`.

## What it measures

Consumer paid subscribers from e-receipts across every visible billing channel (Apple, Google Play, PayPal, Stripe,
direct). Same outputs as the card report: daily subscriber index (per 1,000 active mailboxes and share of tracked
subscribers), gross adds, reactivations, churn, at provider and plan level, for the US and five European countries.

## Panels

| Panel | Table | Member | Panel rule | Denominator |
|---|---|---|---|---|
| US | `SRS_SLICE.COMMON.ITEMS_LIVE` (NIQ Slice; Muse app precedent) | MAILBOX_ID | Mailboxes active today; a mailbox that left is removed from history | `SRS_SLICE.COMMON.NORMAL_ACTIVE` 84-day active |
| UK, DE, FR, ES, IT | `SHARE_NIQ.SRS.FOX_TRANSACTION_ITEMS` (NIQ Fox) + `FOX_MAILBOXES` (country) | USER_ID | A user with no receipt of any kind for 90 days has left; their lapsing subscriptions are removed | Users with a receipt in the trailing 90 days |

Both panels backfill years of each mailbox's history when it joins, so pre-join history is used (no tenure rule);
history revises slightly as mailboxes join. Fox rows flagged spam are excluded; deleted/trashed receipts are kept.
`TXNS_CORE` / brand-selected tables are not usable for this (see CARD_TRACKER.md).

## Subscriber rules (`subs_receipts.py`)

- Gross add = first paid receipt of a subscription; reactivation = a later one after churn.
- Continuation: next paid receipt within 75 days of a monthly charge (135 quarterly, 400 annual) and no cancellation
  email in between. 75 days tolerates one missed renewal email (renewal capture is ~60–90% month to month).
- Churn = earlier of a cancellation email (email day) or renewals stopping (dated one month after the last payment).
  Cancellation emails alone capture only 20–85% of US churners (Google Play best, direct worst) and Fox has none except
  ChatGPT direct, so they cannot be used alone.
- ChatGPT direct sends sign-up receipts only (renewals 4% US, 0% EU): churn modelled from the survival curve of ChatGPT's
  renewing channels in the same panel; the unmodelled line (`chatgpt_raw`, open until a cancellation email) is shown
  and excluded from shares.
- Settled month: lapses are only known 75 days later, so the report's headline month is the latest month ending
  75+ days before the data end (US Jul 2026, EU Jun 2026). Later months understate churn and overstate subscribers.

## Channel visibility (what receipts can and cannot see)

| Provider | US receipts | EU receipts | Use card panel for |
|---|---|---|---|
| ChatGPT | Apple, Google Play, direct (sign-up only) | Apple, Google Play, PayPal, Stripe, direct (sign-up only) | – |
| Claude | direct (`Anthropic` 'Payment' at list prices), Apple, Google Play | `anthropic`/Stripe (plan named), Apple, Google Play, PayPal | – |
| Gemini | Google Play (incl. Google One web), Apple | Google Play, Apple, PayPal | – |
| Grok / X Premium+ | Apple, Google Play (no direct xAI/X Corp) | Apple, Google Play, Stripe | Direct web billing |
| Muse | Apple (bare 'Power Plan'), Google Play | none (not launched) | Web (Meta Pay) |
| Cursor | Apple only (~10 payers) | a handful | Everything |
| Perplexity | Apple, Google Play (direct = unpriced welcome emails) | Apple, Google Play | Direct web billing |

Cards see web billing but not Apple; receipts see app stores but miss most web billing for X, Grok, Perplexity, Cursor
and Muse. The two sources are complementary.

## Open decisions

1. Combine card and receipt sources, or read each provider from the source that sees its main channel.
2. Perplexity direct: 'Welcome to Perplexity Pro' emails as a sign-up proxy (mixes paid, trial, partner promos) or leave out (current).
3. ChatGPT direct: modelled (current) vs unmodelled.
4. The X Subscription: own line or within Grok (current).
5. Monthly churn of 11–14% for ChatGPT/Claude and ~37% for Grok in settled months looks high; check how much is
   cancel-then-resubscribe within the paid period (counted as churn + reactivation).

## Rerun

```
python extract_receipts.py us eu          # ANALYST_XL, ~10 min
python run_receipts.py --reclassify       # filters + engine (drop --reclassify to reuse cached classification)
python -c "import build_report as B; B.main('.cache/receipts/metrics','ai_subs_receipts.html','template_receipts.html','methods_receipts',settle_days=75)"
```
