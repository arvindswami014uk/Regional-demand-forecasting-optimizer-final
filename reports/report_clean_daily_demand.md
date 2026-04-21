# Data Cleaning Report: Daily Demand

| Field | Value |
|-------|-------|
| **Generated** | 2026-04-21 09:48 UTC |
| **Dataset** | `daily_demand` |
| **Rows in (raw)** | 5,000 |
| **Rows out (clean)** | 5,000 |
| **Net change** | 0 |
| **Steps run** | 16 |
| **PASS / WARN / FAIL** | 15 / 1 / 0 |

## Dataset Overview

daily_demand contains transactional demand records — one row per date-SKU-region combination. It is the primary input for the demand forecasting pipeline. Key issue: each sku_id appears only once, so per-SKU time-series forecasting is not possible. The pipeline aggregates to week-region-category grain for the LightGBM forecasting model.

## Key Data Quality Findings

- weekend_flag is CORRUPTED — contains Unix epoch date strings 01/01/1970 not binary 0/1
- Each sku_id appears only ONCE — per-SKU time-series forecasting is not possible
- day column is redundant — derived from date, validated then dropped
- units_ordered may contain negative values and extreme outliers
- Binary flag columns validated against {0, 1} with coercion to 0 on failure
- Aggregation grain for forecasting: year_week x region x category

## Cleaning Step Log

| Step | Before | After | Affected | Status | Issue | Action |
|------|-------:|------:|---------:|--------|-------|--------|
| load_raw | 0 | 5,000 | -5,000 | **PASS** | Raw file loaded | Read 5,000 rows from CSV |
| parse_date_column | 5,000 | 5,000 | 0 | **PASS** | date column stored as string dtype | pd.to_datetime applied, unparseable rows dropped |
| drop_corrupted_weekend_flag | 5,000 | 5,000 | 0 | **PASS** | weekend_flag contains 01/01/1970 Unix epoch strings not binary 0/1 | Column dropped entirely |
| drop_day_column | 5,000 | 5,000 | 0 | **PASS** | day column is redundant -- derived from date | Validated sample then dropped column |
| coerce_numeric_columns | 5,000 | 5,000 | 0 | **PASS** | Numeric columns stored as string dtype after all-string CSV load | pd.to_numeric applied to units_ordered, price_usd, weather_disruption_index |
| standardise_region | 5,000 | 5,000 | 0 | **PASS** | Region values may have inconsistent casing or whitespace | Strip whitespace and apply Title Case. Validate against canonical list. |
| validate_sku_ids | 5,000 | 5,000 | 0 | **PASS** | SKU IDs must match canonical format SKU-XXXXXX (6 digits) | Regex validation applied. Non-conforming IDs flagged not dropped. |
| remove_negative_units | 5,000 | 5,000 | 0 | **PASS** | units_ordered may contain negative or zero values | Rows with units_ordered <= 0 removed |
| cap_units_outliers | 5,000 | 5,000 | 0 | **PASS** | Extreme units_ordered values inflate safety stock calculations | Winsorised at 99.9th percentile |
| assert_price_positive | 5,000 | 5,000 | 0 | **PASS** | price_usd must be strictly positive for stockout penalty calc | Positivity assertion passed -- no action needed |
| validate_binary_flags | 5,000 | 5,000 | 0 | **PASS** | Binary flags may contain values outside {0, 1} | Values outside {0,1} coerced to 0. Columns cast to int. |
| engineer_date_features | 5,000 | 5,000 | 0 | **PASS** | Temporal features not present in raw data | Derived year, month, quarter, week_number, day_of_week, year_week, is_weekend |
| audit_sku_occurrence | 5,000 | 5,000 | 0 | **WARN** | All 5,000 sku_ids appear exactly once -- no longitudinal SKU history | Documented. Forecasting pipeline will aggregate to week-region-category grain. |
| write_interim_checkpoint | 5,000 | 5,000 | 0 | **PASS** |  | Interim CSV written to /content/Regional-demand-forecasting-optimizer-final/data/interim/daily_demand_interim.csv |
| schema_audit | 5,000 | 5,000 | 0 | **PASS** |  | Schema validated against project_config.COLUMNS contract |
| write_processed_output | 5,000 | 5,000 | 0 | **PASS** |  | Clean CSV written to /content/Regional-demand-forecasting-optimizer-final/data/processed/daily_demand_clean.csv |

## Engineered Columns

| Column | Formula / Description |
|--------|-----------------------|
| `is_weekend` | 1 if Saturday or Sunday derived from date, replaces corrupted weekend_flag |
| `year` | Calendar year extracted from date |
| `month` | Calendar month 1-12 extracted from date |
| `quarter` | Fiscal quarter 1-4 extracted from date |
| `week_number` | ISO 8601 week number 1-53 extracted from date |
| `day_of_week` | Monday=0 through Sunday=6 extracted from date |
| `year_week` | ISO year-week string such as 2023-W04 — the forecasting grain key |

## Assumptions Made

- All columns loaded as string dtype for safe inspection
- All dates follow ISO 8601 YYYY-MM-DD format
- is_weekend will be re-derived deterministically from the date column
- date column is the single authoritative source for all temporal data
- Non-numeric strings in these columns are data entry errors coerced to NaN
- Canonical regions are North South East West in Title Case
- Canonical SKU format is SKU- followed by exactly 6 numeric digits
- Negative values are data entry errors not product returns
- Values above 99.9th percentile are anomalies not genuine demand signals
- Free products with price=0 are not in scope for this pipeline
- An unrecognised flag value means the event was not active
- ISO 8601 week standard used. year_week format is YYYY-Www e.g. 2023-W04
- week x region x category grain has sufficient history for LightGBM regression
- Interim file is for debugging only -- not used by downstream modules
- All columns in project_config.COLUMNS must be present in clean output
