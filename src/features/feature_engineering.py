"""
Feature engineering for regional demand forecasting.

This module builds the modeling dataset used by the forecasting step.
The business goal is to turn raw demand history and event signals into
predictive features that planners can trust across regions and categories.
"""

import os
import datetime
import numpy as np
import pandas as pd


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA_PROCESSED = os.path.join(PROJECT_ROOT, 'data', 'processed')
OUTPUT_LOGS = os.path.join(PROJECT_ROOT, 'outputs', 'logs')


def load_processed_inputs():
    """
    Load cleaned demand and event data needed for feature generation.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        Clean demand and event datasets ready for feature building.
    """
    demand_path = os.path.join(DATA_PROCESSED, 'daily_demand_clean.csv')
    event_path = os.path.join(DATA_PROCESSED, 'event_calendar_clean.csv')

    if not os.path.exists(demand_path):
        raise FileNotFoundError(f'Expected demand file not found: {demand_path}')
    if not os.path.exists(event_path):
        raise FileNotFoundError(f'Expected event file not found: {event_path}')

    demand_df = pd.read_csv(demand_path)
    event_df = pd.read_csv(event_path)

    print(f'Loaded {len(demand_df):,} demand rows from {demand_path}')
    print(f'Loaded {len(event_df):,} event rows from {event_path}')
    return demand_df, event_df


def standardise_date_columns(demand_df, event_df):
    """
    Align date fields so demand and event data can be merged cleanly.

    Parameters
    ----------
    demand_df : pd.DataFrame
        Daily demand history.
    event_df : pd.DataFrame
        Event calendar history.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        DataFrames with standardised datetime columns.
    """
    demand_df = demand_df.copy()
    event_df = event_df.copy()

    date_candidates = ['date', 'order_date', 'demand_date']
    demand_date_col = next((col for col in date_candidates if col in demand_df.columns), None)
    event_date_col = next((col for col in date_candidates if col in event_df.columns), None)

    if demand_date_col is None:
        raise ValueError(f'Expected one of {date_candidates} in demand data, found: {list(demand_df.columns)}')
    if event_date_col is None:
        raise ValueError(f'Expected one of {date_candidates} in event data, found: {list(event_df.columns)}')

    demand_df['date'] = pd.to_datetime(demand_df[demand_date_col])
    event_df['date'] = pd.to_datetime(event_df[event_date_col])
    return demand_df, event_df


def add_calendar_features(modeling_df):
    """
    Add time features that help the forecast pick up seasonality and timing effects.
    """
    modeling_df = modeling_df.copy()
    modeling_df['year'] = modeling_df['date'].dt.year
    modeling_df['month'] = modeling_df['date'].dt.month
    modeling_df['week'] = modeling_df['date'].dt.isocalendar().week.astype(int)
    modeling_df['day_of_week'] = modeling_df['date'].dt.dayofweek
    modeling_df['quarter'] = modeling_df['date'].dt.quarter
    modeling_df['is_weekend'] = modeling_df['day_of_week'].isin([5, 6]).astype(int)
    return modeling_df


def add_group_lag_features(modeling_df, group_cols, target_col, lag_periods=None):
    """
    Create lag features by region and category to preserve local demand memory.
    """
    modeling_df = modeling_df.copy()
    lag_periods = lag_periods or [1, 2, 3, 4, 8, 12, 27]
    modeling_df = modeling_df.sort_values(group_cols + ['date'])

    for lag_value in lag_periods:
        lag_name = f'{target_col}_lag_{lag_value}'
        modeling_df[lag_name] = modeling_df.groupby(group_cols)[target_col].shift(lag_value)

    return modeling_df


def add_group_rollups(modeling_df, group_cols, target_col, windows=None):
    """
    Add trailing demand summaries that capture local trend and stability.
    """
    modeling_df = modeling_df.copy()
    windows = windows or [4, 8, 12]
    modeling_df = modeling_df.sort_values(group_cols + ['date'])

    grouped_series = modeling_df.groupby(group_cols)[target_col]
    for window_value in windows:
        mean_name = f'{target_col}_roll_mean_{window_value}'
        std_name = f'{target_col}_roll_std_{window_value}'
        modeling_df[mean_name] = grouped_series.transform(lambda s: s.shift(1).rolling(window_value).mean())
        modeling_df[std_name] = grouped_series.transform(lambda s: s.shift(1).rolling(window_value).std())

    return modeling_df


def build_modeling_dataset():
    """
    Build the forecast-ready dataset used by the training pipeline.

    Returns
    -------
    pd.DataFrame
        Modeling dataset with engineered time, lag, and rolling features.
    """
    demand_df, event_df = load_processed_inputs()
    demand_df, event_df = standardise_date_columns(demand_df, event_df)

    modeling_df = demand_df.merge(event_df, on='date', how='left')
    print(f'Merged demand and event data into {len(modeling_df):,} rows')

    if 'units_sold' not in modeling_df.columns:
        target_candidates = ['demand_units', 'units', 'sales_units']
        matched_target = next((col for col in target_candidates if col in modeling_df.columns), None)
        if matched_target is None:
            raise ValueError(f'Expected target column from {target_candidates} or units_sold, found: {list(modeling_df.columns)}')
        modeling_df['units_sold'] = modeling_df[matched_target]

    region_col = 'region' if 'region' in modeling_df.columns else 'warehouse_region' if 'warehouse_region' in modeling_df.columns else None
    category_col = 'category' if 'category' in modeling_df.columns else 'product_category' if 'product_category' in modeling_df.columns else None

    if region_col is None:
        raise ValueError(f"Expected 'region' or 'warehouse_region' in modeling data, found: {list(modeling_df.columns)}")
    if category_col is None:
        raise ValueError(f"Expected 'category' or 'product_category' in modeling data, found: {list(modeling_df.columns)}")

    modeling_df['region'] = modeling_df[region_col]
    modeling_df['category'] = modeling_df[category_col]
    modeling_df = add_calendar_features(modeling_df)
    modeling_df = add_group_lag_features(modeling_df, ['region', 'category'], 'units_sold')
    modeling_df = add_group_rollups(modeling_df, ['region', 'category'], 'units_sold')

    modeling_df = modeling_df.sort_values(['region', 'category', 'date']).reset_index(drop=True)
    print(f'Feature engineering complete: {modeling_df.shape[0]:,} rows x {modeling_df.shape[1]:,} columns')
    return modeling_df


def save_outputs(modeling_df):
    """
    Save the modeling dataset and a lightweight process log for traceability.
    """
    os.makedirs(DATA_PROCESSED, exist_ok=True)
    os.makedirs(OUTPUT_LOGS, exist_ok=True)

    data_path = os.path.join(DATA_PROCESSED, 'modeling_dataset.csv')
    log_path = os.path.join(OUTPUT_LOGS, 'log_feature_engineering.csv')

    modeling_df.to_csv(data_path, index=False)
    assert os.path.exists(data_path), f'Write failed: {data_path}'

    log_df = pd.DataFrame(
        [
            {
                'run_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'rows_written': len(modeling_df),
                'columns_written': len(modeling_df.columns),
                'output_path': data_path,
            }
        ]
    )
    log_df.to_csv(log_path, index=False)
    assert os.path.exists(log_path), f'Write failed: {log_path}'
    print(f'Saved modeling dataset to {data_path}')
    print(f'Saved feature engineering log to {log_path}')


def main():
    """Run the feature engineering workflow end to end."""
    modeling_df = build_modeling_dataset()
    save_outputs(modeling_df)


if __name__ == '__main__':
    main()