# Gamma Presentation Master Prompt

Paste everything below the horizontal rule directly into gamma.app.
The prompt is complete and self-contained.
Do not edit it before pasting.

---

Create a 12-slide executive presentation titled:
Regional Demand Forecasting and Inventory Placement Optimizer

THEME AND STYLE

Use a modern dark theme with these exact colours:
- Deep navy #1B4F72 for headers and primary bars
- Mid blue #2E86C1 for secondary elements
- Amber #F39C12 for alerts and KPI highlights
- Forest green #1E8449 for positive metrics
- Red #C0392B for critical warnings and overstock signals
- Off-white #F8F9FA for backgrounds
- Body text #2C3E50

Font: Inter or a clean sans-serif equivalent.

Every slide must have exactly this structure:
- One headline stat, large and prominent
- One clear visual
- One sentence of context below the visual
- No bullet walls
- Maximum 3 short points per slide where lists are needed

VOICE AND TONE

This is a senior data engineer explaining a real supply chain problem to an operations sponsor.
Tone is direct, precise, and slightly opinionated.
Business-first, not academic.
The story has two clearly separate outcomes and they must not be merged:
Outcome 1: routing improved materially
Outcome 2: holding cost is still a large open problem that the routing fix did not solve

EXACT FACTS TO USE

Do not change any of these numbers.

Forecast model results:
LightGBM MAE 33.37 RMSE 50.13 WAPE 21.5% R2 0.7554
Prophet MAE 41.20 RMSE 58.90 WAPE 33.8% R2 0.621
Naive MAE 44.49 RMSE 62.20 WAPE 69.9% R2 -1.91
Linear Regression MAE 141.21 RMSE 182.43 WAPE 221.9% R2 -24.03

Statistical tests:
Holiday effect Mann-Whitney p less than 0.0001 lift 64.8%
Marketing effect Mann-Whitney p less than 0.0001 lift 71.4%
Shapiro-Wilk W=0.7247 residuals non-normal kurtosis 44.3
Prediction interval calibration 80.0% empirical coverage
ACF/PACF 81 weeks 27 lags confirmed
VIF 19 severe 2 moderate 10 OK

ABC-XYZ classification:
ELECTRONICS A|X CV 0.928% Revenue 35.22%
TOYS A|X CV 0.440% Revenue 23.24%
PET B|X CV 0.571% Revenue 14.61%
KITCHEN B|X CV 0.670% Revenue 14.01%
HOME C|X CV 0.718% Revenue 9.57%
BEAUTY C|X CV 0.617% Revenue 3.35%

Safety stock:
Total 134 units
Maximum 18 units East ELECTRONICS
Minimum 3 units South HOME
Formula Z x sigma x sqrt lead time x 1.20 buffer

Optimisation:
Solver HiGHS
Variables 120
Constraints 29
All 3 scenarios OPTIMAL
Pareto collapse confirmed across all scenarios

Routing savings: weekly saving $14,831.57 which is 63.2% reduction
Annual saving $770,841.64
Carbon reduction 97.2% which is 22,137 kg CO2

Holding cost: $406,381.70 per day
12-week total $34,136,062.80
This was not solved by the LP optimiser
Required action is staged liquidation not routing changes

Warehouse facts:
WH-NORTH capacity 120,000 daily cost \$1,800 status CRITICAL
WH-SOUTH capacity 115,000 daily cost \$1,700 status CRITICAL
WH-EAST capacity 118,000 daily cost \$1,750 status CRITICAL
WH-WEST capacity 110,000 daily cost \$1,680 status CRITICAL
WH-CENTRAL capacity 180,000 daily cost \$2,600 status CRITICAL
Utilisation range 998% to 1,604%
Average days cover 11,461 against a target of 30

SLIDE-BY-SLIDE INSTRUCTIONS

SLIDE 1 TITLE AND HOOK
Headline stat: \$406,381.70 per day in holding cost
Visual: bold title card with the project name large, one prominent number, and a subtle dark warehouse-network background
Context: The network has a forecasting problem, a routing problem, and a much larger inventory capital problem that sits behind both.

SLIDE 2 THE WAREHOUSE CRISIS
Headline stat: Utilisation 998% to 1,604% across all five warehouses
Visual: horizontal bar chart of warehouse utilisation by site, all bars in red, WH-EAST clearly the highest
Context: When every warehouse is critical and average days cover is 11,461 against a target of 30, this stopped being a local placement problem.

SLIDE 3 DATA LANDSCAPE
Headline stat: 81 weeks of demand signal with 27 useful lags
Visual: compact data flow diagram showing demand, event calendar, inventory, warehouse, and cost data feeding into the modeling pipeline
Context: The data was good enough to work with, but schema discipline and a processed reporting layer mattered more than the raw files.

SLIDE 4 WHY LIGHTGBM WON
Headline stat: MAE 33.37 versus 141.21 for Linear Regression
Visual: horizontal bar chart comparing all four models on MAE, LightGBM bar in green, others in blue, Linear Regression bar clearly longest
Context: LightGBM won because the demand pattern was non-linear, event-sensitive, and full of regional and category interactions that a linear model was never going to handle.

SLIDE 5 FORECAST RESULTS
Headline stat: R2 0.7554 WAPE 21.5%
Visual: 12-week forecast line chart with confidence bands shown by region or combined, using the navy-to-amber colour range
Context: The forecast is strong enough to support planning decisions but the residuals are far from normal and intervals should be used with that in mind.

SLIDE 6 WHAT THE STATS CONFIRMED
Headline stat: Marketing periods lifted demand by 71.4%
Visual: two-panel slide with event lift comparison bars on the left and residual or calibration summary on the right
Context: Holiday and marketing effects are core demand drivers with p less than 0.0001, while Shapiro-Wilk W=0.7247 and kurtosis 44.3 mean the error distribution is not clean.

SLIDE 7 ABC-XYZ INVENTORY CLASSIFICATION
Headline stat: Electronics and Toys account for 58.46% of revenue
Visual: treemap showing all six categories by revenue share with A|X B|X and C|X labels visible, using the category colour palette
Context: Value is concentrated enough that a small number of categories carry most of the inventory risk and most of the cost of a planning mistake.

SLIDE 8 SAFETY STOCK FRAMEWORK
Headline stat: Total safety stock 134 units
Visual: region by category heatmap with East ELECTRONICS at 18 highlighted in amber and South HOME at 3 in light blue
Context: The formula is simple and auditable, which is more useful here than a complex stochastic model that hides its assumptions.

SLIDE 9 LP OPTIMISATION RESULTS
Headline stat: $14,831.57 per week in shipping savings
Visual: before-and-after waterfall or grouped bar chart showing old versus new routing cost by lane, with a small solver setup note
Context: HiGHS solved all three scenarios to OPTIMAL with 120 variables and 29 constraints, and the routing recommendation is ready to act on now.

SLIDE 10 THE CAPITAL CRISIS
Headline stat: $34,136,062.80 in holding cost over 12 weeks
Visual: large number slide with a holding-cost timeline in red showing the weekly accumulation, warehouse overstock context visible in background
Context: This is the number the LP did not fix because no routing model closes a $406,381.70 per day capital problem caused by excess stock.

SLIDE 11 THREE RECOMMENDATIONS
Headline stat: Start with the $406k per day problem first
Visual: three numbered action cards side by side, each with a short title, one supporting number, and a colour-coded priority indicator
Action 1: Launch staged liquidation and replenishment restraint to reduce the $406,381.70 per day holding cost burden
Action 2: Implement LP routing changes to capture $14,831.57 per week and 22,137 kg CO2 reduction immediately
Action 3: Keep LightGBM as the planning engine and tighten event labels before hardening into a production workflow
Context: Inventory reduction comes first, routing second, model refinement third.

SLIDE 12 NEXT STEPS AND CONTACT
Headline stat: Two-week operational track, four to six week planning track
Visual: phased roadmap with two lanes, near-term actions on the left and planning-track actions on the right, using navy and amber to separate them
Near-term: implement routing flows, initiate liquidation controls, freeze inbound where days cover is furthest above target
Planning track: tighten event labels, stress-test optimisation scenarios, harden LightGBM into a repeatable weekly planning workflow
Context: The routing work is ready now and the inventory reset needs deliberate staging over the next planning period.

END OF PROMPT

---

_Gamma prompt generated: 2026-04-23T20:53:21.311928+00:00_