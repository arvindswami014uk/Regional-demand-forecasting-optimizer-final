"""
feature_engineering.py
======================
Phase 2B — Feature Engineering
Produces data/processed/modeling_dataset.csv

WHY  : The LightGBM forecast model needs a single, flat, fully-
       joined feature table at week x region x category grain.
       Raw processed CSVs are at different grains and must be
       aggregated, joined, and enriched before modelling.

WHAT : Executes the full join chain specified in the project spec:
  Base  : daily_demand + sku_master  ->  week x region x category
  Join 1: event_calendar on year_week (MAX flags, MEAN weather)
  Join 2: sku_master aggregated to category level
  Join 3: warehouses (capacity_units, fixed_daily_cost per region)
  Join 4: warehouse_region_costs (ship_cost, lead_time, efficiency)
  Compute: carbon_kg_per_unit (full EEA formula)
  Lag/window features:
    lag_1_week_demand, lag_2_week_demand, lag_4_week_demand
    rolling_4wk_mean, rolling_4wk_std, demand_trend
    weeks_since_epoch, is_q4, region_demand_rank, category_velocity

MANDATORY FORECAST GRAIN: week x region x category

CRITICAL CONSTRAINT:
  Each sku_id appears only ONCE in daily_demand.
  There is NO per-SKU time series.
  All forecasting is at the aggregated grain above.

CARBON FORMULA (EEA road freight):
  distance_km   = lead_time_days x 500
  weight_tonnes = volume_m3 x 200 / 1000  (per unit)
  carbon_kg     = distance_km x weight_tonnes x 0.062
"""

import os
import logging
import datetime
import csv

import numpy as np
import pandas as pd

SCRIPT_NAME       = 'feature_engineering.py'
RANDOM_SEED       = 42
np.random.seed(RANDOM_SEED)

# Carbon emission constants — EEA road freight
KM_PER_LEAD_DAY   = 500
DENSITY_KG_PER_M3 = 200
EEA_FACTOR        = 0.062

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)

PROCESSED_DIR  = os.path.join(PROJECT_ROOT, 'data', 'processed')
DEMAND_CSV     = os.path.join(PROCESSED_DIR, 'daily_demand_clean.csv')
SKU_CSV        = os.path.join(PROCESSED_DIR, 'sku_master_clean.csv')
EVENT_CSV      = os.path.join(PROCESSED_DIR, 'event_calendar_clean.csv')
WH_CSV         = os.path.join(PROCESSED_DIR, 'warehouses_clean.csv')
LANE_CSV       = os.path.join(PROCESSED_DIR, 'warehouse_region_costs_clean.csv')

OUTPUT_CSV     = os.path.join(PROCESSED_DIR, 'modeling_dataset.csv')

LOGS_DIR       = os.path.join(PROJECT_ROOT, 'outputs', 'logs')
LOG_PATH       = os.path.join(LOGS_DIR, 'log_feature_engineering.csv')

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


def ensure_dirs():
    for d in [PROCESSED_DIR, LOGS_DIR]:
        os.makedirs(d, exist_ok=True)
    _log_step('ensure_dirs', 'OK', 'output dirs ready')


def load_raw():
    """
    WHY  : All 5 processed CSVs must be loaded before any join.
    WHAT : Loads and validates each CSV; returns dict of DataFrames.
    """
    logger.info('Loading all processed CSVs ...')

    demand = pd.read_csv(DEMAND_CSV, parse_dates=['date'])
    sku    = pd.read_csv(SKU_CSV)
    event  = pd.read_csv(EVENT_CSV)
    wh     = pd.read_csv(WH_CSV)
    lanes  = pd.read_csv(LANE_CSV)

    logger.info('  daily_demand         : %s', demand.shape)
    logger.info('  sku_master           : %s', sku.shape)
    logger.info('  event_calendar       : %s', event.shape)
    logger.info('  warehouses           : %s', wh.shape)
    logger.info('  warehouse_region_costs: %s', lanes.shape)

    # Critical column assertions
    assert 'year_week'     in demand.columns, 'year_week missing from demand'
    assert 'category'      in sku.columns,    'category missing from sku'
    assert 'year_week'     in event.columns,  'year_week missing from event'
    assert 'region'        in wh.columns,     'region missing from warehouses'
    assert 'demand_region' in lanes.columns,  'demand_region missing from lanes'
    assert 'volume_m3'     in sku.columns,    'volume_m3 missing from sku'

    _log_step('load_raw', 'OK',
              f'demand={len(demand)} sku={len(sku)} event={len(event)} '
              f'wh={len(wh)} lanes={len(lanes)}')
    return {'demand': demand, 'sku': sku, 'event': event,
            'wh': wh, 'lanes': lanes}


def build_base(data):
    """
    WHY  : The mandatory forecast grain is week x region x category.
           daily_demand has no category; sku_master provides it.
    WHAT : Joins demand + sku_master on sku_id, then aggregates
           to year_week x region x category.
    ASSUMPTION: Every sku_id in demand has a match in sku_master.
    """
    logger.info('Building base grain: week x region x category ...')

    demand = data['demand']
    sku    = data['sku']

    # Join category onto demand rows
    df = demand.merge(sku[['sku_id', 'category']], on='sku_id', how='left')
    orphans = df['category'].isna().sum()
    assert orphans == 0, f'{orphans} demand rows missing category after join'

    # Aggregate to week x region x category
    base = (
        df.groupby(['year_week', 'region', 'category'], as_index=False)
        .agg(
            total_units         =('units_ordered',           'sum'),
            avg_price_usd       =('price_usd',               'mean'),
            holiday_peak_flag   =('holiday_peak_flag',       'max'),
            prime_event_flag    =('prime_event_flag',        'max'),
            marketing_push_flag =('marketing_push_flag',     'max'),
            weather_disruption  =('weather_disruption_index','mean'),
            year                =('year',                    'first'),
            month               =('month',                   'first'),
            quarter             =('quarter',                 'first'),
            week_number         =('week_number',             'first'),
        )
    )

    # Parse week_start from ISO year-week string
    base['week_start'] = pd.to_datetime(
        base['year_week'] + '-1', format='%G-W%V-%u'
    )

    logger.info('  base shape : %s', base.shape)
    logger.info('  weeks      : %d', base['year_week'].nunique())
    logger.info('  regions    : %s', sorted(base['region'].unique()))
    logger.info('  categories : %s', sorted(base['category'].unique()))
    logger.info('  total_units: %s', f"{base['total_units'].sum():,.0f}")

    _log_step('build_base', 'OK',
              f'rows={len(base)} weeks={base["year_week"].nunique()} '
              f'total_units={base["total_units"].sum():,.0f}')
    return base


def join_event_calendar(base, event):
    """
    WHY  : Event calendar has authoritative flag values at week grain.
           We prefer event_calendar over demand-derived flags for
           any weeks where demand data may be sparse.
    WHAT : Left join on year_week; takes MAX flags, MEAN weather
           from event_calendar and uses them to OVERRIDE base flags.
    ASSUMPTION: event_calendar covers the full demand date range.
    """
    logger.info('Joining event calendar ...')

    event_agg = (
        event.groupby('year_week', as_index=False)
        .agg(
            ev_holiday_peak   =('holiday_peak_flag',       'max'),
            ev_prime_event    =('prime_event_flag',        'max'),
            ev_marketing_push =('marketing_push_flag',     'max'),
            ev_weather        =('weather_disruption_index','mean'),
        )
    )

    merged = base.merge(event_agg, on='year_week', how='left')

    # Override base flags with event_calendar values where available
    for base_col, ev_col in [
        ('holiday_peak_flag',   'ev_holiday_peak'),
        ('prime_event_flag',    'ev_prime_event'),
        ('marketing_push_flag', 'ev_marketing_push'),
        ('weather_disruption',  'ev_weather'),
    ]:
        mask = merged[ev_col].notna()
        merged.loc[mask, base_col] = merged.loc[mask, ev_col]

    # Drop the temporary ev_ columns
    merged = merged.drop(columns=[c for c in merged.columns
                                   if c.startswith('ev_')])

    unmatched = merged['holiday_peak_flag'].isna().sum()
    assert unmatched == 0, f'{unmatched} rows missing flag after event join'

    logger.info('  post-event-join shape : %s', merged.shape)
    _log_step('join_event_calendar', 'OK',
              f'rows={len(merged)} event_weeks={event_agg["year_week"].nunique()}')
    return merged


def join_sku_category_agg(base, sku):
    """
    WHY  : Category-level cost and physical attributes drive safety
           stock calculations and holding cost estimates.
    WHAT : Aggregates sku_master to category level (mean of numeric
           columns), then left-joins onto the base grain.
    """
    logger.info('Joining sku category aggregates ...')

    cat_agg = (
        sku.groupby('category', as_index=False)
        .agg(
            avg_unit_cost_usd      =('unit_cost_usd',          'mean'),
            avg_selling_price_usd  =('selling_price_usd',      'mean'),
            avg_cube_ft            =('cube_ft',                'mean'),
            avg_gross_margin_usd   =('gross_margin_usd',       'mean'),
            avg_margin_pct         =('margin_pct',             'mean'),
            avg_holding_cost_daily =('holding_cost_daily_usd', 'mean'),
            avg_stockout_penalty   =('stockout_penalty_usd',   'mean'),
            avg_volume_m3          =('volume_m3',              'mean'),
        )
    )

    merged = base.merge(cat_agg, on='category', how='left')
    missing = merged['avg_unit_cost_usd'].isna().sum()
    assert missing == 0, f'{missing} rows missing sku category agg'

    logger.info('  post-sku-agg shape : %s', merged.shape)
    _log_step('join_sku_category_agg', 'OK',
              f'rows={len(merged)} categories={cat_agg["category"].nunique()}')
    return merged


def join_warehouse_info(base, wh):
    """
    WHY  : Warehouse capacity and fixed cost are inputs to the
           cost-to-serve optimization objective.
    WHAT : Joins the HOME warehouse (same region) capacity and
           fixed daily cost onto each row.
    ASSUMPTION: Each demand region maps to exactly one home warehouse.
                WH-CENTRAL is excluded from this home-region join
                (it serves all regions as a hub — handled in lanes).
    """
    logger.info('Joining warehouse info ...')

    # Only home-region warehouses (excludes WH-CENTRAL)
    wh_home = wh[wh['region'].isin(['North','South','East','West'])].copy()
    wh_home = wh_home.rename(columns={
        'capacity_units':      'home_wh_capacity',
        'fixed_daily_cost_usd':'home_wh_fixed_cost',
        'warehouse_id':        'home_warehouse_id',
    })[['region', 'home_warehouse_id', 'home_wh_capacity', 'home_wh_fixed_cost']]

    merged = base.merge(wh_home, on='region', how='left')
    missing = merged['home_wh_capacity'].isna().sum()
    assert missing == 0, f'{missing} rows missing home warehouse info'

    logger.info('  post-wh-join shape : %s', merged.shape)
    _log_step('join_warehouse_info', 'OK',
              f'rows={len(merged)}')
    return merged


def join_lane_costs(base, lanes):
    """
    WHY  : Shipping cost and lead time from the HOME warehouse to
           each demand region are core cost-to-serve features.
    WHAT : Joins the HOME lane (where warehouse region = demand region)
           ship_cost, lead_time, distance, and efficiency score,
           then computes the full carbon_kg_per_unit.
    ASSUMPTION: Home lane = warehouse_id matches home_warehouse_id.
    """
    logger.info('Joining lane costs and computing carbon ...')

    lane_sub = lanes.rename(columns={
        'warehouse_id':        'home_warehouse_id',
        'demand_region':       'region',
        'ship_cost_per_unit':  'home_ship_cost',
        'lead_time_days':      'home_lead_time',
        'distance_km_proxy':   'home_distance_km',
        'lane_efficiency_score':'home_lane_efficiency',
    })[['home_warehouse_id', 'region', 'home_ship_cost',
         'home_lead_time', 'home_distance_km', 'home_lane_efficiency']]

    merged = base.merge(
        lane_sub,
        on=['home_warehouse_id', 'region'],
        how='left'
    )

    missing = merged['home_ship_cost'].isna().sum()
    assert missing == 0, f'{missing} rows missing lane cost after join'

    # ── Full EEA carbon calculation ──────────────────────────────
    # distance_km   = home_lead_time x KM_PER_LEAD_DAY
    # weight_tonnes = avg_volume_m3 x DENSITY_KG_PER_M3 / 1000
    # carbon_kg     = distance_km x weight_tonnes x EEA_FACTOR
    merged['carbon_distance_km']  = merged['home_lead_time'] * KM_PER_LEAD_DAY
    merged['carbon_weight_tonnes'] = (
        merged['avg_volume_m3'] * DENSITY_KG_PER_M3 / 1000
    )
    merged['carbon_kg_per_unit'] = (
        merged['carbon_distance_km']
        * merged['carbon_weight_tonnes']
        * EEA_FACTOR
    ).round(6)

    logger.info('  carbon range : %.4f – %.4f',
                merged['carbon_kg_per_unit'].min(),
                merged['carbon_kg_per_unit'].max())
    logger.info('  post-lane-join shape : %s', merged.shape)
    _log_step('join_lane_costs', 'OK',
              f'rows={len(merged)} '
              f'carbon={merged["carbon_kg_per_unit"].min():.4f}-'
              f'{merged["carbon_kg_per_unit"].max():.4f}')
    return merged


def add_lag_features(base):
    """
    WHY  : Lag features are the most powerful predictors in demand
           forecasting. What sold last week, 2 weeks ago, and 4 weeks
           ago provides the model with autocorrelation signal.
    WHAT : For each region x category series (sorted by week_start),
           computes lag-1, lag-2, lag-4, rolling mean/std (4-week),
           and a simple demand trend (lag1 - lag4).
    WATCH OUT: Lag features produce NaN for the first N rows of each
               series. These rows are kept — the model handles NaN
               via LightGBM's native missing-value support.
    """
    logger.info('Computing lag and window features ...')

    base = base.sort_values(['region', 'category', 'week_start']).copy()

    grp = base.groupby(['region', 'category'])['total_units']

    base['lag_1_week_demand'] = grp.shift(1)
    base['lag_2_week_demand'] = grp.shift(2)
    base['lag_4_week_demand'] = grp.shift(4)

    base['rolling_4wk_mean'] = (
        grp.transform(lambda x: x.shift(1).rolling(4, min_periods=1).mean())
    )
    base['rolling_4wk_std'] = (
        grp.transform(lambda x: x.shift(1).rolling(4, min_periods=1).std())
    )

    # Demand trend: change from 4 weeks ago to last week
    # Positive = accelerating demand; negative = decelerating
    base['demand_trend'] = base['lag_1_week_demand'] - base['lag_4_week_demand']

    lag_null_pct = base['lag_1_week_demand'].isna().mean() * 100
    logger.info('  lag_1 null pct : %.1f%% (expected for first few weeks)',
                lag_null_pct)

    _log_step('add_lag_features', 'OK',
              f'lag_null_pct={lag_null_pct:.1f}%')
    return base


def add_calendar_features(base):
    """
    WHY  : Calendar features encode seasonality signals that the
           model cannot derive from lags alone.
    WHAT : Adds weeks_since_epoch, is_q4, region_demand_rank,
           category_velocity.
    """
    logger.info('Adding calendar and context features ...')

    # weeks_since_epoch: ordinal week index for trend modelling
    epoch = base['week_start'].min()
    base['weeks_since_epoch'] = (
        (base['week_start'] - epoch).dt.days // 7
    ).astype(int)

    # is_q4: binary flag for October-December holiday season
    base['is_q4'] = (base['quarter'] == 4).astype(int)

    # region_demand_rank: rank of each region by total demand that week
    # WHY: tells the model which region is hottest each week
    week_region_totals = (
        base.groupby(['year_week', 'region'])['total_units']
        .transform('sum')
    )
    base['region_demand_rank'] = (
        base.groupby('year_week')['total_units']
        .rank(method='dense', ascending=False)
        .astype(int)
    )

    # category_velocity: each category's share of total units that week
    # WHY: fast-moving categories need tighter replenishment cycles
    week_total = base.groupby('year_week')['total_units'].transform('sum')
    base['category_velocity'] = (base['total_units'] / week_total).round(6)

    logger.info('  weeks_since_epoch range : %d – %d',
                base['weeks_since_epoch'].min(),
                base['weeks_since_epoch'].max())
    logger.info('  is_q4 rows : %d / %d',
                base['is_q4'].sum(), len(base))

    _log_step('add_calendar_features', 'OK',
              f'weeks_since_epoch_max={base["weeks_since_epoch"].max()}')
    return base


def validate_and_save(df):
    """
    WHY  : The modeling dataset must be validated before the model
           ingests it. Silent data issues here corrupt all forecasts.
    WHAT : Asserts required columns, checks for unexpected nulls in
           non-lag columns, prints summary, saves CSV.
    """
    logger.info('Validating and saving modeling dataset ...')

    required_cols = [
        # Grain keys
        'year_week', 'region', 'category', 'week_start',
        # Target
        'total_units',
        # Demand features
        'avg_price_usd', 'holiday_peak_flag', 'prime_event_flag',
        'marketing_push_flag', 'weather_disruption',
        'year', 'month', 'quarter', 'week_number',
        # SKU category features
        'avg_unit_cost_usd', 'avg_selling_price_usd', 'avg_cube_ft',
        'avg_gross_margin_usd', 'avg_margin_pct',
        'avg_holding_cost_daily', 'avg_stockout_penalty', 'avg_volume_m3',
        # Warehouse features
        'home_warehouse_id', 'home_wh_capacity', 'home_wh_fixed_cost',
        # Lane features
        'home_ship_cost', 'home_lead_time', 'home_distance_km',
        'home_lane_efficiency', 'carbon_kg_per_unit',
        # Lag features (NaN allowed for early rows)
        'lag_1_week_demand', 'lag_2_week_demand', 'lag_4_week_demand',
        'rolling_4wk_mean', 'rolling_4wk_std', 'demand_trend',
        # Calendar features
        'weeks_since_epoch', 'is_q4',
        'region_demand_rank', 'category_velocity',
    ]

    missing_cols = [c for c in required_cols if c not in df.columns]
    assert len(missing_cols) == 0, f'Missing columns: {missing_cols}'

    # Non-lag columns must have zero nulls
    non_lag_cols = [c for c in required_cols
                    if 'lag' not in c and 'rolling' not in c
                    and 'trend' not in c]
    for col in non_lag_cols:
        n_null = df[col].isna().sum()
        assert n_null == 0, f'Unexpected nulls in {col}: {n_null}'

    # Shape checks
    assert len(df) > 0,        'Modeling dataset is empty'
    assert df['total_units'].min() >= 0, 'Negative units found'
    assert df['carbon_kg_per_unit'].min() > 0, 'Zero/negative carbon found'

    # Save
    df.to_csv(OUTPUT_CSV, index=False)

    # Verify write
    check = pd.read_csv(OUTPUT_CSV)
    assert len(check) == len(df), 'Row count mismatch after save'
    assert len(check.columns) == len(df.columns), 'Column count mismatch'

    logger.info('  modeling_dataset.csv saved')
    logger.info('  shape                : %s', df.shape)
    logger.info('  total_units range    : %d – %d',
                df['total_units'].min(), df['total_units'].max())
    logger.info('  carbon range         : %.4f – %.4f',
                df['carbon_kg_per_unit'].min(), df['carbon_kg_per_unit'].max())
    logger.info('  lag_1 null rows      : %d',
                df['lag_1_week_demand'].isna().sum())

    _log_step('validate_and_save', 'OK',
              f'shape={df.shape} output={OUTPUT_CSV}')
    return df


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
    data = load_raw()

    # ── Join chain ───────────────────────────────────────────────
    base = build_base(data)
    base = join_event_calendar(base, data['event'])
    base = join_sku_category_agg(base, data['sku'])
    base = join_warehouse_info(base, data['wh'])
    base = join_lane_costs(base, data['lanes'])

    # ── Feature engineering ──────────────────────────────────────
    base = add_lag_features(base)
    base = add_calendar_features(base)

    # ── Validate and save ────────────────────────────────────────
    df = validate_and_save(base)
    write_log()

    print()
    print('=' * 60)
    print(f'  {SCRIPT_NAME}  —  COMPLETE')
    print('=' * 60)
    print(f'  Output rows    : {len(df):,}')
    print(f'  Output columns : {len(df.columns)}')
    print(f'  Output file    : {OUTPUT_CSV}')
    print(f'  Log file       : {LOG_PATH}')
    print()
    print('  Column groups:')
    print(f'    Grain keys       : year_week, region, category, week_start')
    print(f'    Target           : total_units')
    print(f'    Demand features  : 9')
    print(f'    SKU features     : 8')
    print(f'    Warehouse feat.  : 3')
    print(f'    Lane features    : 5 + carbon')
    print(f'    Lag features     : 6')
    print(f'    Calendar feat.   : 4')
    print('=' * 60)


if __name__ == '__main__':
    main()
