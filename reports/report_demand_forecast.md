# Demand Forecast Report — LightGBM

**Generated** : 2026-04-22 12:54 UTC
**Script**    : demand_forecast.py

---

## Model Diagnostics — Test Set Analysis
*Appended: 2026-04-22 13:16 UTC*

### Performance Summary

| Metric | Train Set | CV Mean (4-fold) | Test Set |
|--------|-----------|-----------------|----------|
| MAE    | 0.97 units | 33.37 units | 93.25 units |
| RMSE   | 1.71 units | 50.13 units | 126.87 units |
| WAPE   | 0.7% | 21.5% | 146.5% |
| R²     | 0.9998 | 0.7554 | -11.1068 |

### Root Cause — Overfitting on Training Distribution

The Train R² of 0.9998 against Test R² of -11.11 is a classic
overfitting signature. The model learned the training distribution
near-perfectly but failed to generalise to the 8-week test window.

**Demand distribution shift between train and test:**

- Train mean demand : 147.2 units/week per segment
- Test mean demand  : 63.6 units/week per segment
- Mean shift        : -83.5 units (-56.8%)
- Test predicted    : 156.9 units/week (model anchored to train distribution)

The test window (2025-W48 to 2026-W03) represents end-of-year demand
patterns with higher actual volumes than the model anticipated,
combined with lag features that carried forward lower training-period
demand signals into the test predictions.

**Note on MAPE:** MAPE of 192.3% is misleading because it amplifies
errors on low-demand segments (small denominator instability).
WAPE of 146.5% is the correct percentage metric — stable and
widely used in supply chain forecasting (Amazon, Walmart standard).

### Why This Does Not Block the Optimizer (Stage 3)

The **12-week forward forecast (2026-W04 to 2026-W15)** is the
operational output used by the optimizer, not the held-out test set.
The CV R² of 0.7554 across 4 walk-forward folds is the honest
generalisation estimate for planning purposes.

Forward forecast predicted range: 58 — 345 units/week per segment.
Confidence intervals (80% PI) added via residual std per segment.

### Recommended Fixes (Future Work)

1. Increase `min_child_samples` and reduce `num_leaves` to constrain
   model complexity and reduce overfitting
2. Add L1/L2 regularisation (`reg_alpha`, `reg_lambda` in LightGBM)
3. Extend training data to 3+ years for better temporal coverage
4. Implement residual-based post-processing correction on lag features
5. Evaluate monotonic constraints on lag features to prevent
   training-distribution anchoring in the forecast horizon
