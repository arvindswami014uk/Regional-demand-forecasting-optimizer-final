TO: Operations Sponsor
FROM: Arvind Swami, Senior Data Engineer / Data Scientist
DATE: 2026-04-23
RE: Regional demand forecast and inventory placement decisions

## The short version

$406,381.70 per day in holding cost is the main issue, and the network is already operating with warehouse utilisation between 998% and 1,604%. The forecasting work is good enough to support planning, with LightGBM leading at MAE 33.37 and RMSE 50.13, but better forecasting alone will not fix inventory that should not be in the network. The routing optimiser does help, with $14,831.57 in weekly shipping savings and a 97.2% carbon reduction, so I would treat transport and overstock as two separate action tracks.

## What we found

Demand is forecastable enough to act on, but it is not clean in a textbook sense. LightGBM was the best model by a clear margin, ahead of Prophet, the naive baseline, and far ahead of linear regression. The residuals were far from normal with Shapiro-Wilk W=0.7247 and kurtosis 44.3, so I would trust the forecast for planning decisions but stay careful on how tightly we talk about uncertainty.

Event effects are doing real work. Holiday periods showed a 64.8% lift with p<0.0001, and marketing periods showed a 71.4% lift with p<0.0001. Inventory value is also concentrated, with Electronics at 35.22% of revenue and Toys at 23.24%, so a small number of categories drive most of the financial exposure.

The warehouse position is worse than a simple capacity issue. Average days cover is 11,461 against a target of 30, and every warehouse is in critical territory. That tells me we are not looking at a local placement issue first; we are looking at a network carrying far too much stock.

## What it costs to do nothing

If nothing changes, the business keeps carrying $406,381.70 per day in holding cost, or $34,136,062.80 over 12 weeks, while the warehouse network stays overloaded. That cost is much larger than the transport inefficiency, which is why I would not frame this as a routing problem with a routing answer. The transport piece matters, but the capital tied up in excess inventory matters more.

There is also an opportunity cost to delay. The linear program found weekly shipping savings of $14,831.57, equivalent to $770,841.64 annually, and a carbon reduction of 22,137 kg CO2. Those gains are available now, but they should not distract from the bigger issue sitting in inventory.

## Three actions, ranked by impact

First, reduce inventory deliberately. I would start a staged liquidation and replenishment throttle where days cover is furthest above target, because the biggest open cost remains $406,381.70 per day in holding cost. This is the action with the largest financial effect.

Second, implement the routing recommendations from the LP. The optimiser solved cleanly with the HiGHS solver across all three scenarios and found $14,831.57 in weekly savings, a 63.2% reduction, with materially lower transport emissions. This is the fastest operational win in the current work.

Third, keep LightGBM as the primary planning model and retain Prophet only as a benchmark. LightGBM was the only option that combined usable accuracy with enough flexibility to absorb event effects, seasonality, and region-category interactions. I would revisit the feature set if we had richer event labels, but I would not go back to linear methods for this demand shape.

## One risk to flag

The optimiser solved to the same Pareto point in all three scenarios. That can mean the answer is genuinely stable, but it can also mean the scenario design is not creating enough real tension between cost and service objectives. I am comfortable using the routing recommendation now, though I would still want to stress-test it with richer lane costs and service penalties before treating it as the final production design.

## Next steps

If you want speed, I would separate the next steps into a 2-week operational track and a 4- to 6-week planning track. The operational track is liquidation controls, inbound restraint, and implementation of the recommended routing flows. The planning track is tightening event labels, improving scenario design in the optimiser, and hardening the LightGBM forecast into a repeatable planning workflow.

_Prepared: 2026-04-23T20:26:27.495545+00:00_