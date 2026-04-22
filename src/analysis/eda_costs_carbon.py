"""
eda_costs_carbon.py
===================
Exploratory Data Analysis — Shipping Costs, Lane Efficiency,
and Carbon Emission Estimates

WHY  : Cost-to-serve = shipping + holding + stockout penalty.
       Before optimizing we must understand the shipping cost
       landscape across all 20 warehouse-to-region lanes,
       which lanes are most efficient, and the carbon footprint
       implied by each lane choice.

WHAT : Produces 3 figures, 1 markdown report, 1 CSV log.
       Implements the FULL carbon formula from the spec
       (not the placeholder zeros in the processed data).

BUSINESS ISSUE SOLVED:
  Choosing WH-EAST to serve the West region costs \$8/unit and
  emits ~4x more carbon than serving West from WH-WEST at \$1.50.
  This EDA quantifies every such trade-off before the optimizer runs.

CARBON FORMULA (authoritative — EEA road freight):
  distance_km   = lead_time_days x 500
  weight_tonnes = units x volume_m3 x 200 / 1000
  carbon_kg_CO2 = distance_km x weight_tonnes x 0.062
  Where:
    0.062     = EEA road freight emission factor (kg CO2 per tonne-km)
    volume_m3 = cube_ft x 0.028317  (from sku_master)
    200 kg/m3 = assumed product density for mixed retail SKUs

ASSUMPTIONS:
  - carbon_kg_per_unit in processed data is a placeholder (0.0).
  - Full carbon is computed here using avg volume_m3 per lane.
  - One unit shipped per lane for per-unit carbon comparison.
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

SCRIPT_NAME = 'eda_costs_carbon.py'
RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

# Carbon emission constants — EEA road freight specification
KM_PER_LEAD_DAY      = 500        # km proxy per lead-time day
DENSITY_KG_PER_M3    = 200        # assumed mixed retail product density
EEA_FACTOR           = 0.062      # kg CO2 per tonne-km
M3_PER_CUFT          = 0.028317   # cubic feet to cubic metres

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)

PROCESSED_DIR  = os.path.join(PROJECT_ROOT, 'data', 'processed')
LANE_CSV       = os.path.join(PROCESSED_DIR, 'warehouse_region_costs_clean.csv')
WH_CSV         = os.path.join(PROCESSED_DIR, 'warehouses_clean.csv')
SKU_CSV        = os.path.join(PROCESSED_DIR, 'sku_master_clean.csv')

FIGURES_DIR    = os.path.join(PROJECT_ROOT, 'figures')
REPORTS_DIR    = os.path.join(PROJECT_ROOT, 'reports')
LOGS_DIR       = os.path.join(PROJECT_ROOT, 'outputs', 'logs')

REPORT_PATH    = os.path.join(REPORTS_DIR, 'report_eda_costs_carbon.md')
LOG_PATH       = os.path.join(LOGS_DIR,    'log_eda_costs_carbon.csv')

FIG_LANE_HM    = os.path.join(FIGURES_DIR, 'eda_costs_lane_heatmap.png')
FIG_EFFICIENCY = os.path.join(FIGURES_DIR, 'eda_costs_efficiency_scores.png')
FIG_CARBON     = os.path.join(FIGURES_DIR, 'eda_costs_carbon_placeholder.png')

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
    WHY  : Three datasets needed:
           lane costs (20 rows) + warehouses (5 rows) +
           sku_master (for avg volume_m3 used in carbon calc).
    RETURNS: enriched lane DataFrame with carbon computed.
    """
    logger.info('Loading cost/carbon datasets ...')

    lanes = pd.read_csv(LANE_CSV)
    wh    = pd.read_csv(WH_CSV)
    sku   = pd.read_csv(SKU_CSV)

    logger.info('  lane costs   : %s', lanes.shape)
    logger.info('  warehouses   : %s', wh.shape)
    logger.info('  sku_master   : %s', sku.shape)

    # Validate required columns
    for col in ['warehouse_id', 'demand_region', 'ship_cost_per_unit',
                'lead_time_days', 'distance_km_proxy',
                'lane_efficiency_score']:
        assert col in lanes.columns, f'Missing column in lanes: {col}'
    assert 'volume_m3' in sku.columns, 'volume_m3 missing from sku_master'
    assert 'cube_ft'   in sku.columns, 'cube_ft missing from sku_master'

    # Compute portfolio avg volume_m3 across all SKUs
    # WHY: carbon formula needs volume; we use fleet average for per-lane EDA
    avg_volume_m3 = sku['volume_m3'].mean()
    logger.info('  avg volume_m3 across SKUs : %.6f m3', avg_volume_m3)

    # ── Carbon calculation — full EEA formula ────────────────────
    # distance_km   = lead_time_days x KM_PER_LEAD_DAY
    # weight_tonnes = 1 unit x volume_m3 x DENSITY_KG_PER_M3 / 1000
    # carbon_kg     = distance_km x weight_tonnes x EEA_FACTOR
    lanes = lanes.copy()
    lanes['distance_km']       = lanes['lead_time_days'] * KM_PER_LEAD_DAY
    lanes['weight_tonnes']      = avg_volume_m3 * DENSITY_KG_PER_M3 / 1000
    lanes['carbon_kg_per_unit'] = (
        lanes['distance_km'] * lanes['weight_tonnes'] * EEA_FACTOR
    ).round(6)

    logger.info('  carbon_kg_per_unit range : %.4f – %.4f',
                lanes['carbon_kg_per_unit'].min(),
                lanes['carbon_kg_per_unit'].max())

    # Join warehouse fixed daily cost for context
    lanes = lanes.merge(
        wh[['warehouse_id', 'region', 'fixed_daily_cost_usd', 'capacity_units']],
        on='warehouse_id', how='left'
    )

    assert len(lanes) == 20, f'Expected 20 lanes, got {len(lanes)}'
    logger.info('  enriched lanes shape : %s', lanes.shape)

    _log_step('load_data', 'OK',
              f'lanes={len(lanes)} avg_vol_m3={avg_volume_m3:.6f} '
              f'carbon_range={lanes["carbon_kg_per_unit"].min():.4f}-'
              f'{lanes["carbon_kg_per_unit"].max():.4f}')
    return lanes, wh, sku


def plot_lane_heatmap(lanes):
    """
    WHY  : A heatmap of ship_cost_per_unit across all 20 lanes
           instantly reveals the cheapest and most expensive
           warehouse-to-region pairings.
           This is the primary input to the cost-minimization optimizer.
    WHAT : Two side-by-side heatmaps:
           Left  = ship_cost_per_unit ($ per unit)
           Right = lead_time_days
           Rows = warehouse, Columns = demand region.
    """
    logger.info('Plotting Figure 1: lane cost heatmap ...')

    cost_pivot = lanes.pivot(
        index='warehouse_id', columns='demand_region',
        values='ship_cost_per_unit'
    )
    lead_pivot = lanes.pivot(
        index='warehouse_id', columns='demand_region',
        values='lead_time_days'
    )

    fig, axes = plt.subplots(1, 2, figsize=(16, 5))

    # Left — shipping cost
    sns.heatmap(
        cost_pivot, ax=axes[0], cmap='YlOrRd',
        annot=True, fmt='.2f', linewidths=0.5,
        cbar_kws={'label': 'Ship Cost ($ / unit)'},
        annot_kws={'size': 10},
    )
    axes[0].set_title('Shipping Cost per Unit\n($ / unit)',
                      fontsize=13, fontweight='bold')
    axes[0].set_xlabel('Demand Region')
    axes[0].set_ylabel('Warehouse')

    # Right — lead time
    sns.heatmap(
        lead_pivot, ax=axes[1], cmap='Blues',
        annot=True, fmt='.0f', linewidths=0.5,
        cbar_kws={'label': 'Lead Time (days)'},
        annot_kws={'size': 10},
    )
    axes[1].set_title('Lead Time\n(days)',
                      fontsize=13, fontweight='bold')
    axes[1].set_xlabel('Demand Region')
    axes[1].set_ylabel('Warehouse')

    plt.suptitle('Warehouse-to-Region Lane Costs and Lead Times',
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(FIG_LANE_HM, dpi=150, bbox_inches='tight')
    plt.close(fig)

    # Summary stats
    stats = {
        'cheapest_lane' : lanes.loc[lanes['ship_cost_per_unit'].idxmin(),
                                    ['warehouse_id','demand_region','ship_cost_per_unit']].to_dict(),
        'costliest_lane': lanes.loc[lanes['ship_cost_per_unit'].idxmax(),
                                    ['warehouse_id','demand_region','ship_cost_per_unit']].to_dict(),
        'fastest_lane'  : lanes.loc[lanes['lead_time_days'].idxmin(),
                                    ['warehouse_id','demand_region','lead_time_days']].to_dict(),
        'slowest_lane'  : lanes.loc[lanes['lead_time_days'].idxmax(),
                                    ['warehouse_id','demand_region','lead_time_days']].to_dict(),
    }
    _log_step('plot_lane_heatmap', 'OK', str(stats))
    return stats


def plot_efficiency_scores(lanes):
    """
    WHY  : lane_efficiency_score aggregates cost, speed, and
           distance into a single 0-1 metric.
           Score = 1.0 is the gold standard; 0.0 is worst.
           The optimizer should prefer high-efficiency lanes.
    WHAT : Heatmap of efficiency score (warehouse x region) +
           bar chart of mean efficiency per warehouse.
    """
    logger.info('Plotting Figure 2: efficiency scores ...')

    eff_pivot = lanes.pivot(
        index='warehouse_id', columns='demand_region',
        values='lane_efficiency_score'
    )

    wh_mean_eff = (
        lanes.groupby('warehouse_id')['lane_efficiency_score']
        .mean().sort_values(ascending=False)
    )

    fig, axes = plt.subplots(1, 2, figsize=(16, 5))

    # Left — heatmap
    sns.heatmap(
        eff_pivot, ax=axes[0], cmap='RdYlGn',
        annot=True, fmt='.3f', linewidths=0.5,
        vmin=0, vmax=1,
        cbar_kws={'label': 'Efficiency Score (0=worst, 1=best)'},
        annot_kws={'size': 9},
    )
    axes[0].set_title('Lane Efficiency Score\n(0 = worst, 1 = best)',
                      fontsize=13, fontweight='bold')
    axes[0].set_xlabel('Demand Region')
    axes[0].set_ylabel('Warehouse')

    # Right — mean efficiency per warehouse
    colors = ['#2ca02c' if v >= 0.5 else '#d62728'
              for v in wh_mean_eff.values]
    axes[1].barh(wh_mean_eff.index, wh_mean_eff.values,
                 color=colors, edgecolor='white')
    axes[1].axvline(0.5, color='gray', linestyle='--',
                    linewidth=1.2, label='0.5 midpoint')
    axes[1].set_title('Mean Lane Efficiency by Warehouse',
                      fontsize=13, fontweight='bold')
    axes[1].set_xlabel('Mean Efficiency Score')
    axes[1].set_xlim(0, 1.05)
    axes[1].legend(fontsize=9)
    for i, (wh, val) in enumerate(wh_mean_eff.items()):
        axes[1].text(val + 0.01, i, f'{val:.3f}', va='center', fontsize=9)

    plt.suptitle('Lane Efficiency Analysis',
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(FIG_EFFICIENCY, dpi=150, bbox_inches='tight')
    plt.close(fig)

    stats = {
        'best_wh':      wh_mean_eff.idxmax(),
        'worst_wh':     wh_mean_eff.idxmin(),
        'best_score':   round(float(wh_mean_eff.max()), 4),
        'worst_score':  round(float(wh_mean_eff.min()), 4),
        'perfect_lanes': int((lanes['lane_efficiency_score'] == 1.0).sum()),
        'zero_lanes':    int((lanes['lane_efficiency_score'] == 0.0).sum()),
    }
    _log_step('plot_efficiency_scores', 'OK', str(stats))
    return stats


def plot_carbon_per_unit(lanes):
    """
    WHY  : The dual mandate requires minimizing carbon alongside cost.
           Visualising carbon_kg_per_unit per lane shows which
           routes the optimizer must penalise for sustainability.
    WHAT : Heatmap of computed carbon_kg_per_unit (warehouse x region)
           + scatter of carbon vs ship_cost to reveal trade-offs.
    NOTE : carbon_kg_per_unit in processed data = 0 (placeholder).
           This figure uses the FULL EEA formula computed in load_data.)
    """
    logger.info('Plotting Figure 3: carbon per unit ...')

    carbon_pivot = lanes.pivot(
        index='warehouse_id', columns='demand_region',
        values='carbon_kg_per_unit'
    )

    fig, axes = plt.subplots(1, 2, figsize=(16, 5))

    # Left — carbon heatmap
    sns.heatmap(
        carbon_pivot, ax=axes[0], cmap='Greens',
        annot=True, fmt='.4f', linewidths=0.5,
        cbar_kws={'label': 'Carbon (kg CO2 / unit)'},
        annot_kws={'size': 9},
    )
    axes[0].set_title('Carbon Emissions per Unit\n(kg CO2 — EEA Formula)',
                      fontsize=13, fontweight='bold')
    axes[0].set_xlabel('Demand Region')
    axes[0].set_ylabel('Warehouse')

    # Right — cost vs carbon scatter
    warehouses = lanes['warehouse_id'].unique()
    pal = sns.color_palette('tab10', len(warehouses))
    wh_color = {wh: pal[i] for i, wh in enumerate(sorted(warehouses))}

    for wh in sorted(warehouses):
        sub = lanes[lanes['warehouse_id'] == wh]
        axes[1].scatter(
            sub['ship_cost_per_unit'],
            sub['carbon_kg_per_unit'],
            color=wh_color[wh], s=80, alpha=0.85, label=wh
        )
        for _, row in sub.iterrows():
            axes[1].annotate(
                row['demand_region'],
                (row['ship_cost_per_unit'], row['carbon_kg_per_unit']),
                fontsize=7, alpha=0.7,
                xytext=(3, 3), textcoords='offset points'
            )

    axes[1].set_title('Cost vs Carbon Trade-off\nper Lane',
                      fontsize=13, fontweight='bold')
    axes[1].set_xlabel('Ship Cost ($ / unit)')
    axes[1].set_ylabel('Carbon (kg CO2 / unit)')
    axes[1].legend(title='Warehouse', fontsize=7,
                   bbox_to_anchor=(1.01, 1), loc='upper left')
    axes[1].yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:.4f}'))

    plt.suptitle('Carbon Emissions Analysis — EEA Road Freight Formula',
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(FIG_CARBON, dpi=150, bbox_inches='tight')
    plt.close(fig)

    stats = {
        'min_carbon_kg':  round(float(lanes['carbon_kg_per_unit'].min()), 6),
        'max_carbon_kg':  round(float(lanes['carbon_kg_per_unit'].max()), 6),
        'mean_carbon_kg': round(float(lanes['carbon_kg_per_unit'].mean()), 6),
        'greenest_lane':  lanes.loc[lanes['carbon_kg_per_unit'].idxmin(),
                                    ['warehouse_id','demand_region','carbon_kg_per_unit']].to_dict(),
        'dirtiest_lane':  lanes.loc[lanes['carbon_kg_per_unit'].idxmax(),
                                    ['warehouse_id','demand_region','carbon_kg_per_unit']].to_dict(),
    }
    _log_step('plot_carbon_per_unit', 'OK', str(stats))
    return stats


def write_report(lanes, lane_stats, eff_stats, carbon_stats):
    """
    WHY  : Stakeholders need cost/carbon findings without running code.
    WHAT : Writes reports/report_eda_costs_carbon.md.
    """
    logger.info('Writing markdown report ...')

    rpt = []
    rpt.append('# EDA Report — Costs and Carbon')
    rpt.append('')
    rpt.append(f'**Generated** : {datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}')
    rpt.append(f'**Script**    : {SCRIPT_NAME}')
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 1. Lane Cost Overview')
    rpt.append('')
    rpt.append('![Lane Heatmap](../figures/eda_costs_lane_heatmap.png)')
    rpt.append('')
    rpt.append('| Metric | Warehouse | Region | Value |')
    rpt.append('|--------|-----------|--------|-------|')
    cl = lane_stats['cheapest_lane']
    rpt.append(f"| Cheapest lane | {cl['warehouse_id']} | {cl['demand_region']} | ${cl['ship_cost_per_unit']:.2f}/unit |")
    xl = lane_stats['costliest_lane']
    rpt.append(f"| Costliest lane | {xl['warehouse_id']} | {xl['demand_region']} | ${xl['ship_cost_per_unit']:.2f}/unit |")
    fl = lane_stats['fastest_lane']
    rpt.append(f"| Fastest lane | {fl['warehouse_id']} | {fl['demand_region']} | {fl['lead_time_days']:.0f} day(s) |")
    sl = lane_stats['slowest_lane']
    rpt.append(f"| Slowest lane | {sl['warehouse_id']} | {sl['demand_region']} | {sl['lead_time_days']:.0f} days |")
    rpt.append('')
    rpt.append('**All 20 lanes:**')
    rpt.append('')
    rpt.append('| Warehouse | Region | Ship Cost ($/unit) | Lead Time (days) | Efficiency |')
    rpt.append('|-----------|--------|--------------------|------------------|------------|')
    for _, row in lanes.sort_values(['warehouse_id','demand_region']).iterrows():
        rpt.append(
            f"| {row['warehouse_id']} | {row['demand_region']}"
            f" | ${row['ship_cost_per_unit']:.2f}"
            f" | {row['lead_time_days']:.0f}"
            f" | {row['lane_efficiency_score']:.4f} |"
        )
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 2. Lane Efficiency')
    rpt.append('')
    rpt.append('![Efficiency Scores](../figures/eda_costs_efficiency_scores.png)')
    rpt.append('')
    rpt.append('| Metric | Value |')
    rpt.append('|--------|-------|')
    rpt.append(f'| Best warehouse (avg efficiency) | {eff_stats["best_wh"]} ({eff_stats["best_score"]:.4f}) |')
    rpt.append(f'| Worst warehouse (avg efficiency) | {eff_stats["worst_wh"]} ({eff_stats["worst_score"]:.4f}) |')
    rpt.append(f'| Perfect lanes (score = 1.0) | {eff_stats["perfect_lanes"]} |')
    rpt.append(f'| Zero-score lanes (score = 0.0) | {eff_stats["zero_lanes"]} |')
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 3. Carbon Emissions')
    rpt.append('')
    rpt.append('![Carbon](../figures/eda_costs_carbon_placeholder.png)')
    rpt.append('')
    rpt.append('**Formula:** `carbon_kg = distance_km x weight_tonnes x 0.062`')
    rpt.append('')
    rpt.append('| Metric | Value |')
    rpt.append('|--------|-------|')
    rpt.append(f'| Min carbon per unit | {carbon_stats["min_carbon_kg"]:.6f} kg CO2 |')
    rpt.append(f'| Max carbon per unit | {carbon_stats["max_carbon_kg"]:.6f} kg CO2 |')
    rpt.append(f'| Mean carbon per unit | {carbon_stats["mean_carbon_kg"]:.6f} kg CO2 |')
    gl = carbon_stats['greenest_lane']
    rpt.append(f"| Greenest lane | {gl['warehouse_id']} → {gl['demand_region']} ({gl['carbon_kg_per_unit']:.6f} kg) |")
    dl = carbon_stats['dirtiest_lane']
    rpt.append(f"| Dirtiest lane | {dl['warehouse_id']} → {dl['demand_region']} ({dl['carbon_kg_per_unit']:.6f} kg) |")
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 4. Figures Index')
    rpt.append('')
    rpt.append('| # | Filename | Description |')
    rpt.append('|---|----------|-------------|')
    rpt.append('| 1 | eda_costs_lane_heatmap.png | Ship cost and lead time heatmaps |')
    rpt.append('| 2 | eda_costs_efficiency_scores.png | Lane efficiency heatmap and bar |')
    rpt.append('| 3 | eda_costs_carbon_placeholder.png | Carbon per unit heatmap and scatter |')
    rpt.append('')
    rpt.append('*End of EDA costs and carbon report.*')

    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(REPORT_PATH, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(rpt))

    with open(REPORT_PATH, 'r', encoding='utf-8') as fh:
        content = fh.read()
    assert 'EDA Report' in content,       'Report header missing'
    assert 'Carbon Emissions' in content, 'Carbon section missing'
    assert 'Lane Efficiency' in content,  'Efficiency section missing'
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
    lanes, wh, sku = load_data()

    lane_stats   = plot_lane_heatmap(lanes)
    eff_stats    = plot_efficiency_scores(lanes)
    carbon_stats = plot_carbon_per_unit(lanes)

    write_report(lanes, lane_stats, eff_stats, carbon_stats)
    write_log()

    print()
    print('=' * 60)
    print(f'  {SCRIPT_NAME}  —  COMPLETE')
    print('=' * 60)
    print(f'  Lanes analysed  : {len(lanes)}')
    print(f'  Figures written : 3')
    print(f'  Report          : {REPORT_PATH}')
    print(f'  Log             : {LOG_PATH}')
    print()
    print('  Figures:')
    for fp in [FIG_LANE_HM, FIG_EFFICIENCY, FIG_CARBON]:
        mark = 'OK' if os.path.isfile(fp) else 'MISSING'
        print(f'    [{mark}] {os.path.basename(fp)}')
    print('=' * 60)


if __name__ == '__main__':
    main()
