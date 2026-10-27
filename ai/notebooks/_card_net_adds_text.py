"""Finding notes for card_net_adds.ipynb, written after reading the executed results (card data to 2026-10-25 with the
truncated "CHATGP" descriptor matched; e-receipts to 2026-10-20). Churn rule: fixed 45-day cutoff on both sources."""
FINDINGS = {
    "cycles": """
**Finding: the billing cycle is 31 days, but p99 is about two cycles (58-63 days).**
- About 92-94% of in-subscription gaps are 26-35 days, and the median is 31 days in every provider x channel x family.
- The tail is not a slow drift (36, 40, 45 days). It is a second bump at 56-66 days: one monthly charge missing between two normal ones. This is about 1% of web gaps and 2-6% of Google Play gaps, and the p99 lands on it.
- p95 is 33-34 days on the web and for ChatGPT Google Play. Claude and Perplexity Google Play and Gemini have p95s of 39-61 days, pushed up by a Jul-Aug 2026 skip (section 2).
- **The churn rule therefore uses a fixed 45-day cutoff** (section 4), not p99. 45 days sits past the 26-35 day cycle plus late or retried payments, but before the two-cycle bump. Each gap above 45 days reads as a churn followed by a re-add: about 1.5% of web gaps.
""",
    "steady": """
**Finding: most members are steady, and conditioning on a steady history only helps on the web.**
- **Per member:** 64-78% of members have every gap 26-35 days, and the median member's gaps span 3-5 days. Calendar months alone (28-31 days) account for 3 days. But over their whole history, 15-34% of members have at least one gap above 35 days.
- **"Paid the prior month" barely moves p99:** web 58 → 56-59, Google Play 62-63 → 61-63. With 3+ prior normal months, web p99 is 46-52; with 6+ it is 43-47. Google Play stays at 61-63 even after 6 normal months, and so do the Google Play e-receipts (p99 61-62).
- **Even the steadiest members have 1.6-1.8% of web gaps above 35 days** (2.4% for ChatGPT Google Play). A 35-day rule would read that share of continuing subscribers as churn plus re-add every month.
- **Anchor test:** 26-49% of web gaps of 40-75 days, and 42-68% of Google-billed card gaps, are exactly two cycles (±2 days). The billing day is kept and one charge is missing. A re-subscription would restart billing on a random day. In the Google Play e-receipts only 16-28% of long gaps keep the billing day. So the extra two-cycle gaps on Google-billed cards are mostly charges we don't see, not cancellations.
""",
    "regularity": """
**Finding: members keep a steady cycle; the irregularity is skipped months, and on Google-billed cards much of it was our descriptor matching.**
- Of gaps above p95, 58-83% are followed by a normal gap. A late payment is a one-off (one missing charge), not a change of cycle. The "t+30, t+40, t+30" pattern is rare: 36-45 day gaps are about 1-1.5% of all gaps.
- **ChatGPT: fixed.** Some issuers truncate the Google Play descriptor to `GOOGLE *CHATGP MOUNTAIN VIE CA` (no final T). This form grew from Oct 2025 and peaked at about 3.8k panel rows a month in Aug 2026. Before the fix it was not matched, so 10-15% of continuing ChatGPT Google Play subscribers appeared to skip a month in Jul-Aug 2026 (5% in Nov 2025). With `CHATGP` matched, the skip share is a flat 2-3%, close to the e-receipts (about 1.2-1.8%).
- **Not yet checked for the others:** 11-21% of continuing Claude and Perplexity Google Play subscribers, and of Gemini (Google One), still skip a month in Jul-Aug 2026, against 2-4% before. The Google Play e-receipts show no change, so this is likely a similar descriptor change that our patterns miss. These two months are marked as card gap months in sections 5-8.
""",
    "receipt_cycles": """
**Finding: the cycles now agree for ChatGPT.** Card and e-receipts both have a median of 31 days, p95 of 34 vs 37 days and p99 of 62 days. The ~60-day bump is in both sources (1-2% of receipt gaps), so part of it is real: paused subscriptions, failed payments recovered a month later, or a renewal email that didn't arrive. Claude and Perplexity card p95s are still inflated by the Jul-Aug 2026 skip.
""",
    "card_flows": """
**Findings (card, 45-day lapse churn, complete months to Sep 2026).**
- Monthly churn per start-of-month subscriber: ChatGPT web Plus about 7-10%, Google Play Plus about 11-15%; Claude web Pro about 12-17%; Gemini AI Pro about 8-12% outside Jul-Aug 2026. Google Play churns faster than web.
- **ChatGPT Google Play is now steady:** 11.5-14.7% a month, with no spikes in Nov 2025 or Jul-Aug 2026.
- Plan switches are 3-6% of plan-level churn for ChatGPT, Gemini and Perplexity, but 27% for Claude web (Pro to Max upgrades). For Claude, a plan-level read overstates churn and gross adds by about 8k each since 2025.
- **Gemini, and Claude and Perplexity on Google Play, still spike in Jul-Aug 2026** (e.g. Gemini AI Pro 21-23% vs about 9%). This is the same kind of missed charge; not fixed yet.
""",
    "comparison": """
**Findings (45-day cutoff on both sides, ChatGPT descriptor fixed).**
- **Gross adds and net adds move together** for ChatGPT: correlation of monthly rates 0.97 (gross adds) and 0.95 (net adds). For Claude it is 0.78 / 0.84, and for Perplexity 0.61 / 0.68.
- **Card lapse churn tracks e-receipt lapse churn** for ChatGPT: correlation 0.63, and a stable ratio (card 0.81x receipts, CV 0.08). The card rate is about 13% a month against 16% on receipts. Both sources measure the same thing in the same way, and they agree.
- **Card churn does not track e-receipt cancellations:** correlation 0.29 on levels, 0.18 on monthly changes. The card/cancellation ratio drifts from about 1.0-1.1 in 2025 to 1.4-1.5 from Jun 2026. Card churn is steady at 12-15%, while e-receipt cancellations fall from about 13% to 7.6% (Sep 2026).
- **So the 2026 divergence is inside the e-receipts.** Cancellations as a share of e-receipt lapses fall from about 0.70-0.77 to 0.49 (section 8). A growing share of ChatGPT Google Play subscriptions end without a cancellation email.
- **Claude and Perplexity Google Play are too small to judge** (50-1,400 card subscribers a month). Their ratios have a CV of about 0.3, even outside Jul-Aug 2026.
- About 60-71% of e-receipt cancellations fall inside a seen subscription. The rest have no paid receipt in the channel (trials, or sign-ups before the receipt window).
""",
    "timing": """
**Finding: e-receipts flag churn about seven weeks before the 45-day card rule can confirm it.** The median cancellation email arrives 22-24 days before the next charge would have been due, and **46-48 days before the card rule knows** (last payment + 45 days + 10 days posting lag). A quarter of cases are 55+ days earlier. The upper deciles (80+ days) are cancellations with a later renewal receipt, e.g. cancel then resubscribe.
""",
    "backtest": """
**Finding: with the ChatGPT descriptor fixed, the nowcast does not beat the naive forecast.**
- **ChatGPT:** MAE 1.8pp vs 1.05pp naive, with the nowcast running about 1pp low. Card churn is now so steady (11.5-14.7%) that "same as the last complete month" is hard to beat. The nowcast inherits the downward drift in e-receipt cancellations, and the trailing ratio lags behind it.
- The earlier result (nowcast beats naive once the gap months were excluded) came from the false card churn spikes. It does not hold on the corrected data.
- **Claude and Perplexity:** worse than or equal to naive, on small panels.
""",
    "gpt_counts": """
**Findings: where they track and where they deviate (ChatGPT descriptor fixed).**
- **Card churn rises steadily** from about 270 a month (Jan 2025) to 2,560 (Sep 2026), at a steady 11.5-14.7% of start-of-month subscribers, as the card base grows from 1.9k to 22k.
- **E-receipt lapse churn moves with it:** 620 → 2,240, at 14-19%. In 2026 the counts are close (e.g. May 2,035 vs card 2,109; Sep 2,236 vs 2,557), although the card base has grown faster (about 12x since Jan 2025 vs 4x on receipts).
- **E-receipt cancellations track until about Mar 2026, then fall away:** they rise with the others to 1,478 in March, then decline to about 1,100 a month while both lapse measures keep rising. As a share of start-of-month subscribers, cancellations fall from about 11-13% to 7.6%.
- **The deviation is inside the e-receipts.** Cancellations as a share of e-receipt lapses fall from about 0.70-0.77 (2025 to Mar 2026) to 0.58 (Jul-Aug) and 0.49 (Sep). A growing share of subscriptions end without a cancellation email. Possible causes: involuntary churn (failed payments send no cancellation email), promo or discounted subscriptions ending, or lower capture of cancellation emails.
- **Practical read:** for ChatGPT Google Play, e-receipt *lapse* churn is the close match to card churn, but it is no faster (it also needs 45 days after the last receipt). Cancellation emails are faster, but their coverage of churn has been falling since March 2026, so they need correcting before they can nowcast card churn.
""",
    "summary": """
## Summary (45-day cutoff, ChatGPT descriptor fixed)

1. **The billing cycle is regular** (92-94% of gaps 26-35 days, median 31, members keep their cycle). p99 is about 60 days because of one-off missed charges, not because the cycle drifts. **A fixed 45-day cutoff** confirms card churn about 55 days after the last payment.
2. **Card tagging:** the truncated `GOOGLE *CHATGP` descriptor (no final T) was missed until 2026-10-26 and caused false card churn spikes for ChatGPT Google Play in Nov 2025 and Jul-Aug 2026. It is now matched. Claude, Perplexity and Gemini still show a Jul-Aug 2026 skip, probably the same kind of descriptor change; not checked yet.
3. **ChatGPT Google Play, card vs e-receipts:** gross adds and net adds trend alike (r = 0.97 / 0.95), and card lapse churn tracks e-receipt lapse churn (r = 0.63, stable ratio 0.81). **E-receipt cancellations do not track:** since March 2026 they cover a falling share of churn (cancellations / lapses 0.75 → 0.49). The nowcast built on them does not beat the naive forecast.
4. **Next step:** find out why ChatGPT Google Play subscriptions increasingly end without a cancellation email. Look at mailboxes whose Google Play renewals stop with no cancellation since March 2026: failed-payment emails, promo plans, or mailboxes that stop sending receipts. If it is involuntary churn, model it separately and add it to the cancellations.
""",
}
