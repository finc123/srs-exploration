**Headline: Showcase is still roughly doubling year on year, but the active base has plateaued since July at about 61–64k listings.** The reason is that new Showcase additions have stopped growing while exits keep pace with the larger base. Exit behaviour itself has not changed.

1. **Level (6 Oct 2026):**
   - 63.2k active Showcase listings, **2.59% of for-sale + pending** listings, against 1.35% a year ago. The count is +94% YoY.
   - In the two months since the 2 Aug snapshot the base grew only about +2.6k (60.6k → 63.2k), after about +4k a month in March–June.
   - YoY growth is fading steadily: +128% in early June, +113% in early August, +94% now.
   - The share keeps creeping up (2.45% → 2.59%) because total inventory is seasonally flat to down.
2. **Flows: the base has reached a steady state.** At weekly cadence (25 Aug–6 Oct):
   - Inflows are **~5.0k/week** (3.4k new listings entering as Showcase + 1.7k existing listings switched on). That is the same as March–May 2026 (5.0k/week).
   - Weekly exits are **~7.6% of the base**, against 7.8% in spring and 7.2% a year ago.
   - With a base of about 62k, exits (~4.7k/week) now nearly match inflows, so net adds are ~+0.3k/week, against ~+1.5k/week in spring.
   - At these rates the implied steady state is about 66k.
   - Showcase being *removed* from live listings is negligible (~0.3k/week, about 0.5% of the base).
   - **So this is not churn. It is a flat gross-add rate in a seasonally slowing listing market.**
   - New listings enter as Showcase at a **flat ~2.4% rate** since spring (1.4% a year ago).
   - Much of the snapshot-to-snapshot lumpiness comes from how we collect the data (section 4 note).
2b. **Reconciliation to management (section 2b).** On a comparable basis, our data tracks management's series closely.
   - Comparable basis: new agent-listed homes that carry Showcase at any point.
   - Q2-26 is **4.4% vs management's ~5%**. Management reads 1.03–1.20x ours in every quarter since Q4-24, with no drift.
   - The 2.59% figure is a different measure: share of the active stock, including vacant lots.
   - **Monthly and quarterly view, and the Q3-26 estimate (section 2c).** Management's wording ("as of the end of Q3", "end of March", year-end chart points) implies a national, new for-sale, quarter-end measure. Two versions, each applying one Showcase cutoff consistently across quarters:
     - **A. Point-in-time** (Showcase by quarter-end): quarterly average 3.65% → **3.97%** (+8.7% Q/Q). Sequential estimate **5.4%** (80% band 4.9–5.9%; backtest MAPE 5.9%).
     - **B. Reporting-lag** (Showcase by quarter-end + 35 days; Q3 projected using older cohorts' growth of 1.04–1.08x): 4.15% → **4.29%** (+3.5%). Sequential estimate **5.2%** (80% band 4.5–5.8%; MAPE 6.7%). **B is the base case.**
     - Both point to **flat to slightly up** Q/Q. An earlier "slightly down" read compared fully matured Q2 months with immature Q3 months, which is inconsistent.
     - The backtest bias is about +3%, driven by Q1-25 and Q1-26 overshoots (our Q4→Q1 jump is sharper than management's). Q3 has no such pattern.
3. **Brokers:**
   - **Opendoor** is the clear new adopter: 3 → **314** Showcase listings since July, about 9% of its inventory.
   - **RE/MAX** (4.8% penetration), **Keller Williams** (+0.6k), **Real Broker** (+0.25k) and Samson are still growing.
   - **Howard Hanna** keeps sliding: 11.1% penetration a year ago, 9.3% now, −190 listings since July.
   - **Redfin's** spring test (335 in April) has nearly gone (13).
   - Coldwell Banker and BHHS are flat.
   - By state, FL (−185), GA, NJ, PA, NY and OH fell from July to October. AZ (+527), TX, NC, CA and WA grew.
   - **Share of each state's listings** (ex-lots), against 3.2% for the US:
     - **Highest:** NE 6.1%, NV 5.6%, CO 5.5%, WA 4.9%, SC 4.8%.
     - **Lowest:** WV 0.9%, MS 1.1%, ND/AR/LA/IL ~1.4%.
     - **Lagging large states:** TX 2.0%, NY 1.9%.
     - Every state rose YoY. WA (+3.3pp) and CO (+2.9pp) rose most; OH (+0.7pp) and NY (+0.65pp) least.
4. **Benchmark (weak, short history):**
   - Showcase YoY has correlation 0.30 with Other Residential revenue YoY and 0.57 with Residential YoY. That is n = 7 quarters, all with Showcase growth above +100%.
   - The level correlation (0.97) is just a shared trend.
   - A "last year × (1 + β·signal YoY)" nowcast gave 4.7% MAPE against 5.1% for consensus. It called beat/miss only 40% of the time (n = 5).
   - Revenue-per-listing scaling fails (+81% bias), because Showcase is a small part of Other Residential.
   - **Treat the signal as a directional read on adoption, not a revenue predictor.**
   - The Q3 signal (+109% YoY average listings) implies Other Residential around $101M against $88M consensus. But Q3 Residential is guided flat because of the shift into Mortgages, so this comparison is not reliable.
5. **Preview:** about 210–290 listings per snapshot, falling, and about 1.05k distinct listings since August. 22% also carry Showcase, and the median observed Preview window is one snapshot. This is consistent with management's "quite small".

**Caveats:**
- There is no July 2026 snapshot (v2→v3), and cadence changed from twice monthly to weekly. Flows are per-week rates, but exits over long gaps are understated.
- The 1 Nov 2025 snapshot is an outlier: total inventory jumped to 2.63M.
- On a comparable definition, we run about 10–15% below management: 4.4% vs ~5% in Q2-26. The likely causes are listings that start and go pending between snapshots, Zillow's exact "new listings" definition, and Showcase flags we miss.
  - Scale our number up by about 1.14x to approximate management's metric.
  - Treat the 2.59% active-stock share as a separate measure, not as an estimate of management's number.
- Brand mapping uses `broker_name` string matching, and about 20% of Showcase listings have no broker.
