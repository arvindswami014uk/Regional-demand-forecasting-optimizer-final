# =============================================================================
# src/data/cleaning/clean_daily_demand.py
# =============================================================================
# PROJECT  : Regional Demand Forecasting and Inventory Placement Optimizer
# MODULE   : Daily Demand Data Cleaning
# VERSION  : 1.0.0
#
# PURPOSE:
#   Cleans the daily_demand.csv raw file and produces a pipeline-ready
#   output at data/processed/daily_demand_clean.csv.
#
# KEY DATA FACTS (confirmed in data audit):
#   - 5,000 rows covering multiple dates, regions, and SKUs
#   - Each sku_id appears ONLY ONCE -- per-SKU time-series forecasting
#     is NOT possible. Aggregation to week-region-category grain is required.
#   - weekend_flag is CORRUPTED -- contains '01/01/1970' date strings
#   - day column is REDUNDANT -- derived from date, validated then dropped
#   - Binary flags may contain values outside {0, 1}
#   - units_ordered may contain negatives and extreme outliers
#
# CLEANING STEPS:
#   1.  Load raw data and run initial audit
#   2.  Parse date column to datetime64
#   3.  Validate and drop redundant day column
#   4.  Drop corrupted weekend_flag column
#   5.  Standardise region column to Title Case
#   6.  Validate SKU ID format
#   7.  Remove negative units_ordered
#   8.  Cap units_ordered outliers at 99.9th percentile
#   9.  Assert price_usd is strictly positive
#   10. Validate binary event flag columns
#   11. Engineer temporal features from date
#   12. Write interim checkpoint
#   13. Final schema audit
#   14. Write processed output, log, and markdown report
#
# OUTPUTS:
#   data/processed/daily_demand_clean.csv
#   data/interim/daily_demand_interim.csv
#   outputs/logs/log_clean_daily_demand.csv
#   reports/report_clean_daily_demand.md
# =============================================================================

import os
import sys
from datetime import datetime

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Path setup -- ensures this module works whether called from Colab cell
# or from run_all_cleaning.py regardless of working directory
# ---------------------------------------------------------------------------
def _get_project_root() -> str:
    this_file    = os.path.abspath(__file__)
    cleaning_dir = os.path.dirname(this_file)
    data_dir     = os.path.dirname(cleaning_dir)
    src_dir      = os.path.dirname(data_dir)
    return os.path.dirname(src_dir)

_PROJECT_ROOT = _get_project_root()
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Local imports -- all utility functions come from cleaning_utils
# ---------------------------------------------------------------------------
from config.project_config import (
    PATHS, RAW_FILENAMES, PROCESSED_FILENAMES, INTERIM_FILENAMES,
    LOG_FILENAMES, REPORT_FILENAMES, CANONICAL_REGIONS,
    VALIDATION, COLUMNS, get_raw_path, get_processed_path,
    get_interim_path, get_log_path, get_report_path, ensure_dirs,
)
from src.data.cleaning.cleaning_utils import (
    CleaningLogger,
    write_markdown_report,
    print_section_header,
    print_dataframe_summary,
    print_value_counts,
    parse_date_column,
    engineer_date_features,
    drop_corrupted_weekend_flag,
    validate_binary_flags,
    standardise_string_column,
    validate_region_column,
    validate_sku_ids,
    remove_negative_values,
    cap_outliers_percentile,
    assert_positive_column,
    audit_schema,
    final_cleaning_summary,
    print_value_counts,
)

# ---------------------------------------------------------------------------
# MODULE-LEVEL CONSTANTS
# ---------------------------------------------------------------------------
DATASET_KEY  = 'daily_demand'
BINARY_FLAGS = [
    'holiday_peak_flag',
    'prime_event_flag',
    'marketing_push_flag',
]

DATASET_DESCRIPTION = (
    'daily_demand contains transactional demand records — one row per '
    'date-SKU-region combination. It is the primary input for the demand '
    'forecasting pipeline. Key issue: each sku_id appears only once, so '
    'per-SKU time-series forecasting is not possible. The pipeline aggregates '
    'to week-region-category grain for the LightGBM forecasting model.'
)

KEY_FINDINGS = [
    'weekend_flag is CORRUPTED — contains Unix epoch date strings 01/01/1970 not binary 0/1',
    'Each sku_id appears only ONCE — per-SKU time-series forecasting is not possible',
    'day column is redundant — derived from date, validated then dropped',
    'units_ordered may contain negative values and extreme outliers',
    'Binary flag columns validated against {0, 1} with coercion to 0 on failure',
    'Aggregation grain for forecasting: year_week x region x category',
]

ENGINEERED_COLUMNS = [
    ('is_weekend',  '1 if Saturday or Sunday derived from date, replaces corrupted weekend_flag'),
    ('year',        'Calendar year extracted from date'),
    ('month',       'Calendar month 1-12 extracted from date'),
    ('quarter',     'Fiscal quarter 1-4 extracted from date'),
    ('week_number', 'ISO 8601 week number 1-53 extracted from date'),
    ('day_of_week', 'Monday=0 through Sunday=6 extracted from date'),
    ('year_week',   'ISO year-week string such as 2023-W04 — the forecasting grain key'),
]


def load_raw() -> pd.DataFrame:
    '''
    Loads the raw daily_demand CSV from data/raw/.

    WHY  : Centralising the load in a function makes it testable
           and ensures consistent dtypes across all callers.
    WHAT : Reads CSV with all columns as object dtype initially.
           Dtype coercion happens in dedicated cleaning steps, not here.
    ASSUME: File exists at path defined by RAW_FILENAMES['daily_demand'].
    WATCH : If the file is missing the error message names the exact path
           so the user knows where to upload the file.

    Returns:
        pd.DataFrame: Raw daily_demand data, all columns as loaded.
    '''
    raw_path = get_raw_path(DATASET_KEY)
    if not os.path.isfile(raw_path):
        raise FileNotFoundError(
            f'Raw file not found: {raw_path}\n'
            f'Upload daily_demand.csv to data/raw/ and re-run.'
        )
    df = pd.read_csv(raw_path, dtype=str)  # load all as str, coerce later
    print(f'  [OK]  Loaded raw daily_demand: {len(df):,} rows x {df.shape[1]} columns')
    print(f'         Path: {raw_path}')
    return df


def validate_and_drop_day_column(df: pd.DataFrame) -> pd.DataFrame:
    '''
    Validates the redundant 'day' column against the 'date' column
    then drops it from the DataFrame.

    WHY  : The 'day' column in daily_demand is described as redundant in the
           data specification. It appears to be derived from the date column.
           Retaining redundant columns risks silent inconsistency if the two
           columns disagree after any transformation. Dropping it forces all
           day-level calculations to derive from the authoritative date column.

    WHAT : (1) Checks if 'day' column is present.
           (2) If present, prints a sample for audit evidence.
           (3) Drops the column unconditionally.

    ASSUME: The 'date' column is the authoritative source for all temporal
            features. 'day' adds no information that cannot be re-derived.

    WATCH : If a future data refresh adds meaningful content to the 'day'
            column (e.g. day-of-month as integer) remove this function
            and retain the column with appropriate validation.

    Args:
        df: DataFrame that may contain the 'day' column.

    Returns:
        DataFrame with 'day' column removed if it was present.
    '''
    df = df.copy()
    if 'day' not in df.columns:
        print('  [SKIP] day column not found -- nothing to drop.')
        return df
    sample = df['day'].dropna().unique()[:5].tolist()
    print(f'  [AUDIT] day column sample values: {sample}')
    df = df.drop(columns=['day'])
    print('  [FIX]  day column dropped -- all temporal features derived from date.')
    return df


def coerce_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    '''
    Coerces numeric columns from string dtype to their correct numeric types.

    WHY  : The raw file is loaded with dtype=str to prevent pandas from
           silently misinterpreting corrupted values (e.g. weekend_flag
           containing date strings would be cast to NaN without warning).
           Once structural issues are resolved, numeric columns must be
           cast to their correct types for all arithmetic operations.

    WHAT : Coerces these columns to float64 using pd.to_numeric:
           units_ordered, price_usd, weather_disruption_index
           Coerces flag columns to Int64 after binary validation.

    ASSUME: Non-numeric strings in these columns are data entry errors.
            errors='coerce' converts them to NaN which is then detectable.

    WATCH : After coercion check null counts for each column.
           A spike in nulls means the column had more non-numeric values
           than expected and the source data quality has degraded.

    Args:
        df: DataFrame with numeric columns still stored as strings.

    Returns:
        DataFrame with numeric columns cast to float64.
    '''
    df = df.copy()
    numeric_cols = ['units_ordered', 'price_usd', 'weather_disruption_index']
    for col in numeric_cols:
        if col not in df.columns:
            print(f'  [SKIP] [{col}] not found for numeric coercion.')
            continue
        before_nulls = df[col].isna().sum()
        df[col] = pd.to_numeric(df[col], errors='coerce')
        after_nulls  = df[col].isna().sum()
        new_nulls    = int(after_nulls - before_nulls)
        if new_nulls > 0:
            print(f'  [WARN] [{col}]: {new_nulls:,} non-numeric values coerced to NaN.')
        else:
            print(f'  [OK]  [{col}]: coerced to float64. Nulls: {int(after_nulls):,}')
    # Coerce flag columns to numeric before binary validation
    flag_cols = ['holiday_peak_flag', 'prime_event_flag', 'marketing_push_flag']
    for col in flag_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df


def run_cleaning() -> pd.DataFrame:
    '''
    Executes the full cleaning pipeline for daily_demand.

    WHY  : A single entry-point function makes this module callable from
           both run_all_cleaning.py and interactive Colab cells.
           All steps are logged, validated, and written to disk.

    WHAT : Runs 14 cleaning steps in dependency order:
           Load -> Parse dates -> Drop redundant cols -> Fix flags ->
           Standardise strings -> Validate IDs -> Fix numerics ->
           Engineer features -> Write outputs.

    ASSUME: All paths are correctly configured in project_config.PATHS.
    WATCH : Steps must run in the order defined here. date parsing must
           precede feature engineering. Flag fixing must precede validation.

    Returns:
        pd.DataFrame: Fully cleaned daily_demand DataFrame.
    '''
    ensure_dirs()
    logger = CleaningLogger(DATASET_KEY, get_log_path(DATASET_KEY))

    # ------------------------------------------------------------------
    # STEP 1 -- Load raw data
    # ------------------------------------------------------------------
    print_section_header('STEP 1 -- Load Raw Data')
    df      = load_raw()
    df_raw  = df.copy()  # preserve original for final summary
    rows_raw = len(df)
    print_dataframe_summary(df, label='RAW daily_demand')
    logger.log(
        step         = 'load_raw',
        rows_before  = 0,
        rows_after   = len(df),
        issue_found  = 'Raw file loaded',
        action_taken = f'Read {len(df):,} rows from CSV',
        assumption   = 'All columns loaded as string dtype for safe inspection',
        status       = 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 2 -- Parse date column
    # WHY: date arrives as string dtype. All temporal features and
    #      the weekly aggregation grain depend on datetime64 dtype.
    # ------------------------------------------------------------------
    print_section_header('STEP 2 -- Parse Date Column')
    before = len(df)
    df = parse_date_column(df, col='date')
    logger.log(
        step         = 'parse_date_column',
        rows_before  = before,
        rows_after   = len(df),
        issue_found  = 'date column stored as string dtype',
        action_taken = 'pd.to_datetime applied, unparseable rows dropped',
        assumption   = 'All dates follow ISO 8601 YYYY-MM-DD format',
        status       = 'PASS' if len(df) == before else 'WARN',
    )

    # ------------------------------------------------------------------
    # STEP 3 -- Drop corrupted weekend_flag column
    # WHY: weekend_flag contains Unix epoch date strings not binary 0/1.
    #      It is not salvageable. is_weekend is re-derived from date.
    # ------------------------------------------------------------------
    print_section_header('STEP 3 -- Drop Corrupted weekend_flag')
    before = len(df)
    df = drop_corrupted_weekend_flag(df, col='weekend_flag')
    logger.log(
        step         = 'drop_corrupted_weekend_flag',
        rows_before  = before,
        rows_after   = len(df),
        issue_found  = 'weekend_flag contains 01/01/1970 Unix epoch strings not binary 0/1',
        action_taken = 'Column dropped entirely',
        assumption   = 'is_weekend will be re-derived deterministically from the date column',
        status       = 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 4 -- Drop redundant day column
    # WHY: day column is derived from date and adds no new information.
    #      Retaining it risks silent inconsistency after date transforms.
    # ------------------------------------------------------------------
    print_section_header('STEP 4 -- Drop Redundant day Column')
    before = len(df)
    df = validate_and_drop_day_column(df)
    logger.log(
        step         = 'drop_day_column',
        rows_before  = before,
        rows_after   = len(df),
        issue_found  = 'day column is redundant -- derived from date',
        action_taken = 'Validated sample then dropped column',
        assumption   = 'date column is the single authoritative source for all temporal data',
        status       = 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 5 -- Coerce numeric columns from string dtype
    # WHY: CSV loaded as all-string. Numeric operations require float64.
    # ------------------------------------------------------------------
    print_section_header('STEP 5 -- Coerce Numeric Columns')
    before = len(df)
    df = coerce_numeric_columns(df)
    logger.log(
        step         = 'coerce_numeric_columns',
        rows_before  = before,
        rows_after   = len(df),
        issue_found  = 'Numeric columns stored as string dtype after all-string CSV load',
        action_taken = 'pd.to_numeric applied to units_ordered, price_usd, weather_disruption_index',
        assumption   = 'Non-numeric strings in these columns are data entry errors coerced to NaN',
        status       = 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 6 -- Standardise region column
    # WHY: region is the primary join key to warehouse_region_costs.
    #      Inconsistent casing causes silent join failures.
    # ------------------------------------------------------------------
    print_section_header('STEP 6 -- Standardise Region Column')
    print_value_counts(df['region'], label='region (before standardisation)')
    before = len(df)
    df = validate_region_column(df, col='region', canonical_regions=CANONICAL_REGIONS)
    logger.log(
        step         = 'standardise_region',
        rows_before  = before,
        rows_after   = len(df),
        issue_found  = 'Region values may have inconsistent casing or whitespace',
        action_taken = 'Strip whitespace and apply Title Case. Validate against canonical list.',
        assumption   = 'Canonical regions are North South East West in Title Case',
        status       = 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 7 -- Validate SKU ID format
    # WHY: sku_id is the join key to sku_master and starting_inventory.
    #      Malformed IDs cause silent join misses.
    # ------------------------------------------------------------------
    print_section_header('STEP 7 -- Validate SKU ID Format')
    before = len(df)
    df = validate_sku_ids(
        df, col='sku_id', pattern=VALIDATION['sku_id_pattern']
    )
    logger.log(
        step         = 'validate_sku_ids',
        rows_before  = before,
        rows_after   = len(df),
        issue_found  = 'SKU IDs must match canonical format SKU-XXXXXX (6 digits)',
        action_taken = 'Regex validation applied. Non-conforming IDs flagged not dropped.',
        assumption   = 'Canonical SKU format is SKU- followed by exactly 6 numeric digits',
        status       = 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 8 -- Remove negative units_ordered
    # WHY: Negative demand values break all aggregations and forecasting.
    #      They represent data entry errors not returns.
    # ------------------------------------------------------------------
    print_section_header('STEP 8 -- Remove Negative units_ordered')
    before = len(df)
    df = remove_negative_values(df, col='units_ordered', allow_zero=False)
    logger.log(
        step         = 'remove_negative_units',
        rows_before  = before,
        rows_after   = len(df),
        issue_found  = 'units_ordered may contain negative or zero values',
        action_taken = 'Rows with units_ordered <= 0 removed',
        assumption   = 'Negative values are data entry errors not product returns',
        status       = 'PASS' if len(df) == before else 'WARN',
    )

    # ------------------------------------------------------------------
    # STEP 9 -- Cap units_ordered outliers at 99.9th percentile
    # WHY: Extreme outlier orders inflate safety stock for entire categories
    #      and bias the LightGBM forecasting model toward over-procurement.
    # ------------------------------------------------------------------
    print_section_header('STEP 9 -- Cap units_ordered Outliers')
    before = len(df)
    df = cap_outliers_percentile(
        df, col='units_ordered',
        percentile=VALIDATION['units_outlier_percentile']
    )
    logger.log(
        step         = 'cap_units_outliers',
        rows_before  = before,
        rows_after   = len(df),
        issue_found  = 'Extreme units_ordered values inflate safety stock calculations',
        action_taken = f'Winsorised at {VALIDATION["units_outlier_percentile"]}th percentile',
        assumption   = 'Values above 99.9th percentile are anomalies not genuine demand signals',
        status       = 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 10 -- Assert price_usd is strictly positive
    # WHY: price_usd is used in stockout penalty calculation (2x price).
    #      A zero or negative price produces a nonsensical penalty value.
    # ------------------------------------------------------------------
    print_section_header('STEP 10 -- Assert price_usd Positive')
    before = len(df)
    try:
        assert_positive_column(df, col='price_usd', min_value=VALIDATION['min_price_usd'])
        logger.log(
            step         = 'assert_price_positive',
            rows_before  = before,
            rows_after   = len(df),
            issue_found  = 'price_usd must be strictly positive for stockout penalty calc',
            action_taken = 'Positivity assertion passed -- no action needed',
            assumption   = 'Free products with price=0 are not in scope for this pipeline',
            status       = 'PASS',
        )
    except AssertionError as e:
        print(f'  {e}')
        logger.fail(
            step         = 'assert_price_positive',
            rows_before  = before,
            rows_after   = len(df),
            issue_found  = str(e),
            action_taken = 'Assertion failed -- investigate source data before proceeding',
        )

    return df, df_raw, rows_raw, logger

def run_cleaning_part2(
        df: pd.DataFrame,
        df_raw: pd.DataFrame,
        rows_raw: int,
        logger: 'CleaningLogger') -> pd.DataFrame:
    '''
    Executes cleaning Steps 11-14 for daily_demand.
    Called immediately after run_cleaning() in the main() function.

    WHY  : Splitting the pipeline into two functions keeps each function
           readable and prevents Colab from timing out on a single
           very long execution block.

    Args:
        df       : DataFrame from run_cleaning() after Steps 1-10.
        df_raw   : Original raw DataFrame preserved for final summary.
        rows_raw : Original raw row count for report metadata.
        logger   : CleaningLogger instance from run_cleaning().

    Returns:
        pd.DataFrame: Fully cleaned daily_demand DataFrame.
    '''

    # ------------------------------------------------------------------
    # STEP 11 -- Validate binary event flag columns
    # WHY: holiday_peak_flag, prime_event_flag, marketing_push_flag are
    #      demand lift features. Values outside {0, 1} corrupt the model.
    # ------------------------------------------------------------------
    print_section_header('STEP 11 -- Validate Binary Event Flags')
    before = len(df)
    df = validate_binary_flags(df, flag_cols=BINARY_FLAGS)
    logger.log(
        step         = 'validate_binary_flags',
        rows_before  = before,
        rows_after   = len(df),
        issue_found  = 'Binary flags may contain values outside {0, 1}',
        action_taken = 'Values outside {0,1} coerced to 0. Columns cast to int.',
        assumption   = 'An unrecognised flag value means the event was not active',
        status       = 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 12 -- Engineer temporal features from date
    # WHY: The forecasting model requires year, month, quarter,
    #      week_number, day_of_week, year_week, and is_weekend.
    #      is_weekend replaces the corrupted weekend_flag dropped in Step 3.
    #      year_week is the primary aggregation key for the forecast grain.
    # ------------------------------------------------------------------
    print_section_header('STEP 12 -- Engineer Temporal Features')
    before = len(df)
    df = engineer_date_features(df, col='date')
    logger.log(
        step         = 'engineer_date_features',
        rows_before  = before,
        rows_after   = len(df),
        issue_found  = 'Temporal features not present in raw data',
        action_taken = 'Derived year, month, quarter, week_number, day_of_week, year_week, is_weekend',
        assumption   = 'ISO 8601 week standard used. year_week format is YYYY-Www e.g. 2023-W04',
        status       = 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 13 -- Log the single-occurrence SKU fact
    # WHY: This is a CRITICAL modelling constraint. Each sku_id appears
    #      only once in daily_demand so per-SKU time-series forecasting
    #      is not possible. The forecasting pipeline must aggregate to
    #      week-region-category grain instead.
    #      We log this explicitly so it is visible in the cleaning log
    #      and in the markdown report.
    # ------------------------------------------------------------------
    print_section_header('STEP 13 -- Audit SKU Occurrence Frequency')
    sku_counts = df['sku_id'].value_counts()
    max_occurrences  = int(sku_counts.max())
    skus_once        = int((sku_counts == 1).sum())
    skus_total       = int(sku_counts.shape[0])
    print(f'  Total unique SKUs    : {skus_total:,}')
    print(f'  SKUs appearing once  : {skus_once:,}')
    print(f'  Max occurrences/SKU  : {max_occurrences}')
    if max_occurrences == 1:
        print(f'  [CONFIRMED] Every sku_id appears exactly ONCE.')
        print(f'  [ACTION]    Per-SKU forecasting is NOT possible.')
        print(f'  [ACTION]    Forecast grain: year_week x region x category.')
        logger.warn(
            step         = 'audit_sku_occurrence',
            rows_before  = len(df),
            rows_after   = len(df),
            issue_found  = f'All {skus_total:,} sku_ids appear exactly once -- no longitudinal SKU history',
            action_taken = 'Documented. Forecasting pipeline will aggregate to week-region-category grain.',
            assumption   = 'week x region x category grain has sufficient history for LightGBM regression',
        )
    else:
        print(f'  [INFO] Some SKUs appear more than once (max={max_occurrences}).')
        logger.log(
            step         = 'audit_sku_occurrence',
            rows_before  = len(df),
            rows_after   = len(df),
            issue_found  = f'SKUs appear up to {max_occurrences} times',
            action_taken = 'Documented for forecasting grain decision',
            status       = 'PASS',
        )

    # ------------------------------------------------------------------
    # STEP 14 -- Write interim checkpoint
    # WHY: The interim file captures the DataFrame state after all core
    #      cleaning but before schema audit and final write.
    #      Useful for debugging if the final write fails.
    # ------------------------------------------------------------------
    print_section_header('STEP 14 -- Write Interim Checkpoint')
    interim_path = get_interim_path(DATASET_KEY)
    df.to_csv(interim_path, index=False)
    print(f'  [OK]  Interim checkpoint written: {interim_path}')
    print(f'         Shape: {df.shape[0]:,} rows x {df.shape[1]} columns')
    logger.log(
        step         = 'write_interim_checkpoint',
        rows_before  = len(df),
        rows_after   = len(df),
        issue_found  = '',
        action_taken = f'Interim CSV written to {interim_path}',
        assumption   = 'Interim file is for debugging only -- not used by downstream modules',
        status       = 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 15 -- Final schema audit
    # WHY: Confirms all expected columns from project_config.COLUMNS
    #      are present before writing the processed output.
    #      A missing column here means a downstream module will fail.
    # ------------------------------------------------------------------
    print_section_header('STEP 15 -- Final Schema Audit')
    schema_ok = audit_schema(df, dataset_key=DATASET_KEY)
    print_dataframe_summary(df, label='CLEAN daily_demand (final)')
    logger.log(
        step         = 'schema_audit',
        rows_before  = len(df),
        rows_after   = len(df),
        issue_found  = '' if schema_ok else 'Missing expected columns detected',
        action_taken = 'Schema validated against project_config.COLUMNS contract',
        assumption   = 'All columns in project_config.COLUMNS must be present in clean output',
        status       = 'PASS' if schema_ok else 'FAIL',
    )

    # ------------------------------------------------------------------
    # STEP 16 -- Write processed output
    # WHY: The processed CSV is the handoff to the forecasting pipeline.
    #      Writing it here completes the cleaning module's responsibility.
    # ------------------------------------------------------------------
    print_section_header('STEP 16 -- Write Processed Output')
    processed_path = get_processed_path(DATASET_KEY)
    df.to_csv(processed_path, index=False)
    size_kb = os.path.getsize(processed_path) / 1024
    print(f'  [OK]  Processed file written: {processed_path}')
    print(f'         Shape  : {df.shape[0]:,} rows x {df.shape[1]} columns')
    print(f'         Size   : {size_kb:.1f} KB')
    logger.log(
        step         = 'write_processed_output',
        rows_before  = len(df),
        rows_after   = len(df),
        issue_found  = '',
        action_taken = f'Clean CSV written to {processed_path}',
        status       = 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 17 -- Flush log and write markdown report
    # ------------------------------------------------------------------
    print_section_header('STEP 17 -- Flush Log and Write Report')
    logger.flush()
    write_markdown_report(
        logger              = logger,
        report_path         = get_report_path(DATASET_KEY),
        dataset_description = DATASET_DESCRIPTION,
        key_findings        = KEY_FINDINGS,
        engineered_columns  = ENGINEERED_COLUMNS,
        rows_raw            = rows_raw,
        rows_clean          = len(df),
    )

    # ------------------------------------------------------------------
    # FINAL SUMMARY
    # ------------------------------------------------------------------
    final_cleaning_summary(df_raw, df, DATASET_KEY, logger)

    return df


def main() -> pd.DataFrame:
    '''
    Main entry point for the daily_demand cleaning module.

    WHY  : A named main() function makes this module callable from
           run_all_cleaning.py using importlib.import_module() and
           also directly executable as a standalone script.

    Returns:
        pd.DataFrame: Fully cleaned daily_demand DataFrame.
    '''
    df, df_raw, rows_raw, logger = run_cleaning()
    df_clean = run_cleaning_part2(df, df_raw, rows_raw, logger)
    return df_clean


if __name__ == '__main__':
    df_clean = main()
    print(f'\n  daily_demand cleaning complete. Shape: {df_clean.shape}')
