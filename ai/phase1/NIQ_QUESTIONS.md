# Questions for NIQ: receipt capture changes seen in AI-subscription work (Oct 2026)

Sources:
- US: `SRS_SLICE.COMMON.ITEMS_LIVE` (Slice), active mailboxes, data to 2026-10-18.
- EU: `SHARE_NIQ.SRS.FOX_TRANSACTION_ITEMS` (Fox), UK/DE/FR/ES/IT, data to 2026-10-13.

Panel: mailboxes or users with at least one paid AI-subscription receipt (US 397k, EU 139k). For each change below,
please tell us whether a parsing, sender-mapping or ingestion change explains it, and if so when it happened and whether
history was or will be restated.

## 1. May–June 2026: fewer Google One storage receipts from Google Play (US and EU)

Measure: of panelists with a paid monthly receipt from a sender in both of the two prior months, the share that also
have one in the given month.

| Sender (paid monthly receipts) | Mar | Apr | May | **Jun** | Jul | Aug | Sep 2026 |
|---|---|---|---|---|---|---|---|
| US Google Play "NNN GB (Google One)" storage | 0.958 | 0.956 | 0.849 | **0.711** | 0.937 | 0.936 | 0.920 |
| US iTunes "iCloud : iCloud+ … (Monthly)" | 0.972 | 0.974 | 0.977 | 0.975 | 0.978 | 0.979 | 0.976 |
| US YouTube Premium (iTunes / Google Play / YouTube) | 0.915 | 0.902 | 0.905 | 0.898 | 0.919 | 0.920 | 0.899 |
| EU google play "(google one)" storage | 0.943 | 0.938 | 0.865 | **0.755** | 0.921 | 0.926 | 0.841 |
| EU apple "icloud+" | 0.953 | 0.962 | 0.965 | 0.963 | 0.969 | 0.967 | 0.959 |
| EU YouTube Premium | 0.948 | 0.947 | 0.950 | 0.905 | 0.873 | 0.925 | 0.857 |

Paid Google One storage receipts on Google Play in our panel, by month:

| | Apr | May | Jun | Jul 2026 |
|---|---|---|---|---|
| US | 70.4k | 62.9k | 46.8k | 46.3k |
| EU | 20.0k | 18.5k | 14.9k | 14.6k |

That is a drop of about one third from April to June, and the level has not recovered. iCloud+ is flat over the same
period.

**Questions:**
- Did Google Play storage receipts change format, sender or subject in May–June 2026, in either panel?
- Did parsing of "(Google One)" items on Google Play change?
- Or is this a real product change, for example storage being folded into Google AI plans?

## 2. Around July 2025: step up in Apple ("iTunes Cancellation") cancellation emails for AI apps (US)

Measure: the share of confirmed lapses of Apple-billed AI subscriptions that have an "iTunes Cancellation" email for the
same app within ±45 days of the end of the paid period, by paid-through month. A confirmed lapse means no further paid
receipt within the renewal window, with the mailbox still active.

| App | Mar 2025 | Apr | May | Jun | **Jul** | Aug | Sep | Oct 2025 |
|---|---|---|---|---|---|---|---|---|
| ChatGPT | 0.41 | 0.46 | 0.52 | 0.54 | **0.61** | 0.61 | 0.61 | 0.63 |
| Claude | 0.51 | 0.54 | 0.52 | 0.57 | **0.75** | 0.72 | 0.77 | 0.80 |
| Grok | 0.35 | 0.50 | 0.61 | 0.64 | **0.78** | 0.75 | 0.79 | 0.82 |
| Perplexity | 0.46 | 0.66 | 0.59 | 0.60 | **0.69** | 0.69 | 0.69 | 0.81 |

ChatGPT quarterly: 0.46–0.52 in 2024Q4–2025Q2, then 0.61–0.64 in 2025Q3–2026Q2. Google Play cancellation emails show no
step at that point.

**Questions:**
- Was "iTunes Cancellation" parsing or sender coverage extended around June–July 2025?
- Were any Apple subscription-status email types added then (for example "subscription expiring" or "cancelled")?

## 3. From July 2025: fewer ChatGPT direct sign-up receipts relative to cancellations (US)

Measure: the share of "Chat GPT Cancellation" emails ("ChatGPT Plus/Go/Pro subscription cancellation") whose mailbox
has an earlier paid ChatGPT direct sign-up receipt.

| | Sep 2024 – Jun 2025 | Jul 2025 | Aug 2025 – Sep 2026 |
|---|---|---|---|
| Share with an earlier direct sign-up receipt | 0.92–0.95 | 0.86 | 0.61–0.73 |

Volumes over the same period: direct sign-up receipts were 3–6k a month (about 10k in Apr 2025 and 9–11k in Jul–Sep
2026), while direct cancellation emails rose from 1.2–2k a month (late 2024) to 6–12k a month (2026).

**Questions:**
- Did the ChatGPT direct paid-receipt sender, template or parsing change around July 2025 (for example a new billing
  provider, sender address or receipt layout)?
- Are some sign-up receipts no longer captured?
