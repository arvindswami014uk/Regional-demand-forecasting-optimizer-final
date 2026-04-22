"""
eda_demand.py
=============
Exploratory Data Analysis — Demand Signal

WHY  : Before building any forecast model we must understand the
       demand signal: its shape, seasonality, event sensitivity,
       and weather relationship. Surprises found here reshape
       every downstream modelling and placement decision.

WHAT : Produces 5 publication-quality figures, 1 markdown report,
       and 1 structured CSV log. All outputs are deterministic
       and reproducible (random seed fixed).

BUSINESS ISSUE SOLVED:
  Amazon-scale inventory placement requires knowing WHICH regions
  spike WHEN and WHY (events vs weather vs organic seasonality).
  Without this the optimizer places stock in the wrong warehouse.

ASSUMPTIONS:
  - daily_demand_clean.csv is the authoritative demand source.
  - sku_master_clean.csv provides the category dimension.
  - week x region x category is the mandatory forecast grain.
  - weather_disruption_index is continuous (z-score-like), NOT binary.

WATCH OUT:
  - Each sku_id appears only ONCE in daily_demand — no per-SKU series.
  - Category must be joined from sku_master, NOT inferred from sku_id.
"""

import os
import sys
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

# ── CONSTANTS ────────────────────────────────────────────────────
SCRIPT_NAME = 'eda_demand.py'
RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

# Two levels up from src/analysis/ = project root
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)

PROCESSED_DIR    = os.path.join(PROJECT_ROOT, 'data', 'processed')
DEMAND_CSV       = os.path.join(PROCESSED_DIR, 'daily_demand_clean.csv')
SKU_MASTER_CSV   = os.path.join(PROCESSED_DIR, 'sku_master_clean.csv')

FIGURES_DIR      = os.path.join(PROJECT_ROOT, 'figures')
REPORTS_DIR      = os.path.join(PROJECT_ROOT, 'reports')
LOGS_DIR         = os.path.join(PROJECT_ROOT, 'outputs', 'logs')

REPORT_PATH      = os.path.join(REPORTS_DIR, 'report_eda_demand.md')
LOG_PATH         = os.path.join(LOGS_DIR,    'log_eda_demand.csv')

FIG_WEEKLY_UNITS = os.path.join(FIGURES_DIR, 'eda_demand_weekly_units_by_region.png')
FIG_BY_CATEGORY  = os.path.join(FIGURES_DIR, 'eda_demand_units_by_category.png')
FIG_HEATMAP      = os.path.join(FIGURES_DIR, 'eda_demand_seasonality_heatmap.png')
FIG_EVENT_IMPACT = os.path.join(FIGURES_DIR, 'eda_demand_event_flag_impact.png')
FIG_WEATHER      = os.path.join(FIGURES_DIR, 'eda_demand_weather_vs_units.png')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(SCRIPT_NAME)

_log_records = []


# ── Helper ───────────────────────────────────────────────────────
def _log_step(step, status, detail=''):
    record = {
        'timestamp': datetime.datetime.utcnow().isoformat(),
        'script':    SCRIPT_NAME,
        'step':      step,
        'status':    status,
        'detail':    str(detail),
    }
    _log_records.append(record)
    logger.info('[%-35s] %-8s %s', step, status, detail)


# ── Step 1: Output directories ───────────────────────────────────
def ensure_output_dirs():
    for d in [FIGURES_DIR, REPORTS_DIR, LOGS_DIR]:
        os.makedirs(d, exist_ok=True)
    _log_step('ensure_output_dirs', 'OK', 'all output dirs ready')


# ── Step 2: Load and join data ───────────────────────────────────
def load_data():
    """
    WHY  : daily_demand has NO category column.
           Category must come from sku_master via left join on sku_id.
    ASSUMPTION: Every sku_id in daily_demand exists in sku_master.
    """
    logger.info('Loading daily_demand_clean.csv ...')
    demand = pd.read_csv(DEMAND_CSV, parse_dates=['date'])
    logger.info('  daily_demand shape : %s', demand.shape)

    logger.info('Loading sku_master_clean.csv ...')
    sku = pd.read_csv(SKU_MASTER_CSV)
    logger.info('  sku_master shape   : %s', sku.shape)

    assert 'sku_id'   in demand.columns, 'sku_id missing from daily_demand'
    assert 'sku_id'   in sku.columns,    'sku_id missing from sku_master'
    assert 'category' in sku.columns,    'category missing from sku_master'

    df = demand.merge(sku[['sku_id', 'category']], on='sku_id', how='left')

    orphans = df['category'].isna().sum()
    assert orphans == 0, f'{orphans} demand rows have no matching category'

    logger.info('  merged shape       : %s', df.shape)
    logger.info('  categories         : %s', sorted(df['category'].unique()))
    logger.info('  regions            : %s', sorted(df['region'].unique()))
    logger.info('  date range         : %s to %s',
                df['date'].min().date(), df['date'].max().date())

    _log_step('load_data', 'OK',
              f'rows={len(df)} cats={df["category"].nunique()} '
              f'regions={df["region"].nunique()}')
    return df


# ── Step 3: Aggregate to week x region x category ────────────────
def build_weekly_grain(df):
    """
    WHY  : All forecasting runs at week x region x category grain.
           Daily data has noise; weekly aggregation is the correct
           planning horizon for replenishment decisions.
    ASSUMPTION: year_week column already present in daily_demand_clean.
    """
    logger.info('Building weekly grain ...')

    assert 'year_week'     in df.columns, 'year_week missing'
    assert 'units_ordered' in df.columns, 'units_ordered missing'

    weekly = (
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

    # Parse week_start date from ISO year-week string e.g. '2024-W27'
    weekly['week_start'] = pd.to_datetime(
        weekly['year_week'] + '-1', format='%G-W%V-%u'
    )

    logger.info('  weekly grain shape : %s', weekly.shape)
    _log_step('build_weekly_grain', 'OK',
              f'rows={len(weekly)} weeks={weekly["year_week"].nunique()} '
              f'total_units={weekly["total_units"].sum():,.0f}')
    return weekly


# ── Step 4: Figure 1 — Weekly units by region ────────────────────
def plot_weekly_units_by_region(weekly):
    """
    WHY  : Regional demand patterns drive warehouse allocation.
           A missed spike in one region causes stockouts while
           another warehouse sits on excess inventory.
    WHAT : Line chart — one line per region, x=week, y=total units.
    """
    logger.info('Plotting Figure 1: weekly units by region ...')

    rw = (
        weekly.groupby(['week_start', 'region'], as_index=False)
        ['total_units'].sum()
    )

    regions = sorted(rw['region'].unique())
    palette = sns.color_palette('tab10', len(regions))

    fig, ax = plt.subplots(figsize=(14, 5))
    for i, region in enumerate(regions):
        sub = rw[rw['region'] == region]
        ax.plot(sub['week_start'], sub['total_units'],
                label=region, color=palette[i], linewidth=1.8)

    ax.set_title('Weekly Units Ordered by Region', fontsize=14, fontweight='bold')
    ax.set_xlabel('Week Starting')
    ax.set_ylabel('Total Units Ordered')
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))
    ax.legend(title='Region', bbox_to_anchor=(1.01, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(FIG_WEEKLY_UNITS, dpi=150, bbox_inches='tight')
    plt.close(fig)

    stats = (
        rw.groupby('region')['total_units']
        .agg(['sum', 'mean', 'std'])
        .round(1)
        .rename(columns={'sum':'total_units','mean':'avg_weekly','std':'std_weekly'})
        .to_dict('index')
    )
    _log_step('plot_weekly_units_by_region', 'OK', FIG_WEEKLY_UNITS)
    return stats


# ── Step 5: Figure 2 — Units by category ─────────────────────────
def plot_units_by_category(weekly):
    """
    WHY  : Category velocity determines which SKUs need the most
           safety stock and the shortest replenishment cycles.
    WHAT : Horizontal bar + pie chart side-by-side.
    """
    logger.info('Plotting Figure 2: units by category ...')

    ct = (
        weekly.groupby('category', as_index=False)['total_units'].sum()
        .sort_values('total_units', ascending=True)
    )
    ct['share_pct'] = (ct['total_units'] / ct['total_units'].sum() * 100).round(1)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    colors = sns.color_palette('muted', len(ct))

    # Horizontal bar
    ax = axes[0]
    ax.barh(ct['category'], ct['total_units'], color=colors)
    ax.set_title('Total Units by Category', fontsize=13, fontweight='bold')
    ax.set_xlabel('Total Units Ordered')
    ax.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))
    for idx, row in ct.iterrows():
        ax.text(row['total_units'] * 1.01, list(ct.index).index(idx),
                f"{row['share_pct']:.1f}%", va='center', fontsize=9)

    # Pie
    ax2 = axes[1]
    ax2.pie(ct['total_units'], labels=ct['category'],
            autopct='%1.1f%%',
            colors=sns.color_palette('muted', len(ct)),
            startangle=140)
    ax2.set_title('Demand Share by Category', fontsize=13, fontweight='bold')

    plt.suptitle('Category Demand Analysis', fontsize=14,
                 fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(FIG_BY_CATEGORY, dpi=150, bbox_inches='tight')
    plt.close(fig)

    stats = ct.set_index('category').to_dict('index')
    _log_step('plot_units_by_category', 'OK', FIG_BY_CATEGORY)
    return stats


# ── Step 6: Figure 3 — Seasonality heatmap ───────────────────────
def plot_seasonality_heatmap(weekly):
    """
    WHY  : Q4 holiday peaks and Prime Day are the largest inventory
           positioning triggers. A heatmap of ISO-week x region
           reveals them more clearly than any line chart.
    WHAT : Pivot rows=week_number, cols=region, values=mean units.
    """
    logger.info('Plotting Figure 3: seasonality heatmap ...')

    pivot = (
        weekly.groupby(['week_number', 'region'], as_index=False)
        ['total_units'].mean()
        .pivot(index='week_number', columns='region', values='total_units')
    )

    fig, ax = plt.subplots(figsize=(12, 10))
    sns.heatmap(pivot, ax=ax, cmap='YlOrRd', linewidths=0.3,
                annot=False,
                cbar_kws={'label': 'Avg Weekly Units'})
    ax.set_title(
        'Demand Seasonality — Avg Weekly Units\n(ISO Week x Region)',
        fontsize=13, fontweight='bold')
    ax.set_xlabel('Region')
    ax.set_ylabel('ISO Week Number')
    plt.tight_layout()
    plt.savefig(FIG_HEATMAP, dpi=150, bbox_inches='tight')
    plt.close(fig)

    hot = pivot.stack().reset_index()
    hot.columns = ['week_number', 'region', 'avg_units']
    top5 = hot.nlargest(5, 'avg_units').to_dict('records')
    _log_step('plot_seasonality_heatmap', 'OK', FIG_HEATMAP)
    return {'top5_hot_cells': top5}


# ── Step 7: Figure 4 — Event flag impact ─────────────────────────
def plot_event_flag_impact(weekly):
    """
    WHY  : Quantifying demand lift per flag validates whether the
           model needs interaction features and how large safety
           stock buffers must be during events.
    WHAT : Box-plots — one panel per flag, flag=0 vs flag=1.
    """
    logger.info('Plotting Figure 4: event flag impact ...')

    flags  = ['holiday_peak_flag', 'prime_event_flag', 'marketing_push_flag']
    labels = ['Holiday Peak',      'Prime Event',       'Marketing Push']

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=False)
    lift_stats = {}

    for ax, flag, label in zip(axes, flags, labels):
        gm = weekly.groupby(flag)['total_units'].mean()
        v0 = gm.get(0, np.nan)
        v1 = gm.get(1, np.nan)
        lift = ((v1 / v0) - 1) * 100 if (v0 and not np.isnan(v0)) else np.nan
        lift_stats[flag] = round(float(lift), 1) if not np.isnan(lift) else None

        sns.boxplot(data=weekly, x=flag, y='total_units', ax=ax,
                    palette=['#4C72B0', '#DD8452'], showfliers=False)

        title_str = f'{label}'
        if lift_stats[flag] is not None:
            title_str += f'\nLift: {lift_stats[flag]:+.1f}%'
        ax.set_title(title_str, fontsize=11, fontweight='bold')
        ax.set_xlabel('Flag Active (1=Yes)')
        ax.set_ylabel('Total Units / Week')
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))

    plt.suptitle('Event Flag Impact on Weekly Demand',
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(FIG_EVENT_IMPACT, dpi=150, bbox_inches='tight')
    plt.close(fig)

    _log_step('plot_event_flag_impact', 'OK', str(lift_stats))
    return lift_stats


# ── Step 8: Figure 5 — Weather disruption vs demand ──────────────
def plot_weather_vs_units(weekly):
    """
    WHY  : weather_disruption_index is a continuous z-score signal.
           Its correlation with demand tells us whether extreme
           weather suppresses or boosts orders.
    WHAT : Scatter + regression line per region, colour=category.
    ASSUMPTION: weather_disruption is continuous, NOT binary.
    """
    logger.info('Plotting Figure 5: weather disruption vs units ...')

    regions = sorted(weekly['region'].unique())
    n = len(regions)
    fig, axes = plt.subplots(1, n, figsize=(5 * n, 5), sharey=False)
    if n == 1:
        axes = [axes]

    corr_stats = {}
    for ax, region in zip(axes, regions):
        sub  = weekly[weekly['region'] == region]
        r    = sub['weather_disruption'].corr(sub['total_units'])
        corr_stats[region] = round(float(r), 3)

        cats = sorted(sub['category'].unique())
        pal  = sns.color_palette('tab10', len(cats))
        for j, cat in enumerate(cats):
            cd = sub[sub['category'] == cat]
            ax.scatter(cd['weather_disruption'], cd['total_units'],
                       alpha=0.45, s=18, color=pal[j], label=cat)

        xv = sub['weather_disruption'].values
        yv = sub['total_units'].values
        if len(xv) > 1 and np.std(xv) > 0:
            m, b = np.polyfit(xv, yv, 1)
            xs = np.sort(xv)
            ax.plot(xs, m * xs + b, 'k--', linewidth=1.5,
                    label=f'Trend (r={r:.2f})')

        ax.set_title(f'{region}\nr = {r:.3f}', fontsize=11, fontweight='bold')
        ax.set_xlabel('Weather Disruption Index')
        ax.set_ylabel('Total Units / Week')
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))
        if region == regions[0]:
            ax.legend(fontsize=7, loc='upper right')

    plt.suptitle('Weather Disruption Index vs Weekly Demand',
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(FIG_WEATHER, dpi=150, bbox_inches='tight')
    plt.close(fig)

    _log_step('plot_weather_vs_units', 'OK', str(corr_stats))
    return corr_stats


# ── Step 9: Markdown report ───────────────────────────────────────
def write_report(region_stats, cat_stats, seasonality,
                 lift_stats, weather_corr, weekly):
    """
    WHY  : Stakeholders need findings without running code.
    WHAT : Writes reports/report_eda_demand.md with stats + fig refs.
    """
    logger.info('Writing markdown report ...')

    total_units = int(weekly['total_units'].sum())
    n_weeks     = weekly['year_week'].nunique()
    n_regions   = weekly['region'].nunique()
    n_cats      = weekly['category'].nunique()
    date_min    = weekly['week_start'].min().date()
    date_max    = weekly['week_start'].max().date()

    rpt = []
    rpt.append('# EDA Report — Demand Signal')
    rpt.append('')
    rpt.append(f'**Generated** : {datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}')
    rpt.append(f'**Script**    : {SCRIPT_NAME}')
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 1. Dataset Overview')
    rpt.append('')
    rpt.append('| Metric | Value |')
    rpt.append('|--------|-------|')
    rpt.append(f'| Weekly grain rows | {len(weekly):,} |')
    rpt.append(f'| ISO weeks covered | {n_weeks} |')
    rpt.append(f'| Date range | {date_min} to {date_max} |')
    rpt.append(f'| Regions | {n_regions} |')
    rpt.append(f'| Categories | {n_cats} |')
    rpt.append(f'| Total units ordered | {total_units:,} |')
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 2. Regional Demand Patterns')
    rpt.append('')
    rpt.append('![Weekly Units by Region](../figures/eda_demand_weekly_units_by_region.png)')
    rpt.append('')
    rpt.append('| Region | Total Units | Avg Weekly | Std Dev |')
    rpt.append('|--------|-------------|------------|---------|')
    for region, s in sorted(region_stats.items()):
        rpt.append(
            f"| {region} | {s['total_units']:,.0f} |"
            f" {s['avg_weekly']:,.1f} | {s['std_weekly']:,.1f} |"
        )
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 3. Category Demand Share')
    rpt.append('')
    rpt.append('![Units by Category](../figures/eda_demand_units_by_category.png)')
    rpt.append('')
    rpt.append('| Category | Total Units | Share % |')
    rpt.append('|----------|-------------|---------|')
    for cat, s in sorted(cat_stats.items(),
                         key=lambda x: -x[1]['total_units']):
        rpt.append(f"| {cat} | {s['total_units']:,.0f} | {s['share_pct']:.1f}% |")
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 4. Seasonality Heatmap')
    rpt.append('')
    rpt.append('![Seasonality Heatmap](../figures/eda_demand_seasonality_heatmap.png)')
    rpt.append('')
    rpt.append('**Top-5 hottest week x region cells:**')
    rpt.append('')
    rpt.append('| Rank | ISO Week | Region | Avg Units |')
    rpt.append('|------|----------|--------|-----------|')
    for i, cell in enumerate(seasonality.get('top5_hot_cells', []), 1):
        rpt.append(
            f"| {i} | W{int(cell['week_number']):02d}"
            f" | {cell['region']} | {cell['avg_units']:,.1f} |"
        )
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 5. Event Flag Demand Lift')
    rpt.append('')
    rpt.append('![Event Flag Impact](../figures/eda_demand_event_flag_impact.png)')
    rpt.append('')
    rpt.append('| Flag | Demand Lift When Active |')
    rpt.append('|------|------------------------|')
    flag_display = {
        'holiday_peak_flag':   'Holiday Peak',
        'prime_event_flag':    'Prime Event',
        'marketing_push_flag': 'Marketing Push',
    }
    for flag, label in flag_display.items():
        val = lift_stats.get(flag)
        if val is not None:
            rpt.append(f'| {label} | {val:+.1f}% |')
        else:
            rpt.append(f'| {label} | N/A |')
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 6. Weather Disruption vs Demand')
    rpt.append('')
    rpt.append('![Weather vs Units](../figures/eda_demand_weather_vs_units.png)')
    rpt.append('')
    rpt.append('| Region | Pearson r |')
    rpt.append('|--------|-----------|')
    for region, r in sorted(weather_corr.items()):
        rpt.append(f'| {region} | {r:.3f} |')
    rpt.append('')
    rpt.append('---')
    rpt.append('')
    rpt.append('## 7. Figures Index')
    rpt.append('')
    rpt.append('| # | Filename | Description |')
    rpt.append('|---|----------|-------------|')
    rpt.append('| 1 | eda_demand_weekly_units_by_region.png | Weekly demand trends per region |')
    rpt.append('| 2 | eda_demand_units_by_category.png | Category demand share |')
    rpt.append('| 3 | eda_demand_seasonality_heatmap.png | ISO-week x region heatmap |')
    rpt.append('| 4 | eda_demand_event_flag_impact.png | Box-plots of flag lift |')
    rpt.append('| 5 | eda_demand_weather_vs_units.png | Weather scatter per region |')
    rpt.append('')
    rpt.append('*End of EDA demand report.*')

    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(REPORT_PATH, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(rpt))

    # Validate
    with open(REPORT_PATH, 'r', encoding='utf-8') as fh:
        content = fh.read()
    assert 'EDA Report' in content,          'Report header missing'
    assert 'Weekly Units by Region' in content, 'Section 2 missing'
    logger.info('  Report written : %s', REPORT_PATH)
    _log_step('write_report', 'OK', REPORT_PATH)


# ── Step 10: CSV log ─────────────────────────────────────────────
def write_log():
    """Write all accumulated step records to log_eda_demand.csv."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    fieldnames = ['timestamp', 'script', 'step', 'status', 'detail']
    with open(LOG_PATH, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(_log_records)
    logger.info('Log written : %s  (%d records)', LOG_PATH, len(_log_records))


# ── Step 11: main ────────────────────────────────────────────────
def main():
    logger.info('=' * 60)
    logger.info('START  %s', SCRIPT_NAME)
    logger.info('=' * 60)

    ensure_output_dirs()
    df     = load_data()
    weekly = build_weekly_grain(df)

    region_stats = plot_weekly_units_by_region(weekly)
    cat_stats    = plot_units_by_category(weekly)
    seasonality  = plot_seasonality_heatmap(weekly)
    lift_stats   = plot_event_flag_impact(weekly)
    weather_corr = plot_weather_vs_units(weekly)

    write_report(region_stats, cat_stats, seasonality,
                 lift_stats, weather_corr, weekly)
    write_log()

    print()
    print('=' * 60)
    print(f'  {SCRIPT_NAME}  —  COMPLETE')
    print('=' * 60)
    print(f'  Weekly grain rows : {len(weekly):,}')
    print(f'  Figures written   : 5')
    print(f'  Report            : {REPORT_PATH}')
    print(f'  Log               : {LOG_PATH}')
    print()
    print('  Figures:')
    for fp in [FIG_WEEKLY_UNITS, FIG_BY_CATEGORY, FIG_HEATMAP,
                FIG_EVENT_IMPACT, FIG_WEATHER]:
        mark = 'OK' if os.path.isfile(fp) else 'MISSING'
        print(f'    [{mark}] {os.path.basename(fp)}')
    print('=' * 60)


if __name__ == '__main__':
    main()
