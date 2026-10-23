# Provider filter brief (card panels)

Goal: for ONE provider, find the card transactions that are consumer, web-billed (direct) subscription payments, and
classify each into a plan (tier x cadence). The output feeds `subs.py` (subscriber index, gross adds, churn).

## Inputs (all in `C:/Users/fintan.creedon/code/exploration/ai/`)
- `.cache/omega_ai_txn.parquet` — US (Earnest CE Prime Omega, 2022 consistent-shopper panel). Columns: transid, uid,
  cardid, merchid, descr (raw descriptor, per MERCHID, UPPERCASE), dt, partner_post_date, filedate, amount (positive =
  debit), currency (USD; drop others), transtype (debit/credit), cardtype, user_score.
- `.cache/{uk,de,fr,es,it}_ai_txn.parquet` — Europe (Fable). Columns: fdtxnkey, uid, descr (per transaction,
  lowercase), dt, posteddate, reportdate, spendout (NEGATIVE = spend), spendin (inflow/refund), currency (GBP/EUR),
  usertype (C consumer / B business), usercountry, tag, mcc, txntype, recordstatus, paymentprocessorname,
  origmerchantcountry. The EU files land over time: wait for them with
  `until grep -q "it_ai_txn" .cache/extract.log; do sleep 60; done` (also check the log for errors). Start on US/UK.
- These extracts are a deliberately broad keyword prefilter (`keywords.py`), from 2023-01-01. Matching keywords for other
  providers are in the same files; ignore them.
- `plans/{provider}_prices.csv` + `plans/{provider}_notes.md` — researched price history by region, incl. VAT, promos,
  collisions, non-consumer plans, known descriptors. Treat as hypotheses: the data decides.

## Agreed rules (user decisions)
- Consumer only. Exclude Team/Business/Enterprise seats, API/usage/credits, app-store billing (Apple; Google Play
  rows — e.g. US `GOOGLE *CHATGPT` — are tagged `channel='google_play'`, keep=False, but count them in the report).
- Exclude refunds/credits (transtype credit, spendin>0), $0/$1 auths, trial-cancel artefacts; de-duplicate same uid +
  same day + same amount (pending/posted repeats).
- Fable: keep usertype C only (report B's share of matched payments); keep `ABS(reportdate - dt) <= 7`.
- Plan = tier x cadence (M monthly / A annual). Where amounts collide across plans (e.g. $200 Claude Pro annual vs Max
  20x monthly; Google One AI vs storage tiers), use the uid's own payment history (gap between same-amount payments:
  ~28-31d = monthly, ~365d = annual) to resolve; if unresolvable, label `ambiguous` and report the count.
- USD-billed providers in Europe (Cursor, Perplexity, some legacy ChatGPT/Claude subs) show converted GBP/EUR amounts
  that drift with FX: derive bands empirically (amount clusters by month) rather than fixed list prices.
- US prices exclude sales tax: allow up to ~+11% above list.
- Promos (50% off months, referral credits) produce odd amounts: map them to the plan when defensible, and say so.

## Deliverables (write ONLY these files)
1. `filters/{provider}.py` exposing `classify(df: pd.DataFrame, panel: str) -> pd.DataFrame`, where `panel` is one of
   omega/uk/de/fr/es/it and `df` is the raw extract for that panel. Return one row per kept-or-rejected candidate
   payment for THIS provider with columns: `uid, dt, amount` (positive, local currency), `currency, descr, provider,
   tier, cadence (M/A), plan` (e.g. `plus_M`), `channel` (web/google_play/other), `keep` (bool), `reason` (why
   rejected, or 'ok'). Pure pandas, deterministic, no Snowflake calls. Provider ids: chatgpt, claude, gemini, grok
   (SuperGrok direct), grok_x (X Premium+ — a separate provider line), muse, cursor, perplexity.
2. `filters/{provider}_report.md` (<700 words + small tables): descriptors found and the include/exclude regex with
   member counts; amount bands per plan/region/period and how they were set (show the amount histograms in words or
   tables); monthly vs annual evidence (inter-payment gap distribution); exclusions and their volumes (Team, API,
   Google Play, refunds, business users); unclassified/ambiguous share; a sanity series: monthly unique kept payers by
   plan per panel (2024-01 onward); panel-specific caveats; open questions for the user.

Small Snowflake follow-ups are allowed only via the local connector on the `ANALYST_L` warehouse
(`snowflake.connector.connect(connection_name="default", warehouse="ANALYST_L")`, `USE SCHEMA SRS_MCP.SANDBOX` for
temp tables) — e.g. to check a descriptor missed by the keyword prefilter. Never scan full tables without date
filters. Do not edit shared files (`subs.py`, `extract.py`, `keywords.py`); if the prefilter misses descriptors, say so
in the report with the evidence.

Return a summary (<300 words): filter, plans found per panel, kept payers latest month per panel, main caveats, open
questions.
