-- ============================================================
-- SUPPLY CHAIN SQL QUERIES
-- Regional Demand Forecasting and Inventory Placement Optimizer
-- Amazon-Inspired Capstone Project
-- Author : Arvind Swami
-- Date   : April 2026
-- ============================================================
--
-- DATASET REFERENCE:
--   daily_demand_clean          5,000 x 16   transaction grain
--   fact_demand_enriched        5,000 x 33   enriched demand
--   forecast_residual_std          24 x 8    CV per segment
--   safety_stock_by_segment        24 x 10   SS per segment
--   service_level_breach_report    24 x 17   SL compliance
--   pbi_demand_summary          1,549 x 54   Power BI demand
--   pbi_inventory_summary           5 x 11   Power BI WH
--   pbi_cost_summary                4 x 9    Power BI costs
--
-- LOCKED-IN RESULTS (all queries expected to reproduce):
--   Holiday lift   : +64.8%   p<0.0001
--   Marketing lift : +71.4%   p<0.0001
--   Total SS       : 134 units across 24 segments
--   SL breaches    : 0 (24/24 segments compliant)
--   LP saving      : 63.2% weekly shipping cost reduction
-- ============================================================


-- ============================================================
-- Q1: WEEKLY DEMAND BY REGION AND CATEGORY
-- ============================================================
-- Business purpose:
--   Identify seasonal demand peaks and regional patterns.
--   Used to validate LightGBM forecast against raw actuals
--   and to set replenishment trigger levels by segment.
--
-- Expected output: 1 row per year_week x region x category
--   ~1,540 rows (81 weeks x 4 regions x 6 categories)
-- ============================================================

SELECT
    year_week,
    region,
    category,
    SUM(units_ordered)                              AS total_units,
    ROUND(AVG(units_ordered), 2)                   AS avg_daily_units,
    MAX(units_ordered)                              AS peak_units,
    MIN(units_ordered)                              AS min_units,
    COUNT(*)                                        AS transaction_count
FROM daily_demand_clean
GROUP BY
    year_week,
    region,
    category
ORDER BY
    year_week,
    region,
    category;


-- ============================================================
-- Q2: TOP 10 SKUs BY TOTAL REVENUE
-- ============================================================
-- Business purpose:
--   Identify highest-value SKUs for priority handling,
--   safety stock protection, and dedicated warehouse slots.
--   A-class SKUs (ELECTRONICS, TOYS) should dominate this list.
--
-- Expected output: 10 rows
--   Top SKUs likely from ELECTRONICS (35.22% revenue share)
-- ============================================================

SELECT
    d.sku_id,
    s.category,
    d.region,
    SUM(d.transaction_price_usd)                   AS total_revenue,
    SUM(d.units_ordered)                           AS total_units,
    ROUND(
        SUM(d.transaction_price_usd) / SUM(d.units_ordered),
        2
    )                                              AS avg_price_per_unit
FROM fact_demand_enriched d
JOIN sku_master_clean s
    ON d.sku_id = s.sku_id
GROUP BY
    d.sku_id,
    s.category,
    d.region
ORDER BY
    total_revenue DESC
LIMIT 10;


-- ============================================================
-- Q3: HOLIDAY VS NON-HOLIDAY DEMAND UPLIFT
-- ============================================================
-- Business purpose:
--   Quantify promotional impact for forward planning.
--   Results should reproduce the Mann-Whitney finding:
--   +64.8% demand uplift during holiday weeks (p<0.0001).
--   Used to set promotional safety stock buffers.
--
-- Expected output: 2 rows (holiday_peak_flag = 0 and 1)
--   holiday=1 avg_weekly_demand should be ~64.8% higher
--   than holiday=0 avg_weekly_demand
-- ============================================================

SELECT
    holiday_peak_flag,
    COUNT(*)                                       AS week_segments,
    ROUND(AVG(total_units), 2)                     AS avg_weekly_demand,
    ROUND(MAX(total_units), 2)                     AS peak_demand,
    ROUND(MIN(total_units), 2)                     AS min_demand,
    ROUND(STDDEV(total_units), 2)                  AS demand_stddev,
    ROUND(
        AVG(total_units) FILTER (WHERE holiday_peak_flag = 1)
        / NULLIF(AVG(total_units) FILTER (WHERE holiday_peak_flag = 0), 0)
        * 100 - 100,
        1
    )                                              AS uplift_pct
FROM pbi_demand_summary
GROUP BY
    holiday_peak_flag
ORDER BY
    holiday_peak_flag;
-- Expected: holiday=1 shows +64.8% uplift vs holiday=0


-- ============================================================
-- Q4: WAREHOUSE UTILISATION AND OVERSTOCK SUMMARY
-- ============================================================
-- Business purpose:
--   Quantify overstock severity per warehouse.
--   All 5 warehouses expected to show CRITICAL status
--   (days_of_cover >> 365 days).
--   Drives the P1 recommendation: staged inventory liquidation.
--
-- Expected output: 5 rows (one per warehouse)
--   All rows: overstock_status = CRITICAL
--   Days of cover range: 10,557 (WH-WEST) to 11,844 (WH-SOUTH)
--   Total daily holding cost: \$406,381.70/day
-- ============================================================

SELECT
    warehouse_id,
    home_region,
    capacity_units,
    starting_inventory_units,
    ROUND(starting_utilisation_pct, 2)             AS utilisation_pct,
    days_of_cover,
    ROUND(daily_holding_cost_usd, 2)               AS daily_holding_cost_usd,
    ROUND(daily_holding_cost_usd * 84, 2)          AS holding_cost_12wk_usd,
    CASE
        WHEN days_of_cover > 365  THEN 'CRITICAL'
        WHEN days_of_cover > 90   THEN 'HIGH'
        WHEN days_of_cover > 30   THEN 'ELEVATED'
        ELSE                           'NORMAL'
    END                                            AS overstock_status
FROM pbi_inventory_summary
ORDER BY
    days_of_cover DESC;
-- Expected: all 5 rows CRITICAL (days_of_cover 10,557 - 11,844)


-- ============================================================
-- Q5: FORECAST ACCURACY BY REGION-CATEGORY SEGMENT
-- ============================================================
-- Business purpose:
--   Identify which segments have the highest forecast error.
--   XYZ classification applied per segment.
--   All segments expected XYZ=X (CV < 30%).
--   High-error segments require larger safety stock buffers.
--
-- Expected output: 24 rows (4 regions x 6 categories)
--   All rows: xyz_classification = 'XYZ=X (predictable)'
--   CV range: 0.44% (TOYS) to 0.93% (ELECTRONICS)
-- ============================================================

SELECT
    region,
    category,
    ROUND(residual_std, 4)                         AS residual_std,
    ROUND(cv_pct, 4)                               AS cv_pct,
    ROUND(mean_actual_demand, 2)                   AS mean_actual_demand,
    train_row_count,
    CASE
        WHEN cv_pct < 10  THEN 'XYZ=X (predictable)'
        WHEN cv_pct < 30  THEN 'XYZ=Y (moderate)'
        ELSE                   'XYZ=Z (unpredictable)'
    END                                            AS xyz_classification,
    CASE
        WHEN residual_std = (SELECT MAX(residual_std)
                             FROM forecast_residual_std)
             THEN 'HIGHEST ERROR — review SS buffer'
        WHEN residual_std = (SELECT MIN(residual_std)
                             FROM forecast_residual_std)
             THEN 'LOWEST ERROR — lean SS viable'
        ELSE 'NORMAL'
    END                                            AS error_flag
FROM forecast_residual_std
ORDER BY
    cv_pct DESC;
-- Expected: all 24 rows XYZ=X (CV range 0.44% - 0.93%)


-- ============================================================
-- Q6: SAFETY STOCK REQUIREMENTS BY SEGMENT
-- ============================================================
-- Business purpose:
--   Review safety stock adequacy vs service level targets.
--   Formula: SS = Z x residual_std x sqrt(lead_time) x 1.20
--   1.20x buffer applied for non-normal residuals (kurtosis=44.3)
--
-- Z-scores by category:
--   ELECTRONICS SL=98%  Z=2.054  |  BEAUTY/TOYS SL=95%  Z=1.645
--   HOME/KITCHEN SL=92% Z=1.405  |  PET SL=90% Z=1.282
--
-- Expected output: 24 rows
--   Max SS: East/ELECTRONICS = 18 units
--   Min SS: South/BEAUTY = 3 units
--   Total: 134 units across all 24 segments
-- ============================================================

SELECT
    region,
    category,
    safety_stock_units,
    target_sl_pct,
    z_score,
    lead_time_days,
    ROUND(safety_stock_units * avg_holding_cost_daily, 4)
                                                   AS ss_daily_holding_cost,
    CASE
        WHEN category = 'ELECTRONICS'
             THEN 'A-class — protect stock — SL 98%'
        WHEN category IN ('TOYS')
             THEN 'A-class — protect stock — SL 95%'
        WHEN category IN ('PET', 'KITCHEN')
             THEN 'B-class — standard replenishment'
        ELSE      'C-class — lean / consolidate'
    END                                            AS abc_priority
FROM safety_stock_by_segment
ORDER BY
    safety_stock_units DESC,
    region ASC;
-- Expected: East/ELECTRONICS = 18 units (highest)
-- Expected: South/BEAUTY = 3 units (lowest)
-- Expected: SUM(safety_stock_units) = 134


-- ============================================================
-- Q7: LP SCENARIO COST COMPARISON
-- ============================================================
-- Business purpose:
--   Compare optimised vs baseline weekly shipping cost.
--   Reproduces Story 2 (LP shipping optimisation only).
--   NEVER combines with Story 1 (holding cost).
--
-- Story 2 confirmed results:
--   Unoptimised: \$23,461/week (\$4.20/unit cross-lane avg)
--   Optimised:   \$8,629/week  (\$1.545/unit home-lane)
--   Saving:      \$14,832/week (63.2%)  ->  \$770,842/year
--   Carbon:      22,781 kg -> 644 kg   (97.2% reduction)
--
-- Expected output: 4 rows (Baseline + 3 LP scenarios)
--   Scenarios A, B, C all identical (Pareto collapse confirmed)
-- ============================================================

SELECT
    scenario,
    scenario_label,
    ROUND(ship_cost_usd, 2)                        AS ship_cost_usd,
    ROUND(holding_cost_usd, 2)                     AS holding_cost_usd,
    ROUND(total_cost_usd, 2)                       AS total_cost_usd,
    ROUND(vs_baseline_usd, 2)                      AS saving_vs_baseline_usd,
    ROUND(vs_baseline_pct, 1)                      AS saving_pct,
    ROUND(cost_per_unit_served, 4)                 AS cost_per_unit_served,
    CASE
        WHEN scenario = 'Baseline'
             THEN 'Unoptimised — cross-lane avg \$4.20/unit'
        ELSE      'Optimised — home-lane \$1.545/unit'
    END                                            AS routing_strategy
FROM pbi_cost_summary
ORDER BY
    total_cost_usd DESC;
-- Expected saving: 63.2% weekly shipping cost reduction
-- Pareto note: Scenarios A, B, C identical — network already optimal


-- ============================================================
-- Q8: SERVICE LEVEL COMPLIANCE BY SEGMENT
-- ============================================================
-- Business purpose:
--   Confirm all 24 region-category segments meet fill rate targets.
--   Zero tolerance for SL breaches on A-class categories.
--   ELECTRONICS (98% SL) and TOYS (95% SL) are highest priority.
--
-- Expected output: 24 rows
--   All 24 rows: compliance_status = 'COMPLIANT'
--   breach_flag = 0 for all rows
--   0 breaches confirmed by LP optimizer (status=OPTIMAL)
-- ============================================================

SELECT
    region,
    category,
    ROUND(fill_rate_pct, 2)                        AS fill_rate_pct,
    target_sl_pct,
    ROUND(fill_rate_pct - target_sl_pct, 2)        AS sl_gap,
    breach_flag,
    status,
    CASE
        WHEN breach_flag = 0  THEN 'COMPLIANT'
        ELSE                       'BREACH — ACTION REQUIRED'
    END                                            AS compliance_status,
    CASE
        WHEN category = 'ELECTRONICS'  THEN 'A-class — 98% target'
        WHEN category = 'TOYS'         THEN 'A-class — 95% target'
        WHEN category = 'BEAUTY'       THEN 'C-class — 95% target'
        WHEN category IN ('HOME',
                          'KITCHEN')   THEN 'B/C-class — 92% target'
        ELSE                                'B-class — 90% target'
    END                                            AS sl_priority
FROM service_level_breach_report
ORDER BY
    sl_gap ASC,
    category ASC;
-- Expected: all 24 rows COMPLIANT (0 breaches confirmed)
-- LP optimizer status=OPTIMAL for all 3 scenarios


-- ============================================================
-- END OF SUPPLY CHAIN QUERIES
-- 8 queries covering: demand, revenue, promotions, overstock,
-- forecast accuracy, safety stock, LP scenarios, service level
-- ============================================================
