"""Pattern extractor — aggregates the parameter distributions across a set
of search hits so the design agent can reason about "what the literature
typically does" for a query.

Given a list of search results (the dict shape produced by tools/search.py),
combine() returns a structured digest:

    {
      "n_hits": 47,
      "n_papers": 31,
      "droplet_type": [("charged microdroplet", 18), ("water droplet", 9), ...],
      "droplet_generation_method": [...],
      "solvent_or_medium": [...],
      "reactants": [(extracted_term, freq, [example row_ids]), ...],
      "mechanism_claims": [...],
      "key_findings_excerpts": [(row_id, text), ...],
    }

The idea: the agent uses this digest plus the raw hits to author a
"reaction-design recipe card" that is fully traceable to the underlying
papers.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import io
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stdin, 'reconfigure'):
    sys.stdin.reconfigure(encoding='utf-8', errors='replace')

# Fields that get tallied directly (their values are typically short labels)
LABEL_FIELDS = [
    'microdroplet_type',
    'droplet_generation_method',
    'solvent_or_medium',
]

# Fields that need to be broken into sub-items before tallying
LIST_FIELDS = ['reactants', 'products']

# Fields kept as free-text excerpts for the agent to quote
EXCERPT_FIELDS = ['proposed_mechanism', 'key_information_summary']


def _split_items(text: str) -> list[str]:
    """Cheap split for fields like "AgNO3, NaBH4 and Tween-20" → list of 3.

    LLM extractions vary in how reactants are listed; we use a permissive
    splitter and let downstream callers deal with imperfect normalization.
    """
    if not isinstance(text, str):
        return []
    # Split on common separators (Chinese & English), drop parentheticals
    parts = re.split(r'[,;、；,]|(?:\s+and\s+)|(?:\s+及\s+)|(?:\s+和\s+)', text)
    out: list[str] = []
    for p in parts:
        p = re.sub(r'\(([^)]*)\)', '', p)
        p = re.sub(r'（([^）]*)）', '', p)
        p = p.strip(' .;,:、；')
        if 2 <= len(p) <= 120:
            out.append(p)
    return out


def _normalize_label(s: str) -> str:
    if not isinstance(s, str):
        return ''
    s = s.strip().lower()
    s = re.sub(r'\s+', ' ', s)
    return s


def combine(hits: list[dict], *, top_n: int = 8, excerpt_chars: int = 280) -> dict:
    """Aggregate parameter distributions across a set of search hits."""
    if not hits:
        return {
            'n_hits': 0, 'n_papers': 0,
            'droplet_type': [], 'droplet_generation_method': [],
            'solvent_or_medium': [], 'reactants': [], 'products': [],
            'mechanism_claims': [], 'key_findings_excerpts': [],
        }

    # Counter per label field (normalised to lowercase for grouping, but we
    # preserve a canonical surface form per bucket)
    label_counters: dict[str, Counter] = {f: Counter() for f in LABEL_FIELDS}
    label_surfaces: dict[str, dict[str, str]] = {f: {} for f in LABEL_FIELDS}

    list_counters: dict[str, Counter] = {f: Counter() for f in LIST_FIELDS}
    list_surfaces: dict[str, dict[str, str]] = {f: {} for f in LIST_FIELDS}
    list_examples: dict[str, dict[str, list[str]]] = {f: {} for f in LIST_FIELDS}

    mechanism_claims: list[tuple[str, str]] = []
    findings_excerpts: list[tuple[str, str]] = []

    paper_keys: set[str] = set()

    for h in hits:
        rid = h.get('row_id', '?')
        paper_keys.add(h.get('paper_key', rid))

        for f in LABEL_FIELDS:
            v = h.get(f)
            if not isinstance(v, str) or not v.strip():
                continue
            key = _normalize_label(v)
            label_counters[f][key] += 1
            if key not in label_surfaces[f]:
                label_surfaces[f][key] = v.strip()

        for f in LIST_FIELDS:
            v = h.get(f)
            for item in _split_items(v):
                k = _normalize_label(item)
                if not k:
                    continue
                list_counters[f][k] += 1
                if k not in list_surfaces[f]:
                    list_surfaces[f][k] = item.strip()
                list_examples[f].setdefault(k, [])
                if rid not in list_examples[f][k] and len(list_examples[f][k]) < 5:
                    list_examples[f][k].append(rid)

        mech = h.get('proposed_mechanism')
        if isinstance(mech, str) and mech.strip():
            mechanism_claims.append((rid, mech.strip()[:excerpt_chars]))
        kf = h.get('key_information_summary')
        if isinstance(kf, str) and kf.strip():
            findings_excerpts.append((rid, kf.strip()[:excerpt_chars]))

    def _top(cnt: Counter, surfaces: dict[str, str]) -> list[tuple[str, int]]:
        return [(surfaces.get(k, k), n) for k, n in cnt.most_common(top_n)]

    def _top_with_examples(
        cnt: Counter, surfaces: dict[str, str], examples: dict[str, list[str]]
    ) -> list[dict]:
        return [
            {'value': surfaces.get(k, k), 'count': n, 'example_rows': examples.get(k, [])}
            for k, n in cnt.most_common(top_n)
        ]

    return {
        'n_hits': len(hits),
        'n_papers': len(paper_keys),
        'droplet_type':              _top(label_counters['microdroplet_type'],
                                          label_surfaces['microdroplet_type']),
        'droplet_generation_method': _top(label_counters['droplet_generation_method'],
                                          label_surfaces['droplet_generation_method']),
        'solvent_or_medium':         _top(label_counters['solvent_or_medium'],
                                          label_surfaces['solvent_or_medium']),
        'reactants':                 _top_with_examples(list_counters['reactants'],
                                                        list_surfaces['reactants'],
                                                        list_examples['reactants']),
        'products':                  _top_with_examples(list_counters['products'],
                                                        list_surfaces['products'],
                                                        list_examples['products']),
        'mechanism_claims': mechanism_claims[: top_n * 2],
        'key_findings_excerpts': findings_excerpts[: top_n * 2],
    }


def _cli() -> None:
    ap = argparse.ArgumentParser(
        description='Aggregate parameter patterns over search hits.\n\n'
                    'Reads a JSON list of hits from stdin (as produced by tools.search), '
                    'writes a digest JSON to stdout.'
    )
    ap.add_argument('--top-n', type=int, default=8)
    args = ap.parse_args()
    hits = json.load(sys.stdin)
    digest = combine(hits, top_n=args.top_n)
    print(json.dumps(digest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    _cli()
