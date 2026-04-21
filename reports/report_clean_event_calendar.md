# Data Cleaning Report: Event Calendar

| Field | Value |
|-------|-------|
| **Generated** | 2026-04-21 09:52 UTC |
| **Dataset** | `event_calendar` |
| **Rows in (raw)** | 5,000 |
| **Rows out (clean)** | 562 |
| **Net change** | -4,438 |
| **Steps run** | 12 |
| **PASS / WARN / FAIL** | 10 / 2 / 0 |

## Dataset Overview

event_calendar contains one row per date with demand-driver flags: holiday_peak_flag, prime_event_flag, marketing_push_flag, and weather_disruption_index. The raw file contains duplicate dates which must be collapsed to one row per date before joining to demand. After deduplication and cleaning, this table has exactly one row per calendar date and serves as the event feature lookup for the forecast model.

## Key Data Quality Findings

- Raw file contains DUPLICATE DATES -- multiple rows per date must be collapsed
- Deduplication strategy: MAX for binary flags, MEAN for weather_disruption_index
- weekend_flag is CORRUPTED -- contains Unix epoch date strings not binary 0/1
- Binary flags validated against {0, 1} after deduplication
- weather_disruption_index validated as continuous float after mean aggregation

## Cleaning Step Log

| Step | Before | After | Affected | Status | Issue | Action |
|------|-------:|------:|---------:|--------|-------|--------|
| load_raw | 0 | 5,000 | -5,000 | **PASS** | Raw file loaded | Read 5,000 rows from CSV |
| parse_date_column | 5,000 | 5,000 | 0 | **PASS** | date column stored as string dtype | pd.to_datetime applied, unparseable rows dropped |
| drop_corrupted_weekend_flag | 5,000 | 5,000 | 0 | **PASS** | weekend_flag contains 01/01/1970 Unix epoch strings not binary 0/1 | Column dropped entirely before deduplication |
| coerce_numeric_columns | 5,000 | 5,000 | 0 | **PASS** | Numeric columns stored as string after all-string CSV load | pd.to_numeric applied. Flag NaN values filled with 0. |
| audit_duplicate_dates | 5,000 | 5,000 | 0 | **WARN** | 4,438 duplicate date rows found in raw event_calendar | Documented. Deduplication will collapse to 562 unique dates. |
| deduplicate_dates | 5,000 | 562 | 4,438 | **PASS** | 4,438 duplicate date rows removed | groupby(date).agg(max for flags, mean for weather) |
| validate_binary_flags | 562 | 562 | 0 | **PASS** | groupby max() produces float dtype -- flags must be re-cast to int | validate_binary_flags() applied post-deduplication |
| validate_weather_index | 562 | 562 | 0 | **WARN** | 202 weather_disruption_index values outside [0,1] | Flagged for investigation -- values retained as-is |
| engineer_date_features | 562 | 562 | 0 | **PASS** | Temporal features not present in raw data | Derived year, month, quarter, week_number, day_of_week, year_week, is_weekend |
| write_interim_checkpoint | 562 | 562 | 0 | **PASS** |  | Interim CSV written to /content/Regional-demand-forecasting-optimizer-final/data/interim/event_calendar_interim.csv |
| schema_audit | 562 | 562 | 0 | **PASS** |  | Schema validated against project_config.COLUMNS contract |
| write_processed_output | 562 | 562 | 0 | **PASS** |  | Clean CSV written to /content/Regional-demand-forecasting-optimizer-final/data/processed/event_calendar_clean.csv |

## Engineered Columns

| Column | Formula / Description |
|--------|-----------------------|
| `is_weekend` | 1 if Saturday or Sunday derived from date, replaces corrupted weekend_flag |
| `year` | Calendar year extracted from date |
| `month` | Calendar month 1-12 extracted from date |
| `quarter` | Fiscal quarter 1-4 extracted from date |
| `week_number` | ISO 8601 week number 1-53 extracted from date |
| `day_of_week` | Monday=0 through Sunday=6 extracted from date |
| `year_week` | ISO year-week string such as 2023-W04 |

## Assumptions Made

- All columns loaded as string dtype for safe inspection
- All dates follow ISO 8601 YYYY-MM-DD format
- is_weekend will be re-derived deterministically from the date column
- Non-numeric strings are data entry errors coerced to NaN then 0
- Duplicate rows are a data generation artifact not multiple events per day
- A date is an event day if ANY source row has the flag set (MAX)
- After max aggregation all flag values are exactly 0.0 or 1.0
- weather_disruption_index should be normalised to [0,1] in the source system
- ISO 8601 week standard used. year_week format is YYYY-Www.
- Interim file is for debugging only
- All columns in project_config.COLUMNS must be present
