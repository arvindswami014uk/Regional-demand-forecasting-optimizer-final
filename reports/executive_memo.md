# Executive Memo — Regional Demand Forecasting and Inventory Optimisation

| Field | Detail |
|-------|--------|
| **To**   | VP Network Planning |
| **From** | Arvind Swami, Network Analytics Lead |
| **Re**   | Regional Demand Forecasting and Inventory Optimisation — Findings and Recommendations |
| **Date** | April 2026 |
| **Classification** | Internal — Planning Lead Distribution |

---

## 1. The Overstock Problem

We currently hold **8,926,517 units** across our five warehouses at a combined
cost of **$406,381.70 per day**. Warehouse utilisation ranges from 998% to
1,604% of nominal capacity, with WH-SOUTH at the extreme (1,604%). The average
days of cover across the network is **11,461 days** against a 30-day operational
target — a factor of 382 times our stated policy.

| Warehouse  | Utilisation | Units Held | Days Cover | Daily Hold Cost |
|------------|-------------|------------|------------|-----------------|
| WH-CENTRAL | 997.3%      | 1,797,061  | 11,537     | $83,500.97    |
| WH-EAST    | 1,541.0%    | 1,818,359  | 11,674     | $83,382.51    |
| WH-NORTH   | 1,518.1%    | 1,821,735  | 11,695     | $81,153.64    |
| WH-SOUTH   | 1,604.3%    | 1,844,982  | 11,844     | $83,938.57    |
| WH-WEST    | 1,494.9%    | 1,644,380  | 10,557     | $74,406.01    |
| **TOTAL**  | —           | **8,926,517** | **11,461 avg** | **$406,381.70** |

This is not a forecasting problem or a routing problem. It is a **capital
management problem**. The inventory was placed before this analysis was
conducted and the LP optimiser does not resolve it — that requires a staged
liquidation programme (see Action P1 below).

At $406K per day, every week of delay in addressing the overstock costs
the business **$2,844,672**. Every month costs **$12.2M**.

---

## 2. What the Forecast Tells Us

Our LightGBM demand model achieves a cross-validated **WAPE of 21.5%**
(MAE 33.37 units per week per segment), outperforming all three benchmarks:

| Model         | MAE    | RMSE   | WAPE   | R2      |
|---------------|--------|--------|--------|---------|
| LightGBM (CV) | 33.37  | 50.13  | 21.5%  | 0.7554  |
| Prophet       | 41.20  | 58.90  | 33.8%  | 0.621   |
| Naive         | 44.49  | 62.20  | 69.9%  | -1.91   |
| Linear Reg    | 141.21 | 182.43 | 221.9% | -24.03  |

The 80% prediction intervals are well-calibrated at **80.0% empirical
coverage**. Two statistical tests confirm that holiday weeks drive
**+64.8% demand uplift** and marketing campaigns drive **+71.4% uplift**
(both p<0.0001, Mann-Whitney U). These signals are embedded in the model
via binary regressors and 27 confirmed lag features (ACF/PACF analysis).

Critically, all six product categories show a demand coefficient of
variation below 1% (range 0.44%–0.93%) — well below the 30% threshold
that would require unpredictability buffers. **Demand is predictable.
Lean, just-in-time replenishment is analytically viable** across all
categories. The current 11,461-day inventory cover is not justified by
demand volatility.

Non-normal residuals (Shapiro-Wilk W=0.7247, kurtosis=44.3) are
acknowledged. A **1.20x robustness buffer** is applied to all safety
stock calculations to compensate.

---

## 3. The Optimisation Finding

The LP optimiser routes weekly replenishment of **5,585.88 units** across
5 warehouses and 4 regions using the HiGHS solver (120 decision variables,
29 constraints, status=OPTIMAL for all scenarios).

Comparing weekly shipping cost only (Story 2 — LP routing):

| Routing       | Cost/Week   | Cost/Unit  | Annual Cost   |
|---------------|-------------|------------|---------------|
| Unoptimised   | $23,461   | $4.20    | $1,219,972  |
| Optimised     | $8,629    | $1.545   | $448,708    |
| **Saving**    | **$14,832** | **$2.655** | **$770,842** |
| **Saving %**  | **63.2%**   | —          | —             |

Carbon emissions fall from **22,781 kg to 644 kg per week** — a **97.2%
reduction** — at no additional cost.

A key finding is that all three LP scenarios — cost minimisation, balanced
(60/40 cost-carbon), and carbon minimisation — produce **identical
allocations**. Home-lane routing is simultaneously the cheapest and
lowest-carbon option. This is a network design strength: the right lanes
are already in place. No infrastructure change is required to capture
the saving.

Service level targets are met across **all 24 region-category segments**
with zero breaches. Total safety stock is 134 units (range 3–18 units
per segment), with ELECTRONICS at East holding the maximum 18 units
(Z=2.054, SL=98%).

---

## 4. Three Recommended Actions

### Action P1 — Immediate: Staged Inventory Liquidation

Begin a staged inventory liquidation programme targeting reduction
from 998%–1,604% utilisation to below 100%. This is the highest-value
action available to the business.

- Even a **50% reduction** eliminates **$203,190/day** in holding costs
- A **50% reduction** over 12 weeks saves **$17,068,031**
- Full resolution eliminates **$406,381/day** — **$148M/year**

Recommended liquidation channels: third-party liquidators, promotional
clearance events, inter-company transfers, and controlled write-downs
for obsolete SKUs (HOME and BEAUTY C-class candidates).

### Action P2 — This Quarter: Home-Lane-First Routing Policy

Implement a home-lane-first routing policy for all replenishment
decisions. Each warehouse serves its home region as the default lane.
Cross-lane routing is permitted only when home-lane capacity is
exhausted.

- Locks in **$14,832/week** shipping saving (**$770,842/year**)
- Achieves **97.2% carbon reduction** per week
- Requires **zero infrastructure change** — policy update only
- Can be implemented within current WMS configuration

### Action P3 — This Quarter: Deploy LightGBM to Production

Deploy the LightGBM forecast model as the weekly replenishment signal,
replacing manual planning. WAPE of 21.5% with well-calibrated 80%
prediction intervals supports automated safety stock calculation
and placement recommendations.

- Automates 24 segment-level forecasts (4 regions x 6 categories)
- Safety stock calculated from residual std per segment + 1.20x buffer
- Prediction intervals provide planners with 80% CI on weekly demand
- Removes forecast bias from manual adjustment

---

## 5. Limitations and Next Steps

This analysis uses a **single-period LP** with deterministic lead times
and a synthetic dataset. The results are analytically sound but require
validation against live ERP/WMS data before production deployment.

Immediate next steps:
1. Multi-period rolling horizon LP (replace single-period model)
2. Live ERP/WMS data integration (replace synthetic dataset)
3. Stochastic lead time modelling (replace deterministic assumption)
4. Supplier MOQ constraints (add minimum order quantities to LP)
5. Promotion spike scenario planning (holiday/Prime Day stress testing)

The Pareto collapse finding (all 3 LP scenarios identical) is a property
of the current cost structure — home-lane routing dominates both
objectives simultaneously. This will be re-evaluated if lane costs
change materially or if cross-lane capacity constraints are introduced.

---

*This memo was prepared using a fully automated analytics pipeline:
Python, LightGBM, Prophet, HiGHS LP solver, FAISS RAG, Groq LLM.
All numerical results are reproducible from the project repository.*

*Repository: https://github.com/arvindswami014uk/Regional-demand-forecasting-optimizer-final*

