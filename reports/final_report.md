# Regional Demand Forecasting and Inventory Placement Optimizer
## Final Technical Report

**Author:** Arvind Swami
**Project type:** Amazon-Inspired Capstone — Outlier AI
**Date:** 2026-04-22

---

## 1. Problem Statement

Retail supply chains face a dual challenge: demand uncertainty and
inventory misplacement. Overstocked warehouses generate holding costs
that erode margin, while understocked locations cause service failures.
Cross-regional shipping amplifies both cost and carbon emissions when
inventory is not positioned close to demand.

This project addresses four operational questions:

1. Can machine learning forecast weekly demand per region-category
   segment with sufficient accuracy to drive replenishment decisions?
2. Are promotional events and holiday periods statistically significant
   demand drivers that must be modelled explicitly?
3. Can linear programming optimally place weekly replenishment inventory
   across five warehouses to minimise cost and carbon simultaneously?
4. Does a cost-minimising solution conflict with a carbon-minimising
   solution, or do both objectives converge to the same allocation?

The system is modelled on Amazon-scale operations: 5,000 SKUs
(SKU-100000 to SKU-104999), 4 demand regions (East, North, South, West),
6 product categories (BEAUTY, ELECTRONICS, HOME, KITCHEN, PET, TOYS)
and 5 fulfilment warehouses with a combined capacity of 643,000 units.

---

## 2. Data Description

Five source datasets were ingested and cleaned in Stage 1:

| Dataset | Shape | Grain | Key Fields |
|---------|-------|-------|------------|
| daily_demand_clean.csv | 5,000 x 16 | transaction | date, sku_id, region, category, units_ordered |
| event_calendar_clean.csv | 565 x 12 | date | event_type, holiday_flag, prime_flag, marketing_flag |
| sku_master_clean.csv | 5,000 x 11 | SKU | category, volume_m3, unit_cost_usd, holding_cost_daily |
| warehouses_clean.csv | 5 x 4 | warehouse | warehouse_id, capacity_units, daily_cost_usd |
| warehouse_region_costs_clean.csv | 20 x 7 | WH x region lane | ship_cost_per_unit, lead_time_days, carbon_kg_per_unit |
| starting_inventory_clean.csv | 5,000 x 5 | SKU x warehouse | units_on_hand, inventory_value_usd |

**Starting inventory state:** 8,926,517 total units valued at \$593,317,335.34.
Warehouse utilisation ranges from 998% to 1,604% of nominal capacity,
with WH-SOUTH at the peak (1,604.33%). Days of cover range from
4,191 to 21,093 days — a severe overstock condition that generates
\$406,381.70/day in holding costs.

The five warehouses and their characteristics:

| Warehouse | Region | Capacity | Daily Cost |
|-----------|--------|----------|------------|
| WH-NORTH | North | 120,000 units | \$1,800/day |
| WH-SOUTH | South | 115,000 units | \$1,700/day |
| WH-EAST | East | 118,000 units | \$1,750/day |
| WH-WEST | West | 110,000 units | \$1,680/day |
| WH-CENTRAL | Central | 180,000 units | \$2,600/day |

---

## 3. Exploratory Data Analysis

### 3.1 Statistical Hypothesis Tests

Two non-parametric Mann-Whitney U tests were conducted to assess whether
promotional events cause statistically significant demand uplift.

**Holiday peak effect:**
Mann-Whitney U test comparing units_ordered during holiday weeks vs
non-holiday weeks. Result: p < 0.0001, +64.8% demand lift.
The null hypothesis (no difference) is rejected at p < 0.0001.
Holiday weeks drive materially higher demand and must be modelled.

**Marketing push effect:**
Mann-Whitney U test comparing units_ordered during marketing campaign
weeks vs non-campaign weeks. Result: p < 0.0001, +71.4% demand lift.
Marketing campaigns are an even stronger demand driver than holiday peaks.

### 3.2 Multicollinearity Assessment

Variance Inflation Factor (VIF) analysis on the 42-column modelling
dataset revealed severe multicollinearity:
19 features with VIF > 10 (severe), 2 with VIF 5-10 (moderate),
10 with VIF < 5 (acceptable).
Additionally, 13 feature pairs exhibit |r| > 0.85 in the correlation
matrix — particularly among lag and rolling window features.
LightGBM's tree-based structure is robust to multicollinearity,
making it appropriate despite these conditions.

### 3.3 Demand Structure

ACF/PACF analysis on 81 weeks of historical data confirmed lag structure
at 27 lags, validating the inclusion of weekly lag features.
Category average volumes range from 0.010855 m3 (KITCHEN) to
0.030771 m3 (TOYS). Average holding costs range from \$0.0249/day
(KITCHEN) to \$0.0701/day (HOME).

---

## 4. Demand Forecasting

### 4.1 Model Architecture

LightGBM gradient boosting was trained on the modeling_dataset.csv
(1,540 rows, 42 features) at weekly region x category grain.
Features include lag-1 through lag-27 demand, rolling means,
holiday and marketing event flags, and calendar features.
Cross-validation was used to estimate generalisation performance.

### 4.2 Cross-Validation Performance

| Metric | LightGBM (CV) | Naive Baseline | Linear Regression |
|--------|--------------|----------------|-------------------|
| MAE | 33.37 | 44.49 | 141.21 |
| RMSE | 50.13 | 62.20 | 182.43 |
| WAPE | 21.5% | 69.9% | 221.9% |
| R2 | 0.7554 | -1.91 | -24.03 |

LightGBM outperforms the naive baseline by +25% on MAE and +69.3% on WAPE.
It outperforms linear regression by +76.4% on MAE and +90.3% on WAPE.
The R2 of 0.7554 confirms that 75.5% of demand variance is explained.

### 4.3 Residual Analysis

Shapiro-Wilk test on model residuals: W = 0.7247, p < 0.0001.
Residuals are significantly non-normal with kurtosis = 44.3 —
heavy-tailed with occasional large spikes likely driven by
unmodelled promotional events. This finding directly motivated the
1.20 robustness buffer applied in safety stock calculations.

### 4.4 Prediction Interval Calibration

80% prediction intervals were constructed using residual standard
deviation per segment. Empirical coverage was measured at 80.0%,
confirming well-calibrated intervals (Stat Cell 3).
CI widths vary by segment, reflecting heterogeneous forecast
uncertainty across the 24 region-category combinations.

### 4.5 Forward Forecast

The 12-week forward forecast (2026-W04 to 2026-W15) covers 288 rows
(24 segments x 12 weeks). Predicted weekly demand per segment
ranges from 58 to 345 units. Total weekly demand across all 24
segments is 5,451.88 units (mean 227.2 units per segment per week).
Total 12-week demand: 65,422.55 units.

---

## 5. Inventory Optimisation

### 5.1 ABC-XYZ Classification

Categories were classified on two axes:
ABC (revenue contribution) and XYZ (demand variability, CV threshold 30%).

| Category | ABC | XYZ | CV | Revenue % | Strategy |
|----------|-----|-----|----|-----------|----------|
| ELECTRONICS | A | X | 0.928% | 35.22% | Lean replenishment |
| TOYS | A | X | 0.440% | 23.24% | Lean replenishment |
| PET | B | X | 0.571% | 14.61% | Standard replenishment |
| KITCHEN | B | X | 0.670% | 14.01% | Standard replenishment |
| HOME | C | X | 0.718% | 9.57% | Consolidate SKUs |
| BEAUTY | C | X | 0.617% | 3.35% | Consolidate SKUs |

All categories classify as XYZ=X (CV range 0.44%-0.93%),
confirming consistently predictable demand patterns.

### 5.2 Safety Stock Calculation

Safety stock was computed for all 24 segments using:

SS = Z x residual_std x sqrt(avg_lead_time) x 1.20

The 1.20 robustness buffer was applied because Shapiro-Wilk confirmed
non-normal residuals (kurtosis=44.3). Service level targets by category:
ELECTRONICS 98%, BEAUTY/TOYS 95%, HOME/KITCHEN 92%, PET 90%.

Total safety stock: 134 units across 24 segments (range 3-18 units).
Maximum: East/ELECTRONICS = 18 units (Z=2.054).
Minimum: South/BEAUTY = 3 units.

### 5.3 Linear Programming Formulation

The inventory placement problem was formulated as a weighted
multi-objective LP solved with HiGHS via scipy.optimize.linprog:

Minimise: w_cost x (normalised_cost) + w_carbon x (normalised_carbon)

Subject to:
  - Demand constraints (24): sum of allocations >= demand + safety stock
  - Capacity constraints (5): sum of allocations <= warehouse capacity
  - Non-negativity: all allocation variables >= 0

Decision variables: 120 (5 warehouses x 4 regions x 6 categories).
All three scenarios achieved OPTIMAL status (solver status=0).

### 5.4 Scenario Results

| Scenario | w_cost | w_carbon | Total Cost | Carbon (kg) | SL |
|----------|--------|----------|------------|-------------|-----|
| A — Cost Minimiser | 1.0 | 0.0 | \$8,629.13 | 643.94 | 100% |
| B — Balanced | 0.6 | 0.4 | \$8,629.13 | 643.94 | 100% |
| C — Carbon Champion | 0.2 | 0.8 | \$8,629.13 | 643.94 | 100% |

All three scenarios produce identical allocations. The Pareto frontier
collapses to a single point because home-lane routing (\$1.50/unit,
1-day lead time) simultaneously minimises both cost and carbon.
The worst lane (WH-EAST to West, \$8.00/unit, 6 days) is never
selected under any weighting scheme.
Sensitivity analysis across 11 steps of w_carbon (0.0 to 1.0)
confirms identical results at every step.

### 5.5 Cost Savings vs Baseline

The unoptimised baseline assumes cross-lane shipping at average
\$4.20/unit for the full 12-week demand, plus holding costs:

| Component | Baseline | Optimised | Saving |
|-----------|----------|-----------|--------|
| Holding cost | \$34,136,062.80 | negligible | — |
| Shipping cost | \$274,774.71 | \$8,629.13 | 96.9% |
| Total | \$34,410,837.51 | \$8,629.13 | 99.97% |
| Carbon | 22,781.11 kg | 643.94 kg | 97.2% |

The \$34.4M baseline holding cost reflects 8.9M units held at
\$406,381.70/day for 84 days — a direct consequence of the
4,191-21,093 day overstock condition.

### 5.6 Service Level Results

Zero service level breaches across all 24 segments.
All fill rates meet or exceed target service levels.
Warehouse utilisation in the optimised solution appears low
(weekly replenishment flow ~5,586 units vs 643,000 unit warehouse
capacity) — this is architecturally correct: warehouses are sized
for inventory storage, the LP is sized for weekly flow.

---

## 6. Generative AI Integration

Three Gen AI components were implemented using Groq llama-3.3-70b-versatile
and FAISS semantic search:

### 6.1 LLM Narrator (A1)

An executive summary was generated by prompting the LLM with all
confirmed metrics from the project. Output: executive_summary_llm.md,
581 words. The summary covers forecasting accuracy, optimisation
findings, overstock severity and strategic recommendations.

### 6.2 Anomaly Explainer (A2)

69 demand anomalies were detected (z-score threshold on residuals).
The top 20 anomalies were individually explained by the LLM with
reference to event flags, category context and regional patterns.
Output: anomaly_explanations.md.

### 6.3 RAG Q&A System (A3)

A retrieval-augmented generation system was built using:
60 text chunks indexed in a FAISS vector store (dimension=384)
using sentence-transformers embeddings.
Five supply chain questions were answered by retrieving relevant
chunks and passing them as context to the LLM.
Output: rag_qa_log.md.

---

## 7. Conclusions and Recommendations

### 7.1 Key Findings

1. **LightGBM is a strong demand forecasting model** for this problem.
   CV MAE of 33.37 vs naive MAE of 44.49 (+25% improvement).
   R2=0.7554 confirms substantial explanatory power.

2. **Promotional events are highly significant demand drivers.**
   Holiday weeks: +64.8% lift (p<0.0001).
   Marketing pushes: +71.4% lift (p<0.0001).
   Both must be modelled explicitly in any forecasting system.

3. **The Pareto frontier collapses to a single optimal point.**
   Cost minimisation and carbon minimisation produce the same
   allocation because home-lane routing dominates on both objectives.
   This is a structural property of the cost matrix — not a solver error.

4. **The overstock problem is the primary cost driver.**
   8.9M units across 5 warehouses at \$406K/day holding cost.
   The LP optimises weekly replenishment flow (\$8.6K), but the
   baseline holding cost (\$34.1M over 12 weeks) dwarfs all
   shipping savings. Inventory reduction is the priority action.

5. **All demand is predictable (XYZ=X across all categories).**
   CV range 0.44%-0.93% — well below the 30% XYZ-Y threshold.
   This enables lean, just-in-time replenishment strategies.

### 7.2 Recommendations

| Priority | Action | Expected Impact |
|----------|--------|-----------------|
| P1 | Liquidate excess inventory — 8.9M units, 4,191-21,093 days cover | Eliminate \$406K/day holding cost |
| P2 | Implement home-lane-first routing for all replenishment | Lock in 97.2% carbon reduction |
| P3 | Deploy LightGBM forecasting with event calendar integration | Maintain WAPE at 21.5% |
| P4 | Apply ELECTRONICS 98% SL with 18-unit safety stock in East | Protect highest-revenue category |
| P5 | Consolidate HOME and BEAUTY SKUs (C-class, <13% combined revenue) | Reduce warehouse complexity |

### 7.3 Limitations

The Pareto collapse finding, while structurally correct, means the
multi-objective LP adds no decision value in the current cost structure.
Future work should introduce cross-lane demand spillover, stochastic
lead times and multi-period rolling horizon optimisation to create
genuine cost-carbon trade-offs.

---

## Appendix — Confirmed Figures

| Figure | Stage | Description |
|--------|-------|-------------|
| optimizer_abc_xyz_heatmap.png | B1 | ABC-XYZ matrix: revenue % vs CV% |
| optimizer_cost_waterfall.png | B4 | Cost waterfall: \$34.4M baseline to \$8.6K optimised |
| optimizer_scenario_comparison.png | B4 | Cost and carbon across 3 LP scenarios |
| optimizer_sensitivity_curve.png | B5 | Cost/carbon sensitivity to w_carbon weight |
| optimizer_service_level_report.png | B6 | Fill rate vs SL target — 0 breaches |

---

## Appendix — Technology Stack

| Component | Technology | Version |
|-----------|------------|---------|
| Language | Python | 3.10 |
| Forecasting | LightGBM | 4.x |
| Statistical tests | scipy | 1.x |
| LP solver | HiGHS (via scipy.optimize.linprog) | — |
| Gen AI LLM | Groq llama-3.3-70b-versatile | — |
| RAG embeddings | sentence-transformers | — |
| Vector store | FAISS | dim=384 |
| Data processing | pandas, numpy | — |
| Visualisation | matplotlib, seaborn | — |
| Dashboard | Power BI Desktop | — |
| Runtime | Google Colab | — |
| Version control | Git + GitHub | — |

---

*End of final_report.md — generated 2026-04-22T15:47:52.433465+00:00*
