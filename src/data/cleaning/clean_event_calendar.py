# =============================================================================
# src/data/cleaning/clean_event_calendar.py
# =============================================================================
# PROJECT  : Regional Demand Forecasting and Inventory Placement Optimizer
# MODULE   : Event Calendar Data Cleaning
# VERSION  : 1.0.0
#
# PURPOSE:
#   Cleans the event_calendar.csv raw file and produces a pipeline-ready
#   output at data/processed/event_calendar_clean.csv.
#   The clean event calendar is joined to the weekly aggregated demand
#   table to provide event-flag features for the forecasting model.
#
# KEY DATA FACTS (confirmed in data audit):
#   - Raw file contains DUPLICATE DATES -- multiple rows per date
#   - weekend_flag is CORRUPTED -- contains date strings not binary 0/1
#   - Binary flags: holiday_peak_flag, prime_event_flag, marketing_push_flag
#   - weather_disruption_index is a continuous float (0.0 to 1.0)
#   - After deduplication the table should have exactly one row per date
#
# DEDUPLICATION STRATEGY:
#   For binary flags    : take MAX per date (if ANY row has flag=1, date has flag=1)
#   For weather index   : take MEAN per date (average disruption across duplicate rows)
#   WHY MAX for flags   : A date is a holiday if at least one source row says so.
#                         Taking MIN would silently suppress real event signals.
#   WHY MEAN for weather: Weather disruption is a continuous measure -- averaging
#                         duplicate readings is more appropriate than max/min.
#
# CLEANING STEPS:
#   1.  Load raw data and run initial audit
#   2.  Parse date column to datetime64
#   3.  Drop corrupted weekend_flag column
#   4.  Coerce numeric columns from string dtype
#   5.  Validate binary flag columns before deduplication
#   6.  Deduplicate to one row per date (max flags, mean weather)
#   7.  Engineer temporal features from date
#   8.  Write interim checkpoint
#   9.  Final schema audit
#   10. Write processed output, log, and markdown report
#
# OUTPUTS:
#   data/processed/event_calendar_clean.csv
#   data/interim/event_calendar_interim.csv
#   outputs/logs/log_clean_event_calendar.csv
#   reports/report_clean_event_calendar.md
# =============================================================================

import os
import sys
import warnings
from datetime import datetime

import pandas as pd
import numpy as np

# Silence the dd/mm/yyyy format warning from corrupted weekend_flag strings
# WHY: pandas emits a UserWarning when it encounters dd/mm/yyyy-style strings
#      in columns being parsed. This is expected for the corrupted weekend_flag
#      column and does not affect the correctness of our date parsing.
warnings.filterwarnings('ignore', message='Parsing dates')

# ---------------------------------------------------------------------------
# Path setup
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
# Local imports
# ---------------------------------------------------------------------------
from config.project_config import (
    PATHS, RAW_FILENAMES, PROCESSED_FILENAMES, INTERIM_FILENAMES,
    LOG_FILENAMES, REPORT_FILENAMES, VALIDATION, COLUMNS,
    get_raw_path, get_processed_path, get_interim_path,
    get_log_path, get_report_path, ensure_dirs,
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
    audit_schema,
    final_cleaning_summary,
)

# ---------------------------------------------------------------------------
# MODULE-LEVEL CONSTANTS
# ---------------------------------------------------------------------------
DATASET_KEY  = 'event_calendar'

BINARY_FLAGS = [
    'holiday_peak_flag',
    'prime_event_flag',
    'marketing_push_flag',
]

# Aggregation rules for deduplication
# WHY: Each column needs a specific aggregation rule that reflects its
#      business meaning. Applying the wrong rule (e.g. mean to a flag)
#      produces fractional values like 0.5 which are not valid binary flags.
FLAG_AGG_RULE    = 'max'   # 1 if ANY source row has the flag set
WEATHER_AGG_RULE = 'mean'  # average disruption level across duplicate rows

DATASET_DESCRIPTION = (
    'event_calendar contains one row per date with demand-driver flags: '
    'holiday_peak_flag, prime_event_flag, marketing_push_flag, and '
    'weather_disruption_index. The raw file contains duplicate dates '
    'which must be collapsed to one row per date before joining to demand. '
    'After deduplication and cleaning, this table has exactly one row per '
    'calendar date and serves as the event feature lookup for the forecast model.'
)

KEY_FINDINGS = [
    'Raw file contains DUPLICATE DATES -- multiple rows per date must be collapsed',
    'Deduplication strategy: MAX for binary flags, MEAN for weather_disruption_index',
    'weekend_flag is CORRUPTED -- contains Unix epoch date strings not binary 0/1',
    'Binary flags validated against {0, 1} after deduplication',
    'weather_disruption_index validated as continuous float after mean aggregation',
]

ENGINEERED_COLUMNS = [
    ('is_weekend',  '1 if Saturday or Sunday derived from date, replaces corrupted weekend_flag'),
    ('year',        'Calendar year extracted from date'),
    ('month',       'Calendar month 1-12 extracted from date'),
    ('quarter',     'Fiscal quarter 1-4 extracted from date'),
    ('week_number', 'ISO 8601 week number 1-53 extracted from date'),
    ('day_of_week', 'Monday=0 through Sunday=6 extracted from date'),
    ('year_week',   'ISO year-week string such as 2023-W04'),
]


def load_raw() -> pd.DataFrame:
    '''
    Loads the raw event_calendar CSV from data/raw/.

    WHY  : Centralising the load ensures consistent all-string dtype
           loading across all callers. Dtype coercion happens in
           dedicated cleaning steps, not at load time.
    ASSUME: File exists at path defined by RAW_FILENAMES['event_calendar'].
    WATCH : If the file is missing the error names the exact expected path.

    Returns:
        pd.DataFrame: Raw event_calendar data, all columns as string dtype.
    '''
    raw_path = get_raw_path(DATASET_KEY)
    if not os.path.isfile(raw_path):
        raise FileNotFoundError(
            f'Raw file not found: {raw_path}\n'
            f'Upload event_calendar.csv to data/raw/ and re-run.'
        )
    df = pd.read_csv(raw_path, dtype=str)
    print(f'  [OK]  Loaded raw event_calendar: {len(df):,} rows x {df.shape[1]} columns')
    print(f'         Path: {raw_path}')
    return df


def coerce_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    '''
    Coerces numeric columns from string dtype to float64.

    WHY  : Raw file is loaded as all-string dtype for safe inspection.
           Deduplication aggregations (max, mean) require numeric dtype.
           Coercion must happen BEFORE deduplication so that groupby
           aggregations produce correct numeric results.

    WHAT : Coerces weather_disruption_index to float64.
           Coerces binary flag columns to float first (for groupby max),
           then they are re-cast to int after deduplication and validation.

    ASSUME: Non-numeric strings are data entry errors -> coerced to NaN.
    WATCH : After coercion check null counts. New NaN values mean there
            were non-numeric strings in that column in the source data.

    Args:
        df: DataFrame with numeric columns still stored as string dtype.

    Returns:
        DataFrame with weather_disruption_index as float64,
        flag columns as float64 (re-cast to int post-deduplication).
    '''
    df = df.copy()
    cols_to_coerce = ['weather_disruption_index'] + BINARY_FLAGS
    for col in cols_to_coerce:
        if col not in df.columns:
            print(f'  [SKIP] [{col}] not found for numeric coercion.')
            continue
        before_nulls = df[col].isna().sum()
        df[col]      = pd.to_numeric(df[col], errors='coerce')
        after_nulls  = df[col].isna().sum()
        new_nulls    = int(after_nulls - before_nulls)
        if new_nulls > 0:
            print(f'  [WARN] [{col}]: {new_nulls:,} non-numeric values coerced to NaN.')
            # Fill NaN flags with 0 (conservative -- flag not active)
            if col in BINARY_FLAGS:
                df[col] = df[col].fillna(0)
                print(f'         NaN values in [{col}] filled with 0 (conservative).')
        else:
            print(f'  [OK]  [{col}]: coerced to float64. Nulls: {int(after_nulls):,}')
    return df


def deduplicate_dates(df: pd.DataFrame) -> pd.DataFrame:
    '''
    Collapses duplicate date rows to one row per calendar date.

    WHY  : event_calendar.csv contains multiple rows per date -- a data
           generation artifact. If left uncollapsed, joining this table
           to daily_demand on date produces a row explosion: every demand
           record gets duplicated for each copy of the date in the calendar.
           This inflates aggregated demand values by the duplication factor
           and corrupts the entire forecasting pipeline.

    WHAT : Groups by date and applies column-specific aggregations:
           Binary flags      -> max()  (1 if ANY row has flag=1)
           weather_disruption -> mean() (average across duplicate rows)

    ASSUME:
        MAX for binary flags: A date is a holiday/event if at least one
        source row flags it as such. Taking MIN would suppress real signals.
        MEAN for weather: Duplicate readings of a continuous measure should
        be averaged. A single extreme reading is an outlier, not ground truth.

    WATCH:
        After deduplication the row count should equal the number of unique
        dates in the raw file. If it does not, the date column had NaT values
        that were coerced during parsing -- investigate the source.
        After deduplication binary flags may have float values from groupby.
        Re-cast to int after this function using validate_binary_flags().

    Args:
        df: DataFrame with parsed date column and numeric flag columns.

    Returns:
        DataFrame with exactly one row per unique date.
    '''
    df = df.copy()
    before       = len(df)
    unique_dates = df['date'].nunique()
    duplicate_n  = before - unique_dates

    if duplicate_n == 0:
        print(f'  [OK]  No duplicate dates found -- deduplication not needed.')
        print(f'         {before:,} rows, {unique_dates:,} unique dates.')
        return df

    print(f'  [WARN] {duplicate_n:,} duplicate date rows detected.')
    print(f'         Raw rows: {before:,}  |  Unique dates: {unique_dates:,}')

    # Build aggregation dict
    # WHY: Each column type needs its own aggregation rule.
    #      Applying a single rule to all columns would give wrong results.
    agg_dict = {}
    for col in BINARY_FLAGS:
        if col in df.columns:
            agg_dict[col] = FLAG_AGG_RULE    # max -- flag is 1 if any row has 1
    if 'weather_disruption_index' in df.columns:
        agg_dict['weather_disruption_index'] = WEATHER_AGG_RULE  # mean

    df_deduped = (
        df.groupby('date', as_index=False)
          .agg(agg_dict)
    )

    after = len(df_deduped)
    print(f'  [FIX]  Deduplicated: {before:,} rows -> {after:,} rows')
    print(f'         Strategy: MAX for flags {BINARY_FLAGS}')
    print(f'                   MEAN for weather_disruption_index')
    return df_deduped


def run_cleaning():
    '''
    Executes cleaning Steps 1-8 for event_calendar.

    WHY  : Single entry-point function callable from both
           run_all_cleaning.py and interactive Colab cells.

    WHAT : Load -> Parse dates -> Drop corrupted flag -> Coerce numerics ->
           Validate flags -> Deduplicate -> Engineer features -> Checkpoint.

    ASSUME: Deduplication must happen AFTER numeric coercion.
            Feature engineering must happen AFTER deduplication.
            Both of these ordering constraints are enforced by step sequence.

    Returns:
        Tuple of (df, df_raw, rows_raw, logger) for use by run_cleaning_part2().
    '''
    ensure_dirs()
    logger   = CleaningLogger(DATASET_KEY, get_log_path(DATASET_KEY))

    # ------------------------------------------------------------------
    # STEP 1 -- Load raw data
    # ------------------------------------------------------------------
    print_section_header('STEP 1 -- Load Raw Data')
    df      = load_raw()
    df_raw  = df.copy()
    rows_raw = len(df)
    print_dataframe_summary(df, label='RAW event_calendar')
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
    # WHY: date arrives as string dtype. datetime64 is required for
    #      groupby deduplication and temporal feature engineering.
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
    # STEP 3 -- Drop corrupted weekend_flag
    # WHY: Same corruption as daily_demand -- Unix epoch date strings.
    #      Must be dropped BEFORE deduplication to prevent the groupby
    #      aggregation from failing on non-numeric string values.
    # ------------------------------------------------------------------
    print_section_header('STEP 3 -- Drop Corrupted weekend_flag')
    before = len(df)
    df = drop_corrupted_weekend_flag(df, col='weekend_flag')
    logger.log(
        step         = 'drop_corrupted_weekend_flag',
        rows_before  = before,
        rows_after   = len(df),
        issue_found  = 'weekend_flag contains 01/01/1970 Unix epoch strings not binary 0/1',
        action_taken = 'Column dropped entirely before deduplication',
        assumption   = 'is_weekend will be re-derived deterministically from the date column',
        status       = 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 4 -- Coerce numeric columns
    # WHY: groupby aggregation (max, mean) requires numeric dtype.
    #      Must happen BEFORE deduplication in Step 6.
    # ------------------------------------------------------------------
    print_section_header('STEP 4 -- Coerce Numeric Columns')
    before = len(df)
    df = coerce_numeric_columns(df)
    logger.log(
        step         = 'coerce_numeric_columns',
        rows_before  = before,
        rows_after   = len(df),
        issue_found  = 'Numeric columns stored as string after all-string CSV load',
        action_taken = 'pd.to_numeric applied. Flag NaN values filled with 0.',
        assumption   = 'Non-numeric strings are data entry errors coerced to NaN then 0',
        status       = 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 5 -- Audit duplicate dates before deduplication
    # WHY: Documenting duplication count before and after deduplication
    #      provides a clear audit trail for the thesis data quality appendix.
    # ------------------------------------------------------------------
    print_section_header('STEP 5 -- Audit Duplicate Dates')
    total_rows   = len(df)
    unique_dates = df['date'].nunique()
    dup_rows     = total_rows - unique_dates
    print(f'  Total rows     : {total_rows:,}')
    print(f'  Unique dates   : {unique_dates:,}')
    print(f'  Duplicate rows : {dup_rows:,}')
    if dup_rows > 0:
        dup_dates = df[df.duplicated(subset=['date'], keep=False)]['date']
        sample    = dup_dates.dt.strftime('%Y-%m-%d').unique()[:5].tolist()
        print(f'  Sample duplicated dates: {sample}')
    logger.warn(
        step         = 'audit_duplicate_dates',
        rows_before  = total_rows,
        rows_after   = total_rows,
        issue_found  = f'{dup_rows:,} duplicate date rows found in raw event_calendar',
        action_taken = f'Documented. Deduplication will collapse to {unique_dates:,} unique dates.',
        assumption   = 'Duplicate rows are a data generation artifact not multiple events per day',
    )

    # ------------------------------------------------------------------
    # STEP 6 -- Deduplicate to one row per date
    # WHY: Multiple rows per date causes row explosion when joining to
    #      daily_demand, inflating demand aggregations by the dupe factor.
    # STRATEGY: MAX for binary flags, MEAN for weather_disruption_index.
    # ------------------------------------------------------------------
    print_section_header('STEP 6 -- Deduplicate to One Row Per Date')
    before = len(df)
    df = deduplicate_dates(df)
    logger.log(
        step         = 'deduplicate_dates',
        rows_before  = before,
        rows_after   = len(df),
        issue_found  = f'{before - len(df):,} duplicate date rows removed',
        action_taken = 'groupby(date).agg(max for flags, mean for weather)',
        assumption   = 'A date is an event day if ANY source row has the flag set (MAX)',
        status       = 'PASS' if len(df) < before else 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 7 -- Re-validate binary flags after deduplication
    # WHY: groupby max() on float columns produces float output.
    #      e.g. max of [0.0, 1.0] = 1.0 not 1 (int).
    #      Flags must be cast back to int and validated as {0, 1}.
    # ------------------------------------------------------------------
    print_section_header('STEP 7 -- Re-validate Binary Flags Post-Deduplication')
    before = len(df)
    df = validate_binary_flags(df, flag_cols=BINARY_FLAGS)
    logger.log(
        step         = 'validate_binary_flags',
        rows_before  = before,
        rows_after   = len(df),
        issue_found  = 'groupby max() produces float dtype -- flags must be re-cast to int',
        action_taken = 'validate_binary_flags() applied post-deduplication',
        assumption   = 'After max aggregation all flag values are exactly 0.0 or 1.0',
        status       = 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 8 -- Validate weather_disruption_index range
    # WHY: After mean aggregation the weather index should remain within
    #      a plausible range [0, 1]. Values outside this range indicate
    #      data quality issues in the source that aggregation cannot fix.
    # ------------------------------------------------------------------
    print_section_header('STEP 8 -- Validate weather_disruption_index Range')
    if 'weather_disruption_index' in df.columns:
        wdi_min = df['weather_disruption_index'].min()
        wdi_max = df['weather_disruption_index'].max()
        wdi_mean = df['weather_disruption_index'].mean()
        print(f'  weather_disruption_index stats after mean aggregation:')
        print(f'    min  : {wdi_min:.4f}')
        print(f'    max  : {wdi_max:.4f}')
        print(f'    mean : {wdi_mean:.4f}')
        out_of_range = int(((df['weather_disruption_index'] < 0) | (df['weather_disruption_index'] > 1)).sum())
        if out_of_range > 0:
            print(f'  [WARN] {out_of_range:,} values outside [0, 1] after mean aggregation.')
            logger.warn(
                step         = 'validate_weather_index',
                rows_before  = len(df),
                rows_after   = len(df),
                issue_found  = f'{out_of_range:,} weather_disruption_index values outside [0,1]',
                action_taken = 'Flagged for investigation -- values retained as-is',
                assumption   = 'weather_disruption_index should be normalised to [0,1] in the source system',
            )
        else:
            print(f'  [OK]  All weather_disruption_index values in [0, 1].')
            logger.log(
                step         = 'validate_weather_index',
                rows_before  = len(df),
                rows_after   = len(df),
                issue_found  = '',
                action_taken = 'Range validation passed [0, 1]',
                status       = 'PASS',
            )

    return df, df_raw, rows_raw, logger

def run_cleaning_part2(
        df: pd.DataFrame,
        df_raw: pd.DataFrame,
        rows_raw: int,
        logger) -> pd.DataFrame:
    '''
    Executes cleaning Steps 9-10 for event_calendar.
    Called immediately after run_cleaning() by main().

    Args:
        df       : DataFrame from run_cleaning() after Steps 1-8.
        df_raw   : Original raw DataFrame preserved for final summary.
        rows_raw : Original raw row count for report metadata.
        logger   : CleaningLogger instance from run_cleaning().

    Returns:
        pd.DataFrame: Fully cleaned event_calendar DataFrame.
    '''

    # ------------------------------------------------------------------
    # STEP 9 -- Engineer temporal features
    # WHY: Temporal features enable week-level join to demand data and
    #      allow the forecasting model to use the event calendar as a
    #      weekly feature lookup. is_weekend replaces the corrupted
    #      weekend_flag dropped in Step 3.
    # ------------------------------------------------------------------
    print_section_header('STEP 9 -- Engineer Temporal Features')
    before = len(df)
    df = engineer_date_features(df, col='date')
    logger.log(
        step         = 'engineer_date_features',
        rows_before  = before,
        rows_after   = len(df),
        issue_found  = 'Temporal features not present in raw data',
        action_taken = 'Derived year, month, quarter, week_number, day_of_week, year_week, is_weekend',
        assumption   = 'ISO 8601 week standard used. year_week format is YYYY-Www.',
        status       = 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 10 -- Write interim checkpoint
    # WHY: Captures state after all cleaning but before schema audit.
    #      Useful for debugging if downstream steps fail.
    # ------------------------------------------------------------------
    print_section_header('STEP 10 -- Write Interim Checkpoint')
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
        assumption   = 'Interim file is for debugging only',
        status       = 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 11 -- Final schema audit
    # ------------------------------------------------------------------
    print_section_header('STEP 11 -- Final Schema Audit')
    schema_ok = audit_schema(df, dataset_key=DATASET_KEY)
    print_dataframe_summary(df, label='CLEAN event_calendar (final)')
    logger.log(
        step         = 'schema_audit',
        rows_before  = len(df),
        rows_after   = len(df),
        issue_found  = '' if schema_ok else 'Missing expected columns detected',
        action_taken = 'Schema validated against project_config.COLUMNS contract',
        assumption   = 'All columns in project_config.COLUMNS must be present',
        status       = 'PASS' if schema_ok else 'FAIL',
    )

    # ------------------------------------------------------------------
    # STEP 12 -- Write processed output
    # ------------------------------------------------------------------
    print_section_header('STEP 12 -- Write Processed Output')
    processed_path = get_processed_path(DATASET_KEY)
    df.to_csv(processed_path, index=False)
    size_kb = os.path.getsize(processed_path) / 1024
    print(f'  [OK]  Processed file written: {processed_path}')
    print(f'         Shape : {df.shape[0]:,} rows x {df.shape[1]} columns')
    print(f'         Size  : {size_kb:.1f} KB')
    logger.log(
        step         = 'write_processed_output',
        rows_before  = len(df),
        rows_after   = len(df),
        issue_found  = '',
        action_taken = f'Clean CSV written to {processed_path}',
        status       = 'PASS',
    )

    # ------------------------------------------------------------------
    # STEP 13 -- Flush log and write markdown report
    # ------------------------------------------------------------------
    print_section_header('STEP 13 -- Flush Log and Write Report')
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
    Main entry point for the event_calendar cleaning module.

    WHY  : Named main() function makes this module callable from
           run_all_cleaning.py and also directly as a standalone script.

    Returns:
        pd.DataFrame: Fully cleaned event_calendar DataFrame.
    '''
    df, df_raw, rows_raw, logger = run_cleaning()
    df_clean = run_cleaning_part2(df, df_raw, rows_raw, logger)
    return df_clean


if __name__ == '__main__':
    df_clean = main()
    print(f'\n  event_calendar cleaning complete. Shape: {df_clean.shape}')
