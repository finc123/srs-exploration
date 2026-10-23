# Muse from Meta (`muse`): card-panel filter report

Data through 2026-10-17 (Omega). Muse launched in the US on 2026-09-08 and in Canada on 2026-09-18. It is not available in the UK or EU. The series is about six weeks long.

## Descriptors and rule

The rule is reused unchanged from `meta/app/sections.py` (`muse_web_sql`, `WEB_BUCKETS`, `plan_sql`).

| Channel | Regex (case-insensitive) | Omega rows / uids / variants |
|---|---|---|
| web (candidate) | `METAPAY ?(?:\d{4} )?META\.COM` AND NOT `METAPAY ?\*` | 174 / 107 / 14 |
| google_play (kept, user decision) | `GOOGLE ?\*? ?MUSE FROM META` | 24 / 23 / 12 |
| not Muse (not returned) | `METAPAY ?\*…` (Meta Pay P2P, e.g. `METAPAY*GEMINI LEE`) | 120 / 11 |

The web variants are processor wrappers around a single merchant: `METAPAY META.COM CA`, `METAPAY 5818 META.COM CA …`, `DC : PURCH METAPAY 5818 META.COM CA`, `METAPAYMETA.COM CA`, and so on. These other META.COM merchants are not matched: TRUEMED META, SP NEW META, VONEMETA, MKMETA and SIKA * META WWW.META.COM. No Meta Quest or hardware descriptor appears on `METAPAY META.COM`. The one large charge ($213.20, 2026-10-11) is out of band and rejected.

**Google Play.** The notes say Google bills Muse as `GOOGLE *FACEBOOK`, which would make it inseparable from other Meta apps. That is wrong: Google Play has a dedicated `GOOGLE *MUSE FROM META` descriptor, first seen on 2026-10-07. It shows 23 payers in October, mostly at $20.00 to $21.90 (Power at $20 plus tax). **Per the user's decision, these rows are kept** with `channel='google_play'`, using Play price bands `PLAY_BUCKETS`: Power $19.99 to $22.20 and Max $99.99 to $111.00 ($20 / $100 plus tax). 21 rows are kept, all Power, $20.00 to $21.86. Two rows are out of band ($15.00 and $50.67) and one is a courtesy-pay fee. No Max rows appear on Play yet. The Meta One look-alike bands are not applied to Play, because that descriptor is specific to Muse.

## Amount bands (Omega, web descriptor, dated 2026-09-07 or later)

| Band (USD) | Rows | Read |
|---|---|---|
| ≤ 1.00 | 0 | (auth) |
| 1.22 to 6.49 | 9 | out_of_band: possibly token packs or other Meta charges |
| 11.99 to 13.25 | 29 | **lookalike**: a legacy Meta subscription that predates Muse, seen monthly since June 2026 |
| 15.00 | 1 | out_of_band (the same uid paid $15 on 09-06, before launch) |
| **15.99 to 17.60** | **49** | **Power, web.** $16.00 untaxed (25 rows), $16.96 to $17.51 taxed |
| 19.99 to 22.19 | 12 | **lookalike**: Meta One Premium / Verified, recurring since June |
| 30.00, 48.35 to 55.34 | 10 | out_of_band: **unexplained cluster around $50 plus tax** (8 uids, from 2026-09-08) |
| **79.99 to 88.00** | **1** | **Max, web** ($84.80) |
| 213.20 | 1 | out_of_band |

The bands are the fixed `WEB_BUCKETS` (list price to +10% tax). The data support them. The Power band holds nothing before launch, while the adjacent $11.99 to $13.25 and $19.99 to $21.59 bands hold June to August recurring payers, which confirms that those are separate products. No Meta One Core charge at $7.99 appears on this descriptor. In-band charges dated before 2026-09-07 are rejected as `pre_launch`; there are none.

## Cadence

Muse is monthly only, so every row is `cadence=M`. Only one kept uid has a second payment so far, 30 days after the first (09-08 to 10-08). Most first payments fall on 09-17 or later, so their renewals land after the data cutoff.

## Exclusions (Omega)

| Reason | Rows | uids |
|---|---|---|
| ok (kept): web | 50 | 49 |
| ok (kept): google_play | 21 | 21 |
| lookalike_legacy_meta_sub ($11.99 to 13.30) | 69 | 31 |
| lookalike_meta_one_premium ($19.99 to 22.19) | 32 | 10 |
| out_of_band: web | 23 | 20 |
| out_of_band: google_play | 2 | 2 |
| fee_or_adjustment (Google courtesy-pay fee) | 1 | 1 |
| refunds / credits, auths, duplicates | 0 | 0 |

Unclassified or ambiguous: there are no ambiguous plans, because the Power and Max bands do not collide. The only unexplained in-descriptor spend is the web out-of-band share (23 rows), and the $50 cluster is the part of it that matters.

## Sanity series: monthly unique kept payers (2024-01 onward)

| Panel | ≤ 2026-08 | 2026-09 | 2026-10 (to 10-17) |
|---|---|---|---|
| omega power_M, web | 0 | 21 | 28 |
| omega max_M, web | 0 | 0 | 1 |
| omega power_M, google_play | 0 | 0 | 21 |
| omega, all (unique uids) | 0 | 21 | 50 |
| uk / de / fr / es / it | 0 | 0 | 0 |

## Europe (Fable)

Muse has no hits in any Fable panel, which matches the non-launch: there are zero rows on `metapay … meta.com` and zero on `muse from meta`, in all periods, for every panel (UK 2.43M, DE 1.32M, FR 3.56M, ES 1.43M and IT 1.13M prefiltered rows). The only `meta.com` matches are unrelated merchants such as leadershipmeta.com, mkmeta.com and vonemeta.com. The `muse.ai` and `my-muse.ai` hits are other companies (muse.ai video hosting in San Ramon, my-muse.ai in Nicosia/Dover, vidmuse.ai). Because no Muse rows exist, the business-user share has nothing to apply to (no report-lag filter is applied: all rows are used). For Fable, `classify` returns an empty frame, and any future web or Play hit would be rejected as `region_not_launched` until a UK/EU launch.

## Caveats

- The samples are very small (about 50 payers). Use the series for direction only until more months accrue.
- First payments cluster from 09-17 onward, with only one in 09-08 to 09-16. This could be slow early web uptake, or panel or posting lag. Check it against SensorTower downloads and NIQ.
- Prefilter coverage: I ran a Snowflake check on Omega MID_V1_0 and TRANS for September and October 2026, covering Meta-like descriptors that the prefilter did not match. It found no Muse or META.COM variant. What it did find was `METAPAY*` (P2P and marketplace, often negative), `FACEBK *` (ads), `META DES:PAYROLL` and `META PAY` ($8 median, about 1.1k rows). It also found two **masked** descriptors with no merchant URL: `METAPAY ____ ____ - NA` (about 3.1k rows, $4.99 median) and `METAPAY - NA` (about 2.0k rows, $13 median). These could hide some web Muse charges. They are not in the extract, and their Power-band share is unchecked.
- Canada (CAD 28) is out of scope: Omega is USD only.
- Muse Code plans ($5/$15/$50/$200, from 2026-10-12) may bill on the same descriptor. $15 and $50 sit outside the bands, but the $50-plus-tax cluster starts 2026-09-08, before Code launched, so it is not Code.

## Open questions

1. What is the ~$50 charge on `METAPAY META.COM`? Candidates are a token top-up or a mid-tier web plan. It has 8 uids from launch day, and one uid renewed at $50.00 after 32 days (09-12 to 10-14), which suggests a recurring plan. Should it be added as a tier if confirmed?
2. Google Play rows appear only from 2026-10-07, a month after launch. The October Play count is therefore a step-up from the start of billing, not genuine growth. Should it be dated from its first appearance in subs.py?
3. Should the small amounts ($2.99, $5.00) be treated as Muse add-ons or ignored?
4. Should the masked `METAPAY - NA` and `METAPAY ____ ____ - NA` descriptors be pulled? They are not prefiltered, and I need them to check whether any rows sit in the $15.99 to $17.60 band.
