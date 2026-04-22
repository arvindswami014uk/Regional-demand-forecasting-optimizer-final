"""
llm_narrator.py
LLM Insight Narrator -- Gen AI Cell A1
Regional Demand Forecasting and Inventory Placement Optimizer

Reads real numbers from processed CSVs, builds a structured
context string, and calls Groq (llama-3.3-70b) to generate
an executive summary saved as reports/executive_summary_llm.md
"""

import os
import time
import datetime
import pandas as pd
from groq import Groq


GROQ_MODEL = os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')


def call_groq_with_retry(client, model, prompt, max_retries=4, base_delay=5):
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=1500,
                temperature=0.3,
            )
            return response
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                print(f'Retry in {delay}s...')
                time.sleep(delay)
    raise RuntimeError(f'All retries exhausted: {last_error}')


class LLMNarrator:
    """Generates executive summaries via Groq LLM."""

    def __init__(self, project_root: str):
        self.project_root = project_root
        api_key = os.environ.get('GROQ_API_KEY', '')
        assert api_key, 'GROQ_API_KEY not set in environment'
        self.client = Groq(api_key=api_key)
        self.model  = GROQ_MODEL

    def load_data(self) -> dict:
        processed = os.path.join(self.project_root, 'data', 'processed')
        df_fc = pd.read_csv(os.path.join(processed, 'forecast_12wk_forward.csv'))
        return {
            'fc_min' : float(df_fc['predicted_units'].min()),
            'fc_max' : float(df_fc['predicted_units'].max()),
            'fc_mean': float(df_fc['predicted_units'].mean()),
        }

    def generate(self, context: str) -> str:
        prompt = (
            'You are a senior supply chain analytics consultant. '
            'Write a professional executive summary in markdown. '
            f'Data: {context}'
        )
        response = call_groq_with_retry(self.client, self.model, prompt)
        return response.choices[0].message.content.strip()


def main():
    project_root = os.environ.get(
        'PROJECT_ROOT',
        '/content/Regional-demand-forecasting-optimizer-final'
    )
    narrator = LLMNarrator(project_root)
    numbers  = narrator.load_data()
    summary  = narrator.generate(str(numbers))
    out_path = os.path.join(project_root, 'reports', 'executive_summary_llm.md')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    lines = []
    for line in summary.splitlines():
        lines.append(line)
    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines))
    print(f'Written: {out_path}')


if __name__ == '__main__':
    main()