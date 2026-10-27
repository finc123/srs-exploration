# AI subscriber tracker: card panels (record)

Built 2026-10-19. Report: https://claude.ai/artifact/87noqk9VpcYs6LXFMRfdzC (v1, private).
Per-provider detail (descriptor tests, amount bands, volumes, open questions): `filters/{provider}_report.md`.
Price research by region: `plans/{provider}_prices.csv` and `plans/{provider}_notes.md`.

## What it measures

Consumer **paid** subscribers to AI chatbots and tools, from card charges: web billing plus Google Play where the app
is named. Apple App Store billing has no app name in either panel, so it is excluded everywhere. Free users,
Team/Business seats, API and usage credits are out of scope.

For each panel × provider and panel × plan (tier × billing cycle), daily:
- **Subscribers** (index): members with a live subscription. Shown as subscribers per 1,000 active panel members
  (active = any transaction in the trailing 35 days) and as share of all tracked subscribers in the panel.
- **Gross adds**, of which **reactivations** (a returning churned subscriber), **churn** and churn rate.
- **Adds removed for panel exit** (revision size for recent months).

Unweighted panel counts. No end-of-data cutoff; the latest month is partial and recent months are provisional.

## Panels

| Panel | Source | Member id | Notes |
|---|---|---|---|
| US | Consumer Edge CE Prime Omega base share (`SHARE_CE_PRIME_ENRICHED_OMEGA_2822.PRIME_OMEGA`), `aggregate_consistent_shopper_2022_v2`, `AFFECTED_ACCOUNTS_092026` excluded. Same rows as `EARNEST.COMMON.CE_PRIME_OMEGA_PANEL_TXNS` (2022 panel) without the per-symbol fan-out | CARDLINKID (= MEMID) | 3.6M members; 99.5% active at data end, so exits are rare |
| UK, DE, FR, ES, IT | `SHARE_FABLE.FABLE_SIGNAL.{UK_V2, DE_V2, FR_V3, ES_V2, IT_V2}_TXN`, USERTYPE = C only | FDUSERKEY (card/account level) | Members average 1.5–4.7 activity spells; 35–50% active at data end. European Google Play charges rarely carry the app name |

## Subscriber rules (`subs.py`)

- **Gross add:** first payment of a subscription by a member whose activity spell started more than 35 days earlier.
  New-to-panel subscriptions are excluded at both ends.
- **Lapse:** published v1 used "no renewal within 35 days of a monthly charge". **Code now uses 45 days** (user
  decision after v1: the 35-day rule added ~3–6 points of false monthly churn, because 3–6% of renewals post 36–66
  days after the previous charge). The churn is dated at the end of the paid period (last payment + 31 days).
  Annual: 365 + 35 days. **v1 page not yet re-run with 45 days.**
- **Churn vs panel exit:** churn if the member transacted in the 30 days before the lapse; otherwise a panel exit,
  and the whole subscription is removed from history retroactively.
- **Plan vs provider level:** switching tier or cadence is churn plus an add at plan level and continuous at provider level.
- **Price collisions** (same amount for two plans): descriptor first; otherwise a repeat within 25–40 days means
  monthly, and a one-off means annual or storage. One-offs in the last 40 days are provisional.

## Card descriptors by provider

Descriptors are upper case in the US panel (per merchant id) and lower case in Fable (per transaction). The broad
prefilter is `keywords.py`; the exact rules are in `filters/{provider}.py`.

| Provider | Included descriptors | Plans | Excluded / special handling | Known breaks |
|---|---|---|---|---|
| ChatGPT | `OPENAI *CHATGPT SUBSCR`, `CHAT ?(GPT\|GP\b)` (incl. the truncated `CHATGP`, e.g. `GOOGLE *CHATGP MOUNTAIN VIE CA`, `PAYPAL *OPENAI *CHATGP`; added 2026-10-26), `OPENAI ?* ?CH`, `OPENAIOPCO`, PayPal OpenAI; Google Play `GOOGLE.{0,4}CHAT ?(GPT\|GP\b)`. Bare `OPENAI` only when a plan amount recurs monthly | Go, Plus, Pro 100, Pro 200, Pro 500 (monthly only) | Team/Business by seat-multiple amounts; `CHATGPT CRED` credit packs; Sora on Play; FR €1–1.50 FX fee rows; transfers/payroll; third-party "ChatGPT" apps | Legacy USD billing in UK/EU before ~Feb 2025 (converted amounts) |
| Claude | `CLAUDE.AI SUBSCRIPTION` (to Jun 2026), `ANTHROPIC* CLAUDE SUB`, Fable masked `<name>.ai subscription` and `claudeai`; Google Play | Pro M/A, Max 5x, Max 20x | Team; bare `ANTHROPIC` = API unless a list price recurs monthly; PHILANTHROPIC / ANTHROPICS; fees, refunds | Descriptor change Jun 2026; **ES: masked as MCC 8299 "schools and educational services" from Jun 2026 (not captured)** |
| Gemini | Google One / Google Storage (`GOOGLE *GOOGLE ONE`, `GOOGLE STORAGE`, `GOOGLE ONE AI PREMIUM` = AI only), and **SKU codes from 15 Sep 2026** (`G1AI101` AI Pro, `G1AI102` Ultra, `G1AI103` AI Plus, `G1SK003` 2TB / AI Plus 2TB, `G1SK008` legacy AI Premium; trailing M/A = cadence); Fable masks the code as `google ttttt` | AI Pro M/A, AI Plus M/A, Ultra (incl. 5x/20x), AI Plus 2TB (from 27 Jan 2026) | Storage-only tiers (by price or SKU); GEMINI TRUST (crypto); "One…" Play developers; Workspace. US $19.99 one-offs without SKU = 100GB annual | Google One SKU switch 15 Sep 2026 (old descriptors collapsed); 2TB plan joins on 27 Jan 2026 (~24k US existing payers enter as adds) |
| Grok (xAI) | `GROK XAI`, `XAI LLC`, `X.AI/ABOUT`; Google Play `GOOGLE.{0,4}GROK` | SuperGrok M/A, Heavy M/A, Lite, Plus, The X Subscription (`xsub_*`, from 10 Oct 2026) | API credit top-ups; ngrok etc.; $300/$100 collisions by payment gaps | `XAI LLC` → `GROK XAI` 20 Mar 2026 (continuous) |
| X Premium+ | `X CORP. PAID FEATURES`; **US masks the X from 27 Jun 2024** (`CORP. PAID FEATURES ABOUT. .COM`); Google Play `GOOGLE.{0,4}(TWITTER\|X CORP)` | Premium+ M/A (price ladder Oct 2023, Dec 2024, Feb 2025) | Basic and Premium tiers by price; `PAYPAL *X CORP` (other merchant); ads, dev platform | US masking from Jun 2024 |
| Muse | `METAPAY ?(\d{4} )?META.COM` without `*`; Google Play `GOOGLE *MUSE FROM META` (from 7 Oct 2026) | Power, Maximum (monthly) | Meta One / Verified look-alikes by price; METAPAY* P2P | US only; Europe has no rows |
| Cursor | `CURSOR, AI POWERED IDE` family, bank wrappers, Privacy.com, Curve | Pro M/A, Pro+, Ultra | `CURSOR USAGE` invoices; Klarna instalments; Anysphere ACH/payroll; Precursor etc.; Teams $40 seats | USD billing everywhere (FX-converted in Europe; VAT from 2026); **ES masked as MCC 8299 from Jun 2026**; new sign-ups from 12 Oct 2026 move to The X Subscription |
| Perplexity | `PERPLEX…`, **brandless 8 Jun – 4 Oct 2026** (`PRO SAN FRANCISCO CA`, `PRO WWW.PERPLEXIT`, `MAX …`, FR `cb pro`, ES `compra pro, san francisco`); Google Play | Pro M/A, discounted Pro ($4.99 / $10), Max M/A | Enterprise; API/credits; Computer credits; Samsung store; merch, games | Brandless descriptors Jun–Oct 2026; partner promotions create conversion waves |

## Open decisions (from v1)

1. Spain MCC 8299 rule for Claude (exact Claude prices plus monthly recurrence or prior Claude payment; ~2–5% false
   positives, about +450–500 payers a month). Cursor new sign-ups there can't be identified reliably.
2. Gemini 2TB base as opening stock on 27 Jan 2026 rather than gross adds.
3. The X Subscription as its own line.
4. Keep or drop the bare OPENAI / ANTHROPIC monthly-recurrence rule.
5. Fill-rate study to set how many recent days are provisional (US data dip late Jul / early Aug 2026; FR reporting lag ~16 days).

## Rerun

```
python extract.py omega uk de fr es it --txn-only   # candidate rows (ANALYST_XL, ~45 min); drop --txn-only to refresh activity spells
python -c "import run_metrics as R; R.OUT=R.CACHE/'metrics_omega'; R.main(['omega'])"
python -c "import run_metrics as R; R.OUT=R.CACHE/'metrics_eu'; R.main(['uk','de','fr','es','it'])"
python merge_metrics.py && python build_report.py   # writes report/ai_subs_cards.html
```
