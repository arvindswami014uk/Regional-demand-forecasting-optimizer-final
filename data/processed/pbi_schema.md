# Power BI Dataset Schema

Regional Demand Forecasting and Inventory Placement Optimizer
Amazon-Inspired Capstone Project

Generated: 2026-04-22T15:37:50.207140+00:00

---

## Table Overview

| Table | File | Grain | Rows (approx) | Primary Keys |
|-------|------|-------|---------------|--------------|
| Demand Summary | pbi_demand_summary.csv | week x region x category | ~1,500+ | year_week, region, category |
| Forecast Summary | pbi_forecast_summary.csv | week x region x category | 288 | week_label, region, category |
| Inventory Summary | pbi_inventory_summary.csv | warehouse | 5 | warehouse_id |
| Cost Summary | pbi_cost_summary.csv | scenario | 4 | scenario |
| Carbon Summary | pbi_carbon_summary.csv | scenario x warehouse x region | varies | scenario, warehouse_id, region |

---

## 1. pbi_demand_summary.csv

**Grain:** One row per ISO week x region x category.

**Source files:** fact_demand_enriched.csv, modeling_dataset.csv

| Column | Type | Description | Source |
|--------|------|-------------|--------|
| year_week | STRING | ISO week label e.g. 2024-W12 | Derived from fact_demand_enriched.date |
| region | STRING | Demand region: East, North, South, West | fact_demand_enriched.region |
| category | STRING | Product category: BEAUTY, ELECTRONICS, HOME, KITCHEN, PET, TOYS | fact_demand_enriched.category |
| total_units | FLOAT | Total units ordered in that week-region-category | SUM(fact_demand_enriched.units_ordered) |
| holiday_peak_flag | INT | 1 = holiday peak week, 0 = normal | modeling_dataset.holiday_peak_flag |
| prime_event_flag | INT | 1 = Prime event week, 0 = normal | modeling_dataset.prime_event_flag |
| marketing_push_flag | INT | 1 = marketing campaign active, 0 = none | modeling_dataset.marketing_push_flag |
| demand_yoy_growth_pct | FLOAT | Year-over-year demand growth % (2025 vs 2024 same ISO week). NULL for 2024 rows. | Computed |

**Relationships:** Joins to pbi_forecast_summary on (region, category).

---

## 2. pbi_forecast_summary.csv

**Grain:** One row per forecast week x region x category (12 weeks forward: 2026-W04 to W15).

**Source files:** forecast_12wk_forward.csv

| Column | Type | Description | Source |
|--------|------|-------------|--------|
| week_label | STRING | Forecast week label e.g. 2026-W04 | forecast_12wk_forward.year_week or week_start |
| region | STRING | Demand region | forecast_12wk_forward.region |
| category | STRING | Product category | forecast_12wk_forward.category |
| predicted_units | FLOAT | LightGBM point forecast (units/week) | forecast_12wk_forward.predicted_units |
| predicted_units_lower | FLOAT | 80% prediction interval lower bound | forecast_12wk_forward.predicted_units_lower |
| predicted_units_upper | FLOAT | 80% prediction interval upper bound | forecast_12wk_forward.predicted_units_upper |
| ci_width | FLOAT | Width of 80% PI = upper - lower. Indicates forecast uncertainty. | Computed |
| forecast_type | STRING | Always 'forward_12wk' — identifies this as a forward forecast | Constant |

**PI Calibration:** 80.0% empirical coverage — well-calibrated (confirmed Stat Cell 3).

**Relationships:** Joins to pbi_demand_summary on (region, category).

---

## 3. pbi_inventory_summary.csv

**Grain:** One row per warehouse (5 rows total).

**Source files:** warehouse_utilization.csv, starting_inventory_clean.csv,
warehouse_allocation_recommendations.csv, warehouses_clean.csv

| Column | Type | Description | Source |
|--------|------|-------------|--------|
| warehouse_id | STRING | Warehouse identifier: WH-NORTH, WH-SOUTH, WH-EAST, WH-WEST, WH-CENTRAL | warehouse_utilization |
| home_region | STRING | Primary region served by this warehouse | warehouse_utilization |
| capacity_units | INT | Maximum storage capacity in units | warehouse_utilization |
| starting_inventory_units | INT | Actual inventory on hand at start of study | warehouse_utilization |
| starting_utilisation_pct | FLOAT | starting_inventory / capacity * 100. Range 998%-1604% (massively overstocked) | warehouse_utilization |
| optimised_allocation_units | FLOAT | Weekly units allocated by LP optimizer (Scenario B) | warehouse_allocation_recommendations |
| optimised_utilisation_pct | FLOAT | optimised_allocation / capacity * 100 | warehouse_allocation_recommendations |
| days_of_cover | FLOAT | starting_inventory_units / (5451.88/5) * 7. Extreme overstock indicator. | Computed |
| daily_holding_cost_usd | FLOAT | Fixed daily warehouse operating cost in USD | warehouses_clean |
| recommendation | STRING | Inventory action: e.g. Consolidate, Reduce, Maintain | warehouse_allocation_recommendations |

**Key finding:** Days of cover range 4,191-21,093 days — confirms severe overstock problem.
Total warehouse capacity: 643,000 units across 5 warehouses.

**Relationships:** Joins to pbi_carbon_summary on warehouse_id.

---

## 4. pbi_cost_summary.csv

**Grain:** One row per scenario (4 rows: Baseline + 3 LP scenarios).

**Source files:** cost_to_serve_comparison.csv, scenario_comparison.csv

| Column | Type | Description | Source |
|--------|------|-------------|--------|
| scenario | STRING | Scenario identifier: Baseline, A, B, C | cost_to_serve_comparison |
| scenario_label | STRING | Human-readable label | cost_to_serve_comparison |
| w_cost | FLOAT | LP cost weight (0.0-1.0). NULL for Baseline. | scenario_comparison |
| w_carbon | FLOAT | LP carbon weight (0.0-1.0). NULL for Baseline. | scenario_comparison |
| ship_cost_usd | FLOAT | Total shipping cost in USD | cost_to_serve_comparison |
| holding_cost_usd | FLOAT | Total holding cost in USD | cost_to_serve_comparison |
| total_cost_usd | FLOAT | ship + holding total in USD | cost_to_serve_comparison |
| vs_baseline_usd | FLOAT | Savings vs Baseline in USD (negative = saving) | cost_to_serve_comparison |
| vs_baseline_pct | FLOAT | Savings as % of Baseline | cost_to_serve_comparison |
| cost_per_unit_served | FLOAT | total_cost_usd / units allocated. Baseline uses 12-week total (65,422.55 units). | Computed |
| recommended | BOOL/INT | 1 = recommended scenario | scenario_comparison |

**Key finding:** All 3 LP scenarios identical at USD 8,629.13 — Pareto frontier collapses
to single point. Home-lane routing minimises both cost AND carbon simultaneously.
Total baseline cost: USD 34,410,837.51. Optimised saving: 99.97%.

**Relationships:** Join key = scenario. Links to pbi_carbon_summary on scenario.

---

## 5. pbi_carbon_summary.csv

**Grain:** One row per scenario x warehouse x region,
plus one total row per scenario (warehouse_id='ALL').

**Source files:** inventory_placement_optimized.csv, carbon_comparison.csv

| Column | Type | Description | Source |
|--------|------|-------------|--------|
| scenario | STRING | Scenario identifier: A, B, C | inventory_placement_optimized |
| warehouse_id | STRING | Warehouse identifier. 'ALL' = scenario total row. | inventory_placement_optimized |
| region | STRING | Demand region served. 'ALL' = scenario total row. | inventory_placement_optimized |
| carbon_kg | FLOAT | CO2-equivalent emissions in kg for this allocation | inventory_placement_optimized |
| units_allocated | FLOAT | Units shipped on this lane | inventory_placement_optimized |
| carbon_per_unit_served | FLOAT | carbon_kg / units_allocated | Computed |
| vs_baseline_pct | FLOAT | Carbon reduction vs unoptimised baseline (%) | carbon_comparison |
| lead_time_days | FLOAT | Lane lead time in days. NULL for ALL rows. | inventory_placement_optimized |

**Key finding:** Optimised carbon = 643.94 kg vs baseline 22,781.11 kg — 97.2% reduction.
Carbon computed using EEA formula: distance_km x weight_tonnes x 0.062.

**Relationships:** Joins to pbi_cost_summary on scenario.
Joins to pbi_inventory_summary on warehouse_id.

---

## Relationship Diagram

```
pbi_demand_summary  --(region, category)--  pbi_forecast_summary
       |
   (region)
       |
pbi_inventory_summary  --(warehouse_id)--  pbi_carbon_summary
                                                  |
                                             (scenario)
                                                  |
                                         pbi_cost_summary
```

---

## Pre-Computed Measures Reference

| Measure | Formula | Table | Notes |
|---------|---------|-------|-------|
| demand_yoy_growth_pct | (units_2025 - units_2024) / units_2024 * 100 | pbi_demand_summary | NULL for 2024 rows |
| days_of_cover | starting_inventory / (5451.88/5) * 7 | pbi_inventory_summary | weekly_demand_per_wh = 1,090.38 |
| cost_per_unit_served | total_cost_usd / total_units | pbi_cost_summary | Baseline: 65,422.55 units; optimised: 5,585.88 |
| carbon_per_unit_served | carbon_kg / units_allocated | pbi_carbon_summary | Row level |
| ci_width | predicted_units_upper - predicted_units_lower | pbi_forecast_summary | 80% PI width |

---

## Confirmed Model Performance

| Metric | LightGBM | Naive Baseline | Linear Regression |
|--------|----------|----------------|-------------------|
| MAE | 33.37 | 44.49 | 141.21 |
| RMSE | 50.13 | 62.20 | 182.43 |
| WAPE | 21.5% | 69.9% | 221.9% |
| R2 | 0.7554 | -1.91 | -24.03 |

LightGBM beats Naive by +25% MAE / +69.3% WAPE.

---

## Confirmed Statistical Test Results

| Test | Result |
|------|--------|
| Mann-Whitney (Holiday) | p<0.0001, +64.8% lift, SIGNIFICANT |
| Mann-Whitney (Marketing) | p<0.0001, +71.4% lift, SIGNIFICANT |
| Shapiro-Wilk Residuals | W=0.7247, NON-NORMAL, kurtosis=44.3 |
| PI Calibration | 80.0% coverage, WELL-CALIBRATED |
| VIF | 19 severe, 2 moderate, 10 OK |

---
End of pbi_schema.md
