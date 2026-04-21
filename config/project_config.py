# =============================================================================
# config/project_config.py
# =============================================================================
# PROJECT  : Regional Demand Forecasting and Inventory Placement Optimizer
# DOMAIN   : Supply Chain Analytics | Fulfillment Network Planning
# INSPIRED : Amazon AI-led fulfillment network planning operations
#
# PURPOSE:
#   Single source of truth for the entire pipeline.
#   All paths, filenames, business constants, and validation thresholds
#   are declared here. No other module should hardcode any of these values.
#
# USAGE:
#   from config.project_config import PATHS, RAW_FILENAMES, CANONICAL_NETWORK
#
# MAINTENANCE:
#   If a raw file is renamed  → update RAW_FILENAMES only.
#   If a cost assumption changes → update COST_PARAMS only.
#   If the project moves servers → update BASE_DIR only.
# =============================================================================

import os

# =============================================================================
# BASE DIRECTORY
# =============================================================================
# Declared as an absolute path so the config is portable across machines.
# In Colab this resolves to /content/<repo-name>.
# On a local machine, replace with the absolute path to the cloned repo.
# =============================================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# =============================================================================
# PATH REGISTRY
# =============================================================================
# All directory paths used by the pipeline are derived from BASE_DIR.
# Modules import PATHS['processed'] rather than constructing paths manually.
# =============================================================================

PATHS = {
    'raw':       os.path.join(BASE_DIR, 'data', 'raw'),
    'interim':   os.path.join(BASE_DIR, 'data', 'interim'),
    'processed': os.path.join(BASE_DIR, 'data', 'processed'),
    'logs':      os.path.join(BASE_DIR, 'outputs', 'logs'),
    'reports':   os.path.join(BASE_DIR, 'reports'),
    'figures':   os.path.join(BASE_DIR, 'figures'),
    'config':    os.path.join(BASE_DIR, 'config'),
    'src':       os.path.join(BASE_DIR, 'src'),
}

# =============================================================================
# RAW FILENAMES
# =============================================================================
# Maps logical dataset names (used throughout the codebase) to actual
# filenames on disk. If a file is renamed, only this block needs updating.
#
# NOTE: starting_inventory was uploaded as starting_inventory_snapshot.csv.
#       The logical key 'starting_inventory' is used everywhere in code.
# =============================================================================

RAW_FILENAMES = {
    'daily_demand':           'daily_demand.csv',
    'event_calendar':         'event_calendar.csv',
    'sku_master':             'sku_master.csv',
    'warehouses':             'warehouses.csv',
    'warehouse_region_costs': 'warehouse_region_costs.csv',
    'starting_inventory':     'starting_inventory_snapshot.csv',
}

# =============================================================================
# PROCESSED FILENAMES
# =============================================================================
# Output filenames written to data/processed/ after cleaning.
# Standardised to snake_case with _clean suffix for traceability.
# =============================================================================

PROCESSED_FILENAMES = {
    'daily_demand':           'daily_demand_clean.csv',
    'event_calendar':         'event_calendar_clean.csv',
    'sku_master':             'sku_master_clean.csv',
    'warehouses':             'warehouses_clean.csv',
    'warehouse_region_costs': 'warehouse_region_costs_clean.csv',
    'starting_inventory':     'starting_inventory_clean.csv',
}

# =============================================================================
# INTERIM FILENAMES
# =============================================================================
# Checkpoint files written mid-cleaning to data/interim/.
# Useful for debugging — shows the dataset state before final transforms.
# =============================================================================

INTERIM_FILENAMES = {
    'daily_demand':           'daily_demand_interim.csv',
    'event_calendar':         'event_calendar_interim.csv',
    'sku_master':             'sku_master_interim.csv',
    'warehouses':             'warehouses_interim.csv',
    'warehouse_region_costs': 'warehouse_region_costs_interim.csv',
    'starting_inventory':     'starting_inventory_interim.csv',
}

# =============================================================================
# LOG FILENAMES
# =============================================================================
# Each cleaning module writes its own structured log CSV to outputs/logs/.
# Logs capture: step name, rows before, rows after, issues found, timestamp.
# =============================================================================

LOG_FILENAMES = {
    'daily_demand':           'log_clean_daily_demand.csv',
    'event_calendar':         'log_clean_event_calendar.csv',
    'sku_master':             'log_clean_sku_master.csv',
    'warehouses':             'log_clean_warehouses.csv',
    'warehouse_region_costs': 'log_clean_warehouse_region_costs.csv',
    'starting_inventory':     'log_clean_starting_inventory.csv',
    'master_run':             'log_master_run.csv',
}

# =============================================================================
# REPORT FILENAMES
# =============================================================================
# Markdown technical notes written to reports/ after each cleaning module.
# These form the data quality appendix for the thesis submission.
# =============================================================================

REPORT_FILENAMES = {
    'daily_demand':           'report_clean_daily_demand.md',
    'event_calendar':         'report_clean_event_calendar.md',
    'sku_master':             'report_clean_sku_master.md',
    'warehouses':             'report_clean_warehouses.md',
    'warehouse_region_costs': 'report_clean_warehouse_region_costs.md',
    'starting_inventory':     'report_clean_starting_inventory.md',
    'cleaning_summary':       'report_cleaning_summary.md',
}

# =============================================================================
# CANONICAL WAREHOUSE NETWORK
# =============================================================================
# The 5 real warehouse nodes in the fulfillment network.
# The raw warehouses.csv contains 5000+ duplicate rows — all cleaning
# deduplication targets this canonical set.
#
# Structure per node:
#   warehouse_id      — unique identifier used across all datasets
#   warehouse_region  — demand region this warehouse primarily serves
#   capacity_units    — maximum storage capacity in units
#   fixed_daily_cost  — daily fixed operating cost in USD
#
# BUSINESS ASSUMPTION:
#   Fixed daily costs are structural and do not vary with throughput.
#   This is consistent with Amazon's fixed-cost fulfillment centre model.
# =============================================================================

CANONICAL_NETWORK = [
    {
        'warehouse_id':     'WH-NORTH',
        'warehouse_region': 'North',
        'capacity_units':   120000,
        'fixed_daily_cost': 1800.0,
    },
    {
        'warehouse_id':     'WH-SOUTH',
        'warehouse_region': 'South',
        'capacity_units':   115000,
        'fixed_daily_cost': 1700.0,
    },
    {
        'warehouse_id':     'WH-EAST',
        'warehouse_region': 'East',
        'capacity_units':   118000,
        'fixed_daily_cost': 1750.0,
    },
    {
        'warehouse_id':     'WH-WEST',
        'warehouse_region': 'West',
        'capacity_units':   110000,
        'fixed_daily_cost': 1680.0,
    },
    {
        'warehouse_id':     'WH-CENTRAL',
        'warehouse_region': 'Central',
        'capacity_units':   180000,
        'fixed_daily_cost': 2600.0,
    },
]

# Derived lookup — maps warehouse_id to its dict for O(1) access
CANONICAL_NETWORK_MAP = {wh['warehouse_id']: wh for wh in CANONICAL_NETWORK}

# Canonical warehouse IDs as a set — used for membership checks
CANONICAL_WAREHOUSE_IDS = set(CANONICAL_NETWORK_MAP.keys())

# =============================================================================
# CANONICAL DEMAND REGIONS
# =============================================================================
# The 4 demand regions that appear in daily_demand and warehouse_region_costs.
# All region strings must be standardised to Title Case against this list.
# =============================================================================

CANONICAL_REGIONS = ['North', 'South', 'East', 'West']

# WH-CENTRAL serves all regions (hub node) — excluded from region matching
CENTRAL_WAREHOUSE_ID = 'WH-CENTRAL'

# =============================================================================
# WAREHOUSE ID PREFIX MAP
# =============================================================================
# starting_inventory_snapshot.csv uses abbreviated prefixes (WH-N, WH-S, etc.)
# This map resolves them to canonical IDs used everywhere else.
# =============================================================================

WAREHOUSE_PREFIX_MAP = {
    'WH-N': 'WH-NORTH',
    'WH-S': 'WH-SOUTH',
    'WH-E': 'WH-EAST',
    'WH-W': 'WH-WEST',
    'WH-C': 'WH-CENTRAL',
}

# =============================================================================
# SKU CATEGORIES
# =============================================================================
# The 6 product categories present in sku_master.
# Used for category-level demand aggregation and forecasting grain.
# =============================================================================

SKU_CATEGORIES = ['Electronics', 'Toys', 'Beauty', 'Home', 'Kitchen', 'Pet']

# =============================================================================
# CARBON EMISSION MODEL PARAMETERS
# =============================================================================
# These constants define the carbon calculation chain used throughout the
# pipeline. The model is based on EEA road freight emission factors.
#
# FORMULA:
#   distance_km     = lead_time_days x DISTANCE_KM_PER_DAY
#   weight_tonnes   = units x volume_m3 x FREIGHT_DENSITY_KG_M3 / 1000
#   carbon_kg_CO2   = distance_km x weight_tonnes x EEA_EMISSION_FACTOR
#
# SOURCES:
#   EEA_EMISSION_FACTOR : European Environment Agency road freight
#                         emission intensity = 0.062 kg CO2 per tonne-km
#   DISTANCE_KM_PER_DAY : Industry proxy for road freight speed
#                         500 km/day is standard for HGV long-haul routing
#   FREIGHT_DENSITY     : General freight average 200 kg/m3
#   CUBE_FT_TO_M3       : NIST conversion factor
#
# BUSINESS OBJECTIVE:
#   Warehouses with shortest lead time to highest-volume demand zones
#   will always produce the lowest carbon score. This is the primary
#   placement recommendation criterion.
# =============================================================================

CARBON_PARAMS = {
    'distance_km_per_day':      500.0,    # km per lead-time day (road proxy)
    'freight_density_kg_m3':    200.0,    # kg per cubic metre (general freight)
    'eea_emission_factor':      0.062,    # kg CO2 per tonne-km (EEA road)
    'cube_ft_to_m3':            0.028317, # 1 cubic foot in cubic metres
}

# =============================================================================
# COST MODEL PARAMETERS
# =============================================================================
# Financial constants used to derive engineered cost columns.
#
# HOLDING_COST_RATE:
#   Annual cost of holding 1 unit = 25% of unit cost.
#   Industry standard range is 20-30%; 25% is widely used in
#   academic supply chain literature (Chopra & Meindl, 2016).
#
# STOCKOUT_PENALTY_MULTIPLIER:
#   Stockout penalty = 2x selling price per unit short.
#   Captures lost revenue + customer dissatisfaction + expedite cost.
#   Conservative relative to Amazon's actual penalty (estimated 3-5x)
#   but appropriate for a planning-level model.
# =============================================================================

COST_PARAMS = {
    'holding_cost_rate':          0.25,   # annual holding cost as % of unit cost
    'holding_cost_days_per_year':  365,   # denominator for daily holding cost
    'stockout_penalty_multiplier':   2,   # multiple of selling price per lost unit
}

# =============================================================================
# VALIDATION THRESHOLDS
# =============================================================================
# Boundary values used in assert statements and data quality checks.
# Centralising these means QA rules are consistent across all modules.
# =============================================================================

VALIDATION = {
    'min_service_level':          0.80,   # target_service_level lower bound
    'max_service_level':          1.00,   # target_service_level upper bound
    'units_outlier_percentile':  99.9,    # cap units_ordered above this percentile
    'min_cube_ft':                0.01,   # minimum plausible product volume
    'min_price_usd':              0.01,   # minimum plausible selling price
    'min_unit_cost_usd':          0.01,   # minimum plausible unit cost
    'valid_flag_values':     {0, 1},      # binary flag columns must be in this set
    'sku_id_pattern':    r'^SKU-\d{6}$', # regex for valid SKU ID format
    'expected_wh_count':             5,   # canonical warehouse node count
    'expected_lane_count':          20,   # 5 warehouses x 4 regions
    'expected_region_count':         4,   # North South East West
}

# =============================================================================
# FORECASTING GRAIN
# =============================================================================
# Because each sku_id appears only ONCE in daily_demand, per-SKU time-series
# forecasting is not possible. The pipeline aggregates to week-region-category
# grain before modelling.
#
# AGGREGATION KEYS:
#   year_week  — ISO year-week string (e.g. '2023-W04')
#   region     — one of CANONICAL_REGIONS
#   category   — one of SKU_CATEGORIES
#
# TARGET VARIABLE:
#   total_units_ordered — sum of units_ordered within the grain
# =============================================================================

FORECAST_GRAIN = ['year_week', 'region', 'category']
FORECAST_TARGET = 'total_units_ordered'

# =============================================================================
# COLUMN NAME REGISTRY
# =============================================================================
# Canonical column names for each dataset after cleaning.
# Modules reference these instead of raw string literals to prevent
# silent KeyErrors from typos or schema drift.
# =============================================================================

COLUMNS = {
    'daily_demand': [
        'date', 'sku_id', 'region', 'units_ordered', 'price_usd',
        'holiday_peak_flag', 'prime_event_flag', 'is_weekend',
        'marketing_push_flag', 'weather_disruption_index',
        'year', 'month', 'quarter', 'week_number', 'day_of_week', 'year_week',
    ],
    'event_calendar': [
        'date', 'holiday_peak_flag', 'prime_event_flag', 'is_weekend',
        'marketing_push_flag', 'weather_disruption_index',
        'year', 'month', 'quarter', 'week_number', 'day_of_week', 'year_week',
    ],
    'sku_master': [
        'sku_id', 'category', 'unit_cost_usd', 'selling_price_usd',
        'cube_ft', 'target_service_level',
        'gross_margin_usd', 'margin_pct', 'stockout_penalty_usd',
        'holding_cost_daily_usd', 'volume_m3',
    ],
    'warehouses': [
        'warehouse_id', 'warehouse_region', 'capacity_units', 'fixed_daily_cost',
    ],
    'warehouse_region_costs': [
        'warehouse_id', 'demand_region', 'ship_cost_per_unit', 'lead_time_days',
        'distance_km_proxy', 'carbon_kg_per_unit', 'lane_efficiency_score',
    ],
    'starting_inventory': [
        'warehouse_id', 'sku_id', 'starting_inventory_units',
        'canonical_warehouse_id', 'inventory_value_usd', 'daily_holding_cost_usd',
    ],
}

# =============================================================================
# PROJECT METADATA
# =============================================================================

PROJECT_META = {
    'title':      'Regional Demand Forecasting and Inventory Placement Optimizer',
    'domain':     'Supply Chain Analytics | Fulfillment Network Planning',
    'version':    '1.0.0',
    'author':     'Arvind Swami',
    'repo':       'Regional-demand-forecasting-optimizer-final',
    'thesis_ref': 'Capstone Project — Amazon-Inspired Fulfillment Network Planning',
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_raw_path(dataset_key: str) -> str:
    '''
    Returns the full path to a raw CSV file.
    Args:
        dataset_key: logical name from RAW_FILENAMES (e.g. 'daily_demand')
    Returns:
        Absolute path string to the raw file.
    Raises:
        KeyError if dataset_key is not in RAW_FILENAMES.
    '''
    return os.path.join(PATHS['raw'], RAW_FILENAMES[dataset_key])


def get_processed_path(dataset_key: str) -> str:
    '''
    Returns the full path to a processed CSV file.
    '''
    return os.path.join(PATHS['processed'], PROCESSED_FILENAMES[dataset_key])


def get_interim_path(dataset_key: str) -> str:
    '''
    Returns the full path to an interim checkpoint CSV file.
    '''
    return os.path.join(PATHS['interim'], INTERIM_FILENAMES[dataset_key])


def get_log_path(dataset_key: str) -> str:
    '''
    Returns the full path to a cleaning log CSV file.
    '''
    return os.path.join(PATHS['logs'], LOG_FILENAMES[dataset_key])


def get_report_path(dataset_key: str) -> str:
    '''
    Returns the full path to a markdown report file.
    '''
    return os.path.join(PATHS['reports'], REPORT_FILENAMES[dataset_key])


def ensure_dirs() -> None:
    '''
    Creates all project directories if they do not already exist.
    Call this at the top of any module that writes output files.
    '''
    for path in PATHS.values():
        os.makedirs(path, exist_ok=True)
