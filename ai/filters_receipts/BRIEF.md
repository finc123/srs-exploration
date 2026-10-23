# Provider filter brief (e-receipt panels)

Goal: for ONE provider, classify e-receipt line items into consumer paid-subscription **charges** and
**cancellations**, by plan (tier × cadence) and channel. The output feeds `subs_receipts.py`. Time box: ~30 minutes.
The user wants this phase kept brief: reuse your card counterpart (`filters/{provider}.py`, `filters/{provider}_report.md`)
and the price research (`plans/{provider}_prices.csv`, `plans/{provider}_notes.md`) wherever it applies.

## Inputs (`C:/Users/fintan.creedon/code/exploration/ai/.cache/receipts/`)
- `us_ai_items.parquet` — NIQ `SRS_SLICE.COMMON.ITEMS_LIVE`, active mailboxes only. Columns: uid (mailbox_id), userid,
  dt (order date), email_sent_time, merchant_name, merchant_id, descr (item description), item_price, item_qty,
  ordertotal, tax, slice_order_id, item_id, quality, digital_good, category_name, record_status, entry_date.
  NIQ files cancellations under separate senders: `<Provider> Cancellation`, `iTunes Cancellation`,
  `Google Play Cancellation` (e.g. "Your Google One subscription … will be canceled on Sep 30, 2026").
  Apple paid receipts: `App : Plan (Monthly)` priced; Apple confirmations `App Plan $X /month` are UNPRICED (not charges).
  Apple `ordertotal` is the whole email (multi-item), use item_price. Google Play: `Plan (App) Auto-renewing subscription`.
- `eu_ai_items.parquet` — NIQ Fox `SHARE_NIQ.SRS.FOX_TRANSACTION_ITEMS`, UK/DE/FR/ES/IT. Columns: uid (user_id),
  country, dt, email_type (order / cancel / subscription / plan update / payment-* …), merchant_name (lowercase),
  seller_name (PayPal payee), product_name, descr (product_description), item_price, item_quantity, order_total,
  order_currency, order_id, item_id, industry, payment_method, order_attributes (JSON string; may hold is_spam /
  is_deleted / is_trash flags — exclude those rows if set).
  Apple: `app || plan (period)` with the period in the local language; Google Play: `plan (app)(by|de|di|von publisher)`;
  PayPal: seller_name = provider, product_name = plan; Stripe-billed direct charges appear as merchant `stripe`.
  Fox has cancellation emails ONLY for ChatGPT direct (`email_type = 'cancel'`).
- Both panels backfill years of each mailbox's history before it joined; use it all.

## Facts already measured (2026-10-19)
- Renewal receipts are visible (July payers seen paying in August): US Apple 62–84%, Google Play 71–90%, Claude direct
  87%; EU Apple 46–79%, Google Play 65–89%, PayPal 72–91%, Stripe 68–87%, Claude `anthropic` 56%.
- ChatGPT direct sends a sign-up receipt only (renewals 4% US, 0% EU) plus cancellation emails.
- US direct X Corp / Perplexity / Cursor PAID receipts are essentially absent (cancellation senders exist). Report what
  you find; channels with no paid receipts are left out of that panel (disclosed), not imputed.
- Cancellation emails capture only 20–85% of US churners (uneven by channel), so churn = earlier of cancellation email
  or renewals stopping (handled by the engine, not your filter).

## Deliverables (write ONLY these files)
1. `filters_receipts/{provider}.py` exposing `classify(df, panel) -> pd.DataFrame` (`panel` in us/eu; raw extract in).
   One row per candidate item for THIS provider with columns:
   `uid, dt, country` (eu; 'us' for US), `provider, tier, cadence (M/A), plan` (e.g. `plus_M`),
   `channel` (apple / google_play / paypal / stripe / direct / other), `kind` (`charge` or `cancel`),
   `amount, currency` (charges), `end_date` (cancel: stated end date if the text gives one, else NaT),
   `renews` (bool: does this provider×channel×panel send renewal receipts — False for ChatGPT direct),
   `keep` (bool), `reason` ('ok' or why rejected). Provider ids: chatgpt, claude, gemini, grok, grok_x, muse, cursor,
   perplexity. Pure pandas, deterministic, no Snowflake.
   - Charges: paid consumer subscription receipts only (price > 0). Exclude trials ($0 / "trial"), unpriced
     confirmations, refunds, Team/Business/Enterprise, API / credits / usage, storage-only Google One, unrelated apps
     and false matches (e.g. "x premium" recipe products, ITVX, Gemini Trust).
   - Cancels: cancellation / "has ended" / "will be canceled" / "will end on" emails for a consumer plan. EXCLUDE
     trial endings ("trial has ended") and storage-only plans. Map to the same plan where the text allows (else plan
     'unknown_M' is fine; the engine uses provider level for cancels when plan is unknown).
   - De-duplicate repeated line items (same uid, day, channel, plan, amount).
   - Plan / cadence from the text first (receipts usually name the plan and period), amount bands second.
   - Muse (US only): iTunes bare "Power Plan" / "Maximum Plan" (and "Power Plan : Power Plan (Monthly)") at Muse
     prices from 2026-09-07 are Muse charges; "muse from meta" unpriced Apple rows are confirmations (not charges).
   - Grok: SuperGrok/Heavy/Lite/Plus/X Subscription → `grok`; X Premium+ → `grok_x`; basic X Premium/Basic excluded.
2. `filters_receipts/{provider}_report.md` (<500 words): matched senders/patterns per panel and channel, plans found,
   exclusions with volumes, monthly payers by channel (2025-01 onward, US and EU totals), renewal visibility and
   cancellation volumes per channel, caveats, open questions.

Small Snowflake checks are allowed only via the local connector on `ANALYST_L`
(`snowflake.connector.connect(connection_name="default", warehouse="ANALYST_L")`), filtered by date. Don't edit shared
files. If the keyword prefilter (`extract_receipts.py` RECEIPT_KEYWORDS) misses a sender, say so with evidence.

Return a summary (<250 words): patterns, plans, latest-month payers by channel per panel, caveats, open questions.
