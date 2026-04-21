# =============================================================================
# src/data/cleaning/cleaning_utils.py
# =============================================================================
# PROJECT  : Regional Demand Forecasting and Inventory Placement Optimizer
# MODULE   : Shared Cleaning Utilities
# VERSION  : 1.0.0
#
# PURPOSE:
#   Single shared library of cleaning, validation, and feature engineering
#   functions used by all six dataset-specific cleaning modules.
#   Nothing in this file is dataset-specific.
#
# COMMENT STYLE CONVENTION:
#   WHY    -- the data quality problem or business reason driving this step
#   WHAT   -- the specific transformation being applied
#   ASSUME -- the business or modelling assumption being made
#   WATCH  -- known edge cases or things to re-check on data refresh
#
# SECTIONS:
#   1.  Environment and Path Setup
#   2.  Structured Logging (CleaningLogger class)
#   3.  Markdown Report Writer
#   4.  Console Output and Tabular Formatting
#   5.  Date Parsing and Temporal Feature Engineering
#   6.  Corrupted Flag Detection and Weekend Fix
#   7.  Binary Flag Validation
#   8.  String Standardisation and Region Validation
#   9.  SKU ID Validation
#   10. Numeric Validation and Outlier Capping
#   11. Financial Feature Engineering
#   12. Carbon Emission Feature Engineering
#   13. Warehouse ID Utilities
#   14. Cross-Dataset Referential Integrity Checks
#   15. DataFrame Schema Audit
# =============================================================================

import os
import sys
import re
import csv
import warnings
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any, Set

import numpy as np
import pandas as pd
from tabulate import tabulate

# WHY: Suppress SettingWithCopyWarning -- .copy() is used defensively throughout
warnings.filterwarnings('ignore', category=pd.errors.SettingWithCopyWarning)
warnings.filterwarnings('ignore', category=FutureWarning)


# =============================================================================
# SECTION 1 -- Environment and Path Setup
# =============================================================================
# WHY   : Cleaning modules are called from Colab cells AND from
#         run_all_cleaning.py. Working directory differs in each context.
#         Resolving PROJECT_ROOT programmatically makes imports path-agnostic.
# WATCH : If cleaning/ moves to a different depth update the dirname() chain.
# =============================================================================

def setup_project_root() -> str:
    '''
    Resolves project root by walking three levels up from this file.

    WHY  : cleaning_utils.py lives at src/data/cleaning/ which is exactly
           three dirname() calls above this file equals the project root.
           This is reliable regardless of the absolute path on any machine.

    Returns:
        str: Absolute path to the project root directory.
    '''
    this_file    = os.path.abspath(__file__)
    cleaning_dir = os.path.dirname(this_file)     # src/data/cleaning/
    data_dir     = os.path.dirname(cleaning_dir)  # src/data/
    src_dir      = os.path.dirname(data_dir)      # src/
    project_root = os.path.dirname(src_dir)       # project root
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root


def ensure_output_dirs(paths_dict: Dict[str, str]) -> None:
    '''
    Creates all pipeline output directories if they do not already exist.

    WHY  : GitHub does not commit empty folders. After a fresh clone
           data/processed/, outputs/logs/, and reports/ will not exist.
           Any file write without this guard raises FileNotFoundError.
    WHAT : Calls os.makedirs with exist_ok=True for every path in PATHS.
    ASSUME: The paths_dict comes from config.project_config.PATHS.
    WATCH : New directories added to PATHS are automatically covered here.

    Args:
        paths_dict: The PATHS dictionary from project_config.
    '''
    for name, path in paths_dict.items():
        os.makedirs(path, exist_ok=True)


# =============================================================================
# SECTION 2 -- Structured Logging (CleaningLogger)
# =============================================================================
# WHY   : A structured cleaning log serves two purposes:
#         (1) Audit trail -- every transformation is fully traceable.
#         (2) Thesis appendix -- log CSVs become data quality evidence.
# DESIGN: One CleaningLogger instance per dataset per pipeline run.
#         Instantiate at the top of each clean_<dataset>.py module.
# =============================================================================

class CleaningLogger:
    '''
    Structured per-dataset cleaning audit logger.

    Captures one row per cleaning step with full context:
      dataset       -- which dataset is being cleaned
      step          -- name of the cleaning step
      rows_before   -- row count entering this step
      rows_after    -- row count leaving this step
      rows_affected -- absolute row difference
      issue_found   -- description of the data quality problem
      action_taken  -- what transformation was applied
      assumption    -- business assumption justifying the fix
      status        -- PASS / WARN / FAIL
      timestamp     -- UTC timestamp of this step
    '''

    ENTRY_FIELDS = [
        'dataset', 'step', 'rows_before', 'rows_after',
        'rows_affected', 'issue_found', 'action_taken',
        'assumption', 'status', 'timestamp',
    ]

    def __init__(self, dataset_name: str, log_path: str) -> None:
        self.dataset_name = dataset_name
        self.log_path     = log_path
        self.entries: List[Dict[str, Any]] = []
        self.start_time   = datetime.utcnow()
        self._print_run_header()

    def _print_run_header(self) -> None:
        print()
        print(f'  {"-" * 61}')
        print(f'  CLEANING MODULE : {self.dataset_name.upper()}')
        print(f'  Started         : {self.start_time.strftime("%Y-%m-%d %H:%M:%S")} UTC')
        print(f'  {"-" * 61}')

    def log(self,
            step: str,
            rows_before: int,
            rows_after: int,
            issue_found:  str = '',
            action_taken: str = '',
            assumption:   str = '',
            status:       str = 'PASS') -> None:
        '''
        Records one cleaning step to the in-memory log.

        WHY  : Capturing rows_before and rows_after for every step creates
               a full data lineage chain. A reviewer can see exactly where
               rows were dropped, created, or modified.
        WATCH: Always call logger.log() AFTER the transformation so that
               rows_after reflects the true post-transformation count.
        '''
        affected = rows_before - rows_after
        entry = {
            'dataset':       self.dataset_name,
            'step':          step,
            'rows_before':   rows_before,
            'rows_after':    rows_after,
            'rows_affected': affected,
            'issue_found':   issue_found,
            'action_taken':  action_taken,
            'assumption':    assumption,
            'status':        status,
            'timestamp':     datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        }
        self.entries.append(entry)
        prefix = {'PASS': '[PASS]', 'WARN': '[WARN]', 'FAIL': '[FAIL]'}.get(status, '[INFO]')
        change = f'  ({abs(affected):,} rows affected)' if affected != 0 else ''
        print(f'  {prefix} {step:<42} {rows_before:>7} -> {rows_after:>7}{change}')

    def warn(self, step, rows_before, rows_after,
             issue_found='', action_taken='', assumption='') -> None:
        '''Convenience wrapper -- logs with status=WARN.'''
        self.log(step, rows_before, rows_after,
                 issue_found, action_taken, assumption, status='WARN')

    def fail(self, step, rows_before, rows_after,
             issue_found='', action_taken='', assumption='') -> None:
        '''Convenience wrapper -- logs with status=FAIL.'''
        self.log(step, rows_before, rows_after,
                 issue_found, action_taken, assumption, status='FAIL')

    def flush(self) -> None:
        '''
        Writes all in-memory log entries to CSV on disk.

        WHY  : Writing at end of run avoids repeated file open/close cycles
               and ensures the log is only written if the module completes.
        WATCH: If a module crashes mid-run the log will NOT be written.
               For production pipelines switch to per-step append mode.
        '''
        if not self.entries:
            print('  [WARN] No log entries to flush.')
            return
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.ENTRY_FIELDS)
            writer.writeheader()
            writer.writerows(self.entries)
        elapsed      = round((datetime.utcnow() - self.start_time).total_seconds(), 1)
        pass_count   = sum(1 for e in self.entries if e['status'] == 'PASS')
        warn_count   = sum(1 for e in self.entries if e['status'] == 'WARN')
        fail_count   = sum(1 for e in self.entries if e['status'] == 'FAIL')
        rows_touched = sum(abs(e['rows_affected']) for e in self.entries)
        print()
        print(f'  {"-" * 61}')
        print(f'  LOG FLUSHED : {self.log_path}')
        print(f'  Steps : {len(self.entries)}  |  PASS: {pass_count}  WARN: {warn_count}  FAIL: {fail_count}')
        print(f'  Rows touched (cumulative) : {rows_touched:,}')
        print(f'  Elapsed : {elapsed}s')
        print(f'  {"-" * 61}')

    def get_summary_dict(self) -> Dict[str, Any]:
        '''Returns a run-summary dict for the master pipeline log.'''
        return {
            'dataset':       self.dataset_name,
            'steps_run':     len(self.entries),
            'pass_count':    sum(1 for e in self.entries if e['status'] == 'PASS'),
            'warn_count':    sum(1 for e in self.entries if e['status'] == 'WARN'),
            'fail_count':    sum(1 for e in self.entries if e['status'] == 'FAIL'),
            'rows_affected': sum(abs(e['rows_affected']) for e in self.entries),
            'elapsed_s':     round((datetime.utcnow() - self.start_time).total_seconds(), 1),
            'log_path':      self.log_path,
        }


# =============================================================================
# SECTION 3 -- Markdown Report Writer
# =============================================================================
# WHY   : Each cleaning module produces a human-readable technical note.
#         These notes form the Data Quality Appendix in the thesis.
# WHAT  : write_markdown_report() renders CleaningLogger entries as a
#         structured markdown document saved to reports/.
# ASSUME: Markdown rendering is supported by GitHub and the thesis platform.
# =============================================================================

def write_markdown_report(
        logger: 'CleaningLogger',
        report_path: str,
        dataset_description: str = '',
        key_findings: List[str] = None,
        engineered_columns: List[Tuple[str, str]] = None,
        rows_raw: int = 0,
        rows_clean: int = 0) -> None:
    '''
    Writes a structured markdown cleaning report for one dataset.

    WHY  : Raw log CSVs are machine-readable but not reviewer-friendly.
           Markdown reports provide narrative context for a thesis appendix.

    WHAT : Renders dataset overview, key findings, cleaning step table,
           engineered columns table, and assumptions summary.

    Args:
        logger              : CleaningLogger instance after flush().
        report_path         : Full path to write the .md file.
        dataset_description : One-paragraph description of the dataset.
        key_findings        : List of bullet-point strings.
        engineered_columns  : List of (col_name, description) tuples.
        rows_raw            : Row count before any cleaning.
        rows_clean          : Row count after full cleaning.
    '''
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    now    = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    md     = []
    pass_n = sum(1 for e in logger.entries if e['status'] == 'PASS')
    warn_n = sum(1 for e in logger.entries if e['status'] == 'WARN')
    fail_n = sum(1 for e in logger.entries if e['status'] == 'FAIL')
    md.append(f'# Data Cleaning Report: {logger.dataset_name.replace("_", " ").title()}')
    md.append('')
    md.append('| Field | Value |')
    md.append('|-------|-------|')
    md.append(f'| **Generated** | {now} |')
    md.append(f'| **Dataset** | `{logger.dataset_name}` |')
    md.append(f'| **Rows in (raw)** | {rows_raw:,} |')
    md.append(f'| **Rows out (clean)** | {rows_clean:,} |')
    md.append(f'| **Net change** | {rows_clean - rows_raw:,} |')
    md.append(f'| **Steps run** | {len(logger.entries)} |')
    md.append(f'| **PASS / WARN / FAIL** | {pass_n} / {warn_n} / {fail_n} |')
    md.append('')
    if dataset_description:
        md.append('## Dataset Overview')
        md.append('')
        md.append(dataset_description)
        md.append('')
    if key_findings:
        md.append('## Key Data Quality Findings')
        md.append('')
        for finding in key_findings:
            md.append(f'- {finding}')
        md.append('')
    md.append('## Cleaning Step Log')
    md.append('')
    md.append('| Step | Before | After | Affected | Status | Issue | Action |')
    md.append('|------|-------:|------:|---------:|--------|-------|--------|')
    for e in logger.entries:
        md.append(
            f'| {e["step"]} | {e["rows_before"]:,} | {e["rows_after"]:,}'
            f' | {e["rows_affected"]:,} | **{e["status"]}** | {e["issue_found"]} | {e["action_taken"]} |'
        )
    md.append('')
    if engineered_columns:
        md.append('## Engineered Columns')
        md.append('')
        md.append('| Column | Formula / Description |')
        md.append('|--------|-----------------------|')
        for col_name, col_desc in engineered_columns:
            md.append(f'| `{col_name}` | {col_desc} |')
        md.append('')
    md.append('## Assumptions Made')
    md.append('')
    seen = []
    for e in logger.entries:
        if e['assumption'] and e['assumption'] not in seen:
            seen.append(e['assumption'])
            md.append(f'- {e["assumption"]}')
    if not seen:
        md.append('- No explicit assumptions recorded for this dataset.')
    md.append('')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    print(f'  Report written -> {report_path}')


# =============================================================================
# SECTION 4 -- Console Output and Tabular Formatting
# =============================================================================
# WHY   : Consistent console output makes a long Colab cleaning run readable.
#         Without visual separators output is a wall of text impossible
#         to scan for warnings during execution.
# WHAT  : Section headers, DataFrame summaries, value-count tables.
#         All formatted with tabulate for clean column alignment.
# =============================================================================

def print_section_header(title: str, width: int = 65) -> None:
    '''
    Prints a formatted section header to the console.

    WHY  : Visual separators let a reviewer instantly locate any cleaning
           step in a long Colab output cell.
    '''
    print()
    print(f'  {"=" * width}')
    print(f'  {title}')
    print(f'  {"=" * width}')


def print_dataframe_summary(df: pd.DataFrame, label: str = '') -> None:
    '''
    Prints a schema-level summary of a DataFrame.

    WHY  : After every major transformation the analyst needs to verify:
           (1) Row count is as expected with no silent drops or duplication.
           (2) No unexpected nulls were introduced by the transformation.
           (3) Dtypes are correct such as date being datetime64 not object.
    WHAT : Iterates columns and reports dtype, null count, null%, unique count.
    WATCH: memory_usage(deep=True) is exact but slow on very large DataFrames.
    '''
    if label:
        print(f'  --- {label} ---')
    n = len(df)
    print(f'  Shape  : {n:,} rows x {df.shape[1]} columns')
    print(f'  Memory : {df.memory_usage(deep=True).sum() / 1024:.1f} KB')
    print()
    rows = []
    for col in df.columns:
        null_n   = int(df[col].isna().sum())
        null_pct = f'{100 * null_n / n:.1f}%' if n > 0 else '0.0%'
        uniq     = int(df[col].nunique(dropna=False))
        dtype    = str(df[col].dtype)
        rows.append([col, dtype, null_n, null_pct, uniq])
    print(tabulate(
        rows,
        headers=['Column', 'DType', 'Nulls', 'Null%', 'Unique'],
        tablefmt='simple',
        colalign=('left', 'left', 'right', 'right', 'right'),
    ))
    print()


def print_value_counts(
        series: pd.Series,
        label: str = '',
        top_n: int = 10) -> None:
    '''
    Prints top-N value counts for a Series as a formatted table.

    WHY  : Before standardising region names or warehouse IDs the analyst
           must know what raw values actually exist in the column.
           This prevents silent mismatches from assumed-clean values.
    WHAT : value_counts(dropna=False) ensures NaN is shown if present.
    '''
    vc   = series.value_counts(dropna=False).head(top_n)
    rows = [[str(v), c, f'{100 * c / len(series):.1f}%'] for v, c in vc.items()]
    print(f'  Value counts -- {label or series.name} (top {top_n}):')
    print(tabulate(rows,
                   headers=['Value', 'Count', 'Pct'],
                   tablefmt='simple',
                   colalign=('left', 'right', 'right')))
    print()

# =============================================================================
# SECTION 5 -- Date Parsing and Temporal Feature Engineering
# =============================================================================
# WHY   : Raw date columns arrive as dtype=object (string). All time-series
#         operations, week-level aggregations, and feature engineering require
#         proper datetime64. Leaving dates as strings causes silent
#         lexicographic sorting errors such as 2023-11-01 < 2023-9-01.
# ASSUME: All date strings follow ISO 8601 format YYYY-MM-DD.
#         If the source format changes add format= param to pd.to_datetime.
# WATCH : pd.to_datetime(errors='coerce') converts bad values to NaT silently.
#         Always check how many NaTs were created and log the count.
# =============================================================================

def parse_date_column(df: pd.DataFrame, col: str = 'date') -> pd.DataFrame:
    '''
    Parses a string date column to pandas datetime64[ns].
    Rows where the date cannot be parsed are dropped with a warning.

    WHY  : datetime64 enables the .dt accessor for year, month, and week,
           correct time-series sorting, and pd.Grouper aggregation.
           All of these are required by the weekly forecasting pipeline.

    WHAT : pd.to_datetime(errors='coerce') coerces bad dates to NaT.
           NaT rows are counted, printed as audit evidence, then dropped.

    ASSUME: Any date that cannot be parsed is a data entry error.
            Dropping is safe because a record without a valid date cannot
            be placed on a timeline and is useless for demand forecasting.

    WATCH : If more than 1% of rows produce NaT stop and investigate.
            Bulk NaT creation usually signals a format change in the feed.

    Args:
        df  : DataFrame containing the date column.
        col : Name of the column to parse (default: 'date').

    Returns:
        DataFrame with col cast to datetime64[ns] and NaT rows removed.
    '''
    df     = df.copy()
    before = len(df)
    df[col] = pd.to_datetime(df[col], errors='coerce')
    nat_n   = int(df[col].isna().sum())
    if nat_n > 0:
        pct = 100 * nat_n / before
        print(f'  [WARN] {nat_n:,} unparseable dates in [{col}] ({pct:.2f}%) -- dropped.')
        df = df.dropna(subset=[col])
    after = len(df)
    print(f'  [OK]  parse_date_column [{col}]: {before:,} -> {after:,} rows')
    return df


def engineer_date_features(df: pd.DataFrame, col: str = 'date') -> pd.DataFrame:
    '''
    Derives a full suite of temporal features from a parsed datetime column.

    WHY  : The forecasting model needs temporal signals for seasonality
           via month and quarter, weekly cycles via week_number and
           day_of_week, and the aggregation key year_week which is the
           forecasting grain. None of these are derivable from a string.

    WHAT : Adds these columns to the DataFrame:
        year        -- calendar year as int
        month       -- calendar month 1-12 as int
        quarter     -- fiscal quarter 1-4 as int
        week_number -- ISO 8601 week number 1-53 as int
        day_of_week -- Monday=0 through Sunday=6 as int
        year_week   -- ISO year-week string such as 2023-W04
        is_weekend  -- 1 if Saturday or Sunday, 0 otherwise as int

    CRITICAL -- is_weekend derivation:
        weekend_flag in the raw data is CORRUPTED and contains 01/01/1970.
        We drop that column and re-derive is_weekend from the date using
        dt.dayofweek >= 5. This is deterministic and always correct.

    ASSUME: Weeks follow ISO 8601. Use strftime('%G-W%V') not '%Y-W%W'.
    WATCH : %G is the ISO year not %Y the calendar year. For dates in early
            January they can differ: 2023-01-01 maps to ISO week 2022-W52.

    Args:
        df  : DataFrame with a parsed datetime64 column.
        col : Name of the datetime column (default: 'date').

    Returns:
        DataFrame with 7 temporal feature columns appended.
    '''
    df = df.copy()
    dt = df[col].dt
    df['year']        = dt.year.astype(int)
    df['month']       = dt.month.astype(int)
    df['quarter']     = dt.quarter.astype(int)
    df['week_number'] = dt.isocalendar().week.astype(int)
    df['day_of_week'] = dt.dayofweek.astype(int)   # Monday=0, Sunday=6
    df['year_week']   = dt.strftime('%G-W%V')      # ISO 8601 -- use %G not %Y
    df['is_weekend']  = (dt.dayofweek >= 5).astype(int)  # Sat=5 Sun=6
    print('  [OK]  engineer_date_features: 7 columns added.')
    print('         year, month, quarter, week_number, day_of_week, year_week, is_weekend')
    return df


# =============================================================================
# SECTION 6 -- Corrupted Flag Detection and Weekend Fix
# =============================================================================
# WHY   : weekend_flag in daily_demand and event_calendar contains
#         '01/01/1970' date strings -- a Unix epoch artifact from a broken
#         data generator. The column is not salvageable in any way.
# WHAT  : Drop weekend_flag entirely. is_weekend is re-derived in Section 5
#         from the date column which is always deterministically correct.
# ASSUME: Any column named 'weekend_flag' in the raw data is corrupted.
#         If a future data refresh fixes it remove this call and use
#         validate_binary_flags() on it instead.
# WATCH : Always print a sample of values BEFORE dropping so the corruption
#         is documented in the Colab output as permanent audit evidence.
# =============================================================================

def drop_corrupted_weekend_flag(
        df: pd.DataFrame,
        col: str = 'weekend_flag') -> pd.DataFrame:
    '''
    Drops the corrupted weekend_flag column if it exists in the DataFrame.

    WHY  : weekend_flag contains '01/01/1970' strings -- a Unix epoch
           artifact. Including it as a model feature introduces systematic
           noise that cannot be coerced to binary reliably.

    WHAT : Prints a sample of the corrupted values as audit evidence
           then drops the column from the DataFrame.

    ASSUME: is_weekend will always be re-derived from the date column by
            engineer_date_features() which is called after this function.

    WATCH : If the raw data feed is corrected in a future refresh remove
            this function call and validate with validate_binary_flags().

    Args:
        df  : DataFrame that may contain weekend_flag.
        col : Column name to check and drop (default: 'weekend_flag').

    Returns:
        DataFrame with weekend_flag removed if it was present.
    '''
    df = df.copy()
    if col not in df.columns:
        print(f'  [SKIP] [{col}] not found -- nothing to drop.')
        return df
    sample = df[col].dropna().unique()[:5].tolist()
    print(f'  [AUDIT] [{col}] sample values (should be 0/1 but are): {sample}')
    df = df.drop(columns=[col])
    print(f'  [FIX]  [{col}] dropped -- is_weekend will be derived from date.')
    return df


# =============================================================================
# SECTION 7 -- Binary Flag Validation
# =============================================================================
# WHY   : Binary flags such as holiday_peak_flag, prime_event_flag, and
#         marketing_push_flag are demand lift features in the forecast model.
#         A value of 2 or -1 corrupts event interaction terms and biases
#         demand forecasts without raising any obvious error.
# WHAT  : Assert all values are in {0, 1}. Values outside this set are
#         coerced to 0 which is conservative -- it understates event lift
#         rather than overstating it, which is safer for planning.
# ASSUME: An unrecognised flag value means the event was not active.
# WATCH : If bad_count exceeds 5% for any flag raise WARN and document.
#         Do not silently coerce without noting it in the cleaning log.
# =============================================================================

def validate_binary_flags(
        df: pd.DataFrame,
        flag_cols: List[str],
        valid_values: Set[int] = None) -> pd.DataFrame:
    '''
    Validates and coerces binary flag columns to contain only {0, 1}.

    WHY  : Binary flags drive demand lift multipliers. Any value outside
           {0, 1} propagates through feature engineering and biases model
           outputs unpredictably without raising an obvious error.

    WHAT : For each flag column identifies rows where value is not in
           valid_values, prints count and sample as audit evidence,
           coerces bad values to 0, then casts the column to int dtype.

    ASSUME: Valid values are {0, 1}. NaN is treated as invalid and set to 0.
    WATCH : If bad_count exceeds 5% for any flag raise WARN and document.

    Args:
        df           : DataFrame containing the flag columns.
        flag_cols    : List of column names to validate.
        valid_values : Acceptable integer values (default: {0, 1}).

    Returns:
        DataFrame with all listed flag columns validated and cast to int.
    '''
    if valid_values is None:
        valid_values = {0, 1}
    df = df.copy()
    for col in flag_cols:
        if col not in df.columns:
            print(f'  [SKIP] [{col}] not present in DataFrame.')
            continue
        bad_mask  = ~df[col].isin(valid_values)
        bad_count = int(bad_mask.sum())
        if bad_count > 0:
            pct    = 100 * bad_count / len(df)
            sample = df.loc[bad_mask, col].unique()[:5].tolist()
            level  = '[WARN]' if pct > 5 else '[FIX] '
            print(f'  {level} [{col}]: {bad_count:,} invalid ({pct:.1f}%) sample={sample} -> 0.')
            df.loc[bad_mask, col] = 0
        else:
            print(f'  [OK]  [{col}]: all values in {valid_values}.')
        df[col] = df[col].astype(int)
    return df

# =============================================================================
# SECTION 8 -- String Standardisation and Region Validation
# =============================================================================
# WHY   : String fields like region, category, and warehouse_id can carry
#         invisible differences: leading spaces, mixed case, trailing tabs.
#         'north' != 'North' != ' North' -- all three fail a join silently.
#         Silent join failures return wrong answers without raising errors.
#         They are the most dangerous class of bug in data pipelines.
# WHAT  : Strip whitespace, apply consistent Title Case, validate against
#         the canonical list from project_config.
# ASSUME: Title Case is the canonical form for region and category labels.
#         Warehouse IDs use UPPER-HYPHEN such as WH-NORTH, handled in S13.
# WATCH : After standardisation always call print_value_counts() to confirm
#         no unexpected values remain before any merge operation.
# =============================================================================

def standardise_string_column(
        df: pd.DataFrame,
        col: str,
        case: str = 'strip') -> pd.DataFrame:
    '''
    Strips whitespace from a string column and optionally normalises case.

    WHY  : Leading/trailing spaces and inconsistent casing are invisible
           in a DataFrame display but cause silent join failures on string
           key columns. This is a mandatory pre-join cleaning step.

    Args:
        df   : DataFrame containing the column.
        col  : Column name to clean.
        case : strip -- strip only no case change for IDs like SKU-000001
               title -- Title Case for region and category labels
               upper -- UPPER CASE for codes like warehouse_id
               lower -- lower case

    Returns:
        DataFrame with standardised string column.
    '''
    df = df.copy()
    if col not in df.columns:
        return df
    df[col] = df[col].astype(str).str.strip()
    if   case == 'title': df[col] = df[col].str.title()
    elif case == 'upper': df[col] = df[col].str.upper()
    elif case == 'lower': df[col] = df[col].str.lower()
    return df


def validate_region_column(
        df: pd.DataFrame,
        col: str = 'region',
        canonical_regions: List[str] = None) -> pd.DataFrame:
    '''
    Standardises a region column and validates values against canonical list.

    WHY  : region is the primary join key between daily_demand and
           warehouse_region_costs. One inconsistent label causes an entire
           demand zone to fall out of cost optimisation silently.

    WHAT : Strip then Title Case then check membership in canonical_regions.
           Unrecognised values are WARN-flagged but NOT dropped.
           The analyst must decide whether to remap or exclude them.

    ASSUME: All valid regions are in CANONICAL_REGIONS = North South East West.
    WATCH : If a new region is added to the network update CANONICAL_REGIONS
            in project_config.py BEFORE running this check.

    Args:
        df               : DataFrame with a region column.
        col              : Column name (default: 'region').
        canonical_regions: Valid region strings from project_config.

    Returns:
        DataFrame with standardised region column.
    '''
    df = df.copy()
    if col not in df.columns:
        print(f'  [SKIP] Region column [{col}] not found.')
        return df
    df = standardise_string_column(df, col, case='title')
    if canonical_regions:
        bad_mask  = ~df[col].isin(canonical_regions)
        bad_count = int(bad_mask.sum())
        if bad_count > 0:
            bad_vals = df.loc[bad_mask, col].unique().tolist()
            print(f'  [WARN] [{col}]: {bad_count:,} unrecognised values: {bad_vals}')
            print(f'         Expected one of: {canonical_regions}')
        else:
            print(f'  [OK]  [{col}]: all {df[col].nunique()} values match canonical regions.')
    return df


# =============================================================================
# SECTION 9 -- SKU ID Validation
# =============================================================================
# WHY   : sku_id is the primary join key between daily_demand, sku_master,
#         and starting_inventory. A malformed sku_id causes a silent join miss
#         and the record vanishes from merged datasets without any error.
# WHAT  : Validate all sku_id values against the canonical regex SKU-XXXXXX
#         which is exactly 6 digits. Non-conforming IDs are flagged not dropped.
# ASSUME: Canonical format is SKU-XXXXXX confirmed against sku_master.csv.
# WATCH : If the source system changes SKU format update
#         project_config.VALIDATION['sku_id_pattern'] only.
# =============================================================================

def validate_sku_ids(
        df: pd.DataFrame,
        col: str = 'sku_id',
        pattern: str = r'^SKU-\d{6}$') -> pd.DataFrame:
    '''
    Validates SKU ID format against the canonical regex pattern.

    WHY  : sku_id is the primary join key. A malformed ID causes a silent
           join miss and the row disappears from merged datasets with no error.
           This silently removes inventory records from placement optimisation.

    WHAT : Applies regex match to sku_id column after stripping whitespace.
           Non-conforming IDs are reported with count and sample values.
           Rows are flagged but NOT dropped -- analyst must review.

    ASSUME: Canonical format is SKU- followed by exactly 6 numeric digits.
    WATCH : Regex comes from project_config -- if format changes update
            VALIDATION['sku_id_pattern'] there, not here.

    Args:
        df      : DataFrame containing the sku_id column.
        col     : Column name (default: 'sku_id').
        pattern : Regex pattern for valid SKU IDs.

    Returns:
        DataFrame unchanged -- validation only, no rows dropped.
    '''
    df = df.copy()
    if col not in df.columns:
        print(f'  [SKIP] [{col}] not found in DataFrame.')
        return df
    df = standardise_string_column(df, col, case='strip')
    valid_mask    = df[col].str.match(pattern, na=False)
    invalid_count = int((~valid_mask).sum())
    if invalid_count > 0:
        bad_sample = df.loc[~valid_mask, col].unique()[:5].tolist()
        print(f'  [WARN] [{col}]: {invalid_count:,} IDs do not match {pattern}.')
        print(f'         Sample: {bad_sample}')
    else:
        print(f'  [OK]  [{col}]: all {len(df):,} IDs match pattern {pattern}.')
    return df


# =============================================================================
# SECTION 10 -- Numeric Validation and Outlier Capping
# =============================================================================
# WHY   : Numeric errors in supply chain data compound downstream.
#         Negative units_ordered break demand aggregations.
#         Outlier unit counts inflate safety stock calculations.
#         Negative prices corrupt margin and stockout penalty calculations.
#         Zero or negative cube_ft makes the carbon calculation meaningless.
# WHAT  : Assert positivity constraints, remove negatives, and Winsorise
#         extreme outliers at the 99.9th percentile.
# ASSUME: Negative values are data entry errors not returns or credits.
#         If returns are present in the feed model them as a separate flow.
# WATCH : The 99.9th percentile cap is configured in project_config.VALIDATION.
#         For skewed SKUs check the cap does not suppress genuine demand.
# =============================================================================

def remove_negative_values(
        df: pd.DataFrame,
        col: str,
        allow_zero: bool = False) -> pd.DataFrame:
    '''
    Removes rows where a numeric column is negative or zero if disallowed.

    WHY  : Negative units_ordered cannot represent forward demand.
           They cause safety stock formulas to underestimate need and
           lead to preventable stockouts during peak periods.

    WHAT : Identifies bad rows, prints count, and drops them.
    ASSUME: Negatives are data entry errors not credits or returns.
    WATCH : If returns are significant log them separately rather than
            dropping -- they carry useful signal about demand patterns.

    Args:
        df         : DataFrame containing the numeric column.
        col        : Column name to check.
        allow_zero : If False (default) rows where col equals 0 are also removed.

    Returns:
        DataFrame with invalid rows removed.
    '''
    df   = df.copy()
    mask = df[col] < 0 if allow_zero else df[col] <= 0
    bad_n = int(mask.sum())
    if bad_n > 0:
        label = 'less than 0' if allow_zero else 'less than or equal to 0'
        print(f'  [FIX]  [{col}]: {bad_n:,} rows with value {label} -- dropped.')
        df = df[~mask]
    else:
        print(f'  [OK]  [{col}]: no invalid values found.')
    return df


def cap_outliers_percentile(
        df: pd.DataFrame,
        col: str,
        percentile: float = 99.9) -> pd.DataFrame:
    '''
    Winsorises a numeric column at the given upper percentile threshold.

    WHY  : A single bulk order on a normally low-volume SKU inflates safety
           stock for all SKUs in that category and biases the forecasting
           model toward over-procurement. Winsorising retains distribution
           shape while neutralising individual extreme events.

    WHAT : Computes the percentile cap value, clips all values above it,
           and prints the cap threshold and count of capped rows.

    ASSUME: Values above the 99.9th percentile are anomalies appropriate
            for consumer goods. For B2B datasets consider a higher threshold.

    WATCH : If the 99.9th percentile is more than 10x the median the data
            may be genuinely heavy-tailed and log-transform may be better.

    Args:
        df         : DataFrame containing the numeric column.
        col        : Column name to cap.
        percentile : Cap threshold percentile (default: 99.9).

    Returns:
        DataFrame with values above threshold capped in place.
    '''
    df  = df.copy()
    cap = df[col].quantile(percentile / 100)
    capped_n = int((df[col] > cap).sum())
    if capped_n > 0:
        df[col] = df[col].clip(upper=cap)
        print(f'  [FIX]  [{col}]: {capped_n:,} values capped at {percentile}th pct = {cap:,.4f}.')
    else:
        print(f'  [OK]  [{col}]: no values exceed {percentile}th pct cap of {cap:,.4f}.')
    return df


def assert_positive_column(
        df: pd.DataFrame,
        col: str,
        min_value: float = 0.01) -> None:
    '''
    Hard-asserts that a numeric column has no values below min_value.
    Raises AssertionError with full context if the check fails.

    WHY  : price_usd, unit_cost_usd, cube_ft, and target_service_level must
           all be strictly positive for downstream calculations to be valid.
           unit_cost of 0 causes division by zero in margin_pct.
           cube_ft of 0 causes carbon_kg_per_unit to be 0 for any distance.

    ASSUME: Values below min_value (default 0.01) are data entry errors.

    Args:
        df        : DataFrame containing the column.
        col       : Column name to check.
        min_value : Minimum acceptable value (default: 0.01).
    '''
    if col not in df.columns:
        print(f'  [SKIP] [{col}] not found for positivity check.')
        return
    bad_mask  = df[col] < min_value
    bad_count = int(bad_mask.sum())
    if bad_count > 0:
        sample = df.loc[bad_mask, col].head(5).tolist()
        raise AssertionError(
            f'[FAIL] [{col}]: {bad_count:,} values below minimum {min_value}. '
            f'Sample: {sample}'
        )
    print(f'  [OK]  [{col}]: all {len(df):,} values >= {min_value}.')


def validate_service_level(
        df: pd.DataFrame,
        col: str = 'target_service_level',
        min_sl: float = 0.80,
        max_sl: float = 1.00) -> pd.DataFrame:
    '''
    Validates that target_service_level is within the range [min_sl, max_sl].

    WHY  : target_service_level directly drives safety stock calculations.
           A value below 0.80 produces dangerously low safety stock.
           A value above 1.00 is mathematically impossible and indicates
           a data error that would crash the safety stock formula.

    WHAT : Flags rows outside [0.80, 1.00] with WARN but does NOT drop them.
    ASSUME: Valid service levels fall in [0.80, 1.00].
    WATCH : Verify source did not store service levels as percentages
            such as 80 instead of 0.80 if many rows fail this check.

    Args:
        df     : DataFrame with target_service_level column.
        col    : Column name (default: 'target_service_level').
        min_sl : Minimum acceptable value (default: 0.80).
        max_sl : Maximum acceptable value (default: 1.00).

    Returns:
        DataFrame unchanged -- validation and flagging only.
    '''
    df = df.copy()
    if col not in df.columns:
        print(f'  [SKIP] [{col}] not found.')
        return df
    bad_mask  = (df[col] < min_sl) | (df[col] > max_sl)
    bad_count = int(bad_mask.sum())
    if bad_count > 0:
        sample = df.loc[bad_mask, col].unique()[:5].tolist()
        print(f'  [WARN] [{col}]: {bad_count:,} values outside [{min_sl}, {max_sl}]. Sample: {sample}')
    else:
        print(f'  [OK]  [{col}]: all {len(df):,} values in [{min_sl}, {max_sl}].')
    return df

# =============================================================================
# SECTION 8 -- String Standardisation and Region Validation
# =============================================================================
# WHY   : String fields like region, category, and warehouse_id can carry
#         invisible differences: leading spaces, mixed case, trailing tabs.
#         'north' != 'North' != ' North' -- all three fail a join silently.
#         Silent join failures return wrong answers without raising errors.
#         They are the most dangerous class of bug in data pipelines.
# WHAT  : Strip whitespace, apply consistent Title Case, validate against
#         the canonical list from project_config.
# ASSUME: Title Case is the canonical form for region and category labels.
#         Warehouse IDs use UPPER-HYPHEN such as WH-NORTH, handled in S13.
# WATCH : After standardisation always call print_value_counts() to confirm
#         no unexpected values remain before any merge operation.
# =============================================================================

def standardise_string_column(
        df: pd.DataFrame,
        col: str,
        case: str = 'strip') -> pd.DataFrame:
    '''
    Strips whitespace from a string column and optionally normalises case.

    WHY  : Leading/trailing spaces and inconsistent casing are invisible
           in a DataFrame display but cause silent join failures on string
           key columns. This is a mandatory pre-join cleaning step.

    Args:
        df   : DataFrame containing the column.
        col  : Column name to clean.
        case : strip -- strip only no case change for IDs like SKU-000001
               title -- Title Case for region and category labels
               upper -- UPPER CASE for codes like warehouse_id
               lower -- lower case

    Returns:
        DataFrame with standardised string column.
    '''
    df = df.copy()
    if col not in df.columns:
        return df
    df[col] = df[col].astype(str).str.strip()
    if   case == 'title': df[col] = df[col].str.title()
    elif case == 'upper': df[col] = df[col].str.upper()
    elif case == 'lower': df[col] = df[col].str.lower()
    return df


def validate_region_column(
        df: pd.DataFrame,
        col: str = 'region',
        canonical_regions: List[str] = None) -> pd.DataFrame:
    '''
    Standardises a region column and validates values against canonical list.

    WHY  : region is the primary join key between daily_demand and
           warehouse_region_costs. One inconsistent label causes an entire
           demand zone to fall out of cost optimisation silently.

    WHAT : Strip then Title Case then check membership in canonical_regions.
           Unrecognised values are WARN-flagged but NOT dropped.
           The analyst must decide whether to remap or exclude them.

    ASSUME: All valid regions are in CANONICAL_REGIONS = North South East West.
    WATCH : If a new region is added to the network update CANONICAL_REGIONS
            in project_config.py BEFORE running this check.

    Args:
        df               : DataFrame with a region column.
        col              : Column name (default: 'region').
        canonical_regions: Valid region strings from project_config.

    Returns:
        DataFrame with standardised region column.
    '''
    df = df.copy()
    if col not in df.columns:
        print(f'  [SKIP] Region column [{col}] not found.')
        return df
    df = standardise_string_column(df, col, case='title')
    if canonical_regions:
        bad_mask  = ~df[col].isin(canonical_regions)
        bad_count = int(bad_mask.sum())
        if bad_count > 0:
            bad_vals = df.loc[bad_mask, col].unique().tolist()
            print(f'  [WARN] [{col}]: {bad_count:,} unrecognised values: {bad_vals}')
            print(f'         Expected one of: {canonical_regions}')
        else:
            print(f'  [OK]  [{col}]: all {df[col].nunique()} values match canonical regions.')
    return df


# =============================================================================
# SECTION 9 -- SKU ID Validation
# =============================================================================
# WHY   : sku_id is the primary join key between daily_demand, sku_master,
#         and starting_inventory. A malformed sku_id causes a silent join miss
#         and the record vanishes from merged datasets without any error.
# WHAT  : Validate all sku_id values against the canonical regex SKU-XXXXXX
#         which is exactly 6 digits. Non-conforming IDs are flagged not dropped.
# ASSUME: Canonical format is SKU-XXXXXX confirmed against sku_master.csv.
# WATCH : If the source system changes SKU format update
#         project_config.VALIDATION['sku_id_pattern'] only.
# =============================================================================

def validate_sku_ids(
        df: pd.DataFrame,
        col: str = 'sku_id',
        pattern: str = r'^SKU-\d{6}$') -> pd.DataFrame:
    '''
    Validates SKU ID format against the canonical regex pattern.

    WHY  : sku_id is the primary join key. A malformed ID causes a silent
           join miss and the row disappears from merged datasets with no error.
           This silently removes inventory records from placement optimisation.

    WHAT : Applies regex match to sku_id column after stripping whitespace.
           Non-conforming IDs are reported with count and sample values.
           Rows are flagged but NOT dropped -- analyst must review.

    ASSUME: Canonical format is SKU- followed by exactly 6 numeric digits.
    WATCH : Regex comes from project_config -- if format changes update
            VALIDATION['sku_id_pattern'] there, not here.

    Args:
        df      : DataFrame containing the sku_id column.
        col     : Column name (default: 'sku_id').
        pattern : Regex pattern for valid SKU IDs.

    Returns:
        DataFrame unchanged -- validation only, no rows dropped.
    '''
    df = df.copy()
    if col not in df.columns:
        print(f'  [SKIP] [{col}] not found in DataFrame.')
        return df
    df = standardise_string_column(df, col, case='strip')
    valid_mask    = df[col].str.match(pattern, na=False)
    invalid_count = int((~valid_mask).sum())
    if invalid_count > 0:
        bad_sample = df.loc[~valid_mask, col].unique()[:5].tolist()
        print(f'  [WARN] [{col}]: {invalid_count:,} IDs do not match {pattern}.')
        print(f'         Sample: {bad_sample}')
    else:
        print(f'  [OK]  [{col}]: all {len(df):,} IDs match pattern {pattern}.')
    return df


# =============================================================================
# SECTION 10 -- Numeric Validation and Outlier Capping
# =============================================================================
# WHY   : Numeric errors in supply chain data compound downstream.
#         Negative units_ordered break demand aggregations.
#         Outlier unit counts inflate safety stock calculations.
#         Negative prices corrupt margin and stockout penalty calculations.
#         Zero or negative cube_ft makes the carbon calculation meaningless.
# WHAT  : Assert positivity constraints, remove negatives, and Winsorise
#         extreme outliers at the 99.9th percentile.
# ASSUME: Negative values are data entry errors not returns or credits.
#         If returns are present in the feed model them as a separate flow.
# WATCH : The 99.9th percentile cap is configured in project_config.VALIDATION.
#         For skewed SKUs check the cap does not suppress genuine demand.
# =============================================================================

def remove_negative_values(
        df: pd.DataFrame,
        col: str,
        allow_zero: bool = False) -> pd.DataFrame:
    '''
    Removes rows where a numeric column is negative or zero if disallowed.

    WHY  : Negative units_ordered cannot represent forward demand.
           They cause safety stock formulas to underestimate need and
           lead to preventable stockouts during peak periods.

    WHAT : Identifies bad rows, prints count, and drops them.
    ASSUME: Negatives are data entry errors not credits or returns.
    WATCH : If returns are significant log them separately rather than
            dropping -- they carry useful signal about demand patterns.

    Args:
        df         : DataFrame containing the numeric column.
        col        : Column name to check.
        allow_zero : If False (default) rows where col equals 0 are also removed.

    Returns:
        DataFrame with invalid rows removed.
    '''
    df   = df.copy()
    mask = df[col] < 0 if allow_zero else df[col] <= 0
    bad_n = int(mask.sum())
    if bad_n > 0:
        label = 'less than 0' if allow_zero else 'less than or equal to 0'
        print(f'  [FIX]  [{col}]: {bad_n:,} rows with value {label} -- dropped.')
        df = df[~mask]
    else:
        print(f'  [OK]  [{col}]: no invalid values found.')
    return df


def cap_outliers_percentile(
        df: pd.DataFrame,
        col: str,
        percentile: float = 99.9) -> pd.DataFrame:
    '''
    Winsorises a numeric column at the given upper percentile threshold.

    WHY  : A single bulk order on a normally low-volume SKU inflates safety
           stock for all SKUs in that category and biases the forecasting
           model toward over-procurement. Winsorising retains distribution
           shape while neutralising individual extreme events.

    WHAT : Computes the percentile cap value, clips all values above it,
           and prints the cap threshold and count of capped rows.

    ASSUME: Values above the 99.9th percentile are anomalies appropriate
            for consumer goods. For B2B datasets consider a higher threshold.

    WATCH : If the 99.9th percentile is more than 10x the median the data
            may be genuinely heavy-tailed and log-transform may be better.

    Args:
        df         : DataFrame containing the numeric column.
        col        : Column name to cap.
        percentile : Cap threshold percentile (default: 99.9).

    Returns:
        DataFrame with values above threshold capped in place.
    '''
    df  = df.copy()
    cap = df[col].quantile(percentile / 100)
    capped_n = int((df[col] > cap).sum())
    if capped_n > 0:
        df[col] = df[col].clip(upper=cap)
        print(f'  [FIX]  [{col}]: {capped_n:,} values capped at {percentile}th pct = {cap:,.4f}.')
    else:
        print(f'  [OK]  [{col}]: no values exceed {percentile}th pct cap of {cap:,.4f}.')
    return df


def assert_positive_column(
        df: pd.DataFrame,
        col: str,
        min_value: float = 0.01) -> None:
    '''
    Hard-asserts that a numeric column has no values below min_value.
    Raises AssertionError with full context if the check fails.

    WHY  : price_usd, unit_cost_usd, cube_ft, and target_service_level must
           all be strictly positive for downstream calculations to be valid.
           unit_cost of 0 causes division by zero in margin_pct.
           cube_ft of 0 causes carbon_kg_per_unit to be 0 for any distance.

    ASSUME: Values below min_value (default 0.01) are data entry errors.

    Args:
        df        : DataFrame containing the column.
        col       : Column name to check.
        min_value : Minimum acceptable value (default: 0.01).
    '''
    if col not in df.columns:
        print(f'  [SKIP] [{col}] not found for positivity check.')
        return
    bad_mask  = df[col] < min_value
    bad_count = int(bad_mask.sum())
    if bad_count > 0:
        sample = df.loc[bad_mask, col].head(5).tolist()
        raise AssertionError(
            f'[FAIL] [{col}]: {bad_count:,} values below minimum {min_value}. '
            f'Sample: {sample}'
        )
    print(f'  [OK]  [{col}]: all {len(df):,} values >= {min_value}.')


def validate_service_level(
        df: pd.DataFrame,
        col: str = 'target_service_level',
        min_sl: float = 0.80,
        max_sl: float = 1.00) -> pd.DataFrame:
    '''
    Validates that target_service_level is within the range [min_sl, max_sl].

    WHY  : target_service_level directly drives safety stock calculations.
           A value below 0.80 produces dangerously low safety stock.
           A value above 1.00 is mathematically impossible and indicates
           a data error that would crash the safety stock formula.

    WHAT : Flags rows outside [0.80, 1.00] with WARN but does NOT drop them.
    ASSUME: Valid service levels fall in [0.80, 1.00].
    WATCH : Verify source did not store service levels as percentages
            such as 80 instead of 0.80 if many rows fail this check.

    Args:
        df     : DataFrame with target_service_level column.
        col    : Column name (default: 'target_service_level').
        min_sl : Minimum acceptable value (default: 0.80).
        max_sl : Maximum acceptable value (default: 1.00).

    Returns:
        DataFrame unchanged -- validation and flagging only.
    '''
    df = df.copy()
    if col not in df.columns:
        print(f'  [SKIP] [{col}] not found.')
        return df
    bad_mask  = (df[col] < min_sl) | (df[col] > max_sl)
    bad_count = int(bad_mask.sum())
    if bad_count > 0:
        sample = df.loc[bad_mask, col].unique()[:5].tolist()
        print(f'  [WARN] [{col}]: {bad_count:,} values outside [{min_sl}, {max_sl}]. Sample: {sample}')
    else:
        print(f'  [OK]  [{col}]: all {len(df):,} values in [{min_sl}, {max_sl}].')
    return df

# =============================================================================
# SECTION 11 -- Financial Feature Engineering
# =============================================================================
# WHY   : The optimisation model minimises cost-to-serve which requires
#         per-unit financial metrics that do not exist in the raw data.
#         These must be derived during cleaning so every downstream module
#         uses consistent values from a single calculation point.
#
# ENGINEERED COLUMNS:
#   gross_margin_usd       = selling_price_usd - unit_cost_usd
#   margin_pct             = gross_margin_usd / selling_price_usd
#   stockout_penalty_usd   = selling_price_usd x 2
#   holding_cost_daily_usd = (unit_cost_usd x 0.25) / 365
#   inventory_value_usd    = starting_inventory_units x unit_cost_usd
#   daily_holding_cost_usd = starting_inventory_units x holding_cost_daily_usd
#
# REFERENCES:
#   Holding cost rate  : Chopra and Meindl 2016 Supply Chain Management 6th ed.
#                        Industry standard range 20-30% with 25% used here.
#   Stockout multiplier: 2x selling price is conservative.
#                        Amazon internal estimate is reported at 3-5x.
#                        2x is appropriate for planning-level modelling.
# =============================================================================

def engineer_financial_features(
        df: pd.DataFrame,
        unit_cost_col: str  = 'unit_cost_usd',
        price_col: str      = 'selling_price_usd',
        holding_rate: float = 0.25,
        days_per_year: int  = 365,
        stockout_mult: int  = 2) -> pd.DataFrame:
    '''
    Derives all financial cost and margin columns from raw price inputs.

    WHY  : Raw sku_master has unit_cost and selling_price but no margin,
           penalty, or holding cost columns. These are required inputs for
           the cost-to-serve optimisation objective function.

    WHAT : Adds four engineered columns:
        gross_margin_usd       = selling_price minus unit_cost
        margin_pct             = gross_margin divided by selling_price as decimal
        stockout_penalty_usd   = selling_price multiplied by stockout_mult
        holding_cost_daily_usd = unit_cost x holding_rate divided by days_per_year

    ASSUME: Holding cost rate of 25% per annum of unit cost covers capital
            cost, warehousing space, insurance, and obsolescence per
            Chopra and Meindl 2016. Stockout multiplier of 2x selling price
            per unit short is conservative but appropriate for planning level.

    WATCH : If gross_margin_usd is negative for any SKU this is a data error
            or a loss-leader SKU. Flag it rather than allowing negative margin
            to flow silently into the optimisation objective.

    Args:
        df            : DataFrame from sku_master with unit_cost and price.
        unit_cost_col : Column name for unit cost (default: 'unit_cost_usd').
        price_col     : Column name for selling price (default: 'selling_price_usd').
        holding_rate  : Annual holding cost as fraction of unit cost (default: 0.25).
        days_per_year : Days in year for daily rate conversion (default: 365).
        stockout_mult : Stockout penalty as multiple of selling price (default: 2).

    Returns:
        DataFrame with 4 financial feature columns appended.
    '''
    df = df.copy()

    # Gross margin
    # WHY: Margin drives SKU prioritisation in inventory allocation.
    #      High-margin SKUs should receive preferential safety stock.
    df['gross_margin_usd'] = df[price_col] - df[unit_cost_col]

    # Margin percentage
    # WHY: Normalised margin enables cross-SKU comparison regardless of
    #      absolute price level. Used in dashboard SKU profitability view.
    # WATCH: If selling_price_usd = 0 this creates inf.
    #        assert_positive_column() upstream should prevent this.
    df['margin_pct'] = (df['gross_margin_usd'] / df[price_col]).clip(lower=-1.0)

    # Stockout penalty
    # WHY: Stockout penalty is the cost of failing to meet one unit of demand.
    #      It is used as the penalty term in the cost-to-serve objective.
    #      Set at 2x selling price: captures lost revenue plus expedite cost
    #      plus customer dissatisfaction proxy.
    df['stockout_penalty_usd'] = df[price_col] * stockout_mult

    # Daily holding cost
    # WHY: Holding cost drives the trade-off between overstocking and
    #      understocking. Daily granularity matches the simulation time step.
    # FORMULA: (unit_cost x annual_rate) / 365 = cost per unit per day
    df['holding_cost_daily_usd'] = (df[unit_cost_col] * holding_rate) / days_per_year

    # Margin health check
    # WHY: A negative margin flowing into the optimiser causes it to
    #      recommend stocking loss-making SKUs preferentially which is wrong.
    neg_margin = int((df['gross_margin_usd'] < 0).sum())
    if neg_margin > 0:
        print(f'  [WARN] {neg_margin:,} SKUs have negative gross margin (cost > price).')
        print(f'         Investigate before using in optimisation -- loss-leaders?')
    else:
        print(f'  [OK]  Financial features engineered for {len(df):,} SKUs.')
        print(f'         Columns: gross_margin_usd, margin_pct,')
        print(f'                  stockout_penalty_usd, holding_cost_daily_usd')
    return df


def engineer_inventory_value_features(
        df: pd.DataFrame,
        inv_col: str        = 'starting_inventory_units',
        unit_cost_col: str  = 'unit_cost_usd',
        holding_rate: float = 0.25,
        days_per_year: int  = 365) -> pd.DataFrame:
    '''
    Derives inventory value and daily holding cost from starting inventory.

    WHY  : Starting inventory records show unit counts but not financial
           exposure. Inventory value and daily holding cost are required
           inputs for the placement optimisation cost objective.

    WHAT : Adds two columns:
        inventory_value_usd    = starting_inventory_units x unit_cost_usd
        daily_holding_cost_usd = starting_inventory_units x holding_cost_daily

    ASSUME: unit_cost_usd is sourced from sku_master via a prior join.
            If the join failed and unit_cost is NaN these columns will
            also be NaN which is detectable and must be investigated.

    WATCH : Large inventory_value_usd with high daily_holding_cost_usd signals
            overstocked nodes. These are the primary rebalancing candidates
            in the placement optimisation output.

    Args:
        df            : DataFrame with inventory units and unit cost columns.
        inv_col       : Column name for inventory units.
        unit_cost_col : Column name for unit cost.
        holding_rate  : Annual holding rate as decimal (default: 0.25).
        days_per_year : Days per year for daily rate (default: 365).

    Returns:
        DataFrame with inventory_value_usd and daily_holding_cost_usd added.
    '''
    df = df.copy()
    daily_rate = holding_rate / days_per_year
    df['inventory_value_usd']    = df[inv_col] * df[unit_cost_col]
    df['daily_holding_cost_usd'] = df[inv_col] * df[unit_cost_col] * daily_rate
    null_val = int(df['inventory_value_usd'].isna().sum())
    if null_val > 0:
        print(f'  [WARN] {null_val:,} NaN inventory_value_usd rows -- check unit_cost join.')
    else:
        total_val  = df['inventory_value_usd'].sum()
        total_hold = df['daily_holding_cost_usd'].sum()
        print(f'  [OK]  Inventory value features engineered.')
        print(f'         Total inventory value    : ${total_val:>15,.2f}')
        print(f'         Total daily holding cost : ${total_hold:>15,.2f}')
    return df


# =============================================================================
# SECTION 12 -- Carbon Emission Feature Engineering
# =============================================================================
# WHY   : Carbon emission minimisation is a PRIMARY placement objective.
#         The recommendation engine scores warehouse-region lanes on carbon
#         efficiency. Without these derived columns no carbon scoring is
#         possible and placement recommendations have no sustainability basis.
#
# CARBON CALCULATION CHAIN:
#   distance_km      = lead_time_days x 500  (500 km/day road freight proxy)
#   weight_tonnes    = volume_m3 x 200 kg/m3 / 1000
#   carbon_kg_CO2    = distance_km x weight_tonnes x 0.062
#
# CONSTANTS:
#   0.062    = EEA road freight emission factor kg CO2 per tonne-km
#   200      = general freight density kg/m3
#   500      = HGV long-haul road freight speed proxy km/day
#   0.028317 = cubic feet to cubic metres conversion factor NIST
#
# BUSINESS INSIGHT:
#   Warehouses with shortest lead time to highest-volume demand zones
#   will ALWAYS produce the lowest carbon score for those lanes.
#   This is the primary criterion for the placement recommendation.
#
# REFERENCE:
#   European Environment Agency EMEP/EEA Air Pollutant Emission Inventory
#   Guidebook 2019 -- road freight: 0.062 kg CO2 per tonne-km.
# =============================================================================

def engineer_carbon_features(
        df: pd.DataFrame,
        lead_time_col: str   = 'lead_time_days',
        cube_ft_col: str     = 'cube_ft',
        km_per_day: float    = 500.0,
        density_kg_m3: float = 200.0,
        eea_factor: float    = 0.062,
        cube_ft_to_m3: float = 0.028317) -> pd.DataFrame:
    '''
    Derives volume_m3, distance_km_proxy, and carbon_kg_per_unit columns.

    WHY  : Carbon per unit is a key criterion in the warehouse placement
           recommendation. Shorter lead time lanes with lower cube SKUs
           always produce lower carbon scores. This function makes that
           relationship explicit and quantified for every lane.

    WHAT : Adds three engineered columns:
        volume_m3          = cube_ft x 0.028317
        distance_km_proxy  = lead_time_days x 500
        carbon_kg_per_unit = distance_km x (volume_m3 x 200 / 1000) x 0.062

    ASSUME: 500 km/day is the standard HGV long-haul road freight speed proxy.
            It does not represent actual road distance -- it represents the
            relationship between lead time and kilometres travelled.
            General freight density of 200 kg/m3 is appropriate for mixed
            consumer goods across all 6 SKU categories in this dataset.

    WATCH : If cube_ft equals 0 for any SKU then carbon_kg_per_unit equals 0
            regardless of distance which is physically wrong.
            assert_positive_column() on cube_ft should catch this upstream.
            The guard below prints a warning if zero volumes are detected.

    Args:
        df            : DataFrame with lead_time_days and cube_ft columns.
        lead_time_col : Column name for lead time (default: 'lead_time_days').
        cube_ft_col   : Column name for product volume (default: 'cube_ft').
        km_per_day    : Road freight speed proxy in km/day (default: 500).
        density_kg_m3 : Freight density in kg per cubic metre (default: 200).
        eea_factor    : EEA emission factor kg CO2 per tonne-km (default: 0.062).
        cube_ft_to_m3 : Cubic feet to cubic metres conversion (default: 0.028317).

    Returns:
        DataFrame with volume_m3, distance_km_proxy, carbon_kg_per_unit added.
    '''
    df = df.copy()

    # Step 1 -- Convert volume from cubic feet to cubic metres
    # WHY: All downstream carbon calculations use SI units.
    #      cube_ft is stored in raw data; volume_m3 is the calculation currency.
    if cube_ft_col in df.columns:
        df['volume_m3'] = df[cube_ft_col] * cube_ft_to_m3
        zero_vol = int((df['volume_m3'] == 0).sum())
        if zero_vol > 0:
            print(f'  [WARN] {zero_vol:,} rows have volume_m3 = 0 -- carbon will be 0.')
    else:
        print(f'  [WARN] [{cube_ft_col}] not found -- volume_m3 set to NaN.')
        df['volume_m3'] = np.nan

    # Step 2 -- Derive distance proxy from lead time
    # WHY: Actual road distances are not available in this dataset.
    #      Lead time is the best available proxy: each day of lead time
    #      represents approximately 500 km of road freight movement.
    #      This is standard practice in academic supply chain carbon models.
    if lead_time_col in df.columns:
        df['distance_km_proxy'] = df[lead_time_col] * km_per_day
    else:
        print(f'  [WARN] [{lead_time_col}] not found -- distance_km_proxy set to NaN.')
        df['distance_km_proxy'] = np.nan

    # Step 3 -- Compute carbon kg CO2 per unit
    # FORMULA: carbon = distance_km x weight_tonnes x eea_factor
    # WHERE  : weight_tonnes = volume_m3 x density_kg_m3 / 1000
    # WHY    : This is the standard EEA road freight carbon formula.
    #          It produces kg CO2 emitted to deliver ONE unit over the lane.
    weight_tonnes = (df['volume_m3'] * density_kg_m3) / 1000
    df['carbon_kg_per_unit'] = df['distance_km_proxy'] * weight_tonnes * eea_factor

    print(f'  [OK]  Carbon features engineered:')
    print(f'         volume_m3          : min={df["volume_m3"].min():.4f}  max={df["volume_m3"].max():.4f}')
    print(f'         distance_km_proxy  : min={df["distance_km_proxy"].min():.0f}  max={df["distance_km_proxy"].max():.0f}')
    print(f'         carbon_kg_per_unit : min={df["carbon_kg_per_unit"].min():.6f}  max={df["carbon_kg_per_unit"].max():.6f}')
    return df


def engineer_lane_efficiency_score(
        df: pd.DataFrame,
        cost_col: str   = 'ship_cost_per_unit',
        carbon_col: str = 'carbon_kg_per_unit',
        speed_col: str  = 'lead_time_days') -> pd.DataFrame:
    '''
    Derives a composite lane efficiency score for each warehouse-region pair.

    WHY  : The placement recommendation must balance three competing objectives:
           (1) Lowest shipping cost
           (2) Lowest carbon emissions
           (3) Fastest delivery which is lowest lead time
           A single composite score allows lane ranking across all three
           dimensions simultaneously. Lower score means better lane.

    WHAT : Min-max normalises each of the three metrics to [0, 1] then
           computes a simple equal-weighted mean as the composite score.
           Lower normalised value means better performance on that metric.

    ASSUME: Equal weighting across cost, carbon, and speed is appropriate
            for a planning-level model. In a production system these weights
            would be business-configurable such as 50% cost 30% speed 20% carbon.

    WATCH : Min-max normalisation is sensitive to extreme outliers.
            If one lane has an extreme carbon or cost value it will dominate
            the normalised range and compress all other lanes near zero.
            Cap outliers in cost and carbon before calling this function.

    Args:
        df         : DataFrame with shipping cost, carbon, and lead time columns.
        cost_col   : Shipping cost column (default: 'ship_cost_per_unit').
        carbon_col : Carbon emission column (default: 'carbon_kg_per_unit').
        speed_col  : Lead time column (default: 'lead_time_days').

    Returns:
        DataFrame with lane_efficiency_score column appended.
    '''
    df = df.copy()

    def minmax_norm(series: pd.Series) -> pd.Series:
        # WHY: Min-max normalisation maps each metric to [0,1] making them
        #      directly comparable regardless of unit scale.
        # WATCH: If min == max (constant column) guard with 1e-9 to avoid NaN.
        rng = series.max() - series.min()
        if rng < 1e-9:
            return pd.Series(np.zeros(len(series)), index=series.index)
        return (series - series.min()) / rng

    scores = []
    for col in [cost_col, carbon_col, speed_col]:
        if col in df.columns:
            scores.append(minmax_norm(df[col]))
        else:
            print(f'  [WARN] [{col}] missing -- excluded from lane efficiency score.')

    if scores:
        df['lane_efficiency_score'] = sum(scores) / len(scores)
        lo = df['lane_efficiency_score'].min()
        hi = df['lane_efficiency_score'].max()
        print(f'  [OK]  lane_efficiency_score computed from {len(scores)} metrics.')
        print(f'         Score range: {lo:.4f} -- {hi:.4f}')
        print(f'         Lower score = better lane (lower cost + carbon + lead time).')
    else:
        print('  [FAIL] No valid columns found for lane efficiency score.')
        df['lane_efficiency_score'] = np.nan
    return df

# =============================================================================
# SECTION 13 -- Warehouse ID Utilities
# =============================================================================
# WHY   : The warehouse ID appears in three datasets with different formats:
#         warehouses.csv             -> WH-NORTH WH-SOUTH etc (canonical)
#         warehouse_region_costs.csv -> same as above but duplicated
#         starting_inventory.csv     -> WH-N WH-S WH-E WH-W WH-C (abbreviated)
#         All three must resolve to the same 5 canonical IDs before any join.
#         A mismatch silently drops inventory records from the optimisation.
#
# WHAT  : map_warehouse_prefix() resolves abbreviated IDs to canonical IDs.
#         deduplicate_to_canonical() collapses 5000+ duplicate rows to 5 nodes.
#         validate_warehouse_ids() asserts only canonical IDs remain.
# =============================================================================

def map_warehouse_prefix(
        df: pd.DataFrame,
        col: str = 'warehouse_id',
        prefix_map: Dict[str, str] = None) -> pd.DataFrame:
    '''
    Maps abbreviated warehouse ID prefixes to canonical warehouse IDs.

    WHY  : starting_inventory_snapshot.csv stores warehouse IDs as short
           prefixes such as WH-N and WH-S. These must be resolved to the
           canonical IDs such as WH-NORTH and WH-SOUTH used in all other
           datasets before any join can succeed.

    WHAT : Applies prefix_map as a direct lookup on the column.
           Unmapped values are flagged with WARN and left unchanged.

    ASSUME: The WAREHOUSE_PREFIX_MAP in project_config covers all valid
            abbreviated forms. Any new abbreviation added to the source
            system must be added to the config map first.

    WATCH : After mapping always call validate_warehouse_ids() to confirm
            no abbreviated IDs remain in the output.

    Args:
        df         : DataFrame containing the warehouse ID column.
        col        : Warehouse ID column name (default: 'warehouse_id').
        prefix_map : Dict mapping abbreviated to canonical IDs.
                     Defaults to WAREHOUSE_PREFIX_MAP from project_config.

    Returns:
        DataFrame with col values remapped to canonical IDs where matched.
    '''
    if prefix_map is None:
        from config.project_config import WAREHOUSE_PREFIX_MAP
        prefix_map = WAREHOUSE_PREFIX_MAP
    df = df.copy()
    if col not in df.columns:
        print(f'  [SKIP] [{col}] not found -- no prefix mapping applied.')
        return df
    df = standardise_string_column(df, col, case='strip')
    original_vals = set(df[col].unique())
    df[col] = df[col].replace(prefix_map)
    from config.project_config import CANONICAL_WAREHOUSE_IDS
    truly_unmapped = [v for v in df[col].unique() if v not in CANONICAL_WAREHOUSE_IDS]
    if truly_unmapped:
        print(f'  [WARN] [{col}]: {len(truly_unmapped)} unmapped values: {truly_unmapped}')
    else:
        mapped_n = len([v for v in original_vals if v in prefix_map])
        print(f'  [OK]  [{col}]: {mapped_n} abbreviated IDs mapped to canonical form.')
    return df


def deduplicate_to_canonical(
        df: pd.DataFrame,
        canonical_network: List[Dict] = None) -> pd.DataFrame:
    '''
    Rebuilds the warehouses DataFrame from the canonical network definition.

    WHY  : warehouses.csv contains 5000+ rows but only 5 real warehouses.
           This is a data generation artifact -- the same 5 nodes are
           repeated approximately 1000 times each. Using the raw file
           inflates capacity constraints by 1000x and corrupts the
           optimisation entirely by making each node appear to have
           120 million units of capacity instead of 120 thousand.

    WHAT : Rebuilds the DataFrame entirely from CANONICAL_NETWORK in
           project_config. All raw rows are discarded. The canonical
           values are ground truth and do not depend on the raw data.

    ASSUME: The 5 canonical nodes and their capacities and costs are correct
            as defined in project_config.CANONICAL_NETWORK. If a warehouse
            expands in reality update the config, not this function.

    WATCH : This function REPLACES the DataFrame entirely not filters it.
            The output always has exactly 5 rows. Any raw rows not in the
            canonical set are dropped without a trace by design.

    Args:
        df               : Raw warehouses DataFrame (5000+ rows).
        canonical_network: List of canonical warehouse dicts from project_config.

    Returns:
        DataFrame with exactly 5 rows, one per canonical warehouse node.
    '''
    if canonical_network is None:
        from config.project_config import CANONICAL_NETWORK
        canonical_network = CANONICAL_NETWORK
    before   = len(df)
    df_clean = pd.DataFrame(canonical_network)
    print(f'  [FIX]  deduplicate_to_canonical: {before:,} rows -> {len(df_clean)} canonical nodes.')
    print(f'         Nodes: {df_clean["warehouse_id"].tolist()}')
    return df_clean


def validate_warehouse_ids(
        df: pd.DataFrame,
        col: str = 'warehouse_id',
        canonical_ids: Set[str] = None) -> None:
    '''
    Asserts all warehouse IDs in the column are in the canonical set.
    Raises AssertionError with full context if any non-canonical ID is found.

    WHY  : A non-canonical warehouse ID causes a silent join failure.
           Inventory assigned to WH-NORTH-1 will never match WH-NORTH
           in the cost table and disappears from the model entirely.

    WHAT : Set difference check between actual IDs and canonical_ids.
           Raises immediately if any difference is found.

    ASSUME: canonical_ids comes from project_config.CANONICAL_WAREHOUSE_IDS.
    WATCH : This is a hard assert -- call it AFTER map_warehouse_prefix().
            Calling it before prefix mapping will always fail.

    Args:
        df            : DataFrame containing the warehouse ID column.
        col           : Column name to check (default: 'warehouse_id').
        canonical_ids : Set of valid canonical IDs.
    '''
    if canonical_ids is None:
        from config.project_config import CANONICAL_WAREHOUSE_IDS
        canonical_ids = CANONICAL_WAREHOUSE_IDS
    if col not in df.columns:
        print(f'  [SKIP] [{col}] not found for warehouse ID validation.')
        return
    actual_ids    = set(df[col].unique())
    non_canonical = actual_ids - canonical_ids
    if non_canonical:
        raise AssertionError(
            f'[FAIL] Non-canonical warehouse IDs in [{col}]: {non_canonical}\n'
            f'       Expected one of: {canonical_ids}'
        )
    print(f'  [OK]  [{col}]: all {len(actual_ids)} IDs are canonical. {sorted(actual_ids)}')


# =============================================================================
# SECTION 14 -- Cross-Dataset Referential Integrity Checks
# =============================================================================
# WHY   : Each dataset is cleaned in isolation but the pipeline requires
#         them to join correctly at runtime. A SKU in daily_demand that
#         does not exist in sku_master produces NaN cost columns after the
#         join, silently corrupting the optimisation objective function.
#
# WHAT  : These functions check referential integrity across dataset pairs.
#         They are called by run_all_cleaning.py AFTER all datasets are clean.
#
# PHILOSOPHY:
#   These checks do not fix anything -- they SURFACE problems that must be
#   resolved at the source. Always run all cleaning modules to completion
#   before running cross-dataset checks.
# =============================================================================

def check_sku_referential_integrity(
        df_demand: pd.DataFrame,
        df_sku: pd.DataFrame,
        demand_col: str = 'sku_id',
        sku_col: str    = 'sku_id') -> Dict[str, Any]:
    '''
    Checks that all SKU IDs in daily_demand exist in sku_master.

    WHY  : If a SKU in daily_demand has no matching row in sku_master the
           join produces NaN for unit_cost, cube_ft, and service_level.
           NaN cost flows into the optimisation objective and produces
           undefined results that may not raise an obvious error.

    WHAT : Set difference -- SKUs in demand but not in master are orphaned.
           Also reports SKUs in master but not in demand as dead stock.

    ASSUME: Every SKU that has demand must have a master record.
            SKUs in master with no demand are not an error -- they may be
            new arrivals or slow-moving stock awaiting first sale.

    WATCH : If orphaned SKU count is high the sku_id format may have
            diverged between systems. Check both datasets for format issues.

    Args:
        df_demand  : Cleaned daily_demand DataFrame.
        df_sku     : Cleaned sku_master DataFrame.
        demand_col : sku_id column name in demand df.
        sku_col    : sku_id column name in sku master df.

    Returns:
        Dict with orphaned_count, dead_stock_count, and id sets.
    '''
    demand_skus = set(df_demand[demand_col].unique())
    master_skus = set(df_sku[sku_col].unique())
    orphaned    = demand_skus - master_skus
    dead_stock  = master_skus - demand_skus
    print(f'  SKU Referential Integrity Check:')
    print(f'    SKUs in demand          : {len(demand_skus):,}')
    print(f'    SKUs in master          : {len(master_skus):,}')
    print(f'    Orphaned (demand only)  : {len(orphaned):,}  {"[WARN]" if orphaned else "[OK]  "}')
    print(f'    Dead stock (master only): {len(dead_stock):,}  [INFO]')
    if orphaned:
        print(f'    [WARN] Orphaned sample: {list(orphaned)[:5]}')
    return {
        'demand_sku_count': len(demand_skus),
        'master_sku_count': len(master_skus),
        'orphaned_count':   len(orphaned),
        'dead_stock_count': len(dead_stock),
        'orphaned_ids':     orphaned,
        'dead_stock_ids':   dead_stock,
    }


def check_warehouse_lane_coverage(
        df_costs: pd.DataFrame,
        expected_lanes: int = 20,
        wh_col: str         = 'warehouse_id',
        region_col: str     = 'demand_region') -> Dict[str, Any]:
    '''
    Validates that warehouse_region_costs has exactly 20 unique lanes.

    WHY  : The optimisation requires a shipping cost and lead time for every
           warehouse-region pair which is 5 warehouses x 4 regions = 20 lanes.
           A missing lane means the optimiser cannot route demand from that
           region through the missing warehouse without raising any error.

    WHAT : Counts unique warehouse-region pairs and identifies any missing
           combinations from the full 20-lane expected matrix.

    ASSUME: All 5 warehouses serve all 4 regions including WH-CENTRAL.
    WATCH : If expected_lanes changes update project_config.VALIDATION
            expected_lane_count to match the new network topology.

    Args:
        df_costs       : Cleaned warehouse_region_costs DataFrame.
        expected_lanes : Expected number of unique lanes (default: 20).
        wh_col         : Warehouse ID column name.
        region_col     : Region column name.

    Returns:
        Dict with lane_count, missing_lanes, and coverage status.
    '''
    from config.project_config import CANONICAL_WAREHOUSE_IDS, CANONICAL_REGIONS
    actual_lanes  = df_costs[[wh_col, region_col]].drop_duplicates()
    lane_count    = len(actual_lanes)
    expected_pairs = {(wh, r) for wh in CANONICAL_WAREHOUSE_IDS for r in CANONICAL_REGIONS}
    actual_pairs   = set(zip(actual_lanes[wh_col], actual_lanes[region_col]))
    missing_pairs  = expected_pairs - actual_pairs
    extra_pairs    = actual_pairs - expected_pairs
    ok = lane_count == expected_lanes and not missing_pairs
    print(f'  Warehouse-Region Lane Coverage Check:')
    print(f'    Expected lanes : {expected_lanes}')
    print(f'    Actual lanes   : {lane_count}  {"[OK]  " if ok else "[WARN]"}')
    if missing_pairs:
        print(f'    [WARN] Missing pairs  : {sorted(missing_pairs)}')
    if extra_pairs:
        print(f'    [WARN] Extra pairs    : {sorted(extra_pairs)}')
    return {
        'lane_count':    lane_count,
        'expected_lanes': expected_lanes,
        'missing_pairs': missing_pairs,
        'extra_pairs':   extra_pairs,
        'all_lanes_ok':  ok,
    }


def check_region_consistency(
        dataframes: Dict[str, pd.DataFrame],
        region_col: str = 'region',
        canonical_regions: List[str] = None) -> None:
    '''
    Checks region label consistency across all datasets containing a region column.

    WHY  : If daily_demand uses 'North' and warehouse_region_costs uses 'north'
           the join silently produces an empty result for that region and all
           demand in that zone disappears from the cost model.

    WHAT : For each DataFrame in the dict that has a region-like column
           prints all unique region values so mismatches are immediately visible.

    ASSUME: Canonical regions are Title Case: North South East West.
    WATCH : Run this AFTER all cleaning modules complete not before.
            Pre-cleaning datasets will always show inconsistent regions.

    Args:
        dataframes        : Dict of dataset_name to DataFrame.
        region_col        : Column name substring to match (default: 'region').
        canonical_regions : Valid region strings.
    '''
    if canonical_regions is None:
        from config.project_config import CANONICAL_REGIONS
        canonical_regions = CANONICAL_REGIONS
    print('  Region Consistency Check across datasets:')
    all_ok = True
    for name, df in dataframes.items():
        cols_to_check = [c for c in df.columns if region_col in c.lower()]
        for col in cols_to_check:
            unique_vals = sorted(df[col].dropna().unique().tolist())
            bad = [v for v in unique_vals if v not in canonical_regions]
            status = '[OK]  ' if not bad else '[WARN]'
            print(f'    {status} {name}.{col}: {unique_vals}')
            if bad:
                print(f'           Non-canonical: {bad}')
                all_ok = False
    if all_ok:
        print('    All region labels are consistent across datasets.')


# =============================================================================
# SECTION 15 -- DataFrame Schema Audit
# =============================================================================
# WHY   : After cleaning, the schema of each output DataFrame must match the
#         contract defined in project_config.COLUMNS. A missing column or wrong
#         dtype will cause a KeyError or type error in the forecasting or
#         optimisation modules -- potentially at runtime, not at clean time.
#
# WHAT  : audit_schema() compares actual columns to expected columns and
#         prints a clear PASS/FAIL summary with a list of any mismatches.
#
# PHILOSOPHY:
#   Schema checks are the handshake between the cleaning pipeline and the
#   modelling pipeline. If cleaning passes and schema fails the contract
#   between the two layers has been broken and must be fixed before modelling.
# =============================================================================

def audit_schema(
        df: pd.DataFrame,
        dataset_key: str,
        expected_columns: List[str] = None) -> bool:
    '''
    Audits a cleaned DataFrame against the expected column schema.

    WHY  : Every downstream module assumes specific column names exist.
           If a column was renamed or dropped during cleaning the module
           fails at runtime with a cryptic KeyError not a clear data error.
           Catching schema mismatches here at clean time is far safer.

    WHAT : Compares actual columns to expected columns from project_config.
           Reports missing columns (in expected but not in actual).
           Reports extra columns (in actual but not in expected).
           Prints PASS if all expected columns are present.
           Extra columns are allowed -- they are informational only.

    ASSUME: The expected columns list in project_config.COLUMNS defines the
            minimum required contract. Extra columns are always permitted.
            Missing columns are always a FAIL.

    WATCH : If an expected column name changes in a cleaning module update
            project_config.COLUMNS to match BEFORE re-running.
            The config is the contract -- the code must conform to it.

    Args:
        df               : Cleaned DataFrame to audit.
        dataset_key      : Key into project_config.COLUMNS.
        expected_columns : Override list of expected columns (optional).

    Returns:
        bool: True if all expected columns are present, False otherwise.
    '''
    if expected_columns is None:
        from config.project_config import COLUMNS
        expected_columns = COLUMNS.get(dataset_key, [])
    if not expected_columns:
        print(f'  [SKIP] No expected schema defined for [{dataset_key}].')
        return True
    actual_cols   = set(df.columns.tolist())
    expected_cols = set(expected_columns)
    missing = expected_cols - actual_cols
    extra   = actual_cols - expected_cols
    print(f'  Schema Audit -- {dataset_key}:')
    print(f'    Expected columns : {len(expected_cols)}')
    print(f'    Actual columns   : {len(actual_cols)}')
    if missing:
        print(f'    [FAIL] Missing : {sorted(missing)}')
    else:
        print(f'    [PASS] All expected columns present.')
    if extra:
        print(f'    [INFO] Extra (not in contract): {sorted(extra)}')
    return len(missing) == 0


def final_cleaning_summary(
        df_raw: pd.DataFrame,
        df_clean: pd.DataFrame,
        dataset_name: str,
        logger: 'CleaningLogger') -> None:
    '''
    Prints a formatted end-of-module summary for one cleaning run.

    WHY  : After a cleaning module completes the analyst needs a single
           consolidated view showing what changed, how many rows were
           affected, and whether the run is safe to proceed with.
           This replaces scanning back through all the step-by-step output.

    WHAT : Prints a table with raw vs clean row and column counts,
           step summary, and the final PASS/WARN/FAIL breakdown.

    Args:
        df_raw       : Original raw DataFrame before any cleaning.
        df_clean     : Final cleaned DataFrame after all steps.
        dataset_name : Name of the dataset for display.
        logger       : CleaningLogger instance after flush().
    '''
    pass_n = sum(1 for e in logger.entries if e['status'] == 'PASS')
    warn_n = sum(1 for e in logger.entries if e['status'] == 'WARN')
    fail_n = sum(1 for e in logger.entries if e['status'] == 'FAIL')
    rows_delta = len(df_clean) - len(df_raw)
    cols_delta = df_clean.shape[1] - df_raw.shape[1]
    print()
    print(f'  {"=" * 61}')
    print(f'  CLEANING COMPLETE : {dataset_name.upper()}')
    print(f'  {"=" * 61}')
    summary = [
        ['Rows (raw)',         f'{len(df_raw):,}'],
        ['Rows (clean)',       f'{len(df_clean):,}'],
        ['Row delta',          f'{rows_delta:+,}'],
        ['Columns (raw)',      f'{df_raw.shape[1]}'],
        ['Columns (clean)',    f'{df_clean.shape[1]}'],
        ['Column delta',       f'{cols_delta:+}'],
        ['Steps run',          f'{len(logger.entries)}'],
        ['PASS / WARN / FAIL', f'{pass_n} / {warn_n} / {fail_n}'],
    ]
    print(tabulate(summary, tablefmt='simple', colalign=('left', 'right')))
    print()
    overall = 'PASS' if fail_n == 0 and warn_n == 0 else ('WARN' if fail_n == 0 else 'FAIL')
    print(f'  OVERALL STATUS : {overall}')
    print(f'  {"=" * 61}')
