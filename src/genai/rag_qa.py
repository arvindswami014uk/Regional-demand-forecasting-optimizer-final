"""
rag_qa.py
RAG Inventory Q&A -- Gen AI Cell A3
Regional Demand Forecasting and Inventory Placement Optimizer

Architecture:
  Documents   : 5 processed CSVs converted to text chunks
  Embeddings  : sentence-transformers all-MiniLM-L6-v2 (local)
  Vector store: FAISS IndexFlatIP (cosine similarity)
  Generator   : Groq llama-3.3-70b-versatile
"""

import os
import time
import numpy as np
import pandas as pd
import faiss
from groq import Groq
from sentence_transformers import SentenceTransformer


GROQ_MODEL    = os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')
EMBED_MODEL   = 'all-MiniLM-L6-v2'
TOP_K         = 5


def call_groq_with_retry(client, model, prompt, max_retries=4, base_delay=5):
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=400,
                temperature=0.2,
            )
            return response
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                time.sleep(base_delay * (2 ** (attempt - 1)))
    raise RuntimeError(f'All retries exhausted: {last_error}')


class RAGInventoryQA:
    """
    Retrieval-Augmented Generation Q&A for inventory data.
    Embeds CSV data locally, retrieves via FAISS, generates via Groq.
    """

    def __init__(self, project_root: str):
        self.project_root = project_root
        api_key = os.environ.get('GROQ_API_KEY', '')
        assert api_key, 'GROQ_API_KEY not set in environment'
        self.groq_client = Groq(api_key=api_key)
        self.embedder    = SentenceTransformer(EMBED_MODEL)
        self.chunks      = []
        self.index       = None

    def build_index(self, chunks: list):
        self.chunks = chunks
        texts = [c['text'] for c in chunks]
        embs  = self.embedder.encode(texts, normalize_embeddings=True)
        embs  = np.array(embs, dtype='float32')
        dim   = embs.shape[1]
        self.index = faiss.IndexFlatIP(dim)
        self.index.add(embs)

    def retrieve(self, query: str, top_k: int = TOP_K) -> list:
        q = self.embedder.encode([query], normalize_embeddings=True)
        q = np.array(q, dtype='float32')
        scores, indices = self.index.search(q, top_k)
        return [self.chunks[i] for i in indices[0]]

    def answer(self, question: str) -> str:
        docs    = self.retrieve(question)
        context = '\n'.join(d['text'] for d in docs)
        prompt  = (
            'Answer using ONLY this context. Be specific with numbers. '
            f'Question: {question}\nContext: {context}\nAnswer:'
        )
        resp = call_groq_with_retry(self.groq_client, GROQ_MODEL, prompt)
        return resp.choices[0].message.content.strip()


def main():
    project_root = os.environ.get(
        'PROJECT_ROOT',
        '/content/Regional-demand-forecasting-optimizer-final'
    )
    qa = RAGInventoryQA(project_root)
    print('RAG Q&A system ready')
    questions = [
        'Which warehouse has the highest utilization?',
        'What is the 12-week demand forecast for ELECTRONICS in the East region?',
        'Which shipping lane has the lowest carbon footprint?',
        'What are the top 3 most expensive SKU categories to hold?',
        'Which region-category combination has the highest forecast uncertainty?',
    ]
    for q in questions:
        print(f'Q: {q}')
        print(f'A: {qa.answer(q)}')
        print()


if __name__ == '__main__':
    main()