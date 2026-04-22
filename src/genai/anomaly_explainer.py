"""
anomaly_explainer.py
Anomaly Explainer -- Gen AI Cell A2
Regional Demand Forecasting and Inventory Placement Optimizer

Detects demand anomalies via z-score (|z|>2.0) per region+category group
and generates plain-English explanations via Groq LLM.
"""

import os
import time
import datetime
import numpy as np
import pandas as pd
from groq import Groq


GROQ_MODEL   = os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')
Z_THRESHOLD  = 2.0
MAX_ANOMALIES = 20


def call_groq_with_retry(client, model, prompt, max_retries=4, base_delay=5):
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=300,
                temperature=0.3,
            )
            return response
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                time.sleep(base_delay * (2 ** (attempt - 1)))
    raise RuntimeError(f'All retries exhausted: {last_error}')


class AnomalyExplainer:
    """Detects and explains demand anomalies using z-scores and Groq LLM."""

    def __init__(self, project_root: str):
        self.project_root = project_root
        api_key = os.environ.get('GROQ_API_KEY', '')
        assert api_key, 'GROQ_API_KEY not set in environment'
        self.client = Groq(api_key=api_key)
        self.model  = GROQ_MODEL

    def detect(self, df: pd.DataFrame,
               demand_col: str, region_col: str, cat_col: str) -> pd.DataFrame:
        df_w = df.copy()
        df_w['group_mean'] = df_w.groupby([region_col, cat_col])[demand_col].transform('mean')
        df_w['group_std']  = df_w.groupby([region_col, cat_col])[demand_col].transform('std')
        df_w['group_std']  = df_w['group_std'].replace(0, np.nan)
        df_w['z_score']    = (df_w[demand_col] - df_w['group_mean']) / df_w['group_std']
        df_w = df_w.dropna(subset=['z_score'])
        anomalies = df_w[df_w['z_score'].abs() > Z_THRESHOLD].copy()
        anomalies = anomalies.sort_values('z_score', key=abs, ascending=False)
        return anomalies.head(MAX_ANOMALIES)

    def explain(self, row: dict) -> str:
        prompt = (
            'You are a supply chain analyst. Explain this demand anomaly in 2-3 sentences. '
            f"Region: {row['region']}, Category: {row['category']}, "
            f"Z-score: {row['z_score']:.2f}, Units: {row['units']:.0f}"
        )
        resp = call_groq_with_retry(self.client, self.model, prompt)
        return resp.choices[0].message.content.strip()


def main():
    project_root = os.environ.get(
        'PROJECT_ROOT',
        '/content/Regional-demand-forecasting-optimizer-final'
    )
    processed = os.path.join(project_root, 'data', 'processed')
    df = pd.read_csv(os.path.join(processed, 'modeling_dataset.csv'))
    explainer = AnomalyExplainer(project_root)
    anomalies = explainer.detect(df, 'total_units', 'region', 'category')
    print(f'Anomalies detected: {len(anomalies)}')
    for _, row in anomalies.iterrows():
        explanation = explainer.explain({
            'region'  : row['region'],
            'category': row['category'],
            'z_score' : row['z_score'],
            'units'   : row['total_units'],
        })
        print(explanation)


if __name__ == '__main__':
    main()