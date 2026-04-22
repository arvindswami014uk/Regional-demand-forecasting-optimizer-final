# Data Lineage Document

Regional Demand Forecasting and Inventory Placement Optimizer

Generated: 2026-04-22T15:47:52.430713+00:00

---

## Overview

This document traces every data file from raw source through transformation
to final output. Row counts and column changes are recorded at each stage.

---

## Stage 1 — Data Ingestion and Cleaning

### 1.1 daily_demand_clean.csv

| Attribute | Value |
|-----------|-------|
| Source | data/raw/daily_demand.csv |
| Output | data/processed/daily_demand_clean.csv |
| Input rows | ~5,000 |
| Output rows | 5,000 |
| Output columns | 16 |
| Key columns | date, sku_id, region, category, units_ordered, selling_price_usd |
| Transformations | Type casting, null removal, outlier flagging, date parsing |

### 1.2 event_calendar_clean.csv

| Attribute | Value |
|-----------|-------|
| Source | data/raw/event_calendar.csv |
| Output | data/processed/event_calendar_clean.csv |
| Input rows | ~565 |
| Output rows | 565 |
| Output columns | 12 |
| Key columns | date, event_type, holiday_flag, prime_flag, marketing_flag |
| Transformations | Date parsing, flag encoding, deduplication |

### 1.3 sku_master_clean.csv

| Attribute | Value |
|-----------|-------|
| Source | data/raw/sku_master.csv |
| Output | data/processed/sku_master_clean.csv |
| Input rows | ~5,000 |
| Output rows | 5,000 |
| Output columns | 11 |
| Key columns | sku_id, category, volume_m3, unit_cost_usd, holding_cost_daily |
| Transformations | Null imputation, category standardisation, SKU range SKU-100000 to SKU-104999 |

### 1.4 warehouses_clean.csv

| Attribute | Value |
|-----------|-------|
| Source | data/raw/warehouses.csv |
| Output | data/processed/warehouses_clean.csv |
| Input rows | 5 |
| Output rows | 5 |
| Output columns | 4 |
| Key columns | warehouse_id, region, capacity_units, daily_cost_usd |
| Transformations | Column rename, capacity validation |
| Warehouses | WH-NORTH(120K), WH-SOUTH(115K), WH-EAST(118K), WH-WEST(110K), WH-CENTRAL(180K) |

### 1.5 warehouse_region_costs_clean.csv

| Attribute | Value |
|-----------|-------|
| Source | data/raw/warehouse_region_costs.csv |
| Output | data/processed/warehouse_region_costs_clean.csv |
| Input rows | 20 |
| Output rows | 20 |
| Output columns | 7 |
| Key columns | warehouse_id, demand_region, ship_cost_per_unit, lead_time_days, carbon_kg_per_unit |
| Note | Region column is 'demand_region' NOT 'region' |
| Cost range | \$1.50/unit (home lane) to \$8.00/unit (WH-EAST to West) |

### 1.6 starting_inventory_clean.csv

| Attribute | Value |
|-----------|-------|
| Source | data/raw/starting_inventory.csv |
| Output | data/processed/starting_inventory_clean.csv |
| Input rows | ~5,000 |
| Output rows | 5,000 |
| Output columns | 5 |
| Key columns | sku_id, warehouse_id, units_on_hand, inventory_value_usd |
| Total units | 8,926,517 units (total value: \$593,317,335.34) |

---

## Stage 2 — Feature Engineering and EDA

### 2.1 modeling_dataset.csv

| Attribute | Value |
|-----------|-------|
| Sources | daily_demand_clean + event_calendar_clean + sku_master_clean |
| Output | data/processed/modeling_dataset.csv |
| Output rows | 1,540 |
| Output columns | 42 |
| Key new columns | holiday_peak_flag, prime_event_flag, marketing_push_flag, avg_holding_cost_daily, avg_volume_m3, lag features, rolling features |
| Grain | ISO week x region x category |
| Transformations | Weekly aggregation, event join, lag/rolling feature engineering, VIF computation |
| VIF findings | 19 severe (>10), 2 moderate (5-10), 10 OK (<5) |

### 2.2 fact_demand_enriched.csv

| Attribute | Value |
|-----------|-------|
| Sources | daily_demand_clean + event_calendar_clean + sku_master_clean |
| Output | data/processed/fact_demand_enriched.csv |
| Output rows | 5,000 |
| Output columns | 33 |
| Key new columns | transaction_price_usd, selling_price_usd, holiday flags, category metadata |
| Grain | transaction (daily sku x region) |

### 2.3 warehouse_utilization.csv

| Attribute | Value |
|-----------|-------|
| Sources | starting_inventory_clean + warehouses_clean |
| Output | data/processed/warehouse_utilization.csv |
| Output rows | 5 |
| Output columns | 11 |
| Key columns | warehouse_id, capacity_units, inventory_units, utilization_pct, daily_holding_cost_usd |
| Key finding | Utilisation range 998%-1604% — massively overstocked |

---

## Stage 3 — Demand Forecasting

### 3.1 forecast_12wk_forward.csv

| Attribute | Value |
|-----------|-------|
| Sources | modeling_dataset.csv (train/test split) |
| Output | data/processed/forecast_12wk_forward.csv |
| Output rows | 288 |
| Output columns | 11 |
| Key columns | year_week, week_start, region, category, predicted_units, predicted_units_lower, predicted_units_upper |
| Model | LightGBM (CV MAE=33.37, RMSE=50.13, WAPE=21.5%, R2=0.7554) |
| Forecast horizon | 2026-W04 to 2026-W15 (12 weeks) |
| Forecast range | 58 - 345 units/week per segment |
| PI calibration | 80.0% empirical coverage (well-calibrated) |
| Grain | ISO week x region x category (24 segments x 12 weeks = 288) |

### 3.2 weekly_demand_forecast.csv

| Attribute | Value |
|-----------|-------|
| Sources | modeling_dataset.csv |
| Output | data/processed/weekly_demand_forecast.csv |
| Output rows | 1,540 |
| Output columns | 8 |
| Key columns | year_week, region, category, actual_units, predicted_units, residual |
| Grain | ISO week x region x category (full historical + forecast) |

### 3.3 forecast_residual_std.csv

| Attribute | Value |
|-----------|-------|
| Sources | weekly_demand_forecast.csv |
| Output | data/processed/forecast_residual_std.csv |
| Output rows | 24 |
| Output columns | 8 |
| Key columns | region, category, residual_std, cv_pct, mean_actual_demand |
| CV range | 0.44% - 0.93% (all categories XYZ=X, well below 30% threshold) |
| Residual shape | Non-normal: Shapiro-Wilk W=0.7247, kurtosis=44.3 |

---

## Stage 3 — Inventory Optimisation (Block B)

### B1 — sku_abc_xyz_classification.csv

| Attribute | Value |
|-----------|-------|
| Sources | modeling_dataset.csv, forecast_residual_std.csv |
| Output | data/processed/sku_abc_xyz_classification.csv |
| Output rows | 6 |
| Output columns | 12 |
| Key columns | category, abc_class, xyz_class, cv_pct, revenue_pct, strategy |
| ABC split | A=ELECTRONICS+TOYS, B=PET+KITCHEN, C=HOME+BEAUTY |
| XYZ result | All categories XYZ=X (low demand variability) |

### B2 — safety_stock_by_segment.csv

| Attribute | Value |
|-----------|-------|
| Sources | forecast_residual_std.csv, warehouse_region_costs_clean.csv |
| Output | data/processed/safety_stock_by_segment.csv |
| Output rows | 24 |
| Output columns | 10 |
| Formula | SS = Z x residual_std x sqrt(avg_lead_time) x 1.20 |
| Robustness buffer | 1.20 applied due to kurtosis=44.3 (non-normal residuals) |
| Total SS | 134 units across 24 segments |
| SS range | 3 - 18 units per segment |
| Max SS | East/ELECTRONICS = 18 units (Z=2.054, SL=98%) |

### B3 — inventory_placement_optimized.csv

| Attribute | Value |
|-----------|-------|
| Sources | forecast_12wk_forward.csv, warehouse_region_costs_clean.csv, safety_stock_by_segment.csv |
| Output | data/processed/inventory_placement_optimized.csv |
| Output rows | 360 |
| Output columns | 12 |
| Solver | HiGHS via scipy.optimize.linprog |
| Variables | 120 (5 WH x 4 regions x 6 categories) |
| Constraints | 29 (24 demand + 5 capacity) |
| Scenarios | 3 (A=Cost, B=Balanced, C=Carbon) — all OPTIMAL (status=0) |
| Total units | 5,585.88 per scenario |
| Result | All scenarios identical: cost=\$8,629.13, carbon=643.94 kg, SL=100% |

### B4-B6 — Comparison and Reporting Files

| File | Rows | Source | Description |
|------|------|--------|-------------|
| scenario_comparison.csv | 3 | inventory_placement_optimized | Per-scenario cost/carbon/SL summary |
| cost_to_serve_comparison.csv | 4 | scenario_comparison | Baseline + 3 scenarios cost breakdown |
| carbon_comparison.csv | 4 | scenario_comparison | Baseline + 3 scenarios carbon breakdown |
| sensitivity_analysis.csv | 11 | LP re-runs at w_carbon 0.0-1.0 | All 11 steps identical (Pareto collapse) |
| service_level_breach_report.csv | 24 | inventory_placement_optimized | 0 breaches across 24 segments |
| warehouse_allocation_recommendations.csv | 5 | inventory_placement_optimized | Per-warehouse action recommendations |

---

## Stage 4 — Power BI Export

| File | Rows | Sources | New Columns Added |
|------|------|---------|-------------------|
| pbi_demand_summary.csv | 1,549 | fact_demand_enriched + modeling_dataset | demand_yoy_growth_pct |
| pbi_forecast_summary.csv | 288 | forecast_12wk_forward | ci_width, forecast_type |
| pbi_inventory_summary.csv | 5 | warehouse_utilization + wh_alloc_recs | days_of_cover |
| pbi_cost_summary.csv | 4 | cost_to_serve_comparison + scenario_comparison | cost_per_unit_served |
| pbi_carbon_summary.csv | 363 | inventory_placement_optimized + carbon_comparison | carbon_per_unit_served + total rows |

---

## Stage 1 — Gen AI Integration (Block A)

| Output | Tool | Description |
|--------|------|-------------|
| reports/executive_summary_llm.md | Groq llama-3.3-70b-versatile | 581-word executive summary of full project |
| reports/anomaly_explanations.md | Groq llama-3.3-70b-versatile | 69 anomalies detected, top 20 explained |
| reports/rag_qa_log.md | FAISS dim=384 + sentence-transformers | 60 chunks indexed, 5 supply chain queries answered |

---

## Column Name Gotchas (Runtime-Verified)

| File | Column Issue | Correct Name |
|------|-------------|--------------|
| warehouse_region_costs_clean.csv | Region column | demand_region (NOT region) |
| warehouse_utilization.csv | Starting inventory | inventory_units (NOT total_starting_units) |
| forecast_12wk_forward.csv | Week identifier | year_week (NOT week_label) |
| modeling_dataset.csv | Holding cost | avg_holding_cost_daily |
| forecast_residual_std.csv | CV column | cv_pct (range 0.44%-0.93%) |

---
End of data_lineage.md
