-- =========================================================
-- Regional Demand Forecasting and Inventory Placement Optimizer
-- Supply chain SQL reference queries
-- Updated: 2026-04-23T20:36:06.740473+00:00
-- =========================================================

/*
Business question:
Which region-category combinations drive the most weekly demand volume,
and how concentrated is that demand across the network?
*/
WITH weekly_demand AS (
    SELECT
        dd.region AS region,
        dd.category AS category,
        dd.year_week AS year_week,
        SUM(dd.units_sold) AS weekly_units
    FROM daily_demand dd
    GROUP BY
        dd.region,
        dd.category,
        dd.year_week
),
ranked_demand AS (
    SELECT
        wd.region AS region,
        wd.category AS category,
        wd.year_week AS year_week,
        wd.weekly_units AS weekly_units,
        RANK() OVER (PARTITION BY wd.region ORDER BY wd.weekly_units DESC) AS region_rank
    FROM weekly_demand wd
)
SELECT
    rd.region AS region,
    rd.category AS category,
    rd.year_week AS year_week,
    rd.weekly_units AS weekly_units,
    rd.region_rank AS region_rank
FROM ranked_demand rd
ORDER BY
    rd.region ASC,
    rd.region_rank ASC,
    rd.year_week ASC;

/*
Business question:
How much lift do holiday and marketing periods add relative to non-event periods?
*/
WITH demand_events AS (
    SELECT
        dd.date AS date,
        dd.region AS region,
        dd.category AS category,
        dd.units_sold AS units_sold,
        COALESCE(ec.is_holiday, 0) AS is_holiday,
        COALESCE(ec.is_marketing_campaign, 0) AS is_marketing_campaign
    FROM daily_demand dd
    LEFT JOIN event_calendar ec
        ON dd.date = ec.date
),
event_summary AS (
    SELECT
        CASE
            WHEN de.is_holiday = 1 THEN 'Holiday'
            WHEN de.is_marketing_campaign = 1 THEN 'Marketing'
            ELSE 'Non-event'
        END AS event_type,
        AVG(de.units_sold) AS avg_units,
        SUM(de.units_sold) AS total_units,
        COUNT(*) AS record_count
    FROM demand_events de
    GROUP BY
        CASE
            WHEN de.is_holiday = 1 THEN 'Holiday'
            WHEN de.is_marketing_campaign = 1 THEN 'Marketing'
            ELSE 'Non-event'
        END
)
SELECT
    es.event_type AS event_type,
    ROUND(es.avg_units, 2) AS avg_units,
    es.total_units AS total_units,
    es.record_count AS record_count
FROM event_summary es
ORDER BY
    es.avg_units DESC,
    es.event_type ASC;

/*
Business question:
Which categories hold the most revenue exposure and how should they be prioritised
under an ABC-style inventory review?
*/
WITH category_revenue AS (
    SELECT
        sm.category AS category,
        SUM(dd.units_sold * sm.unit_price) AS revenue
    FROM daily_demand dd
    INNER JOIN sku_master sm
        ON dd.sku_id = sm.sku_id
    GROUP BY
        sm.category
),
category_share AS (
    SELECT
        cr.category AS category,
        cr.revenue AS revenue,
        100.0 * cr.revenue / SUM(cr.revenue) OVER () AS revenue_share_pct,
        100.0 * SUM(cr.revenue) OVER (ORDER BY cr.revenue DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
            / SUM(cr.revenue) OVER () AS cumulative_share_pct
    FROM category_revenue cr
)
SELECT
    cs.category AS category,
    ROUND(cs.revenue, 2) AS revenue,
    ROUND(cs.revenue_share_pct, 2) AS revenue_share_pct,
    ROUND(cs.cumulative_share_pct, 2) AS cumulative_share_pct,
    CASE
        WHEN cs.cumulative_share_pct <= 80 THEN 'A'
        WHEN cs.cumulative_share_pct <= 95 THEN 'B'
        ELSE 'C'
    END AS abc_class
FROM category_share cs
ORDER BY
    cs.revenue DESC,
    cs.category ASC;

/*
Business question:
Where is the warehouse network most overloaded relative to design capacity?
*/
WITH current_inventory AS (
    SELECT
        si.warehouse AS warehouse,
        SUM(si.inventory_units) AS inventory_units
    FROM starting_inventory_snapshot si
    GROUP BY
        si.warehouse
),
warehouse_capacity AS (
    SELECT
        wh.warehouse AS warehouse,
        wh.capacity_units AS capacity_units,
        wh.daily_storage_cost AS daily_storage_cost
    FROM warehouses wh
),
utilisation_view AS (
    SELECT
        wc.warehouse AS warehouse,
        ci.inventory_units AS inventory_units,
        wc.capacity_units AS capacity_units,
        wc.daily_storage_cost AS daily_storage_cost,
        100.0 * ci.inventory_units / NULLIF(wc.capacity_units, 0) AS utilisation_pct
    FROM warehouse_capacity wc
    INNER JOIN current_inventory ci
        ON wc.warehouse = ci.warehouse
)
SELECT
    uv.warehouse AS warehouse,
    uv.inventory_units AS inventory_units,
    uv.capacity_units AS capacity_units,
    ROUND(uv.utilisation_pct, 2) AS utilisation_pct,
    ROUND(uv.daily_storage_cost, 2) AS daily_storage_cost,
    CASE
        WHEN uv.utilisation_pct >= 100 THEN 'CRITICAL'
        WHEN uv.utilisation_pct >= 85 THEN 'HIGH'
        ELSE 'NORMAL'
    END AS utilisation_status
FROM utilisation_view uv
ORDER BY
    uv.utilisation_pct DESC,
    uv.warehouse ASC;

/*
Business question:
What are the cheapest warehouse-to-region lanes available for routing decisions?
*/
WITH lane_costs AS (
    SELECT
        wrc.warehouse AS warehouse,
        wrc.demand_region AS demand_region,
        wrc.shipping_cost_per_unit AS shipping_cost_per_unit,
        wrc.co2_kg_per_unit AS co2_kg_per_unit
    FROM warehouse_region_costs wrc
),
lane_rank AS (
    SELECT
        lc.warehouse AS warehouse,
        lc.demand_region AS demand_region,
        lc.shipping_cost_per_unit AS shipping_cost_per_unit,
        lc.co2_kg_per_unit AS co2_kg_per_unit,
        RANK() OVER (PARTITION BY lc.demand_region ORDER BY lc.shipping_cost_per_unit ASC, lc.co2_kg_per_unit ASC) AS lane_rank
    FROM lane_costs lc
)
SELECT
    lr.demand_region AS demand_region,
    lr.warehouse AS warehouse,
    ROUND(lr.shipping_cost_per_unit, 4) AS shipping_cost_per_unit,
    ROUND(lr.co2_kg_per_unit, 4) AS co2_kg_per_unit,
    lr.lane_rank AS lane_rank
FROM lane_rank lr
ORDER BY
    lr.demand_region ASC,
    lr.lane_rank ASC,
    lr.warehouse ASC;

/*
Business question:
How does forecast output compare by region and category over the 12-week forward view?
*/
WITH forecast_view AS (
    SELECT
        fw.year_week AS year_week,
        fw.region AS region,
        fw.category AS category,
        fw.forecast_units AS forecast_units,
        fw.lower_pi AS lower_pi,
        fw.upper_pi AS upper_pi
    FROM forecast_12wk_forward fw
),
forecast_summary AS (
    SELECT
        fv.region AS region,
        fv.category AS category,
        SUM(fv.forecast_units) AS total_forecast_units,
        AVG(fv.lower_pi) AS avg_lower_pi,
        AVG(fv.upper_pi) AS avg_upper_pi
    FROM forecast_view fv
    GROUP BY
        fv.region,
        fv.category
)
SELECT
    fs.region AS region,
    fs.category AS category,
    ROUND(fs.total_forecast_units, 2) AS total_forecast_units,
    ROUND(fs.avg_lower_pi, 2) AS avg_lower_pi,
    ROUND(fs.avg_upper_pi, 2) AS avg_upper_pi
FROM forecast_summary fs
ORDER BY
    fs.total_forecast_units DESC,
    fs.region ASC,
    fs.category ASC;