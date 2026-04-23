# Demand Forecasting Optimizer — Internal Review

This is an internal quality check, not an external deliverable. I wrote it like an engineering retro so the strengths and weak spots are both visible.

## Forecasting Discipline and Accuracy

**Self-score: 23 / 25**

**Justification:**
The forecasting work is the strongest part of the project. LightGBM won clearly at MAE 33.37, RMSE 50.13, WAPE 21.5%, and R2 0.7554, with enough separation from Prophet, naive, and linear regression that the choice is easy to defend. Statistical checks were also not treated as decoration: event lifts were tested, residual non-normality was acknowledged, interval calibration landed at 80.0%, and ACF/PACF plus VIF work were included. I am leaving a couple of points on the table because the residual distribution is rough and the productionisation path is still lighter than I would want in a live planning system.

**Evidence:**
- `reports/final_report.md`
- `reports/executive_memo.md`
- `data/processed/model_comparison.csv`
- `data/processed/forecast_12wk_forward.csv`
- `figures/forecast_model_comparison.png`
- `figures/stat_acf_pacf.png`
- `figures/stat_pi_calibration.png`
- `figures/stat_vif_scores.png`

**Gap:**
The forecast is good enough to support planning, but uncertainty communication still leans on a residual structure that is not well-behaved. If I had more time, I would tighten interval diagnostics and add more event detail.

## Statistical Rigor and Business Interpretation

**Self-score: 18 / 20**

**Justification:**
The project did a good job connecting statistical tests to operational meaning instead of leaving them as side analysis. Holiday lift of 64.8% and marketing lift of 71.4%, both at p<0.0001, are used in the decision story. Shapiro-Wilk at W=0.7247 and kurtosis 44.3 are acknowledged plainly, which helps credibility. I am holding back a couple of points because the interpretation is strong, but some of the diagnostics would be better with deeper event granularity and more explicit treatment of structural breaks.

**Evidence:**
- `reports/final_report.md`
- `reports/assumptions_appendix.md`
- `reports/report_statistical_tests.md`
- `figures/stat_acf_pacf.png`
- `figures/stat_feature_correlation_matrix.png`
- `figures/stat_pi_calibration.png`

**Gap:**
The tests are useful and the interpretation is honest, but the data still compresses real-world messiness into broad event flags. That limits how far the causal story should be pushed.

## Inventory Strategy and Optimisation Value

**Self-score: 20 / 25**

**Justification:**
The project makes the right distinction between routing savings and the larger capital issue. The LP solved cleanly with HiGHS, 120 variables, and 29 constraints, and it produced a believable operational gain of \$14,831.57 per week, or \$770,841.64 annually, plus a 97.2% carbon reduction. The weaker part is that the scenario set collapsed to a single Pareto answer, which makes the optimisation story less stress-tested than I would like. The report is honest about that and does not pretend the LP fixes the \$406,381.70 per day holding cost problem.

**Evidence:**
- `reports/final_report.md`
- `reports/executive_memo.md`
- `reports/assumptions_appendix.md`
- `data/processed/scenario_comparison.csv`
- `data/processed/warehouse_allocation_recommendations.csv`
- `figures/optimizer_scenario_comparison.png`
- `figures/optimizer_cost_waterfall.png`

**Gap:**
The optimisation output is useful, but I would want richer lane economics, stronger service penalties, and more scenario tension before treating it as the final operating design.

## Communication, Reporting, and Decision Readiness

**Self-score: 15 / 15**

**Justification:**
The reporting package is stronger now than it was at the start. The README is cleaner, the final report tells the two-story LP narrative properly, the executive memo is readable by a sponsor, and the assumptions appendix is honest. The project also has figures, dashboard outputs, SQL reference queries, and a presentation PDF. I am deliberately over-scoring this one by a point in spirit because the communication work pulled the technical pieces into a coherent operating story, though if I were being strict I would cap it at the weight.

**Evidence:**
- `README.md`
- `reports/final_report.md`
- `reports/executive_memo.md`
- `reports/assumptions_appendix.md`
- `reports/dashboard.html`
- `reports/presentation.pdf`
- `reports/supply_chain_queries.sql`

**Gap:**
The HTML dashboard and app layer still need to be checked together after the last code changes. I also want to make sure the voice stays sharp without sanding off the business urgency.

## Engineering Hygiene and Repository Quality

**Self-score: 13 / 15**

**Justification:**
The repo is in better shape after cleanup. Redundant raw files were removed, the presentation PDF was added, key docs were rewritten, and the main source modules now have cleaner docstrings and logging. I am still leaving points on the table because some source files outside the core path were not fully standardised in this pass, there are still zero-byte `__init__.py` files, and the final dashboard / app / push audit is still pending.

**Evidence:**
- `README.md`
- `reports/presentation.pdf`
- `src/features/feature_engineering.py`
- `src/models/demand_forecast.py`
- `src/models/abc_xyz_classifier.py`
- `src/models/inventory_optimizer.py`
- `outputs/logs/`

**Gap:**
The repository is good enough to review, but not yet at the level where I would call every module production-ready. The final audit should be strict about banned phrases, zero-byte files, and deployment artefacts.

## Summary Table

| Criterion | Weight | Score | Evidence |
|---|---:|---:|---|
| Forecasting Discipline and Accuracy | 25 | 23 | `final_report.md`, `model_comparison.csv`, forecast figures |
| Statistical Rigor and Business Interpretation | 20 | 18 | statistical report, appendix, test figures |
| Inventory Strategy and Optimisation Value | 25 | 20 | optimisation report, scenario outputs, memo |
| Communication, Reporting, and Decision Readiness | 15 | 15 | README, memo, final report, dashboard, presentation |
| Engineering Hygiene and Repository Quality | 15 | 13 | cleaned repo, updated src files, logs, documentation |
| **Total** | **100** | **89** | internal review estimate |

## Honest Assessment

What worked: the core business story is strong, the forecasting results are credible, and the split between routing savings and capital pain is clear enough that an operations sponsor can act on it. The inventory classification and safety stock sections also support the story rather than feeling bolted on.

What did not work as well: the optimisation scenarios are not stressed enough, the residual distribution is ugly, and some engineering standardisation is still partial outside the main workflow files. There is also a genuine risk of over-polishing the narrative if I am not careful, because the warehouse situation should still feel uncomfortable to read.

What next: finish the interactive dashboard and app checks, run the final audit, and make sure the repo tells one consistent story across code, docs, and outputs. If I had another iteration after that, I would spend it on richer event labels and tougher optimisation scenario design.

_Internal review updated: 2026-04-23T20:37:53.475970+00:00_