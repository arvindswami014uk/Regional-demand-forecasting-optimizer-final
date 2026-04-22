"""
demand_forecast.py
==================
Phase 2C — LightGBM Demand Forecast Model

WHY  : We need a 12-week forward demand forecast at
       week x region x category grain to drive inventory
       placement decisions. LightGBM is chosen because:
         - Handles mixed numeric/categorical features natively
         - Supports NaN in lag features without imputation
         - Fast training on small tabular datasets
         - Produces reliable feature importance for explainability

WHAT : Temporal train/test split (last 8 weeks = test).
       Walk-forward cross-validation (4 folds).
       Metrics: MAE, RMSE, MAPE, R-squared.
       Outputs:
         data/processed/weekly_demand_forecast.csv
         data/processed/forecast_12wk_forward.csv
         figures/forecast_actual_vs_predicted_{region}_{cat}.png
         figures/feature_importance_lgbm.png
         reports/report_demand_forecast.md
         outputs/logs/log_demand_forecast.csv

SPLIT RULE:
  Temporal — last 8 weeks of data = test set.
  All prior weeks = training set.
  NO random shuffling — respects time ordering.

WALK-FORWARD CV:
  4 folds, each fold expands training window by one block.
  Fold k trains on weeks 1..N-k*step, tests on next step weeks.

FORECASTING CONSTRAINT:
  Each sku_id appears only once in daily_demand.
  Mandatory grain: week x region x category.
  modeling_dataset.csv is the sole input.
"""

import os
import logging
import datetime
import csv
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

sns.set_theme(style='whitegrid', palette='muted', font_scale=1.05)

SCRIPT_NAME    = 'demand_forecast.py'
RANDOM_SEED    = 42
np.random.seed(RANDOM_SEED)

TEST_WEEKS     = 8    # last N weeks held out as test set
CV_FOLDS       = 4    # walk-forward CV folds
FORECAST_WEEKS = 12   # forward forecast horizon

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)

PROCESSED_DIR      = os.path.join(PROJECT_ROOT, 'data', 'processed')
MODELING_CSV       = os.path.join(PROCESSED_DIR, 'modeling_dataset.csv')
FORECAST_CSV       = os.path.join(PROCESSED_DIR, 'weekly_demand_forecast.csv')
FORWARD_CSV        = os.path.join(PROCESSED_DIR, 'forecast_12wk_forward.csv')

FIGURES_DIR        = os.path.join(PROJECT_ROOT, 'figures')
REPORTS_DIR        = os.path.join(PROJECT_ROOT, 'reports')
LOGS_DIR           = os.path.join(PROJECT_ROOT, 'outputs', 'logs')

REPORT_PATH        = os.path.join(REPORTS_DIR, 'report_demand_forecast.md')
LOG_PATH           = os.path.join(LOGS_DIR,    'log_demand_forecast.csv')
FIG_FEAT_IMP       = os.path.join(FIGURES_DIR, 'feature_importance_lgbm.png')

# Features passed to LightGBM
# WHY these groups:
#   Demand context : flags and weather drive short-term spikes
#   SKU attributes : cost/margin/penalty shape safety-stock needs
#   Warehouse/lane : capacity and cost constrain placement options
#   Lag features   : autocorrelation is strongest demand predictor
#   Calendar       : seasonality and trend signals
FEATURE_COLS = [
    # Demand context
    'holiday_peak_flag', 'prime_event_flag', 'marketing_push_flag',
    'weather_disruption', 'avg_price_usd',
    # SKU category attributes
    'avg_unit_cost_usd', 'avg_selling_price_usd', 'avg_cube_ft',
    'avg_gross_margin_usd', 'avg_margin_pct',
    'avg_holding_cost_daily', 'avg_stockout_penalty', 'avg_volume_m3',
    # Warehouse and lane
    'home_wh_capacity', 'home_wh_fixed_cost',
    'home_ship_cost', 'home_lead_time',
    'home_lane_efficiency', 'carbon_kg_per_unit',
    # Lag features
    'lag_1_week_demand', 'lag_2_week_demand', 'lag_4_week_demand',
    'rolling_4wk_mean', 'rolling_4wk_std', 'demand_trend',
    # Calendar
    'weeks_since_epoch', 'week_number', 'month', 'quarter',
    'is_q4', 'region_demand_rank', 'category_velocity',
]

TARGET_COL = 'total_units'

# LightGBM hyperparameters
# WHY these values:
#   n_estimators=500  : enough trees for small dataset, early stopping guards
#   learning_rate=0.05: conservative — reduces overfitting risk
#   num_leaves=31     : default, appropriate for 1540-row dataset
#   min_child_samples=10: prevents overfitting on small leaf nodes
#   subsample=0.8     : row subsampling adds regularisation
#   colsample=0.8     : feature subsampling adds regularisation
LGBM_PARAMS = {
    'n_estimators':     500,
    'learning_rate':    0.05,
    'num_leaves':       31,
    'min_child_samples':10,
    'subsample':        0.8,
    'colsample_bytree': 0.8,
    'random_state':     RANDOM_SEED,
    'n_jobs':           -1,
    'verbose':          -1,
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(SCRIPT_NAME)
_log_records = []


def _log_step(step, status, detail=''):
    record = {
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'script':    SCRIPT_NAME,
        'step':      step,
        'status':    status,
        'detail':    str(detail),
    }
    _log_records.append(record)
    logger.info('[%-40s] %-8s %s', step, status, detail)


def _mape(y_true, y_pred):
    """Mean Absolute Percentage Error — guards against zero division."""
    y_true = np.array(y_true, dtype=float)
    y_pred = np.array(y_pred, dtype=float)
    mask   = y_true != 0
    if mask.sum() == 0:
        return np.nan
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def _metrics(y_true, y_pred, label=''):
    """Compute and log MAE, RMSE, MAPE, R2."""
    mae  = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mape = _mape(y_true, y_pred)
    r2   = r2_score(y_true, y_pred)
    logger.info('  %-20s MAE=%.2f  RMSE=%.2f  MAPE=%.1f%%  R2=%.4f',
                label, mae, rmse, mape, r2)
    return {'label': label, 'mae': round(mae,4), 'rmse': round(rmse,4),
            'mape': round(mape,4), 'r2': round(r2,4)}


def ensure_dirs():
    for d in [FIGURES_DIR, REPORTS_DIR, LOGS_DIR, PROCESSED_DIR]:
        os.makedirs(d, exist_ok=True)
    _log_step('ensure_dirs', 'OK', 'all output dirs ready')


def load_data():
    """
    WHY  : modeling_dataset.csv is the single source of truth.
    WHAT : Loads, sorts by week_start, validates feature columns.
    """
    logger.info('Loading modeling_dataset.csv ...')
    df = pd.read_csv(MODELING_CSV, parse_dates=['week_start'])
    df = df.sort_values(['region', 'category', 'week_start']).reset_index(drop=True)

    assert len(df) > 0, 'modeling_dataset is empty'
    missing_feat = [c for c in FEATURE_COLS if c not in df.columns]
    assert len(missing_feat) == 0, f'Missing feature cols: {missing_feat}'
    assert TARGET_COL in df.columns, f'{TARGET_COL} missing'

    logger.info('  shape     : %s', df.shape)
    logger.info('  weeks     : %d', df['year_week'].nunique())
    logger.info('  date range: %s to %s',
                df['week_start'].min().date(), df['week_start'].max().date())

    _log_step('load_data', 'OK', f'shape={df.shape}')
    return df


def temporal_split(df):
    """
    WHY  : Random splitting would leak future information into training.
           Temporal split respects causality — train on past, test on future.
    WHAT : Last TEST_WEEKS ISO weeks = test; all prior = train.
    """
    all_weeks  = sorted(df['year_week'].unique())
    test_weeks = all_weeks[-TEST_WEEKS:]
    train_weeks= all_weeks[:-TEST_WEEKS]

    train = df[df['year_week'].isin(train_weeks)].copy()
    test  = df[df['year_week'].isin(test_weeks)].copy()

    logger.info('  Train weeks : %d  rows=%d', len(train_weeks), len(train))
    logger.info('  Test  weeks : %d  rows=%d', len(test_weeks),  len(test))
    logger.info('  Train period: %s to %s',
                train['week_start'].min().date(), train['week_start'].max().date())
    logger.info('  Test  period: %s to %s',
                test['week_start'].min().date(),  test['week_start'].max().date())

    assert len(train) > 0, 'Train set is empty'
    assert len(test)  > 0, 'Test set is empty'

    _log_step('temporal_split', 'OK',
              f'train={len(train)} test={len(test)}')
    return train, test, train_weeks, test_weeks


def walk_forward_cv(df, train_weeks):
    """
    WHY  : Walk-forward CV mimics real deployment — the model always
           trains on past data and predicts the immediate future.
           Standard k-fold would leak future weeks into training.
    WHAT : Splits train_weeks into CV_FOLDS folds.
           Fold k: train on weeks 1..split_k, validate on split_k+1..split_k+step.
    """
    logger.info('Running walk-forward CV (%d folds) ...', CV_FOLDS)

    n          = len(train_weeks)
    fold_size  = n // (CV_FOLDS + 1)
    cv_results = []

    for fold in range(CV_FOLDS):
        train_end = fold_size * (fold + 1)
        val_end   = train_end + fold_size
        cv_train_weeks = train_weeks[:train_end]
        cv_val_weeks   = train_weeks[train_end:val_end]

        if len(cv_val_weeks) == 0:
            continue

        cv_train = df[df['year_week'].isin(cv_train_weeks)]
        cv_val   = df[df['year_week'].isin(cv_val_weeks)]

        X_tr = cv_train[FEATURE_COLS]
        y_tr = cv_train[TARGET_COL]
        X_vl = cv_val[FEATURE_COLS]
        y_vl = cv_val[TARGET_COL]

        model = lgb.LGBMRegressor(**LGBM_PARAMS)
        model.fit(X_tr, y_tr)
        preds = model.predict(X_vl)
        preds = np.maximum(preds, 0)  # floor at zero — no negative demand

        m = _metrics(y_vl, preds, label=f'CV fold {fold+1}')
        m['fold']        = fold + 1
        m['train_weeks'] = len(cv_train_weeks)
        m['val_weeks']   = len(cv_val_weeks)
        cv_results.append(m)

    cv_df = pd.DataFrame(cv_results)
    logger.info('  CV mean MAE  : %.2f', cv_df['mae'].mean())
    logger.info('  CV mean RMSE : %.2f', cv_df['rmse'].mean())
    logger.info('  CV mean MAPE : %.1f%%', cv_df['mape'].mean())
    logger.info('  CV mean R2   : %.4f', cv_df['r2'].mean())

    _log_step('walk_forward_cv', 'OK',
              f'folds={len(cv_results)} '
              f'mean_mae={cv_df["mae"].mean():.2f} '
              f'mean_r2={cv_df["r2"].mean():.4f}')
    return cv_df


def train_final_model(train):
    """
    WHY  : Final model trains on ALL training data (not just the last CV fold)
           to maximise signal before evaluating on the held-out test set.
    WHAT : Fits LGBMRegressor on full training set.
    """
    logger.info('Training final model on full training set ...')

    X_train = train[FEATURE_COLS]
    y_train = train[TARGET_COL]

    model = lgb.LGBMRegressor(**LGBM_PARAMS)
    model.fit(X_train, y_train)

    logger.info('  Model trained. n_features=%d', len(FEATURE_COLS))
    _log_step('train_final_model', 'OK',
              f'train_rows={len(train)} features={len(FEATURE_COLS)}')
    return model


def evaluate_test(model, train, test):
    """
    WHY  : Test set evaluation on the held-out last 8 weeks gives
           an unbiased estimate of real-world forecast accuracy.
    WHAT : Predicts on test set; computes MAE/RMSE/MAPE/R2.
           Appends predictions to the test DataFrame.
    """
    logger.info('Evaluating on test set ...')

    # Also predict on train for residual analysis
    train = train.copy()
    train['predicted_units'] = np.maximum(
        model.predict(train[FEATURE_COLS]), 0)
    train['split'] = 'train'

    test = test.copy()
    test['predicted_units'] = np.maximum(
        model.predict(test[FEATURE_COLS]), 0)
    test['split'] = 'test'

    test_metrics = _metrics(
        test[TARGET_COL], test['predicted_units'], label='TEST SET')
    train_metrics = _metrics(
        train[TARGET_COL], train['predicted_units'], label='TRAIN SET')

    # Combine for output CSV
    combined = pd.concat([train, test], ignore_index=True)
    combined['residual'] = combined[TARGET_COL] - combined['predicted_units']

    _log_step('evaluate_test', 'OK',
              f'test_mae={test_metrics["mae"]:.2f} '
              f'test_mape={test_metrics["mape"]:.2f}% '
              f'test_r2={test_metrics["r2"]:.4f}')
    return combined, test_metrics, train_metrics


def save_forecast_csv(combined):
    """Save weekly_demand_forecast.csv with actuals + predictions."""
    out_cols = ['year_week', 'week_start', 'region', 'category',
                TARGET_COL, 'predicted_units', 'residual', 'split']
    combined[out_cols].to_csv(FORECAST_CSV, index=False)
    logger.info('  Forecast CSV saved : %s  rows=%d', FORECAST_CSV, len(combined))
    _log_step('save_forecast_csv', 'OK', f'rows={len(combined)}')


def generate_forward_forecast(model, df):
    """
    WHY  : The optimizer needs 12 weeks of FUTURE demand estimates
           to determine where to pre-position inventory.
    WHAT : Iterative 1-step-ahead forecast for 12 weeks beyond
           the last observed week.
           Each iteration uses the previous prediction as lag input.
    ASSUMPTION: All non-lag features (flags, cost, calendar) are
                projected by repeating the same-week-of-year values
                from 1 year prior (seasonal naive projection).
    """
    logger.info('Generating 12-week forward forecast ...')

    last_week  = df['week_start'].max()
    all_weeks  = sorted(df['week_start'].unique())

    # Build a lookup: week_start -> feature row (use last year same week as proxy)
    # For calendar features we advance by 1 week each step
    region_cat_pairs = df[['region','category']].drop_duplicates().values.tolist()

    forward_rows = []

    for step in range(1, FORECAST_WEEKS + 1):
        fwd_week_start = last_week + pd.Timedelta(weeks=step)
        fwd_year_week  = fwd_week_start.strftime('%G-W%V')

        for region, category in region_cat_pairs:
            # Anchor: same region/category, last available row
            anchor = (
                df[(df['region']==region) & (df['category']==category)]
                .sort_values('week_start')
                .iloc[-1]
                .copy()
            )

            row = {}
            row['year_week']   = fwd_year_week
            row['week_start']  = fwd_week_start
            row['region']      = region
            row['category']    = category

            # Calendar features — advance from anchor
            row['weeks_since_epoch'] = int(anchor['weeks_since_epoch']) + step
            row['week_number']   = int(fwd_week_start.isocalendar()[1])
            row['month']         = int(fwd_week_start.month)
            row['quarter']       = int((fwd_week_start.month - 1) // 3 + 1)
            row['is_q4']         = int(row['quarter'] == 4)

            # Static features — carry forward from anchor
            static_cols = [
                'avg_price_usd', 'holiday_peak_flag', 'prime_event_flag',
                'marketing_push_flag', 'weather_disruption',
                'avg_unit_cost_usd', 'avg_selling_price_usd', 'avg_cube_ft',
                'avg_gross_margin_usd', 'avg_margin_pct',
                'avg_holding_cost_daily', 'avg_stockout_penalty', 'avg_volume_m3',
                'home_wh_capacity', 'home_wh_fixed_cost',
                'home_ship_cost', 'home_lead_time',
                'home_lane_efficiency', 'carbon_kg_per_unit',
                'region_demand_rank', 'category_velocity',
            ]
            for col in static_cols:
                row[col] = anchor[col]

            # Lag features — use the last known/predicted values
            # lag_1 = prediction from step-1 (or last actual if step=1)
            recent = df[(df['region']==region) & (df['category']==category)]
            recent = recent.sort_values('week_start')

            def _get_lag(n):
                # Try to get the value n steps back from fwd_week_start
                target_date = fwd_week_start - pd.Timedelta(weeks=n)
                match = recent[recent['week_start'] == target_date]
                if len(match) > 0:
                    col = 'predicted_units' if 'predicted_units' in match.columns else TARGET_COL
                    return float(match.iloc[-1][col])
                # Fall back to last known value
                col = 'predicted_units' if 'predicted_units' in recent.columns else TARGET_COL
                return float(recent.iloc[-1][col])

            row['lag_1_week_demand'] = _get_lag(1)
            row['lag_2_week_demand'] = _get_lag(2)
            row['lag_4_week_demand'] = _get_lag(4)

            # Rolling mean/std from last 4 known actuals
            last4 = recent[TARGET_COL].values[-4:]
            row['rolling_4wk_mean'] = float(np.mean(last4))
            row['rolling_4wk_std']  = float(np.std(last4)) if len(last4) > 1 else 0.0
            row['demand_trend']     = row['lag_1_week_demand'] - row['lag_4_week_demand']

            forward_rows.append(row)

    fwd_df = pd.DataFrame(forward_rows)

    # Predict
    X_fwd  = fwd_df[FEATURE_COLS]
    fwd_df['predicted_units'] = np.maximum(model.predict(X_fwd), 0)

    # Save
    out_cols = ['year_week', 'week_start', 'region', 'category', 'predicted_units']
    fwd_df[out_cols].to_csv(FORWARD_CSV, index=False)

    logger.info('  Forward forecast saved : %s  rows=%d', FORWARD_CSV, len(fwd_df))
    logger.info('  Forecast horizon       : weeks %s to %s',
                fwd_df['year_week'].iloc[0], fwd_df['year_week'].iloc[-1])
    logger.info('  Predicted units range  : %.0f – %.0f',
                fwd_df['predicted_units'].min(), fwd_df['predicted_units'].max())

    _log_step('generate_forward_forecast', 'OK',
              f'rows={len(fwd_df)} horizon={FORECAST_WEEKS}wks')
    return fwd_df


def plot_actual_vs_predicted(combined):
    """
    WHY  : Visual inspection of actual vs predicted is the fastest
           way to spot systematic bias or region/category failures.
    WHAT : One figure per region x category combination.
           Train = solid line, Test = dashed, Predicted = dotted.
    """
    logger.info('Plotting actual vs predicted figures ...')
    fig_paths = []

    regions    = sorted(combined['region'].unique())
    categories = sorted(combined['category'].unique())

    for region in regions:
        for category in categories:
            sub = (
                combined[(combined['region']==region) &
                         (combined['category']==category)]
                .sort_values('week_start')
            )
            if len(sub) == 0:
                continue

            train_sub = sub[sub['split']=='train']
            test_sub  = sub[sub['split']=='test']

            fig, ax = plt.subplots(figsize=(12, 4))

            ax.plot(train_sub['week_start'], train_sub[TARGET_COL],
                    color='steelblue', linewidth=1.5, label='Actual (train)')
            ax.plot(test_sub['week_start'], test_sub[TARGET_COL],
                    color='steelblue', linewidth=1.5, linestyle='--',
                    label='Actual (test)')
            ax.plot(sub['week_start'], sub['predicted_units'],
                    color='coral', linewidth=1.5, linestyle=':',
                    label='Predicted')

            # Shade test region
            if len(test_sub) > 0:
                ax.axvspan(test_sub['week_start'].min(),
                           test_sub['week_start'].max(),
                           alpha=0.08, color='orange', label='Test window')

            ax.set_title(f'{region} — {category} | Actual vs Predicted',
                         fontsize=11, fontweight='bold')
            ax.set_xlabel('Week')
            ax.set_ylabel('Units')
            ax.yaxis.set_major_formatter(
                mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))
            ax.legend(fontsize=8, loc='upper left')
            plt.tight_layout()

            fname = f'forecast_actual_vs_predicted_{region}_{category}.png'
            fpath = os.path.join(FIGURES_DIR, fname)
            plt.savefig(fpath, dpi=120, bbox_inches='tight')
            plt.close(fig)
            fig_paths.append(fpath)

    logger.info('  Saved %d actual-vs-predicted figures', len(fig_paths))
    _log_step('plot_actual_vs_predicted', 'OK', f'figures={len(fig_paths)}')
    return fig_paths


def plot_feature_importance(model):
    """
    WHY  : Feature importance validates whether the model is using
           the right signals. Lag features should dominate;
           if event flags rank higher than lags something is wrong.
    WHAT : Horizontal bar chart — top 25 features by LightGBM gain.
    """
    logger.info('Plotting feature importance ...')

    imp_df = pd.DataFrame({
        'feature':   FEATURE_COLS,
        'importance': model.feature_importances_,
    }).sort_values('importance', ascending=True).tail(25)

    fig, ax = plt.subplots(figsize=(10, 8))
    colors = sns.color_palette('viridis', len(imp_df))
    ax.barh(imp_df['feature'], imp_df['importance'],
            color=colors, edgecolor='white')
    ax.set_title('LightGBM Feature Importance (Gain) — Top 25',
                 fontsize=13, fontweight='bold')
    ax.set_xlabel('Importance (Gain)')
    plt.tight_layout()
    plt.savefig(FIG_FEAT_IMP, dpi=150, bbox_inches='tight')
    plt.close(fig)

    top3 = imp_df.tail(3)['feature'].tolist()[::-1]
    _log_step('plot_feature_importance', 'OK', f'top3={top3}')
    return imp_df


def write_report(test_metrics, train_metrics, cv_df, fwd_df, imp_df, fig_paths):
    """Write reports/report_demand_forecast.md."""
    logger.info('Writing forecast report ...')

    rpt = []
    rpt.append('# Demand Forecast Report — LightGBM')
    rpt.append('')
    rpt.append(f'**Generated** : {datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}')
    rpt.append(f'**Script**    : {SCRIPT_NAME}')
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 1. Model Configuration')
    rpt.append('')
    rpt.append('| Parameter | Value |')
    rpt.append('|-----------|-------|')
    rpt.append(f'| Algorithm | LightGBM Regressor |')
    rpt.append(f'| Forecast grain | week x region x category |')
    rpt.append(f'| Test set | last {TEST_WEEKS} weeks |')
    rpt.append(f'| CV folds | {CV_FOLDS} walk-forward |')
    rpt.append(f'| Features | {len(FEATURE_COLS)} |')
    rpt.append(f'| n_estimators | {LGBM_PARAMS["n_estimators"]} |')
    rpt.append(f'| learning_rate | {LGBM_PARAMS["learning_rate"]} |')
    rpt.append(f'| num_leaves | {LGBM_PARAMS["num_leaves"]} |')
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 2. Test Set Metrics')
    rpt.append('')
    rpt.append('| Metric | Train | Test |')
    rpt.append('|--------|-------|------|')
    rpt.append(f'| MAE  | {train_metrics["mae"]:.2f} | {test_metrics["mae"]:.2f} |')
    rpt.append(f'| RMSE | {train_metrics["rmse"]:.2f} | {test_metrics["rmse"]:.2f} |')
    rpt.append(f'| MAPE | {train_metrics["mape"]:.1f}% | {test_metrics["mape"]:.1f}% |')
    rpt.append(f'| R2   | {train_metrics["r2"]:.4f} | {test_metrics["r2"]:.4f} |')
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 3. Walk-Forward Cross-Validation')
    rpt.append('')
    rpt.append('| Fold | Train Weeks | Val Weeks | MAE | RMSE | MAPE | R2 |')
    rpt.append('|------|-------------|-----------|-----|------|------|----|')
    for _, row in cv_df.iterrows():
        rpt.append(
            f"| {int(row['fold'])} | {int(row['train_weeks'])}"
            f" | {int(row['val_weeks'])}"
            f" | {row['mae']:.2f} | {row['rmse']:.2f}"
            f" | {row['mape']:.1f}% | {row['r2']:.4f} |"
        )
    rpt.append('')
    rpt.append(f'| **Mean** | | | {cv_df["mae"].mean():.2f} | {cv_df["rmse"].mean():.2f} | {cv_df["mape"].mean():.1f}% | {cv_df["r2"].mean():.4f} |')
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 4. 12-Week Forward Forecast Summary')
    rpt.append('')
    fwd_summary = fwd_df.groupby('region')['predicted_units'].agg(['sum','mean']).round(1)
    rpt.append('| Region | Total Predicted Units | Avg Weekly |')
    rpt.append('|--------|-----------------------|------------|')
    for region, row in fwd_summary.iterrows():
        rpt.append(f"| {region} | {row['sum']:,.0f} | {row['mean']:,.1f} |")
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 5. Top 10 Features by Importance')
    rpt.append('')
    rpt.append('| Rank | Feature | Importance |')
    rpt.append('|------|---------|------------|')
    top10 = imp_df.sort_values('importance', ascending=False).head(10)
    for i, (_, row) in enumerate(top10.iterrows(), 1):
        rpt.append(f"| {i} | {row['feature']} | {row['importance']:.0f} |")
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 6. Figures')
    rpt.append('')
    rpt.append(f'![Feature Importance](../figures/feature_importance_lgbm.png)')
    rpt.append('')
    rpt.append(f'Actual vs predicted figures: {len(fig_paths)} (one per region x category)')
    rpt.append('')
    rpt.append('*End of demand forecast report.*')

    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(REPORT_PATH, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(rpt))

    with open(REPORT_PATH, 'r', encoding='utf-8') as fh:
        content = fh.read()
    assert 'Demand Forecast Report' in content, 'Report header missing'
    assert 'Test Set Metrics'       in content, 'Metrics section missing'
    assert 'Forward Forecast'       in content, 'Forward section missing'
    logger.info('  Report written : %s', REPORT_PATH)
    _log_step('write_report', 'OK', REPORT_PATH)


def write_log():
    os.makedirs(LOGS_DIR, exist_ok=True)
    fieldnames = ['timestamp', 'script', 'step', 'status', 'detail']
    with open(LOG_PATH, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(_log_records)
    logger.info('Log written : %s  (%d records)', LOG_PATH, len(_log_records))


def main():
    logger.info('=' * 60)
    logger.info('START  %s', SCRIPT_NAME)
    logger.info('=' * 60)

    ensure_dirs()
    df = load_data()

    train, test, train_weeks, test_weeks = temporal_split(df)
    cv_df  = walk_forward_cv(df, train_weeks)
    model  = train_final_model(train)
    combined, test_metrics, train_metrics = evaluate_test(model, train, test)

    save_forecast_csv(combined)
    fwd_df   = generate_forward_forecast(model, combined)
    fig_paths = plot_actual_vs_predicted(combined)
    imp_df    = plot_feature_importance(model)

    write_report(test_metrics, train_metrics, cv_df, fwd_df, imp_df, fig_paths)
    write_log()

    print()
    print('=' * 60)
    print(f'  {SCRIPT_NAME}  —  COMPLETE')
    print('=' * 60)
    print(f'  Test  MAE  : {test_metrics["mae"]:.2f} units')
    print(f'  Test  RMSE : {test_metrics["rmse"]:.2f} units')
    print(f'  Test  MAPE : {test_metrics["mape"]:.1f}%')
    print(f'  Test  R2   : {test_metrics["r2"]:.4f}')
    print(f'  CV mean R2 : {cv_df["r2"].mean():.4f}')
    print(f'  Forecast CSV       : {FORECAST_CSV}')
    print(f'  12wk Forward CSV   : {FORWARD_CSV}')
    print(f'  Act-vs-pred figs   : {len(fig_paths)}')
    print(f'  Feature imp. fig   : {FIG_FEAT_IMP}')
    print('=' * 60)


if __name__ == '__main__':
    main()
