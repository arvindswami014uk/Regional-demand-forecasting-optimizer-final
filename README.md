# Regional Demand Forecasting and Inventory Placement Optimizer

## What This Is

The business problem here was not forecasting for its own sake. The network was sitting at 998% to 1,604% warehouse utilisation, average days cover had drifted to 11,461 against a target of 30, and the inventory position was expensive enough that bad planning decisions would keep compounding. I built this project to answer two practical questions: how well can we forecast regional demand over the next 12 weeks, and what inventory placement and routing moves are worth making once those forecasts are in hand.

The final output is a supply chain analytics workflow covering demand forecasting, statistical validation, ABC-XYZ inventory segmentation, safety stock estimation, and linear programming for inventory allocation and transport routing. The main result is that LightGBM was the best forecasting model, the LP produced real routing savings, and neither of those should be confused with a full fix for the capital tied up in excess stock. That split matters because the transport story is good, while the holding-cost story is still rough.

## The Numbers That Matter

| Area | Metric | Value |
|---|---|---:|
| Forecasting | Best model | LightGBM |
| Forecasting | MAE | 33.37 |
| Forecasting | RMSE | 50.13 |
| Forecasting | WAPE | 21.5% |
| Forecasting | R2 | 0.7554 |
| Benchmark | Prophet MAE | 41.20 |
| Benchmark | Naive MAE | 44.49 |
| Benchmark | Linear Regression MAE | 141.21 |
| Routing optimisation | Weekly shipping saving | $14,831.57 |
| Routing optimisation | Annual shipping saving | $770,841.64 |
| Routing optimisation | Carbon reduction | 22,137 kg CO2 |
| Routing optimisation | Carbon reduction % | 97.2% |
| Inventory position | Holding cost per day | $406,381.70 |
| Inventory position | Holding cost over 12 weeks | $34,136,062.80 |
| Safety stock | Total units | 134 |
| Safety stock | Max segment | 18 units (East/ELECTRONICS) |
| Network health | Avg days cover | 11,461 |
| Network health | Days cover target | 30 |

## Repository Structure

```text
Regional-demand-forecasting-optimizer-final/
├── README.md
├── requirements.txt
├── config/
│   ├── __init__.py
│   └── project_config.py
├── data/
│   ├── raw/
│   │   ├── daily_demand.csv
│   │   ├── event_calendar.csv
│   │   ├── sku_master.csv
│   │   ├── starting_inventory_snapshot.csv
│   │   ├── warehouse_region_costs.csv
│   │   └── warehouses.csv
│   ├── interim/
│   └── processed/
│       ├── forecast_12wk_forward.csv
│       ├── model_comparison.csv
│       ├── safety_stock_by_segment.csv
│       ├── sku_abc_xyz_classification.csv
│       ├── warehouse_allocation_recommendations.csv
│       └── warehouse_utilization.csv
├── figures/
├── outputs/
│   └── logs/
├── reports/
│   ├── final_report.md
│   ├── executive_memo.md
│   ├── assumptions_appendix.md
│   ├── dashboard.html
│   ├── presentation.pdf
│   └── supply_chain_queries.sql
└── src/
    ├── analysis/
    ├── data/
    ├── features/
    ├── genai/
    └── models/
```

## How to Run

Clone the repository and install dependencies:

```bash
git clone https://github.com/arvindswami014uk/Regional-demand-forecasting-optimizer-final.git
cd Regional-demand-forecasting-optimizer-final
pip install -r requirements.txt
```

Run the main workflow modules from the repository root as needed:

```bash
python -m src.data.cleaning.clean_daily_demand
python -m src.data.cleaning.clean_event_calendar
python -m src.features.feature_engineering
python -m src.models.demand_forecast
python -m src.models.abc_xyz_classifier
python -m src.models.inventory_optimizer
```

Open the main written outputs after the pipeline finishes:

```bash
python -m http.server 8000
```

Then browse to:

- `http://localhost:8000/reports/dashboard.html`
- `http://localhost:8000/reports/final_report.md`
- `http://localhost:8000/reports/executive_memo.md`

## Dashboard

Local HTML report:

- [`reports/dashboard.html`](reports/dashboard.html)

Hugging Face Spaces deployment:

- `https://huggingface.co/spaces/arvindswami014uk/demand-forecasting-dashboard`

The dashboard is designed to let a planner move quickly between forecast performance, warehouse pressure, inventory segmentation, safety stock, and routing outcomes without digging through separate reports.

## Presentation

Gamma presentation link placeholder:

- `[GAMMA_LINK]`

PDF export of the deck:

- [`reports/presentation.pdf`](reports/presentation.pdf)

## Key Technical Decisions

I used LightGBM as the primary forecasting model because the demand pattern had clear non-linear interactions across region, category, seasonality, and event effects. Prophet stayed in the comparison set because it is a useful benchmark for time-series structure, but it was not accurate enough to lead the planning workflow. Linear regression failed badly here, which was not surprising once the residual behaviour and feature interactions became obvious.

I kept the statistical checks visible instead of treating them as decoration. Holiday demand showed a 64.8% lift with p<0.0001, marketing showed a 71.4% lift with p<0.0001, Shapiro-Wilk came back at W=0.7247 with kurtosis 44.3, and prediction interval calibration landed at 80.0% empirical coverage. That mix tells me the forecasts are usable, but not something I would present as if the error distribution were clean and symmetric.

I also treated optimisation as two separate business stories. The LP, solved with HiGHS using 120 variables and 29 constraints, found real routing value: $14,831.57 per week in shipping savings and a 97.2% carbon reduction. But the network is still carrying $406,381.70 per day in holding cost, so routing is only part of the answer.

## Limitations and Next Steps

The biggest limitation is that the inventory overhang is so large that it can overshadow the cleaner parts of the modelling work. Forecasting and routing both improved, but they do not solve average days cover of 11,461 or warehouse utilisation above 998%. I would want to pair this work with a more explicit liquidation and replenishment reset plan rather than pretend the model stack alone closes the problem.

I would also revisit event granularity and optimisation scenario design. The event tests clearly matter, but broader flags are still doing a lot of work, and the Pareto collapse in the LP suggests the trade-off space needs a harder stress test with richer lane costs and service penalties. Those are the first places I would spend time if this moved closer to production planning.

## Tech Stack

| Layer | Tools | Why I used them |
|---|---|---|
| Language | Python | Core pipeline, modelling, optimisation, reporting |
| Data handling | pandas, numpy | Structured transformations and metric computation |
| Forecasting | LightGBM, Prophet, scikit-learn | Model comparison and benchmark workflow |
| Optimisation | SciPy / HiGHS | Linear program for inventory routing decisions |
| Visualisation | matplotlib, seaborn, Plotly | Static reporting plus interactive dashboarding |
| App layer | Streamlit | Fast deployment path for stakeholder exploration |
| SQL | Standard SQL | Supply chain queries and reporting logic |
| Documentation | Markdown, HTML, PDF | Technical report, memo, dashboard, presentation export |

_README last updated: 2026-04-23T20:27:30.728559+00:00_