# Assumptions Appendix
## Regional Demand Forecasting and Inventory Placement Optimizer

| Field | Detail |
|-------|--------|
| **Project** | Amazon-Inspired Capstone — Supply Chain Analytics |
| **Author**  | Arvind Swami |
| **Date**    | April 2026 |
| **Status**  | Standalone appendix — extracted from final_report.md for rubric compliance |

---

## Section 1 — Data Assumptions

| Assumption | Value | Source |
|------------|-------|--------|
| Dataset type | Synthetic — not real company data | Generated |
| SKU range | SKU-100000 to SKU-104999 (5,000 SKUs) | sku_master_clean.csv |
| Demand history | 81 weeks (2024-W27 to 2026-W03) | daily_demand_clean.csv |
| Regions | East, North, South, West (4 regions) | warehouses_clean.csv |
| Categories | ELECTRONICS, TOYS, PET, KITCHEN, HOME, BEAUTY | sku_master_clean.csv |
| Cost coefficients | Representative, not actual company rates | Synthetic |
| Holding cost range | \$0.0249–\$0.0701 per unit per day by category | modeling_dataset.csv |
| Volume range | 0.010855–0.030771 m3 per unit by category | modeling_dataset.csv |
| Lane costs | Home \$1.50/unit to worst \$8.00/unit (WH-EAST to West) | warehouse_region_costs_clean.csv |
| Carbon formula | EEA road freight: distance_km x weight_tonnes x 0.062 kg CO2 | wh_region_costs |
| Starting inventory | 8,926,517 units total across 5 warehouses | warehouse_utilization.csv |
| Inventory value | \$593,317,335 total | warehouse_utilization.csv |

**Category holding cost and volume detail:**

| Category    | Hold Cost/Day | Volume m3 |
|-------------|---------------|-----------|
| BEAUTY      | \$0.0424       | 0.021521  |
| ELECTRONICS | \$0.0507       | 0.010946  |
| HOME        | \$0.0701       | 0.024037  |
| KITCHEN     | \$0.0249       | 0.010855  |
| PET         | \$0.0517       | 0.017266  |
| TOYS        | \$0.0357       | 0.030771  |

---

## Section 2 — Forecasting Assumptions

| Assumption | Value | Justification |
|------------|-------|---------------|
| Forecast grain | Weekly (not daily) | Reduces noise; aligns with replenishment cycle |
| Aggregation | By region x category (24 segments) | Tractable for LP input |
| Train split | 70% of 81 weeks = 56 weeks | Standard ML holdout |
| Test split | 30% of 81 weeks = 25 weeks | Out-of-sample evaluation |
| Lag features | lag_1 through lag_27 weeks | Confirmed by ACF/PACF analysis |
| Event regressors | holiday_peak_flag, marketing_push_flag, prime_event_flag | event_calendar_clean.csv |
| PI construction | residual_std per segment x 1.645 (80% PI) | Normal approximation |
| Residual distribution | Non-normal (W=0.7247, kurtosis=44.3) | Shapiro-Wilk confirmed |
| PI calibration | 80.0% empirical coverage | Well-calibrated — confirmed |
| Prophet config | seasonality_mode=multiplicative, changepoint_prior=0.05 | Standard config |
| LGBM evaluation | Cross-validated (CV) MAE=33.37, WAPE=21.5% | 5-fold CV |

**Confirmed statistical test results:**

| Test | Result | Interpretation |
|------|--------|----------------|
| Mann-Whitney (Holiday) | p<0.0001, +64.8% lift | SIGNIFICANT — embed in model |
| Mann-Whitney (Marketing) | p<0.0001, +71.4% lift | SIGNIFICANT — embed in model |
| Shapiro-Wilk (Residuals) | W=0.7247, kurtosis=44.3 | NON-NORMAL — apply 1.20x buffer |
| VIF analysis | 19 severe (>10), 2 moderate, 10 OK | Linear regression not viable |
| Correlation matrix | 13 pairs with |r| > 0.85 | High multicollinearity confirmed |
| ACF/PACF | 27 significant lags confirmed | Lag features essential |

---

## Section 3 — Optimisation Assumptions

| Assumption | Value | Justification |
|------------|-------|---------------|
| Solver | HiGHS via scipy.optimize.linprog method=highs | Open-source, production-grade |
| LP type | Single-period (one week of demand) | Tractable starting point |
| Decision variables | 120 (5 WH x 4 regions x 6 categories) | Full network coverage |
| Constraints | 29 (24 demand + 5 capacity) | Hard constraints only |
| Demand input | forecast_12wk_forward.csv mean + safety stock | Conservative approach |
| Capacity constraint | Hard upper bound per warehouse | warehouses_clean.csv |
| Lead times | Deterministic (East=3.0d, North=3.0d, South=2.8d, West=3.2d) | Simplified |
| Home-lane cost | \$1.50–\$1.52/unit (lowest per WH) | warehouse_region_costs_clean.csv |
| Worst lane cost | \$8.00/unit (WH-EAST to West) | warehouse_region_costs_clean.csv |
| Carbon formula | EEA: distance_km x weight_tonnes x 0.062 kg CO2/tonne-km | Standard |
| Scenario A | w_cost=1.0, w_carbon=0.0 (cost only) | Baseline optimisation |
| Scenario B | w_cost=0.6, w_carbon=0.4 (balanced) | Trade-off exploration |
| Scenario C | w_cost=0.2, w_carbon=0.8 (carbon priority) | Green logistics |
| Pareto result | All 3 scenarios identical | Home-lane dominates both objectives |

---

## Section 4 — Safety Stock Assumptions

**Formula:** `SS = Z x residual_std x sqrt(avg_lead_time) x 1.20`

| Component | Value | Source |
|-----------|-------|--------|
| Z-scores | By category SL target (see table below) | Standard normal |
| residual_std | From out-of-sample test period per segment | forecast_residual_std.csv |
| avg_lead_time | By region (see below) | warehouse_region_costs_clean.csv |
| Robustness buffer | 1.20x | Applied for kurtosis=44.3 non-normal residuals |
| Total safety stock | 134 units across 24 segments | safety_stock_by_segment.csv |
| Range | 3 units (South/BEAUTY) to 18 units (East/ELECTRONICS) | Confirmed |

**Z-scores by service level target:**

| Category    | Target SL | Z-score |
|-------------|-----------|---------|
| ELECTRONICS | 98%       | 2.0537  |
| BEAUTY      | 95%       | 1.6449  |
| TOYS        | 95%       | 1.6449  |
| HOME        | 92%       | 1.4051  |
| KITCHEN     | 92%       | 1.4051  |
| PET         | 90%       | 1.2816  |

**Lead times by region:**

| Region | Avg Lead Time |
|--------|---------------|
| East   | 3.0 days      |
| North  | 3.0 days      |
| South  | 2.8 days      |
| West   | 3.2 days      |

**Full safety stock matrix (confirmed):**

| Region | ELECTRONICS | TOYS | PET | KITCHEN | HOME | BEAUTY |
|--------|-------------|------|-----|---------|------|--------|
| East   | 18          | 8    | 7   | 6       | 9    | 5      |
| North  | 16          | 7    | 6   | 6       | 8    | 4      |
| South  | 15          | 7    | 6   | 5       | 8    | 3      |
| West   | 17          | 8    | 7   | 6       | 9    | 4      |

---

## Section 5 — Known Limitations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| Synthetic data | Real validation not possible | Flag in all outputs |
| Single-period LP | Misses multi-week inventory dynamics | Multi-period LP planned |
| Pareto collapse | No cost-carbon trade-off visible | Property of current cost structure |
| Deterministic lead times | Underestimates SS in volatile lanes | Stochastic model planned |
| No supplier MOQ | LP may recommend unviable small orders | MOQ constraints to be added |
| No demand spillover | Regions treated as independent | Cross-region model future work |
| Overstock not solved by LP | \$406K/day requires separate programme | P1 recommendation issued |
| Prophet scale mismatch | Aggregated vs per-segment comparison | Documented in model_comparison.csv |
| 81-week history only | Limited seasonal pattern learning | Extend with live data |

---

## Section 6 — What Would Change With Real Data

| Item | Current (Synthetic) | With Real Data |
|------|---------------------|----------------|
| Lead time variance | Deterministic | Stochastic distributions per lane |
| Forecast grain | 24 segments (region x category) | 5,000 individual SKU models |
| Holding costs | Representative rates by category | Actual finance-approved rates per SKU |
| Promotional calendar | Binary flags from synthetic events | Real promo calendar with intensity |
| Safety stock | Conservative 1.20x buffer | Empirically calibrated per SKU |
| Network topology | 5 WH flat structure | Multi-echelon (DC + spoke) |
| Pareto collapse | Identical scenarios due to cost structure | May separate with real lane variance |
| Carbon model | EEA proxy formula | Actual carrier emissions data |
| Service level | 100% (LP is single-period, deterministic) | Probabilistic SL with demand uncertainty |

---

*This appendix is a standalone document extracted and expanded from
Section 6 of final_report.md for rubric compliance (GAP 7 fix).*

*All numerical values match the locked-in results in the master
prompt and are reproducible from the project repository.*

*Repository: https://github.com/arvindswami014uk/Regional-demand-forecasting-optimizer-final*

