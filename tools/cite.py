"""Citation formatter for design proposals.

Given a list of search-hit row_ids, render compact bibliographic citations
(title + source file + LLM provenance) that the agent can paste into its
reaction-design recommendations.

Two styles:
  - 'inline'    : [Gemini_00123 "Spontaneous Reduction..." (src: foo.pdf)]
  - 'numbered'  : footnote-style numbered references with a key at the end

The agent uses 'inline' during reasoning (so every claim has provenance)
and 'numbered' for the final user-facing recipe card.
"""
from __future__ import annotations

import argparse
import json
import sys
import io
from pathlib import Path
from functools import lru_cache

import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / 'data'


@lru_cache(maxsize=1)
def _corpus() -> pd.DataFrame:
    return pd.read_parquet(DATA / 'unified_corpus.parquet').set_index('_row_id')


def _row(row_id: str) -> pd.Series | None:
    df = _corpus()
    return df.loc[row_id] if row_id in df.index else None


def cite_inline(row_id: str, title_chars: int = 80) -> str:
    row = _row(row_id)
    if row is None:
        return f'[{row_id} UNKNOWN]'
    title = (row.get('title') or row.get('input_title') or '').strip()
    if not title:
        title = (row.get('research_topic') or '').strip()
    src = row.get('source_name', '') or ''
    return f'[{row.get("_source_llm", "?")}_{row_id} "{title[:title_chars]}" (src: {src})]'


def cite_numbered(row_ids: list[str], title_chars: int = 120) -> tuple[list[str], str]:
    """Returns (markers, bibliography_block).

    markers[i] is the in-text marker for row_ids[i] (e.g. "[3]"); the
    bibliography block is a multi-line string suitable for appending to
    the bottom of a recipe card.
    """
    seen: dict[str, int] = {}
    bib_lines: list[str] = []
    markers: list[str] = []
    for rid in row_ids:
        if rid in seen:
            markers.append(f'[{seen[rid]}]')
            continue
        n = len(seen) + 1
        seen[rid] = n
        markers.append(f'[{n}]')
        row = _row(rid)
        if row is None:
            bib_lines.append(f'[{n}] {rid}  UNKNOWN')
            continue
        title = (row.get('title') or row.get('input_title') or '').strip() or '(no title)'
        src = row.get('source_name', '') or ''
        llm = row.get('_source_llm', '?')
        bib_lines.append(f'[{n}] {title[:title_chars]}  — extracted by {llm};  src: {src}')
    return markers, '\n'.join(bib_lines)


def _cli() -> None:
    ap = argparse.ArgumentParser(description='Render citations for a list of row_ids.')
    ap.add_argument('row_ids', nargs='+', help='one or more _row_id values')
    ap.add_argument('--style', choices=['inline', 'numbered'], default='numbered')
    args = ap.parse_args()

    if args.style == 'inline':
        for rid in args.row_ids:
            print(cite_inline(rid))
    else:
        markers, bib = cite_numbered(args.row_ids)
        print('Markers: ' + ', '.join(markers))
        print('Bibliography:')
        print(bib)


if __name__ == '__main__':
    _cli()
