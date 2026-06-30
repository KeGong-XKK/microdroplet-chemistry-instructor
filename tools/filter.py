"""Categorical filtering & taxonomy classifiers.

The reaction-type taxonomy (REACTION_CATS) is migrated verbatim from the
legacy 09_预测系统 work — it has been hand-tuned on this corpus and the
bilingual coverage is non-trivial to redo from scratch.

Functions are designed for two callers:
  - tools/search.py: needs classify_reaction_row to apply reaction_class filter
  - skills: list_reaction_classes() / count_by_class() for situating a query
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import io
from pathlib import Path
from functools import lru_cache

import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / 'data'


# ---------- taxonomies ----------

REACTION_CATS: dict[str, list[str]] = {
    'Organic transformations': [
        r'\borganic synth', r'\borganic transformation', r'\borganic reaction',
        r'c[\s\-]?n bond', r'c[\s\-]?c bond', r'c[\s\-]?o bond',
        r'condensation', r'coupling', r'cycliz', r'cycloaddition',
        r'esterificat', r'amidat', r'aza[\s\-]?michael', r'mannich', r'aldol',
        r'isomerization', r'ring[\s\-]?opening', r'\bhydrolysis\b',
        r'hydrothiolation', r'thiol[\s\-]?ene', r'sufex',
        r'diels[\s\-]?alder', r'suzuki', r'click chemistry', r'click reaction',
        r'\bsynthesis\b', r'imine formation', r'amine formation', r'amide formation',
        r'sn2\b', r'sn1\b', r'nucleophilic', r'electrophilic',
        r'urea synthesis', r'amidation', r'methylation', r'epoxide', r'ring[\s\-]?open',
        r'合成', r'有机', r'缩合', r'偶联', r'环加成', r'环化', r'开环',
        r'酯化', r'酰胺化', r'胺化', r'醛醇', r'迈克尔', r'迈克加成',
        r'脱羧', r'水解(?!氨)', r'异构化', r'重排', r'吲哚',
        r'点击反应', r'硫醇', r'迪尔斯', r'胺基化', r'酯', r'酰胺', r'肽键',
    ],
    'Redox chemistry': [
        r'\bredox\b', r'\boxidation\b', r'\breduction\b',
        r'h2o2', r'hydrogen peroxide', r'\bperoxide\b',
        r'electron transfer', r'\bo2\b.*reduction', r'h2 generation', r'h2 evolution',
        r'singlet oxygen', r'reactive oxygen',
        r'spontaneous oxidation', r'spontaneous reduction',
        r'electrochemical', r'photocatal', r'photoox', r'photored',
        r'co2 reduction', r'co2 fixation', r'co2 activation',
        r'氧化(?!物质)', r'还原(?!性)', r'氧化还原', r'过氧化氢', r'电子转移',
        r'自发氧化', r'自发还原', r'电化学', r'光催化', r'析氢', r'析氧',
        r'活性氧', r'单线态氧', r'co2还原', r'二氧化碳还原',
    ],
    'Atmospheric / environmental': [
        r'atmospher', r'\baerosol', r'cloud droplet', r'sea[\s\-]?spray',
        r'pollutant', r'\bsoa\b', r'secondary organic aerosol',
        r'environmental', r'\bsulfate\b', r'\bnitrate\b', r'\bn2o5\b',
        r'\bozone\b', r'\bozonation\b', r'photoox.*aerosol',
        r'corrosion', r'sulfur dioxide', r'so2 oxid',
        r'particulate matter', r'pm2\.5', r'\bvoc\b',
        r'大气', r'气溶胶', r'云滴', r'海喷', r'污染', r'颗粒物', r'雾霾',
        r'二次有机', r'硫酸盐', r'硝酸盐', r'臭氧', r'腐蚀',
    ],
    'Biochemical / prebiotic': [
        r'peptide', r'protein', r'amino acid', r'enzyme', r'enzymatic',
        r'biochem', r'prebiotic', r'origin of life', r'\brna\b', r'\bdna\b',
        r'nucleoside', r'nucleotide', r'coacervate', r'protocell',
        r'antibody', r'tcep', r'disulfide reduction',
        r'glycosylat', r'deglycosylat', r'proteol', r'digestion',
        r'肽', r'蛋白', r'氨基酸', r'酶', r'生化', r'前生命', r'生命起源',
        r'核酸', r'核糖', r'寡聚', r'蛋白质酶解', r'测序', r'抗体',
        r'二硫键', r'糖基化', r'去糖基化',
    ],
    'Polymerization / oligomerization': [
        r'polymeriz', r'oligomeriz', r'chain extension',
        r'polymer formation', r'oligomer', r'co[\s\-]?polymeriz',
        r'metal[\s\-]?organic framework', r'cross[\s\-]?link',
        r'聚合', r'寡聚物', r'寡聚化', r'交联', r'链增长',
    ],
    'Inorganic / nanomaterial synthesis': [
        r'nanoparticle', r'nanowire', r'nanocluster', r'quantum dot',
        r'\bqd[s]?\b synthes', r'metal nanoparticle', r'\bag\b.*nanopar',
        r'\bau\b.*nanopar', r'gold nanopar', r'silver nanopar',
        r'\bmof\b synthes', r'crystallization', r'crystallizat',
        r'纳米颗粒', r'纳米线', r'量子点', r'金纳米', r'银纳米', r'晶化',
    ],
}

DROPLET_TYPES: dict[str, list[str]] = {
    'Charged / electrospray droplets': [
        r'charged', r'electrospray', r'\besi\b', r'\bessi\b', r'nanoesi',
        r'带电', r'电喷雾',
    ],
    'Sprayed / nebulised neutral droplets': [
        r'\bspray', r'nebuliz', r'aerosol generator', r'ultrasonic',
        r'喷雾', r'雾化', r'超声雾化',
    ],
    'Levitated / suspended droplets': [
        r'levitat', r'optical trap', r'acoustic trap', r'suspended',
        r'悬浮', r'光镊', r'声悬浮',
    ],
    'Microfluidic / segmented droplets': [
        r'microfluid', r'segmented', r'flow[\s\-]?focusing',
        r'oil[\s\-]?in[\s\-]?water', r'water[\s\-]?in[\s\-]?oil',
        r'微流控', r'流动聚焦', r'油包水', r'水包油',
    ],
}

REACTION_FIELDS = [
    'research_topic', 'reaction_or_process', 'paper_type',
    'important_findings', 'key_information_summary',
    'acceleration_related_description',
]


def _haystack(row: pd.Series, fields: list[str]) -> str:
    parts: list[str] = []
    for f in fields:
        v = row.get(f)
        if pd.isna(v):
            continue
        parts.append(str(v))
    return ' || '.join(parts).lower()


def _match_categories(text: str, cats: dict[str, list[str]]) -> set[str]:
    hits: set[str] = set()
    for cat, patterns in cats.items():
        for pat in patterns:
            if re.search(pat, text, re.I):
                hits.add(cat)
                break
    return hits


def classify_reaction_row(row: pd.Series) -> set[str]:
    """Reaction-type label set for one corpus row (may match multiple classes)."""
    hits = _match_categories(_haystack(row, REACTION_FIELDS), REACTION_CATS)
    return hits or {'Other / unclassified'}


def classify_query(query: str, taxonomy: str = 'reaction') -> list[str]:
    """Reaction- or droplet-type labels for a free-text query."""
    cats = REACTION_CATS if taxonomy == 'reaction' else DROPLET_TYPES
    return sorted(_match_categories(query, cats))


# ---------- corpus-level stats ----------

@lru_cache(maxsize=1)
def _corpus() -> pd.DataFrame:
    return pd.read_parquet(DATA / 'unified_corpus.parquet')


def list_reaction_classes() -> list[str]:
    return list(REACTION_CATS.keys()) + ['Other / unclassified']


def list_droplet_types() -> list[str]:
    return list(DROPLET_TYPES.keys())


def count_by_reaction_class(
    droplet_type_contains: str | None = None,
    source_llm: str | None = None,
) -> dict[str, int]:
    """Cohort sizes for each reaction class under optional constraints."""
    df = _corpus()
    if source_llm is not None:
        df = df[df['_source_llm'] == source_llm]
    if droplet_type_contains is not None:
        needle = droplet_type_contains.lower()
        df = df[df['microdroplet_type'].fillna('').str.lower().str.contains(
            re.escape(needle))]
    counts: dict[str, int] = {c: 0 for c in list_reaction_classes()}
    for _, row in df.iterrows():
        for c in classify_reaction_row(row):
            counts[c] += 1
    return counts


def _cli() -> None:
    ap = argparse.ArgumentParser(description='Filter / classify the microdroplet corpus.')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p1 = sub.add_parser('classify-query', help='taxonomy labels for a free-text query')
    p1.add_argument('query')
    p1.add_argument('--taxonomy', choices=['reaction', 'droplet'], default='reaction')

    p2 = sub.add_parser('counts', help='record counts per reaction class')
    p2.add_argument('--droplet-type', dest='droplet_type', default=None)
    p2.add_argument('--source-llm', dest='source_llm', default=None,
                    choices=['Gemini', 'Deepseek', 'Qwen'])

    sub.add_parser('list-reactions', help='list reaction-class names')
    sub.add_parser('list-droplet-types', help='list droplet-type names')

    args = ap.parse_args()

    if args.cmd == 'classify-query':
        print(json.dumps(classify_query(args.query, args.taxonomy),
                         ensure_ascii=False, indent=2))
    elif args.cmd == 'counts':
        print(json.dumps(
            count_by_reaction_class(args.droplet_type, args.source_llm),
            ensure_ascii=False, indent=2))
    elif args.cmd == 'list-reactions':
        print(json.dumps(list_reaction_classes(), ensure_ascii=False, indent=2))
    elif args.cmd == 'list-droplet-types':
        print(json.dumps(list_droplet_types(), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    _cli()
