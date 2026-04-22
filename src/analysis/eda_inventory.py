"""
eda_inventory.py
================
Exploratory Data Analysis — Inventory Position

WHY  : Before optimizing placement we must understand the CURRENT
       inventory state: which warehouses hold the most stock,
       which categories tie up the most capital, and whether
       days-of-cover are dangerously low or wastefully high.

WHAT : Produces 3 publication-quality figures, 1 markdown report,
       and 1 structured CSV log.

BUSINESS ISSUE SOLVED:
  Inventory placement decisions require knowing WHERE stock is NOW
  relative to WHERE demand will occur.  Imbalances identified here
  become the primary input to the Stage 3 optimizer.

ASSUMPTIONS:
  - starting_inventory_clean.csv reflects the initial stock position.
  - Days-of-cover = starting_inventory_units / avg_daily_demand.
  - Avg daily demand derived from daily_demand_clean.csv aggregated
    to warehouse region via the warehouses_clean.csv region mapping.
  - sku_master_clean.csv provides category for inventory breakdown.

WATCH OUT:
  - starting_inventory uses canonical_warehouse_id, NOT region.
  - Must join warehouses to get region for demand alignment.
  - WH-CENTRAL serves all regions — treat separately in DoC calc.
"""

import os
import logging
import datetime
import csv

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns

sns.set_theme(style='whitegrid', palette='muted', font_scale=1.1)

SCRIPT_NAME = 'eda_inventory.py'
RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)

PROCESSED_DIR   = os.path.join(PROJECT_ROOT, 'data', 'processed')
INV_CSV         = os.path.join(PROCESSED_DIR, 'starting_inventory_clean.csv')
SKU_CSV         = os.path.join(PROCESSED_DIR, 'sku_master_clean.csv')
WH_CSV          = os.path.join(PROCESSED_DIR, 'warehouses_clean.csv')
DEMAND_CSV      = os.path.join(PROCESSED_DIR, 'daily_demand_clean.csv')

FIGURES_DIR     = os.path.join(PROJECT_ROOT, 'figures')
REPORTS_DIR     = os.path.join(PROJECT_ROOT, 'reports')
LOGS_DIR        = os.path.join(PROJECT_ROOT, 'outputs', 'logs')

REPORT_PATH     = os.path.join(REPORTS_DIR, 'report_eda_inventory.md')
LOG_PATH        = os.path.join(LOGS_DIR,    'log_eda_inventory.csv')

FIG_WH_UNITS    = os.path.join(FIGURES_DIR, 'eda_inventory_units_by_warehouse.png')
FIG_CAT_VALUE   = os.path.join(FIGURES_DIR, 'eda_inventory_value_by_category.png')
FIG_DOC         = os.path.join(FIGURES_DIR, 'eda_inventory_days_of_cover.png')

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
    logger.info('[%-35s] %-8s %s', step, status, detail)


def ensure_output_dirs():
    for d in [FIGURES_DIR, REPORTS_DIR, LOGS_DIR]:
        os.makedirs(d, exist_ok=True)
    _log_step('ensure_output_dirs', 'OK', 'all output dirs ready')


def load_data():
    """
    WHY  : Four datasets must be joined to compute days-of-cover:
           inventory + sku_master (category) +
           warehouses (region) + daily_demand (avg demand).
    RETURNS: dict of DataFrames keyed by name.
    """
    logger.info('Loading inventory datasets ...')

    inv    = pd.read_csv(INV_CSV)
    sku    = pd.read_csv(SKU_CSV)
    wh     = pd.read_csv(WH_CSV)
    demand = pd.read_csv(DEMAND_CSV, parse_dates=['date'])

    logger.info('  starting_inventory : %s', inv.shape)
    logger.info('  sku_master         : %s', sku.shape)
    logger.info('  warehouses         : %s', wh.shape)
    logger.info('  daily_demand       : %s', demand.shape)

    # Validate required columns
    assert 'canonical_warehouse_id'   in inv.columns,    'canonical_warehouse_id missing'
    assert 'sku_id'                   in inv.columns,    'sku_id missing from inventory'
    assert 'starting_inventory_units' in inv.columns,    'starting_inventory_units missing'
    assert 'inventory_value_usd'      in inv.columns,    'inventory_value_usd missing'
    assert 'daily_holding_cost_usd'   in inv.columns,    'daily_holding_cost_usd missing'
    assert 'warehouse_id'             in wh.columns,     'warehouse_id missing'
    assert 'region'                   in wh.columns,     'region missing from warehouses'
    assert 'category'                 in sku.columns,    'category missing from sku_master'
    assert 'units_ordered'            in demand.columns, 'units_ordered missing'

    _log_step('load_data', 'OK',
              f'inv={len(inv)} sku={len(sku)} wh={len(wh)} demand={len(demand)}')
    return {'inv': inv, 'sku': sku, 'wh': wh, 'demand': demand}


def build_inventory_master(data):
    """
    WHY  : A single enriched table makes all three figures trivial.
    WHAT : Joins inventory + sku_master (category) +
           warehouses (region, capacity).
    ASSUMPTION: canonical_warehouse_id in inventory matches
                warehouse_id in warehouses exactly.
    """
    inv = data['inv'].copy()
    sku = data['sku'][['sku_id', 'category']].copy()
    wh  = data['wh'][['warehouse_id', 'region', 'capacity_units']].copy()

    # Join category
    master = inv.merge(sku, on='sku_id', how='left')
    missing_cat = master['category'].isna().sum()
    assert missing_cat == 0, f'{missing_cat} inventory rows missing category'

    # Join warehouse region and capacity
    master = master.merge(
        wh, left_on='canonical_warehouse_id', right_on='warehouse_id', how='left'
    )
    missing_wh = master['region'].isna().sum()
    assert missing_wh == 0, f'{missing_wh} inventory rows missing warehouse region'

    logger.info('  inventory master shape : %s', master.shape)
    logger.info('  warehouses present     : %s',
                sorted(master['canonical_warehouse_id'].unique()))
    logger.info('  categories present     : %s',
                sorted(master['category'].unique()))

    _log_step('build_inventory_master', 'OK',
              f'rows={len(master)} '
              f'total_units={master["starting_inventory_units"].sum():,.0f} '
              f'total_value=${master["inventory_value_usd"].sum():,.0f}')
    return master


def compute_days_of_cover(master, demand_df):
    """
    WHY  : Days-of-cover (DoC) = inventory / avg_daily_demand is the
           single most important inventory health metric.
           Too low  → stockout risk.
           Too high → capital trapped, holding cost inflated.
    WHAT : Computes avg daily demand per region from daily_demand,
           sums inventory per warehouse-region, divides.
    ASSUMPTION: WH-CENTRAL's inventory is split equally across
                all 4 demand regions for DoC purposes.
    """
    logger.info('Computing days of cover ...')

    # Avg daily demand per region across the full date range
    n_days = (demand_df['date'].max() - demand_df['date'].min()).days + 1
    demand_by_region = (
        demand_df.groupby('region')['units_ordered'].sum() / n_days
    ).rename('avg_daily_demand')

    logger.info('  date range days : %d', n_days)
    logger.info('  avg daily demand per region:')
    for reg, val in demand_by_region.items():
        logger.info('    %-8s : %.1f units/day', reg, val)

    # Inventory per warehouse
    inv_by_wh = (
        master.groupby(['canonical_warehouse_id', 'region'])
        ['starting_inventory_units'].sum()
        .reset_index()
    )

    # For WH-CENTRAL (region=Central), split inventory equally
    # across the 4 demand regions (North/South/East/West)
    demand_regions = [r for r in demand_by_region.index
                      if r in ['North', 'South', 'East', 'West']]

    doc_rows = []
    for _, row in inv_by_wh.iterrows():
        wh_id  = row['canonical_warehouse_id']
        wh_reg = row['region']
        units  = row['starting_inventory_units']

        if wh_reg == 'Central':
            # Split evenly across demand regions
            units_per_region = units / len(demand_regions)
            for dr in demand_regions:
                avg_d = demand_by_region.get(dr, np.nan)
                doc   = units_per_region / avg_d if avg_d > 0 else np.nan
                doc_rows.append({
                    'warehouse_id': wh_id,
                    'region':       dr,
                    'inv_units':    units_per_region,
                    'avg_daily_demand': avg_d,
                    'days_of_cover':    round(doc, 1) if not np.isnan(doc) else np.nan,
                })
        else:
            avg_d = demand_by_region.get(wh_reg, np.nan)
            doc   = units / avg_d if avg_d > 0 else np.nan
            doc_rows.append({
                'warehouse_id': wh_id,
                'region':       wh_reg,
                'inv_units':    units,
                'avg_daily_demand': avg_d,
                'days_of_cover':    round(doc, 1) if not np.isnan(doc) else np.nan,
            })

    doc_df = pd.DataFrame(doc_rows)
    logger.info('  days-of-cover table : %s', doc_df.shape)
    _log_step('compute_days_of_cover', 'OK',
              f'rows={len(doc_df)} '
              f'min_doc={doc_df["days_of_cover"].min():.1f} '
              f'max_doc={doc_df["days_of_cover"].max():.1f}')
    return doc_df


def plot_units_by_warehouse(master):
    """
    WHY  : Knowing which warehouse holds the most units reveals
           whether the current placement matches regional demand.
           A mismatch here is a direct optimization opportunity.
    WHAT : Stacked bar chart — warehouse on x, units on y,
           stacked by category.  Capacity line overlaid.
    """
    logger.info('Plotting Figure 1: inventory units by warehouse ...')

    wh_cat = (
        master.groupby(['canonical_warehouse_id', 'category'])
        ['starting_inventory_units'].sum()
        .unstack(fill_value=0)
    )

    # Capacity per warehouse for overlay line
    cap = (
        master.groupby('canonical_warehouse_id')['capacity_units']
        .first()
    )

    warehouses = wh_cat.index.tolist()
    categories = wh_cat.columns.tolist()
    colors     = sns.color_palette('muted', len(categories))

    fig, ax = plt.subplots(figsize=(12, 6))
    bottom = np.zeros(len(warehouses))
    for i, cat in enumerate(categories):
        vals = wh_cat[cat].values
        ax.bar(warehouses, vals, bottom=bottom,
               label=cat, color=colors[i], edgecolor='white', linewidth=0.4)
        bottom += vals

    # Capacity overlay
    cap_vals = [cap.get(wh, 0) for wh in warehouses]
    ax.plot(warehouses, cap_vals, 'r--o', linewidth=1.8,
            markersize=7, label='Capacity', zorder=5)

    ax.set_title('Starting Inventory Units by Warehouse',
                 fontsize=14, fontweight='bold')
    ax.set_xlabel('Warehouse')
    ax.set_ylabel('Inventory Units')
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))
    ax.legend(title='Category', bbox_to_anchor=(1.01, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(FIG_WH_UNITS, dpi=150, bbox_inches='tight')
    plt.close(fig)

    # Summary stats for report
    wh_totals = master.groupby('canonical_warehouse_id').agg(
        total_units =('starting_inventory_units', 'sum'),
        total_value =('inventory_value_usd',      'sum'),
        capacity    =('capacity_units',            'first'),
    ).round(0)
    wh_totals['utilisation_pct'] = (
        wh_totals['total_units'] / wh_totals['capacity'] * 100
    ).round(1)
    stats = wh_totals.to_dict('index')

    _log_step('plot_units_by_warehouse', 'OK', FIG_WH_UNITS)
    return stats


def plot_value_by_category(master):
    """
    WHY  : Inventory value concentration by category determines
           which SKU groups carry the most financial risk.
           High-value categories need tighter DoC management.
    WHAT : Grouped bar chart — category on x,
           bars = total inventory value and daily holding cost.
    """
    logger.info('Plotting Figure 2: inventory value by category ...')

    cat_agg = (
        master.groupby('category').agg(
            total_value      =('inventory_value_usd',    'sum'),
            total_hold_cost  =('daily_holding_cost_usd', 'sum'),
            total_units      =('starting_inventory_units','sum'),
        ).sort_values('total_value', ascending=False)
    )

    cats   = cat_agg.index.tolist()
    x      = np.arange(len(cats))
    width  = 0.35

    fig, ax1 = plt.subplots(figsize=(13, 6))
    ax2      = ax1.twinx()

    bars1 = ax1.bar(x - width/2, cat_agg['total_value'],
                    width, label='Inventory Value ($)',
                    color='steelblue', edgecolor='white')
    bars2 = ax2.bar(x + width/2, cat_agg['total_hold_cost'],
                    width, label='Daily Holding Cost ($)',
                    color='coral', edgecolor='white')

    ax1.set_title('Inventory Value and Daily Holding Cost by Category',
                  fontsize=13, fontweight='bold')
    ax1.set_xlabel('Category')
    ax1.set_ylabel('Inventory Value (USD)', color='steelblue')
    ax2.set_ylabel('Daily Holding Cost (USD)', color='coral')
    ax1.set_xticks(x)
    ax1.set_xticklabels(cats)
    ax1.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: f'${v:,.0f}'))
    ax2.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: f'${v:,.0f}'))

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2,
               loc='upper right', fontsize=9)
    plt.tight_layout()
    plt.savefig(FIG_CAT_VALUE, dpi=150, bbox_inches='tight')
    plt.close(fig)

    stats = cat_agg.round(2).to_dict('index')
    _log_step('plot_value_by_category', 'OK', FIG_CAT_VALUE)
    return stats


def plot_days_of_cover(doc_df):
    """
    WHY  : Days-of-cover is the primary risk indicator for the
           optimizer.  Warehouses below 14 days DoC are at
           stockout risk; above 90 days signals excess capital.
    WHAT : Horizontal bar chart — one bar per warehouse (or
           warehouse x region for WH-CENTRAL), colour-coded
           by risk zone: red<14, amber 14-30, green>=30.
    """
    logger.info('Plotting Figure 3: days of cover ...')

    doc_plot = doc_df.copy()
    doc_plot['label'] = (
        doc_plot['warehouse_id'] + ' / ' + doc_plot['region']
    )
    doc_plot = doc_plot.sort_values('days_of_cover', ascending=True)

    def _color(doc):
        if doc < 14:  return '#d62728'   # red   — stockout risk
        if doc < 30:  return '#ff7f0e'   # amber — watch zone
        return '#2ca02c'                 # green — healthy

    colors = [_color(d) for d in doc_plot['days_of_cover']]

    fig, ax = plt.subplots(figsize=(12, max(5, len(doc_plot) * 0.55)))
    ax.barh(doc_plot['label'], doc_plot['days_of_cover'],
            color=colors, edgecolor='white')

    # Reference lines
    ax.axvline(14, color='red',    linestyle='--', linewidth=1.2,
               label='14-day risk threshold')
    ax.axvline(30, color='orange', linestyle='--', linewidth=1.2,
               label='30-day watch threshold')

    ax.set_title('Days of Cover by Warehouse / Region',
                 fontsize=13, fontweight='bold')
    ax.set_xlabel('Days of Cover')
    ax.set_ylabel('Warehouse / Region')
    ax.legend(loc='lower right', fontsize=9)

    # Annotate each bar with the DoC value
    for i, (_, row) in enumerate(doc_plot.iterrows()):
        ax.text(row['days_of_cover'] + 0.5, i,
                f"{row['days_of_cover']:.0f}d",
                va='center', fontsize=8)

    plt.tight_layout()
    plt.savefig(FIG_DOC, dpi=150, bbox_inches='tight')
    plt.close(fig)

    stats = {
        'min_doc':  round(float(doc_plot['days_of_cover'].min()), 1),
        'max_doc':  round(float(doc_plot['days_of_cover'].max()), 1),
        'mean_doc': round(float(doc_plot['days_of_cover'].mean()), 1),
        'at_risk':  int((doc_plot['days_of_cover'] < 14).sum()),
        'watch':    int(((doc_plot['days_of_cover'] >= 14) &
                        (doc_plot['days_of_cover'] < 30)).sum()),
        'healthy':  int((doc_plot['days_of_cover'] >= 30).sum()),
    }
    _log_step('plot_days_of_cover', 'OK', str(stats))
    return stats, doc_plot


def write_report(wh_stats, cat_stats, doc_stats, doc_plot, master):
    """
    WHY  : Stakeholders need a concise inventory health summary
           without running code.
    WHAT : Writes reports/report_eda_inventory.md.
    """
    logger.info('Writing markdown report ...')

    total_units = int(master['starting_inventory_units'].sum())
    total_value = master['inventory_value_usd'].sum()
    total_hold  = master['daily_holding_cost_usd'].sum()
    n_skus      = master['sku_id'].nunique()

    rpt = []
    rpt.append('# EDA Report — Inventory Position')
    rpt.append('')
    rpt.append(f'**Generated** : {datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}')
    rpt.append(f'**Script**    : {SCRIPT_NAME}')
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 1. Portfolio Overview')
    rpt.append('')
    rpt.append('| Metric | Value |')
    rpt.append('|--------|-------|')
    rpt.append(f'| Total SKUs | {n_skus:,} |')
    rpt.append(f'| Total units on hand | {total_units:,} |')
    rpt.append(f'| Total inventory value | ${total_value:,.2f} |')
    rpt.append(f'| Daily holding cost | ${total_hold:,.2f} |')
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 2. Units and Utilisation by Warehouse')
    rpt.append('')
    rpt.append('![Units by Warehouse](../figures/eda_inventory_units_by_warehouse.png)')
    rpt.append('')
    rpt.append('| Warehouse | Units on Hand | Capacity | Utilisation % | Value ($) |')
    rpt.append('|-----------|---------------|----------|---------------|-----------|')
    for wh, s in sorted(wh_stats.items()):
        rpt.append(
            f"| {wh} | {int(s['total_units']):,} | {int(s['capacity']):,}"
            f" | {s['utilisation_pct']:.1f}% | ${s['total_value']:,.0f} |"
        )
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 3. Inventory Value by Category')
    rpt.append('')
    rpt.append('![Value by Category](../figures/eda_inventory_value_by_category.png)')
    rpt.append('')
    rpt.append('| Category | Units | Value ($) | Daily Hold Cost ($) |')
    rpt.append('|----------|-------|-----------|---------------------|')
    for cat, s in sorted(cat_stats.items(),
                         key=lambda x: -x[1]['total_value']):
        rpt.append(
            f"| {cat} | {int(s['total_units']):,} | ${s['total_value']:,.0f}"
            f" | ${s['total_hold_cost']:,.2f} |"
        )
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 4. Days of Cover')
    rpt.append('')
    rpt.append('![Days of Cover](../figures/eda_inventory_days_of_cover.png)')
    rpt.append('')
    rpt.append('| Metric | Value |')
    rpt.append('|--------|-------|')
    rpt.append(f'| Min DoC | {doc_stats["min_doc"]} days |')
    rpt.append(f'| Max DoC | {doc_stats["max_doc"]} days |')
    rpt.append(f'| Mean DoC | {doc_stats["mean_doc"]} days |')
    rpt.append(f'| At-risk lanes (DoC < 14) | {doc_stats["at_risk"]} |')
    rpt.append(f'| Watch lanes (14-30 days) | {doc_stats["watch"]} |')
    rpt.append(f'| Healthy lanes (>= 30 days) | {doc_stats["healthy"]} |')
    rpt.append('')
    rpt.append('**Detail by warehouse / region:**')
    rpt.append('')
    rpt.append('| Warehouse | Region | Inv Units | Avg Daily Demand | Days of Cover |')
    rpt.append('|-----------|--------|-----------|------------------|---------------|')
    for _, row in doc_plot.sort_values('days_of_cover').iterrows():
        rpt.append(
            f"| {row['warehouse_id']} | {row['region']}"
            f" | {row['inv_units']:,.0f} | {row['avg_daily_demand']:.1f}"
            f" | {row['days_of_cover']:.0f} |"
        )
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 5. Figures Index')
    rpt.append('')
    rpt.append('| # | Filename | Description |')
    rpt.append('|---|----------|-------------|')
    rpt.append('| 1 | eda_inventory_units_by_warehouse.png | Units + capacity by warehouse |')
    rpt.append('| 2 | eda_inventory_value_by_category.png | Value and holding cost by category |')
    rpt.append('| 3 | eda_inventory_days_of_cover.png | Days of cover risk heatmap |')
    rpt.append('')
    rpt.append('*End of EDA inventory report.*')

    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(REPORT_PATH, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(rpt))

    with open(REPORT_PATH, 'r', encoding='utf-8') as fh:
        content = fh.read()
    assert 'EDA Report' in content,         'Report header missing'
    assert 'Days of Cover' in content,      'DoC section missing'
    assert 'Portfolio Overview' in content,  'Overview section missing'
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

    ensure_output_dirs()
    data   = load_data()
    master = build_inventory_master(data)
    doc_df = compute_days_of_cover(master, data['demand'])

    wh_stats          = plot_units_by_warehouse(master)
    cat_stats         = plot_value_by_category(master)
    doc_stats, doc_plot = plot_days_of_cover(doc_df)

    write_report(wh_stats, cat_stats, doc_stats, doc_plot, master)
    write_log()

    print()
    print('=' * 60)
    print(f'  {SCRIPT_NAME}  —  COMPLETE')
    print('=' * 60)
    print(f'  Inventory master rows : {len(master):,}')
    print(f'  Total units on hand   : {master["starting_inventory_units"].sum():,.0f}')
    print(f'  Total inventory value : ${master["inventory_value_usd"].sum():,.2f}')
    print(f'  Figures written       : 3')
    print()
    print('  Figures:')
    for fp in [FIG_WH_UNITS, FIG_CAT_VALUE, FIG_DOC]:
        mark = 'OK' if os.path.isfile(fp) else 'MISSING'
        print(f'    [{mark}] {os.path.basename(fp)}')
    print('=' * 60)


if __name__ == '__main__':
    main()
