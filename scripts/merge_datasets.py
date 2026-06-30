"""Merge three LLM-extracted Excel datasets into one unified parquet corpus.

Inputs (LLM-derived structured extractions of the same paper corpus):
    04_数据/Gemini/merged_results_for_final_use.xlsx                  (sheet: merged_results)
    04_数据/Deepseek/microdroplet_analysis_output/merged_results_clean.xlsx
    04_数据/Qwen/microdroplet_analysis_output/merged_results_clean.xlsx

Output:
    data/unified_corpus.parquet

Schema additions:
    _row_id          : globally unique row identifier (str)
    _source_llm      : which LLM extracted this record (Gemini/Deepseek/Qwen)
    _paper_key       : canonical key for the underlying paper (used for dedup hints)
    _doc_text        : long-form text used downstream for embedding & search
    _short_text      : compact summary used for display

The 29 original columns are preserved verbatim. Rows of the same paper
extracted by different LLMs share a _paper_key but are kept as separate rows
so that downstream tools can surface inter-LLM agreement / disagreement.
"""
from __future__ import annotations

import re
import sys
import io
from pathlib import Path

import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Resolve repo root from this script's location: scripts/merge_datasets.py
REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
DATA_SRC = ROOT / '04_数据'
DATA_OUT = REPO / 'data'
DATA_OUT.mkdir(parents=True, exist_ok=True)

SOURCES = [
    ('Gemini',   DATA_SRC / 'Gemini' / 'merged_results_for_final_use.xlsx', 'merged_results'),
    ('Deepseek', DATA_SRC / 'Deepseek' / 'microdroplet_analysis_output' / 'merged_results_clean.xlsx', 0),
    ('Qwen',     DATA_SRC / 'Qwen' / 'microdroplet_analysis_output' / 'merged_results_clean.xlsx', 0),
]

# Text fields that go into the embedding/search document. Order matters
# only for human readability of the concatenated form.
DOC_FIELDS = [
    'title',
    'research_topic',
    'reaction_or_process',
    'reactants',
    'products',
    'microdroplet_type',
    'droplet_generation_method',
    'solvent_or_medium',
    'experimental_conditions',
    'instrument_or_platform',
    'proposed_mechanism',
    'interface_related_factors',
    'quantitative_information',
    'important_findings',
    'key_information_summary',
]

# Fields used for the short/display text shown in search results
SHORT_FIELDS = [
    'title', 'reaction_or_process', 'reactants', 'products',
    'microdroplet_type', 'solvent_or_medium',
]


def normalize_for_key(s: str) -> str:
    """Lower-case, strip punctuation/whitespace — for fuzzy paper-key matching."""
    if not isinstance(s, str):
        return ''
    s = s.lower().strip()
    s = re.sub(r'[\s　]+', ' ', s)        # collapse whitespace
    s = re.sub(r'[^\w\s一-鿿]', '', s)  # drop non-alnum non-CJK
    return s


def make_paper_key(row: pd.Series) -> str:
    """Best-effort canonical key for the underlying paper.

    Prefer input_title (clean paper title), then title (LLM-restated), then
    source_name (filename, last resort).
    """
    for f in ('input_title', 'title', 'source_name'):
        v = row.get(f)
        if isinstance(v, str) and v.strip():
            return normalize_for_key(v)[:160]
    return ''


def join_nonnull(row: pd.Series, fields: list[str], sep: str = ' || ') -> str:
    parts = []
    for f in fields:
        v = row.get(f)
        if pd.isna(v):
            continue
        s = str(v).strip()
        if s and s.lower() not in ('unknown', 'nan', 'n/a'):
            parts.append(s)
    return sep.join(parts)


def load_one(name: str, path: Path, sheet) -> pd.DataFrame:
    print(f'[load] {name:9s}  {path.name}', flush=True)
    df = pd.read_excel(path, sheet_name=sheet)
    df = df.copy()
    df['_source_llm'] = name
    df['_row_id'] = [f'{name}_{i:05d}' for i in range(len(df))]
    df['_paper_key'] = df.apply(make_paper_key, axis=1)
    df['_doc_text']  = df.apply(lambda r: join_nonnull(r, DOC_FIELDS, sep=' || '), axis=1)
    df['_short_text'] = df.apply(lambda r: join_nonnull(r, SHORT_FIELDS, sep=' | '), axis=1)
    print(f'           rows={len(df)}  empty_doc_text={(df["_doc_text"].str.len() < 10).sum()}', flush=True)
    return df


def main() -> None:
    frames = [load_one(name, path, sheet) for name, path, sheet in SOURCES]
    merged = pd.concat(frames, ignore_index=True)
    print(f'\n[merged] total rows = {len(merged)}')

    # Drop near-empty docs (would pollute the index)
    before = len(merged)
    merged = merged[merged['_doc_text'].str.len() >= 30].copy()
    print(f'[filter] dropped {before - len(merged)} rows with doc_text < 30 chars')

    # Paper-key clustering stats
    key_counts = merged['_paper_key'].value_counts()
    multi = (key_counts > 1).sum()
    print(f'[stats] unique paper keys = {len(key_counts)}; '
          f'covered by >=2 LLMs = {multi}; '
          f'avg LLMs per paper = {len(merged) / max(len(key_counts), 1):.2f}')

    # Force all object columns to nullable strings so parquet can persist them
    # cleanly (mixed bool/str/None in LLM extractions otherwise breaks Arrow).
    # Also drop invalid UTF-8 surrogates that occasionally sneak in from
    # Excel cells containing pasted binary fragments.
    def _clean_str(s):
        if not isinstance(s, str):
            return s
        return s.encode('utf-8', errors='replace').decode('utf-8')

    for c in merged.columns:
        if merged[c].dtype == object:
            merged[c] = merged[c].apply(_clean_str)
            merged[c] = merged[c].where(merged[c].notna(), None).astype('string')

    out = DATA_OUT / 'unified_corpus.parquet'
    merged.to_parquet(out, index=False)
    print(f'\n[write] {out}  ({out.stat().st_size / 1024:.1f} KB)')

    # Tiny CSV preview for human inspection (first 50 rows, short text only)
    preview = merged[['_row_id', '_source_llm', '_paper_key', '_short_text']].head(50)
    preview.to_csv(DATA_OUT / 'unified_corpus_preview.csv', index=False, encoding='utf-8-sig')
    print(f'[write] {DATA_OUT / "unified_corpus_preview.csv"} (first 50 rows for sanity check)')


if __name__ == '__main__':
    main()
