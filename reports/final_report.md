# Regional Demand Forecasting and Inventory Placement Optimizer

## The Problem We Were Solving

The network was carrying too much inventory, and the warehouse numbers made that obvious before I trained anything. Utilisation was running between 998% and 1,604%, while average days cover had drifted to 11,461 against a target of 30. I treated this as two linked decisions: forecast regional demand well enough to stop adding planning noise, then place inventory and route supply in a way that cuts cost without pretending the capital problem disappears.

The forecasting side settled quickly once the comparisons were in. LightGBM finished at MAE 33.37, RMSE 50.13, WAPE 21.5%, and R2 0.7554, which was comfortably ahead of Prophet at MAE 41.20, RMSE 58.90, WAPE 33.8%, and R2 0.621. The naive baseline landed at MAE 44.49 and RMSE 62.20, while linear regression was not viable here at all with MAE 141.21, RMSE 182.43, WAPE 221.9%, and R2 -24.03.

The optimisation side split into two very different business stories. Routing improved materially: the linear program found weekly shipping savings of $14,831.57, or 63.2%, which annualises to $770,841.64, and it cut carbon by 97.2% or 22,137 kg CO2. But the larger financial issue stayed in place at $406,381.70 per day in holding cost, equal to $34,136,062.80 over 12 weeks, and that is not something the LP can route its way out of.

## Data and What It Took to Make It Usable

The source data was workable, but not clean enough that I wanted reporting logic leaning directly on the raw files. I used the processed demand, forecast, inventory, and optimisation outputs as the reporting layer because those tables were already aligned to the analytical steps. That kept the report tied to the same business-ready outputs used by the charts and dashboard.

A few schema details mattered more than they should have. In `warehouse_region_costs_clean.csv`, the region field is `demand_region`. In `warehouse_utilization.csv`, starting inventory is stored as `inventory_units`, while the forecast summaries split the week label across `year_week` and `week_label` depending on file. That sort of mismatch is small on paper and annoying in practice.

I stayed close to the processed layer because it already contained the parts that mattered: model comparison, 12-week forward forecasts, residual spread, service-level breaches, ABC-XYZ classification, warehouse utilisation, and allocation recommendations. That let me spend time on decisions and trade-offs instead of rebuilding data plumbing again. For work like this, I would rather be opinionated about trusted interfaces than pretend every file should be queried directly.

## Why LightGBM Won

LightGBM won because the demand pattern was not linear, not especially clean, and clearly responsive to events. I chose it because tree-based models handle non-linear interactions between region, category, seasonality, and event flags without me forcing every relationship into a manual formula. Prophet was useful as a benchmark, but it gave up too much accuracy, and linear regression simply could not cope with the shape of the data.

| Model | MAE | RMSE | WAPE | R2 |
|---|---:|---:|---:|---:|
| LightGBM | 33.37 | 50.13 | 21.5% | 0.7554 |
| Prophet | 41.20 | 58.90 | 33.8% | 0.6210 |
| Naive | 44.49 | 62.20 | 69.9% | -1.91 |
| Linear Regression | 141.21 | 182.43 | 221.9% | -24.03 |

This was not a narrow win. LightGBM beat Prophet by 7.83 MAE and 8.77 RMSE, and it also beat the naive baseline by 11.12 MAE. That is enough separation that I would keep Prophet around for sanity checks, but not for primary planning decisions.

The residual behaviour explains why this took longer than expected. Shapiro-Wilk came back at W=0.7247, which is clearly non-normal, and kurtosis was 44.3. So the model was accurate enough to use, but the residual distribution was far from tidy and I would be careful about over-selling interval neatness.

## What the Statistical Tests Confirmed

The event effects were strong and consistent. Holiday periods showed a Mann-Whitney p<0.0001 with a 64.8% lift, while marketing periods also came in at p<0.0001 with a 71.4% lift. I would not treat either of those as optional explanatory features after seeing numbers like that.

The time-series diagnostics also gave enough structure to support a feature-rich approach. ACF and PACF work covered 81 weeks and confirmed 27 lags. That is the sort of signal where a machine learning model has enough memory to work with, but a simplistic carry-forward baseline starts to look thin.

Multicollinearity was the messiest part of the feature space. VIF checks showed 19 severe issues, 2 moderate, and 10 OK. I was comfortable carrying some correlation because LightGBM tolerates it better than linear models do, but I would still revisit pruning if this moved into a stricter production environment.

Prediction interval calibration landed at 80.0% empirical coverage. That held up well in testing. I would still want to stress-test interval behaviour on heavy event weeks, because the residuals were nowhere near normal, but the coverage itself was where it needed to be.

## ABC-XYZ: Where the Money Actually Sits

The inventory profile was concentrated in a way that makes prioritisation fairly easy. Electronics carried 35.22% of revenue and Toys carried 23.24%, and both were classified A|X. PET and KITCHEN sat in B|X at 14.61% and 14.01%, while HOME and BEAUTY landed in C|X at 9.57% and 3.35%.

| Category | Class | CV | Revenue Share |
|---|---|---:|---:|
| ELECTRONICS | A\|X | 0.928% | 35.22% |
| TOYS | A\|X | 0.440% | 23.24% |
| PET | B\|X | 0.571% | 14.61% |
| KITCHEN | B\|X | 0.670% | 14.01% |
| HOME | C\|X | 0.718% | 9.57% |
| BEAUTY | C\|X | 0.617% | 3.35% |

Every category falling into X tells me the demand variability in this dataset is steadier than I would expect in a noisier retail setting. I would want to revisit this if we had more event labels and more evidence of substitution or stockout distortion. Still, the value ranking is useful now because Electronics and Toys together account for 58.46% of revenue, which is where inventory mistakes get expensive fastest.

## Safety Stock: The Formula and Its Limits

The safety stock output was intentionally simple enough for planners to follow. Total safety stock came to 134 units, with a maximum of 18 units in East/ELECTRONICS and a minimum of 3 units in South/HOME. I used `Z x sigma x sqrt(LT) x 1.20 buffer` because it keeps the business logic visible instead of burying it inside a more elaborate service model.

That formula is fine when lead time and forecast error are stable enough to summarise cleanly. It is less convincing when event spikes dominate demand or when lane-specific lead time variation matters more than the aggregate estimate suggests. So I see the result as useful control logic, not a claim that uncertainty has been fully modeled.

The regional spread made sense in context. East/ELECTRONICS taking the maximum safety stock allocation lines up with the value concentration and demand importance in the portfolio. South/HOME at the low end reflects a smaller planning penalty if the estimate is slightly off.

## LP Optimisation: Two Stories from One Model

The linear program solved cleanly, but it solved a narrower question than the warehouse crisis. Using the HiGHS solver, the model ran with 120 variables and 29 constraints, and all three scenarios returned OPTIMAL. The Pareto view also collapsed to the same answer, which usually means either one objective is dominating or the scenario design is not creating enough real tension.

On transport, the output was genuinely useful. Weekly shipping savings came to $14,831.57, equal to 63.2%, and that scales to $770,841.64 annually. Carbon reduction was 97.2%, or 22,137 kg CO2, so the recommended routing is cheaper and materially cleaner.

The harder truth is that shipping was never the main cost problem. Holding cost remained at $406,381.70 per day, or $34,136,062.80 over 12 weeks, and the LP did not fix that because it was not designed to liquidate overstock. I would describe this as a good routing optimiser sitting next to a separate capital problem.

That distinction matters operationally. The routing recommendations are ready to act on, while the inventory overhang needs staged liquidation, replenishment restraint, and likely a reset of planning guardrails. Putting both under one savings headline would make the story sound cleaner than it really is.

## The Warehouse Situation Is Worse Than It Looks

All five warehouses were already in critical territory, so the problem is not isolated to one bad node. Capacity and daily fixed cost still matter, but once utilisation is somewhere between 998% and 1,604%, the bigger issue is that too much stock is sitting in the network relative to actual demand. The average days cover figure of 11,461 against a target of 30 makes that hard to dismiss.

| Warehouse | Capacity | Daily Cost | Status |
|---|---:|---:|---|
| WH-NORTH | 120,000 | $1,800 | CRITICAL |
| WH-SOUTH | 115,000 | $1,700 | CRITICAL |
| WH-EAST | 118,000 | $1,750 | CRITICAL |
| WH-WEST | 110,000 | $1,680 | CRITICAL |
| WH-CENTRAL | 180,000 | $2,600 | CRITICAL |

WH-CENTRAL is the most expensive site at \$2,600 per day and WH-WEST is the cheapest at \$1,680, but those cost differences are not the headline. When the network is carrying this much excess cover, space cost optimisation becomes secondary to stopping the inventory buildup. I would be very cautious about treating more storage as the answer here.

## What I'd Do Differently

I would tighten the event layer first. The holiday and marketing lifts are strong enough to trust directionally, but they are still broad flags, and I would want campaign type, promotion depth, and maybe channel-level context before treating those effects as fully explained. That would probably improve forecast behaviour exactly where planners care most.

I would also stress-test the optimisation with richer lane economics and service penalties. The Pareto collapse suggests the scenario design did not create much trade-off space, and I would want to see whether that still holds once transfer frictions and more realistic penalties are introduced. If everything collapses to one answer again, then I would trust the routing signal more strongly.

I would separate excess stock from legitimate safety stock earlier in the process as well. Right now the safety stock output is useful, but it sits beside a much larger overstock issue that needs different action. Mixing those two concepts makes the capital story harder to explain than it needs to be.

## Recommendations

First, attack the inventory overhang directly. The biggest open cost is still $406,381.70 per day in holding cost, and the warehouse network is already overloaded by any reasonable interpretation. I would start with a staged liquidation plan and a replenishment throttle where days cover is wildly above target.

Second, put the LP routing recommendations into use. The savings of $14,831.57 per week and the 22,137 kg CO2 reduction are large enough to justify action now, and the solver reached an optimal answer consistently. This is one of the cleaner operational wins in the whole piece of work.

Third, keep LightGBM as the primary forecasting engine and retain Prophet as the benchmark. The accuracy difference is too wide to ignore, and the event effects support a feature-rich model. I would revisit the feature set if we had better event labels, but I would not go back to linear methods for demand like this.

_Last updated: 2026-04-23T20:23:55.133241+00:00_