# CarMax ABS — data gaps (as of 2026-10-06)

Companion to `carmax_nonprime_tier_analysis.ipynb`.

| # | Gap | Impact | Remedy |
|---|---|---|---|
| 1 | No loan-level tier or grade in EX-102 or our tables | Tier 1 vs 2/3 is only identifiable in aggregate | 10-K/10-Q allowance and grade tables; prospectus criteria; proxy model |
| 2 | Prospectus doesn't quantify the core vs non-core split (in the extracted text) | Can't pin the Tier 2/3 share per trust | Read the full 424B5 annexes; check rating-agency presale reports; ask CarMax IR |
| 3 | Feed stopped Feb 2026 (last filing loaded 2026-02-17) | Missing loan data Feb–Aug 2026 and the 2026 trusts (2026-1..4, 2026-A..C) | `BOTS` owner restarts the loader and adds the new trusts; or run a one-off EDGAR pull |
| 4 | Loader has no owner in the srs monorepo | Nobody is maintaining it | Identify the owner via Snowflake `table_owner` |
| 5 | `ORIGINATORNAME` is constant ("CBS") | Can't separate core from non-core origination | None in EX-102 |
| 6 | 3–8% of Select loans have no FICO (higher APR, ~18.5–19.4%) | Bias in FICO-based tests; likely skewed to non-core | Separate bucket; `no_fico` flag in the model |
| 7 | ~2.4–2.6% duplicate rows on (trust, asset, period) in the raw tables | Overstated balances if not removed | `QUALIFY ROW_NUMBER()` on (trust, asset, period) |
| 8 | 74k asset numbers appear in two trusts | Wrong joins on `assetnumber` alone | Always key on (trust_name, assetnumber) |

## Key reconciliation

Our first-month data vs the 424B5 cut-off figures:
- **Loan count and weighted-average FICO match exactly** for 2025-A and 2025-B. 2024-A has 32,818 loans vs 32,816 in the prospectus.
- **Balances are ~1.2% higher** using the beginning-of-month balance. The notebook compares the end-of-month balance instead.

## Tier 1 view: evidence

- **Prospectus pool criteria.** Each pool is (i) core-portfolio loans with FICO < 650, plus (ii) loans originated outside the core portfolio.
- **Loan-level data.** 84–92% of Select pool balance fits the FICO < 650 core rule.
- **10-K allowance release on the Sept 2025 sale (Select 2025-B, ~$930M).** $30.3M Tier 1 / $11.9M Tier 2/3, which implies ≈ 91% Tier 1 at a 13.7% Tier 2/3 allowance rate.
- **Caveat.** CAF plans to raise its Tier 2 share to ~30% from FY27, and the Q2 FY27 sale's held-for-sale transfers were all Tier 2/3. The 2026 Select trusts may be much less Tier 1, and we have none of them.
