"""Semantic + keyword hybrid search over the unified corpus.

Designed to be called both as a library function (from skills) and as a CLI:

    python -m tools.search "CO2 reduction in microdroplets" --k 10
    python -m tools.search "CO2 reduction" --k 10 --reaction-class "Redox chemistry"

The hybrid scoring:
    final = alpha * semantic_cosine + (1 - alpha) * keyword_overlap
    default alpha = 0.7 (semantics dominates, but exact-term matches still help)

Outputs JSON to stdout — easy for an LLM to consume.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import io
from pathlib import Path
from functools import lru_cache

import numpy as np
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / 'data'


# ---------- lazy-loaded artefacts ----------

@lru_cache(maxsize=1)
def _corpus() -> pd.DataFrame:
    p = DATA / 'unified_corpus.parquet'
    if not p.exists():
        sys.exit(f'[abort] {p} not found — run scripts/merge_datasets.py')
    return pd.read_parquet(p)


@lru_cache(maxsize=1)
def _embeddings() -> np.ndarray:
    p = DATA / 'embeddings.npy'
    if not p.exists():
        sys.exit(f'[abort] {p} not found — run scripts/build_index.py')
    return np.load(p)


@lru_cache(maxsize=1)
def _index_meta() -> dict:
    with open(DATA / 'index_meta.json', encoding='utf-8') as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _encoder():
    """Load bge-m3 once. Heavy — only invoked when semantic search is actually
    requested (keyword-only paths don't pay this cost)."""
    from sentence_transformers import SentenceTransformer
    import torch
    meta = _index_meta()
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    return SentenceTransformer(meta['model'], device=device)


# ---------- search primitives ----------

def _embed_query(q: str) -> np.ndarray:
    emb = _encoder().encode(
        [q], convert_to_numpy=True, normalize_embeddings=True
    ).astype('float32')
    return emb[0]


def _semantic_scores(q: str) -> np.ndarray:
    """Cosine similarity to every corpus document. Shape: [N]."""
    return _embeddings() @ _embed_query(q)


def _tokenize(s: str) -> set[str]:
    s = s.lower()
    # Keep latin words and CJK runs
    tokens = re.findall(r'[a-z0-9]+|[一-鿿]+', s)
    return {t for t in tokens if len(t) >= 2}


def _keyword_scores(q: str) -> np.ndarray:
    """Per-doc keyword overlap, normalised to [0, 1]. Cheap, complements semantics."""
    q_tokens = _tokenize(q)
    if not q_tokens:
        return np.zeros(len(_corpus()), dtype='float32')
    docs = _corpus()['_doc_text'].astype(str).tolist()
    out = np.zeros(len(docs), dtype='float32')
    for i, d in enumerate(docs):
        d_tokens = _tokenize(d)
        if not d_tokens:
            continue
        out[i] = len(q_tokens & d_tokens) / len(q_tokens)
    return out


# ---------- main entry ----------

def semantic_search(
    query: str,
    k: int = 10,
    *,
    alpha: float = 0.0,
    reaction_class: str | None = None,
    droplet_type_contains: str | None = None,
    source_llm: str | None = None,
    require_acceleration: bool = False,
) -> list[dict]:
    """Hybrid semantic+keyword search with optional filters.

    Parameters
    ----------
    query : the user's free-text reaction description / target.
    k : number of results to return.
    alpha : semantic-vs-keyword mixing weight. Default 0.0 = pure keyword search
            (no semantic deps required). Set 0.7 to blend in BGE-M3 cosine
            similarity once `requirements-semantic.txt` has been installed and
            `scripts/build_index.py` has been run.
    reaction_class : filter to a regex category from tools.filter.REACTION_CATS.
    droplet_type_contains : substring match against microdroplet_type field
                            (case-insensitive). e.g. "charged", "water", "ESI".
    source_llm : restrict to one LLM's view (Gemini/Deepseek/Qwen). Default:
                 all three, deduplicated by paper_key in the final ranking.
    require_acceleration : if True, only return records whose
                           whether_acceleration_discussed != "No".
    """
    df = _corpus()

    # Build candidate mask from filters first (cheap)
    mask = np.ones(len(df), dtype=bool)
    if source_llm is not None:
        mask &= (df['_source_llm'] == source_llm).to_numpy()
    if droplet_type_contains is not None:
        needle = droplet_type_contains.lower()
        mask &= df['microdroplet_type'].fillna('').str.lower().str.contains(
            re.escape(needle)
        ).to_numpy()
    if require_acceleration:
        mask &= ~df['whether_acceleration_discussed'].fillna('').isin(
            ['No', 'no', '否', 'false', 'False']
        ).to_numpy()

    if reaction_class is not None:
        from tools.filter import classify_reaction_row
        rxn_hits = df.apply(classify_reaction_row, axis=1)
        mask &= rxn_hits.apply(lambda hs: reaction_class in hs).to_numpy()

    if not mask.any():
        return []

    # Score (skip embedding load entirely if alpha == 0; lets the agent run
    # in keyword-only mode before scripts/build_index.py has been run)
    if alpha > 0.0:
        sem = _semantic_scores(query)
    else:
        sem = np.zeros(len(df), dtype='float32')
    kw  = _keyword_scores(query) if alpha < 1.0 else np.zeros_like(sem)
    score = alpha * sem + (1 - alpha) * kw
    score[~mask] = -np.inf

    # Rank (over-fetch, then dedup by paper_key keeping top-scoring view)
    top_idx = np.argsort(-score)[: k * 3]
    seen_keys: set[str] = set()
    results: list[dict] = []
    for i in top_idx:
        if not np.isfinite(score[i]):
            break
        key = df.iloc[i]['_paper_key']
        if key in seen_keys:
            continue
        seen_keys.add(key)
        row = df.iloc[i]
        results.append({
            'row_id': row['_row_id'],
            'source_llm': row['_source_llm'],
            'paper_key': key,
            'score': float(score[i]),
            'semantic_score': float(sem[i]),
            'keyword_score': float(kw[i]),
            'title': row.get('title') if pd.notna(row.get('title')) else '',
            'reaction_or_process': row.get('reaction_or_process'),
            'reactants': row.get('reactants'),
            'products': row.get('products'),
            'microdroplet_type': row.get('microdroplet_type'),
            'droplet_generation_method': row.get('droplet_generation_method'),
            'solvent_or_medium': row.get('solvent_or_medium'),
            'experimental_conditions': row.get('experimental_conditions'),
            'proposed_mechanism': row.get('proposed_mechanism'),
            'key_information_summary': row.get('key_information_summary'),
            'source_name': row.get('source_name'),
        })
        if len(results) >= k:
            break

    return results


def _cli() -> None:
    ap = argparse.ArgumentParser(description='Hybrid search over the microdroplet corpus.')
    ap.add_argument('query', help='free-text query')
    ap.add_argument('--k', type=int, default=10)
    ap.add_argument('--alpha', type=float, default=0.0,
                    help='semantic weight (0.0 = pure keyword [default]; 0.7 = balanced; '
                         '1.0 = pure semantic). Set > 0 only after installing '
                         'requirements-semantic.txt and running scripts/build_index.py.')
    ap.add_argument('--reaction-class', default=None)
    ap.add_argument('--droplet-type', dest='droplet_type', default=None,
                    help='substring match against microdroplet_type field')
    ap.add_argument('--source-llm', dest='source_llm', default=None,
                    choices=['Gemini', 'Deepseek', 'Qwen'])
    ap.add_argument('--require-acceleration', action='store_true')
    args = ap.parse_args()

    results = semantic_search(
        args.query, k=args.k, alpha=args.alpha,
        reaction_class=args.reaction_class,
        droplet_type_contains=args.droplet_type,
        source_llm=args.source_llm,
        require_acceleration=args.require_acceleration,
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    _cli()
