"""
abc_xyz_classifier.py
Classifies inventory categories by:
  ABC — cumulative revenue contribution
  XYZ — demand variability (coefficient of variation)
"""
import numpy as np
import pandas as pd

STRATEGY_MAP = {
    "AX": "Lean replenishment - high value, predictable",
    "AY": "Safety stock buffer - high value, variable",
    "AZ": "Expedite capable - high value, unpredictable",
    "BX": "Standard replenishment",
    "BY": "Review cycle increase",
    "BZ": "Reduce complexity",
    "CX": "Consolidate SKUs",
    "CY": "Rationalise",
    "CZ": "Discontinue review",
}


def assign_abc(cum_pct: float) -> str:
    """Return A/B/C based on cumulative revenue percentage."""
    if cum_pct <= 70.0:
        return "A"
    elif cum_pct <= 90.0:
        return "B"
    else:
        return "C"


def assign_xyz(cv: float) -> str:
    """Return X/Y/Z based on coefficient of variation."""
    if cv < 0.30:
        return "X"
    elif cv < 0.60:
        return "Y"
    else:
        return "Z"


def classify_categories(df_revenue: pd.DataFrame,
                        df_cv: pd.DataFrame) -> pd.DataFrame:
    """
    Parameters
    ----------
    df_revenue : DataFrame with columns [category, revenue]
    df_cv      : DataFrame with columns [category, cv]

    Returns
    -------
    DataFrame with abc_class, xyz_class, abc_xyz, strategy columns
    """
    df = df_revenue.sort_values("revenue", ascending=False).copy()
    df["revenue_pct"] = df["revenue"] / df["revenue"].sum() * 100
    df["cum_pct"]     = df["revenue_pct"].cumsum()
    df["abc_class"]   = df["cum_pct"].apply(assign_abc)
    df = df.merge(df_cv, on="category", how="left")
    df["xyz_class"]   = df["cv"].apply(assign_xyz)
    df["abc_xyz"]     = df["abc_class"] + df["xyz_class"]
    df["strategy"]    = df["abc_xyz"].map(STRATEGY_MAP)
    return df


if __name__ == "__main__":
    print("abc_xyz_classifier.py — invoke via notebook cell B1")