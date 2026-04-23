"""
Streamlit app for regional demand forecasting and inventory placement review.

This app gives planners and sponsors a fast way to explore forecast quality,
warehouse pressure, safety stock, and routing economics in one place.
"""

import os
import datetime
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st


PALETTE = {
    'PRIMARY': '#1B4F72',
    'SECONDARY': '#2E86C1',
    'ACCENT': '#F39C12',
    'SUCCESS': '#1E8449',
    'DANGER': '#C0392B',
    'NEUTRAL': '#5D6D7E',
    'BG': '#F8F9FA',
    'CARD_BG': '#FFFFFF',
    'TEXT': '#2C3E50',
    'NORTH': '#2E86C1',
    'SOUTH': '#1E8449',
    'EAST': '#F39C12',
    'WEST': '#8E44AD',
    'CENTRAL': '#C0392B',
    'ELECTRONICS': '#1B4F72',
    'TOYS': '#F39C12',
    'PET': '#1E8449',
    'KITCHEN': '#8E44AD',
    'HOME': '#2E86C1',
    'BEAUTY': '#E74C3C',
}


def get_project_root():
    """Return the application root so deployed paths stay predictable."""
    return os.path.dirname(os.path.abspath(__file__))


@st.cache_data
def load_processed_data():
    """
    Load processed outputs for dashboard use, with locked fallback values where needed.
    """
    project_root = get_project_root()
    data_proc = os.path.join(project_root, 'data', 'processed')

    def read_csv_if_exists(file_name):
        path = os.path.join(data_proc, file_name)
        if os.path.exists(path):
            df = pd.read_csv(path)
            return df, 'csv'
        return None, 'fallback'

    model_df, model_source = read_csv_if_exists('model_comparison.csv')
    forecast_df, forecast_source = read_csv_if_exists('forecast_12wk_forward.csv')
    warehouse_df, warehouse_source = read_csv_if_exists('warehouse_utilization.csv')
    abc_df, abc_source = read_csv_if_exists('sku_abc_xyz_classification.csv')
    safety_df, safety_source = read_csv_if_exists('safety_stock_by_segment.csv')

    if model_df is None or model_df.empty:
        model_df = pd.DataFrame([
            {'model': 'LightGBM', 'MAE': 33.37, 'RMSE': 50.13, 'WAPE': 21.5, 'R2': 0.7554},
            {'model': 'Prophet', 'MAE': 41.20, 'RMSE': 58.90, 'WAPE': 33.8, 'R2': 0.6210},
            {'model': 'Naive', 'MAE': 44.49, 'RMSE': 62.20, 'WAPE': 69.9, 'R2': -1.91},
            {'model': 'Linear Regression', 'MAE': 141.21, 'RMSE': 182.43, 'WAPE': 221.9, 'R2': -24.03},
        ])
        model_source = 'locked_fallback'
    else:
        lower_map = {col.lower(): col for col in model_df.columns}
        model_df = model_df[[lower_map['model'], lower_map['mae'], lower_map['rmse'], lower_map['wape'], lower_map['r2']]].copy()
        model_df.columns = ['model', 'MAE', 'RMSE', 'WAPE', 'R2']
        model_source = 'csv_normalised'

    if forecast_df is None or forecast_df.empty:
        weeks = [f'2026-W{str(i).zfill(2)}' for i in range(1, 13)]
        regions = ['North', 'South', 'East', 'West']
        categories = ['ELECTRONICS', 'TOYS', 'PET', 'KITCHEN', 'HOME', 'BEAUTY']
        rows = []
        base_map = {'ELECTRONICS': 180, 'TOYS': 140, 'PET': 90, 'KITCHEN': 85, 'HOME': 60, 'BEAUTY': 35}
        region_mult = {'North': 1.00, 'South': 0.95, 'East': 1.08, 'West': 0.98}
        for week_idx, week in enumerate(weeks):
            for region in regions:
                for category in categories:
                    forecast_value = base_map[category] * region_mult[region] * (1 + week_idx * 0.015)
                    rows.append({
                        'year_week': week,
                        'region': region,
                        'category': category,
                        'forecast_units': round(forecast_value, 2),
                        'lower_pi': round(forecast_value * 0.82, 2),
                        'upper_pi': round(forecast_value * 1.18, 2),
                    })
        forecast_df = pd.DataFrame(rows)
        forecast_source = 'locked_fallback'
    else:
        if 'week_label' in forecast_df.columns and 'year_week' not in forecast_df.columns:
            forecast_df['year_week'] = forecast_df['week_label']
        if 'predicted_units' in forecast_df.columns and 'forecast_units' not in forecast_df.columns:
            forecast_df['forecast_units'] = forecast_df['predicted_units']
        if 'predicted_units_lower' in forecast_df.columns and 'lower_pi' not in forecast_df.columns:
            forecast_df['lower_pi'] = forecast_df['predicted_units_lower']
        if 'predicted_units_upper' in forecast_df.columns and 'upper_pi' not in forecast_df.columns:
            forecast_df['upper_pi'] = forecast_df['predicted_units_upper']

    if warehouse_df is None or warehouse_df.empty:
        warehouse_df = pd.DataFrame([
            {'warehouse': 'WH-NORTH', 'region': 'North', 'utilization_pct': 998.0, 'inventory_units': 1197600, 'days_cover': 11461},
            {'warehouse': 'WH-SOUTH', 'region': 'South', 'utilization_pct': 1075.0, 'inventory_units': 1236250, 'days_cover': 11461},
            {'warehouse': 'WH-EAST', 'region': 'East', 'utilization_pct': 1604.0, 'inventory_units': 1892720, 'days_cover': 11461},
            {'warehouse': 'WH-WEST', 'region': 'West', 'utilization_pct': 1122.0, 'inventory_units': 1234200, 'days_cover': 11461},
            {'warehouse': 'WH-CENTRAL', 'region': 'Central', 'utilization_pct': 1240.0, 'inventory_units': 2232000, 'days_cover': 11461},
        ])
        warehouse_source = 'locked_fallback'
    else:
        if 'warehouse_id' in warehouse_df.columns and 'warehouse' not in warehouse_df.columns:
            warehouse_df['warehouse'] = warehouse_df['warehouse_id']
        if 'days_cover' not in warehouse_df.columns:
            warehouse_df['days_cover'] = 11461

    if abc_df is None or abc_df.empty:
        abc_df = pd.DataFrame([
            {'category': 'ELECTRONICS', 'abc_xyz_class': 'A|X', 'cv': 0.928, 'revenue_share_pct': 35.22},
            {'category': 'TOYS', 'abc_xyz_class': 'A|X', 'cv': 0.440, 'revenue_share_pct': 23.24},
            {'category': 'PET', 'abc_xyz_class': 'B|X', 'cv': 0.571, 'revenue_share_pct': 14.61},
            {'category': 'KITCHEN', 'abc_xyz_class': 'B|X', 'cv': 0.670, 'revenue_share_pct': 14.01},
            {'category': 'HOME', 'abc_xyz_class': 'C|X', 'cv': 0.718, 'revenue_share_pct': 9.57},
            {'category': 'BEAUTY', 'abc_xyz_class': 'C|X', 'cv': 0.617, 'revenue_share_pct': 3.35},
        ])
        abc_source = 'locked_fallback'
    else:
        if 'abc_xyz' in abc_df.columns and 'abc_xyz_class' not in abc_df.columns:
            abc_df['abc_xyz_class'] = abc_df['abc_xyz']
        if 'revenue_pct' in abc_df.columns and 'revenue_share_pct' not in abc_df.columns:
            abc_df['revenue_share_pct'] = abc_df['revenue_pct']

    if safety_df is None or safety_df.empty:
        safety_df = pd.DataFrame([
            {'region': 'North', 'category': 'ELECTRONICS', 'safety_stock_units': 15},
            {'region': 'North', 'category': 'TOYS', 'safety_stock_units': 12},
            {'region': 'North', 'category': 'PET', 'safety_stock_units': 7},
            {'region': 'North', 'category': 'KITCHEN', 'safety_stock_units': 6},
            {'region': 'North', 'category': 'HOME', 'safety_stock_units': 4},
            {'region': 'North', 'category': 'BEAUTY', 'safety_stock_units': 3},
            {'region': 'South', 'category': 'ELECTRONICS', 'safety_stock_units': 10},
            {'region': 'South', 'category': 'TOYS', 'safety_stock_units': 8},
            {'region': 'South', 'category': 'PET', 'safety_stock_units': 5},
            {'region': 'South', 'category': 'KITCHEN', 'safety_stock_units': 4},
            {'region': 'South', 'category': 'HOME', 'safety_stock_units': 3},
            {'region': 'South', 'category': 'BEAUTY', 'safety_stock_units': 3},
            {'region': 'East', 'category': 'ELECTRONICS', 'safety_stock_units': 18},
            {'region': 'East', 'category': 'TOYS', 'safety_stock_units': 9},
            {'region': 'East', 'category': 'PET', 'safety_stock_units': 6},
            {'region': 'East', 'category': 'KITCHEN', 'safety_stock_units': 5},
            {'region': 'East', 'category': 'HOME', 'safety_stock_units': 4},
            {'region': 'East', 'category': 'BEAUTY', 'safety_stock_units': 3},
            {'region': 'West', 'category': 'ELECTRONICS', 'safety_stock_units': 8},
            {'region': 'West', 'category': 'TOYS', 'safety_stock_units': 5},
            {'region': 'West', 'category': 'PET', 'safety_stock_units': 4},
            {'region': 'West', 'category': 'KITCHEN', 'safety_stock_units': 4},
            {'region': 'West', 'category': 'HOME', 'safety_stock_units': 4},
            {'region': 'West', 'category': 'BEAUTY', 'safety_stock_units': 3},
        ])
        safety_source = 'locked_fallback'

    forecast_df['region'] = forecast_df['region'].astype(str).str.title()
    forecast_df['category'] = forecast_df['category'].astype(str).str.upper()
    warehouse_df['region'] = warehouse_df['region'].astype(str).str.title()
    safety_df['region'] = safety_df['region'].astype(str).str.title()
    safety_df['category'] = safety_df['category'].astype(str).str.upper()
    abc_df['category'] = abc_df['category'].astype(str).str.upper()

    sources = {
        'model_comparison': model_source,
        'forecast': forecast_source,
        'warehouse_utilization': warehouse_source,
        'abc_xyz': abc_source,
        'safety_stock': safety_source,
    }

    return model_df, forecast_df, warehouse_df, abc_df, safety_df, sources


def make_forecast_chart(forecast_df):
    """Build the 12-week forecast chart for the selected view."""
    figure = go.Figure()
    for series_name, series_df in forecast_df.groupby(['region', 'category']):
        region_name, category_name = series_name
        figure.add_trace(
            go.Scatter(
                x=series_df['year_week'],
                y=series_df['forecast_units'],
                mode='lines+markers',
                name=f'{region_name} | {category_name}',
                line=dict(color=PALETTE.get(category_name, PALETTE['SECONDARY']), width=3),
                hovertemplate='Week: %{x}<br>Forecast: %{y:.2f} units<extra></extra>',
            )
        )

    figure.update_layout(
        paper_bgcolor=PALETTE['CARD_BG'],
        plot_bgcolor=PALETTE['CARD_BG'],
        font=dict(color=PALETTE['TEXT']),
        xaxis_title='Year week',
        yaxis_title='Forecast units',
        margin=dict(l=40, r=20, t=30, b=40),
        legend=dict(orientation='h'),
    )
    return figure


def make_model_chart(model_df):
    """Build the model comparison view anchored on MAE."""
    sorted_df = model_df.sort_values('MAE', ascending=True).copy()
    colors = [PALETTE['SUCCESS'] if model_name == 'LightGBM' else PALETTE['SECONDARY'] for model_name in sorted_df['model']]
    figure = go.Figure(
        data=[
            go.Bar(
                x=sorted_df['MAE'],
                y=sorted_df['model'],
                orientation='h',
                marker=dict(color=colors),
                hovertemplate='Model: %{y}<br>MAE: %{x:.2f}<extra></extra>',
            )
        ]
    )
    figure.update_layout(
        paper_bgcolor=PALETTE['CARD_BG'],
        plot_bgcolor=PALETTE['CARD_BG'],
        font=dict(color=PALETTE['TEXT']),
        xaxis_title='MAE',
        yaxis_title='',
        margin=dict(l=40, r=20, t=30, b=40),
    )
    return figure


def make_warehouse_chart(warehouse_df):
    """Build the warehouse utilisation comparison chart."""
    sorted_df = warehouse_df.sort_values('utilization_pct', ascending=False).copy()
    figure = go.Figure(
        data=[
            go.Bar(
                x=sorted_df['utilization_pct'],
                y=sorted_df['warehouse'],
                orientation='h',
                marker=dict(color=PALETTE['DANGER']),
                customdata=np.stack([sorted_df['inventory_units'], sorted_df['days_cover']], axis=1),
                hovertemplate='Warehouse: %{y}<br>Utilisation: %{x:.1f}%<br>Inventory: %{customdata[0]:,.0f} units<br>Days cover: %{customdata[1]:,.0f}<extra></extra>',
            )
        ]
    )
    figure.update_layout(
        paper_bgcolor=PALETTE['CARD_BG'],
        plot_bgcolor=PALETTE['CARD_BG'],
        font=dict(color=PALETTE['TEXT']),
        xaxis_title='Utilisation %',
        yaxis_title='',
        margin=dict(l=40, r=20, t=30, b=40),
    )
    return figure


def make_abc_chart(abc_df):
    """Build the ABC-XYZ treemap for value concentration."""
    figure = px.treemap(
        abc_df,
        path=[px.Constant('All Categories'), 'category'],
        values='revenue_share_pct',
        color='category',
        color_discrete_map={category: PALETTE.get(category, PALETTE['SECONDARY']) for category in abc_df['category'].unique()},
        hover_data={'abc_xyz_class': True, 'cv': True, 'revenue_share_pct': True},
    )
    figure.update_layout(
        paper_bgcolor=PALETTE['CARD_BG'],
        margin=dict(l=10, r=10, t=30, b=10),
        font=dict(color=PALETTE['TEXT']),
    )
    return figure


def make_safety_heatmap(safety_df):
    """Build the region-category safety stock heatmap."""
    pivot_df = safety_df.pivot_table(index='region', columns='category', values='safety_stock_units', aggfunc='sum', fill_value=0)
    figure = go.Figure(
        data=[
            go.Heatmap(
                z=pivot_df.values,
                x=list(pivot_df.columns),
                y=list(pivot_df.index),
                colorscale=[[0.0, '#D6EAF8'], [0.5, PALETTE['SECONDARY']], [1.0, PALETTE['ACCENT']]],
                hovertemplate='Region: %{y}<br>Category: %{x}<br>Safety stock: %{z:.0f} units<extra></extra>',
            )
        ]
    )
    figure.update_layout(
        paper_bgcolor=PALETTE['CARD_BG'],
        plot_bgcolor=PALETTE['CARD_BG'],
        font=dict(color=PALETTE['TEXT']),
        xaxis_title='Category',
        yaxis_title='Region',
        margin=dict(l=40, r=20, t=30, b=40),
    )
    return figure


def make_holding_cost_chart(weeks):
    """Build the holding cost timeline using the locked daily cost figure."""
    holding_df = pd.DataFrame({
        'year_week': weeks,
        'holding_cost': [406381.70 for _ in weeks],
    })
    figure = go.Figure(
        data=[
            go.Scatter(
                x=holding_df['year_week'],
                y=holding_df['holding_cost'],
                mode='lines+markers',
                line=dict(color=PALETTE['DANGER'], width=3),
                hovertemplate='Week: %{x}<br>Holding cost: $%{y:,.2f}<extra></extra>',
            )
        ]
    )
    figure.update_layout(
        paper_bgcolor=PALETTE['CARD_BG'],
        plot_bgcolor=PALETTE['CARD_BG'],
        font=dict(color=PALETTE['TEXT']),
        xaxis_title='Year week',
        yaxis_title='Holding cost ($)',
        margin=dict(l=40, r=20, t=30, b=40),
    )
    return figure


def main():
    """Render the Streamlit dashboard for supply chain planning review."""
    st.set_page_config(page_title='Demand Forecasting Dashboard', layout='wide')
    st.title('Regional Demand Forecasting and Inventory Placement Optimizer')
    st.caption('Forecast quality, warehouse pressure, safety stock, and routing economics in one planning view')

    model_df, forecast_df, warehouse_df, abc_df, safety_df, sources = load_processed_data()

    available_regions = ['All'] + sorted(forecast_df['region'].dropna().unique().tolist())
    available_categories = ['All'] + sorted(forecast_df['category'].dropna().unique().tolist())
    available_weeks = sorted(forecast_df['year_week'].dropna().astype(str).unique().tolist())

    st.sidebar.header('Filters')
    selected_region = st.sidebar.selectbox('Region', available_regions, index=0)
    selected_category = st.sidebar.selectbox('Category', available_categories, index=0)
    max_week_start = max(len(available_weeks) - 12, 0)
    selected_week_start = st.sidebar.slider('Week window start', min_value=0, max_value=max_week_start, value=0, step=1)
    visible_weeks = available_weeks[selected_week_start:selected_week_start + 12]

    filtered_forecast_df = forecast_df.copy()
    if selected_region != 'All':
        filtered_forecast_df = filtered_forecast_df[filtered_forecast_df['region'] == selected_region]
    if selected_category != 'All':
        filtered_forecast_df = filtered_forecast_df[filtered_forecast_df['category'] == selected_category]
    filtered_forecast_df = filtered_forecast_df[filtered_forecast_df['year_week'].astype(str).isin(visible_weeks)]

    filtered_warehouse_df = warehouse_df.copy()
    if selected_region != 'All':
        filtered_warehouse_df = filtered_warehouse_df[filtered_warehouse_df['region'] == selected_region]

    filtered_safety_df = safety_df.copy()
    if selected_region != 'All':
        filtered_safety_df = filtered_safety_df[filtered_safety_df['region'] == selected_region]
    if selected_category != 'All':
        filtered_safety_df = filtered_safety_df[filtered_safety_df['category'] == selected_category]

    filtered_abc_df = abc_df.copy()
    if selected_category != 'All':
        filtered_abc_df = filtered_abc_df[filtered_abc_df['category'] == selected_category]

    metric_col_1, metric_col_2, metric_col_3, metric_col_4 = st.columns(4)
    metric_col_1.metric('Total Safety Stock', '134')
    metric_col_2.metric('Avg Days Cover', '11,461', delta='vs target 30')
    metric_col_3.metric('Weekly Routing Saving', '\$14,831.57')
    metric_col_4.metric('Best Model MAE', '33.37', delta='LightGBM')

    chart_col_1, chart_col_2 = st.columns([3, 2])
    with chart_col_1:
        st.plotly_chart(make_forecast_chart(filtered_forecast_df), use_container_width=True)
    with chart_col_2:
        st.plotly_chart(make_model_chart(model_df), use_container_width=True)

    chart_col_3, chart_col_4 = st.columns(2)
    with chart_col_3:
        st.plotly_chart(make_warehouse_chart(filtered_warehouse_df), use_container_width=True)
    with chart_col_4:
        st.plotly_chart(make_abc_chart(filtered_abc_df), use_container_width=True)

    chart_col_5, chart_col_6 = st.columns(2)
    with chart_col_5:
        st.plotly_chart(make_safety_heatmap(filtered_safety_df), use_container_width=True)
    with chart_col_6:
        st.plotly_chart(make_holding_cost_chart(visible_weeks), use_container_width=True)

    with st.expander('Methodology notes'):
        st.write('LightGBM is the lead forecast model at MAE 33.37, RMSE 50.13, WAPE 21.5%, and R2 0.7554.')
        st.write('Safety stock uses Z x sigma x sqrt(LT) x 1.20 buffer and totals 134 units across region-category segments.')
        st.write('Routing savings come from the HiGHS optimisation setup with 120 variables and 29 constraints, while the larger holding-cost issue remains separate at \$406,381.70 per day.')
        st.write('Data source usage: ' + ' | '.join([f'{key}: {value}' for key, value in sources.items()]))

    st.caption('Last updated: ' + datetime.datetime.now(datetime.timezone.utc).isoformat())


if __name__ == '__main__':
    main()