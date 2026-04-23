# Assumptions Appendix

## Data Assumptions

The reporting and analysis layer assumes the processed CSV outputs are the source of truth for downstream work. I made that choice because the cleaned and engineered tables already carried the joins, flags, and schema consistency needed for forecasting and optimisation. The implication is simple: if a raw file changes but the processed layer is not regenerated, the reporting layer can look clean while being out of date.

| Assumption | Reason | Practical implication |
|---|---|---|
| Processed files are the trusted reporting layer | They already align demand, events, inventory, and cost outputs | Rebuild processed files if upstream raw inputs change |
| Column names are fixed in downstream outputs | Joins depend on exact fields like `demand_region`, `inventory_units`, `year_week`, and `week_label` | Small schema changes can break dashboards and summaries quietly |
| Historical demand is representative enough to train a 12-week forecast | The model needs stable enough structure to learn seasonal and event effects | Large structural breaks would weaken forecast reliability quickly |
| Event flags capture the main external demand signals available | Holiday and marketing effects were statistically strong | Missing event granularity likely leaves explanatory power on the table |

I would call out the event layer as the main data limitation. Holiday and marketing both showed strong lifts, 64.8% and 71.4% with p<0.0001, but those are still broad labels. If we had campaign depth, channel exposure, or promotion mechanics, I would expect the forecast to improve most on the weeks that matter operationally.

## Model Assumptions

The forecasting workflow assumes relative performance on holdout data is a good enough basis for model selection. That is why LightGBM stayed as the lead model: MAE 33.37 and RMSE 50.13 were materially better than Prophet, naive, and linear regression. The implication is that the model is chosen for practical predictive value, not because its error process is especially tidy.

| Assumption | Reason | Practical implication |
|---|---|---|
| Best holdout accuracy should drive model choice | Planning decisions benefit more from lower forecast error than from simpler form alone | LightGBM remains primary even if Prophet is easier to narrate |
| Non-linear interactions matter | Demand responds to region, category, seasonality, and events in combination | Tree-based models are a better fit than linear methods here |
| Residuals do not need to be normal for the forecast to be useful | The business question is predictive control, not a perfect parametric fit | Intervals should be interpreted with caution because Shapiro-Wilk was W=0.7247 and kurtosis was 44.3 |
| Correlated features are acceptable within reason | LightGBM is less sensitive to multicollinearity than linear regression | VIF issues still matter for explainability and model maintenance |
| Interval calibration is more important than aesthetic residual behaviour | Coverage landed at 80.0% empirical coverage | Intervals are usable, but I would still stress-test event-heavy periods |

The main thing I would not hide is that the residual distribution is rough. Non-normality does not stop the forecast from being useful, but it does change how confidently I would talk about forecast uncertainty. If this moved into a more formal planning process, I would want more interval diagnostics before turning the current outputs into policy.

## Optimisation Assumptions

The LP assumes the network decision can be represented well enough with a linear cost structure and the available capacity, demand, and lane information. That worked for transport decisions, where the model found $14,831.57 in weekly shipping savings and 22,137 kg CO2 in carbon reduction. It did not solve the holding-cost problem, which is exactly why I would keep those two stories separate.

| Assumption | Reason | Practical implication |
|---|---|---|
| Linear costs are adequate for routing decisions | The solver needs a tractable representation of lane economics | Real-world thresholds or non-linear fees may shift the exact recommendation |
| Available warehouse and lane inputs are sufficient for optimisation | The model needs capacities, costs, and demand by region | Missing transfer frictions or service penalties can make the result look cleaner than reality |
| Scenario objectives are distinct enough to test trade-offs | Scenario comparison is meant to expose cost-service tension | The Pareto collapse suggests the objective space should be stress-tested with richer economics |
| Optimal solver output is actionable if constraints are credible | HiGHS solved all three scenarios as OPTIMAL using 120 variables and 29 constraints | The answer is technically stable, but still depends on the realism of the inputs |

The Pareto collapse is the point I would revisit first. When all three scenarios land on the same answer, either the recommendation is genuinely stable or the scenario design is not pushing hard enough on competing objectives. I am comfortable with the current routing signal, but I would want richer lane costs and service penalties before calling that fully battle-tested.

## Safety Stock Assumptions

The safety stock logic assumes forecast error and lead time can be summarised well enough through a compact formula. I used `Z x sigma x sqrt(LT) x 1.20 buffer` because it is interpretable and fast to audit. The output was 134 units in total, with a maximum of 18 in East/ELECTRONICS and a minimum of 3 in South/HOME.

| Assumption | Reason | Practical implication |
|---|---|---|
| A compact safety stock formula is sufficient for planning support | Stakeholders need something transparent and quick to validate | Useful for control logic, but not a full stochastic policy |
| Residual spread is a reasonable proxy for demand uncertainty | Sigma gives a practical way to scale protection by forecast variability | If forecast error changes sharply by event type, safety stock may be under- or over-stated |
| Lead time can be represented as a stable input | The square-root lead time treatment assumes manageable variance | Highly variable lanes would justify a more explicit treatment |
| A 20% buffer is acceptable as a practical guard band | It adds protection against under-modeled volatility | The exact buffer should be reviewed if service targets tighten |

I would not confuse this with a full inventory policy. The safety stock output is useful for near-term planning, but it sits beside a much larger overstock issue in the network. When average days cover is 11,461 against a target of 30, excess inventory management matters more than fine-tuning buffer stock.

## What These Assumptions Mean in Practice

The practical read is that the work is strong enough to support decisions, but not clean enough to justify complacency. LightGBM is the right primary forecast given the accuracy results, the LP routing output is useful right now, and the ABC-XYZ view does a good job of showing where value is concentrated. At the same time, the network is still carrying $406,381.70 per day in holding cost, every warehouse is in critical territory, and the data still lacks some event and lane detail that I would want before hardening this into production planning.

If I had to summarise the assumptions in one line, it would be this: the workflow is good at identifying the direction of action, and less good at pretending uncertainty has been eliminated. That is fine for a planning project, as long as the decisions stay honest about where the model is strong and where operational judgement still has to do some work.

_Appendix updated: 2026-04-23T20:28:50.843036+00:00_