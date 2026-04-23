"""
ABC-XYZ inventory classification for category prioritisation.

This module ranks inventory by revenue contribution and variability so
planning teams can focus service and working-capital decisions where they matter most.
"""

import os
import datetime
import pandas as pd
import numpy as np


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA_PROCESSED = os.path.join(PROJECT_ROOT, 'data', 'processed')
OUTPUT_LOGS = os.path.join(PROJECT_ROOT, 'outputs', 'logs')


def load_inputs():
    """Load demand and inventory value inputs used for segmentation."""
    demand_path = os.path.join(DATA_PROCESSED, 'daily_demand_clean.csv')
    if not os.path.exists(demand_path):
        raise FileNotFoundError(f'Expected demand file not found: {demand_path}')

    demand_df = pd.read_csv(demand_path)
    print(f'Loaded {len(demand_df):,} rows from {demand_path}')
    return demand_df


def classify_abc_xyz(demand_df):
    """
    Build category-level ABC-XYZ classes to show where revenue and stability sit.
    """
    demand_df = demand_df.copy()

    category_col = 'category' if 'category' in demand_df.columns else 'product_category' if 'product_category' in demand_df.columns else None
    units_col = 'units_sold' if 'units_sold' in demand_df.columns else 'demand_units' if 'demand_units' in demand_df.columns else None
    revenue_col = 'revenue' if 'revenue' in demand_df.columns else None

    if category_col is None:
        raise ValueError(f"Expected 'category' or 'product_category' in demand data, found: {list(demand_df.columns)}")
    if units_col is None:
        raise ValueError(f"Expected 'units_sold' or 'demand_units' in demand data, found: {list(demand_df.columns)}")

    demand_df['category'] = demand_df[category_col]
    demand_df['units_for_cv'] = demand_df[units_col]

    if revenue_col is None:
        demand_df['revenue'] = demand_df['units_for_cv']
    else:
        demand_df['revenue'] = demand_df[revenue_col]

    summary_df = demand_df.groupby('category', as_index=False).agg(
        revenue=('revenue', 'sum'),
        demand_mean=('units_for_cv', 'mean'),
        demand_std=('units_for_cv', 'std'),
    )

    summary_df['demand_std'] = summary_df['demand_std'].fillna(0.0)
    summary_df['cv'] = np.where(summary_df['demand_mean'] > 0, summary_df['demand_std'] / summary_df['demand_mean'] * 100.0, 0.0)
    summary_df = summary_df.sort_values('revenue', ascending=False).reset_index(drop=True)
    summary_df['revenue_share_pct'] = summary_df['revenue'] / summary_df['revenue'].sum() * 100.0
    summary_df['cumulative_share_pct'] = summary_df['revenue_share_pct'].cumsum()

    summary_df['abc_class'] = np.select(
        [summary_df['cumulative_share_pct'] <= 80, summary_df['cumulative_share_pct'] <= 95],
        ['A', 'B'],
        default='C'
    )
    summary_df['xyz_class'] = np.select(
        [summary_df['cv'] <= 10, summary_df['cv'] <= 25],
        ['X', 'Y'],
        default='Z'
    )
    summary_df['abc_xyz_class'] = summary_df['abc_class'] + '|' + summary_df['xyz_class']
    print(f'Classified {len(summary_df):,} categories into ABC-XYZ segments')
    return summary_df


def save_outputs(classification_df):
    """Save the classification output and process log for reporting use."""
    os.makedirs(DATA_PROCESSED, exist_ok=True)
    os.makedirs(OUTPUT_LOGS, exist_ok=True)

    output_path = os.path.join(DATA_PROCESSED, 'sku_abc_xyz_classification.csv')
    log_path = os.path.join(OUTPUT_LOGS, 'log_abc_xyz_classifier.csv')

    classification_df.to_csv(output_path, index=False)
    assert os.path.exists(output_path), f'Write failed: {output_path}'

    log_df = pd.DataFrame(
        [
            {
                'run_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'rows_written': len(classification_df),
                'output_path': output_path,
            }
        ]
    )
    log_df.to_csv(log_path, index=False)
    assert os.path.exists(log_path), f'Write failed: {log_path}'

    print(f'Saved ABC-XYZ classification to {output_path}')
    print(f'Saved ABC-XYZ log to {log_path}')


def main():
    """Run ABC-XYZ segmentation end to end."""
    demand_df = load_inputs()
    classification_df = classify_abc_xyz(demand_df)
    save_outputs(classification_df)


if __name__ == '__main__':
    main()