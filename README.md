# Regional Demand Forecasting and Inventory Placement Optimizer

![Python](https://img.shields.io/badge/Python-3.10-blue)
![LightGBM](https://img.shields.io/badge/LightGBM-4.x-green)
![Power BI](https://img.shields.io/badge/PowerBI-ready-yellow)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## 1. Project Overview

An end-to-end Amazon-inspired supply chain analytics system covering
demand forecasting, statistical validation, inventory optimisation,
generative AI narrative and Power BI reporting across 5,000 SKUs,
4 demand regions, 6 product categories and 5 warehouses.
The system forecasts 12 weeks forward, places inventory via linear
programming, and quantifies cost and carbon savings vs an unoptimised
baseline across three logistics scenarios.

---

## 2. Repository Structure

```
Regional-demand-forecasting-optimizer-final/
├── data/
│   ├── raw/                          # Original source CSVs
│   └── processed/                    # All cleaned + derived datasets
│       ├── daily_demand_clean.csv
│       ├── event_calendar_clean.csv
│       ├── sku_master_clean.csv
│       ├── warehouses_clean.csv
│       ├── warehouse_region_costs_clean.csv
│       ├── starting_inventory_clean.csv
│       ├── modeling_dataset.csv
│       ├── fact_demand_enriched.csv
│       ├── warehouse_utilization.csv
│       ├── forecast_12wk_forward.csv
│       ├── weekly_demand_forecast.csv
│       ├── forecast_residual_std.csv
│       ├── sku_abc_xyz_classification.csv
│       ├── safety_stock_by_segment.csv
│       ├── inventory_placement_optimized.csv
│       ├── scenario_comparison.csv
│       ├── cost_to_serve_comparison.csv
│       ├── carbon_comparison.csv
│       ├── sensitivity_analysis.csv
│       ├── service_level_breach_report.csv
│       ├── warehouse_allocation_recommendations.csv
│       ├── pbi_demand_summary.csv
│       ├── pbi_forecast_summary.csv
│       ├── pbi_inventory_summary.csv
│       ├── pbi_cost_summary.csv
│       ├── pbi_carbon_summary.csv
│       └── pbi_schema.md
├── figures/
│   ├── optimizer_abc_xyz_heatmap.png
│   ├── optimizer_cost_waterfall.png
│   ├── optimizer_scenario_comparison.png
│   ├── optimizer_sensitivity_curve.png
│   └── optimizer_service_level_report.png
├── outputs/
│   └── logs/
│       ├── log_abc_xyz_classifier.csv
│       ├── log_safety_stock.csv
│       ├── log_inventory_optimizer.csv
│       ├── log_service_level.csv
│       ├── log_power_bi_export.csv
│       └── log_documentation.csv
├── reports/
│   ├── executive_summary_llm.md
│   ├── anomaly_explanations.md
│   ├── rag_qa_log.md
│   ├── report_optimizer.md
│   ├── final_report.md
│   └── data_lineage.md
├── src/
│   └── models/
│       ├── abc_xyz_classifier.py
│       └── inventory_optimizer.py
└── README.md
```

---

## 3. Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/arvindswami014uk/Regional-demand-forecasting-optimizer-final.git
cd Regional-demand-forecasting-optimizer-final

# 2. Install dependencies
pip install pandas numpy lightgbm scipy scikit-learn faiss-cpu groq matplotlib seaborn

# 3. Set environment variables
export GROQ_API_KEY=your_groq_api_key_here
export GROQ_MODEL=llama-3.3-70b-versatile

# 4. Run in Google Colab (recommended)
# Open each notebook stage in sequence — all cells are self-contained
```

**Run order:**

| Stage | Description | Key Output |
|-------|-------------|------------|
| Stage 1 | Data ingestion and cleaning | 5 clean CSVs |
| Stage 2 | EDA and statistical testing | modeling_dataset.csv |
| Stat Cells 1-3 | Hypothesis tests + PI calibration | Confirmed p-values |
| Block A | Gen AI — LLM, anomaly, RAG | 3 report files |
| Block B | Optimizer — ABC-XYZ, SS, LP | 6 output CSVs |
| Block C | Power BI export | 5 PBI CSVs |
| Block D | Documentation | README + reports |

---

## 4. Data Pipeline

```
Stage 1 — Ingestion                Stage 2 — Feature Engineering
  daily_demand.csv (5,000 x 16)  →   modeling_dataset.csv (1,540 x 42)
  event_calendar.csv (565 x 12)      fact_demand_enriched.csv (5,000 x 33)
  sku_master.csv (5,000 x 11)        warehouse_utilization.csv (5 x 11)
  warehouses.csv (5 x 4)
  wh_region_costs.csv (20 x 7)   ↓
  starting_inventory.csv (5,000)  Stage 3 — Forecasting + Optimisation
                                    forecast_12wk_forward.csv (288 x 11)
                                    safety_stock_by_segment.csv (24 x 10)
                                    inventory_placement_optimized.csv (360 x 12)
                                    scenario_comparison.csv (3 x 13)
                                  ↓
                                  Stage 4 — Power BI Export
                                    5 pbi_*.csv files (ready for dashboard)
```

---

## 5. Key Results

### Demand Forecasting

| Metric | LightGBM | Naive | Linear Regression |
|--------|----------|-------|-------------------|
| MAE | 33.37 | 44.49 | 141.21 |
| RMSE | 50.13 | 62.20 | 182.43 |
| WAPE | 21.5% | 69.9% | 221.9% |
| R2 | 0.7554 | -1.91 | -24.03 |

LightGBM beats Naive by **+25% MAE** and **+69.3% WAPE**.
80% prediction interval empirical coverage = **80.0%** (well-calibrated).

### Statistical Tests

| Test | Result |
|------|--------|
| Mann-Whitney Holiday | p<0.0001, +64.8% demand lift |
| Mann-Whitney Marketing | p<0.0001, +71.4% demand lift |
| Shapiro-Wilk Residuals | W=0.7247, NON-NORMAL, kurtosis=44.3 |
| VIF | 19 severe, 2 moderate, 10 OK |

### Inventory Optimisation (LP — HiGHS solver)

| Metric | Baseline | Optimised | Saving |
|--------|----------|-----------|--------|
| Total cost | \$34,410,837.51 | \$8,629.13 | 99.97% |
| Carbon emissions | 22,781.11 kg | 643.94 kg | 97.2% |
| Service level | — | 100% | 0 breaches |

All 3 LP scenarios (Cost / Balanced / Carbon Champion) produce
**identical results** — Pareto frontier collapses to a single point
because home-lane routing minimises both cost and carbon simultaneously.

### ABC-XYZ Classification

| Category | ABC | XYZ | CV | Strategy |
|----------|-----|-----|----|----------|
| ELECTRONICS | A | X | 0.928% | Lean replenishment |
| TOYS | A | X | 0.440% | Lean replenishment |
| PET | B | X | 0.571% | Standard replenishment |
| KITCHEN | B | X | 0.670% | Standard replenishment |
| HOME | C | X | 0.718% | Consolidate SKUs |
| BEAUTY | C | X | 0.617% | Consolidate SKUs |

### Overstock Alert

Starting inventory: **8,926,517 units** (value: \$593,317,335.34).
Warehouse utilisation: 998% - 1,604%. Days of cover: 4,191 - 21,093 days.
Daily holding cost: \$406,381.70/day.

---

## 6. Figures Gallery

| Figure | Description |
|--------|-------------|
| optimizer_abc_xyz_heatmap.png | ABC-XYZ classification matrix — revenue % vs CV% by category |
| optimizer_cost_waterfall.png | Cost waterfall: baseline to optimised — \$34.4M to \$8.6K |
| optimizer_scenario_comparison.png | Side-by-side cost and carbon comparison across 3 LP scenarios |
| optimizer_sensitivity_curve.png | Sensitivity of cost/carbon to w_carbon weight (0.0 to 1.0) |
| optimizer_service_level_report.png | Fill rate vs target SL for all 24 segments — 0 breaches |

---

## 7. Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10 |
| Forecasting | LightGBM 4.x, scikit-learn |
| Statistical tests | scipy (Mann-Whitney, Shapiro-Wilk) |
| Optimisation | scipy.optimize.linprog (HiGHS solver) |
| Gen AI — LLM narrator | Groq API — llama-3.3-70b-versatile |
| Gen AI — RAG Q&A | FAISS (dim=384), sentence-transformers |
| Data processing | pandas, numpy |
| Visualisation | matplotlib, seaborn |
| Reporting | Power BI Desktop |
| Version control | Git + GitHub |
| Runtime | Google Colab |

---

## 8. Limitations and Future Work

- **Single-period LP:** The optimizer solves one weekly replenishment cycle.
  A multi-period rolling horizon model would better reflect real operations.
- **Pareto collapse:** All scenarios converge to the same solution because
  home-lane cost and carbon are perfectly correlated in this cost structure.
  Introducing cross-lane demand spillover would create genuine trade-offs.
- **Synthetic data:** The dataset is procedurally generated.
  Live ERP or WMS integration would validate real-world applicability.
- **Static safety stock:** Safety stock is computed once per segment.
  A dynamic SS recalculation triggered by forecast drift would be more robust.
- **No supplier lead time variability:** Lead times are deterministic.
  Adding stochastic lead time distributions would improve SS accuracy.

---

## 9. Author

Arvind Swami
Regional Demand Forecasting and Inventory Placement Optimizer
Amazon-Inspired Capstone Project — Outlier AI

---

*Last updated: 2026-04-22*

---

## Block 1 — Gap Fills (commits 65d1ef7 – 386720c)

| File | Description | Commit |
|------|-------------|--------|
| `data/processed/prophet_forecast.csv` | Prophet benchmark — 2,819 bytes | 65d1ef7 |
| `data/processed/model_comparison.csv` | 4-model comparison table | 65d1ef7 |
| `figures/forecast_model_comparison.png` | LightGBM vs Prophet vs Naive bar chart | 65d1ef7 |
| `figures/prophet_vs_lgbm_forecast.png` | Overlay forecast chart | 65d1ef7 |
| `reports/capstone_presentation.pptx` | 12-slide python-pptx deck | 5333900 |
| `reports/supply_chain_queries.sql` | 8 supply chain SQL queries | 1a52d74 |
| `reports/executive_memo.md` | Executive memo — 1,062 words | 386720c |
| `reports/assumptions_appendix.md` | Assumptions appendix — 6 sections | 386720c |

**Key Block 1 results:**
- LightGBM WAPE 21.5% vs Prophet 33.8% vs Naive 69.9%
- LightGBM beats Naive by +25.0% MAE / +69.3% WAPE
- Prophet benchmark confirms LightGBM as production model

---

## Block 2 — Dashboard + Visualisations (commits b1b71f5 – present)

| File | Description | Commit |
|------|-------------|--------|
| `reports/dashboard.html` | Interactive Plotly dashboard — 5 tabs, 4.43 MB | b1b71f5 |
| `figures/lgbm_feature_importance.png` | Top-20 feature importance horizontal bar | 990044e |
| `figures/lgbm_feature_importance_summary.png` | Category summary bar + top-10 pie | 990044e |
| `data/processed/feature_importance.csv` | All 36 features ranked with importance % | 990044e |
| `figures/forecast_24panel.png` | 24-panel forecast — 4 regions x 6 categories | 462bec5 |

### Interactive Dashboard (`reports/dashboard.html`)

Open in any browser — no Power BI or Tableau required.
Single self-contained HTML file with embedded Plotly.js.

| Tab | Title | Key Metric |
|-----|-------|------------|
| 1 | Regional Demand Overview — 81 Weeks | Holiday +64.8% \| Marketing +71.4% |
| 2 | 12-Week Forward Forecast — LightGBM WAPE 21.5% | WAPE 21.5% \| R²=0.755 |
| 3 | Warehouse Overstock — \$406,381/Day Holding Cost | 5 WH ALL CRITICAL |
| 4 | LP Optimizer — 63.2% Shipping Cost Reduction | \$770,842/yr saving |
| 5 | 100% Service Level — Zero Breaches — 24 Segments | 134 units SS |

### Feature Importance Findings

| Rank | Feature | Importance % | Category |
|------|---------|-------------|----------|
| 1 | category_velocity | 22.7% | Other |
| 2 | weeks_since_epoch | 10.9% | Calendar |
| 3 | week_number | 10.1% | Calendar |
| 4 | weather_disruption | 9.1% | Other |
| 5 | region_demand_rank | 8.0% | Other |
| 6 | lag_2_week_demand | 6.9% | Lag/Rolling |
| 7 | lag_1_week_demand | 6.6% | Lag/Rolling |

Lag/Rolling features: 29.2% total importance — confirms 27-lag ACF/PACF structure.
Calendar features: 23.5% — confirms week/seasonality effect.

### 24-Panel Forecast (`figures/forecast_24panel.png`)

- 4 rows (East, North, South, West) × 6 columns (BEAUTY, ELECTRONICS,
  HOME, KITCHEN, PET, TOYS)
- Each panel: actual demand (navy) + in-sample predicted (orange dashed)
  + 12-week forward forecast (green) + 80% CI bands
- Vertical dotted line separates historical from forward horizon

*README last updated: 2026-04-23 19:29 UTC*
