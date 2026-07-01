"""Reaction × Mechanism co-occurrence heatmaps.
Self-contained (no exec import). Uses bilingual regex categories.
For each acceleration=Yes paper, compute reaction-type set and mechanism set,
then count co-occurrences. Output 3 heatmaps per model + cross-model consensus.
"""
import re, sys, io
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = Path(r'E:/中国海洋大学工作/2026/课题/微液滴有关课题/微液滴AI多智能体工作')
D = ROOT/'04_数据'
OUT = D/'三模型对齐/统计对比/反应x机制矩阵'
OUT.mkdir(parents=True, exist_ok=True)

# ============== Categories (bilingual) ==============
REACTION_CATS = {
    'Organic transformations': [
        r'\borganic synth', r'\borganic transformation', r'\borganic reaction',
        r'c[\s\-]?n bond', r'c[\s\-]?c bond', r'c[\s\-]?o bond',
        r'condensation', r'coupling', r'cycliz', r'cycloaddition',
        r'esterificat', r'amidat', r'aza[\s\-]?michael', r'mannich', r'aldol',
        r'isomerization', r'ring[\s\-]?opening', r'\bhydrolysis\b',
        r'hydrothiolation', r'thiol[\s\-]?ene', r'sufex',
        r'diels[\s\-]?alder', r'suzuki', r'click chemistry', r'click reaction',
        r'\bsynthesis\b', r'\bformation\b.*(amide|imine|amine|peptide bond|c[\-\s]n|c[\-\s]c)',
        r'imine formation', r'amine formation', r'amide formation',
        r'sn2\b', r'sn1\b', r'nucleophilic', r'electrophilic',
        r'borsche', r'fischer indole', r'pinacol',
        r'urea synthesis', r'amidation', r'methylation', r'epoxide', r'ring[\s\-]?open',
        r'合成', r'有机', r'缩合', r'偶联', r'环加成', r'环化', r'开环',
        r'酯化', r'酰胺化', r'胺化', r'醛醇', r'迈克尔', r'迈克加成',
        r'脱羧', r'水解(?!氨)', r'异构化', r'重排', r'吲哚',
        r'点击反应', r'硫醇', r'迪尔斯', r'C[\-—]N', r'C[\-—]C', r'C[\-—]O',
        r'胺基化', r'酯', r'酰胺', r'肽键', r'选择性烷基化',
    ],
    'Redox chemistry': [
        r'\bredox\b', r'\boxidation\b', r'\breduction\b',
        r'h2o2', r'hydrogen peroxide', r'\bperoxide\b',
        r'electron transfer', r'\bo2\b.*reduction', r'h2 generation', r'h2 evolution',
        r'singlet oxygen', r'\boh\b.*radical', r'reactive oxygen',
        r'spontaneous oxidation', r'spontaneous reduction',
        r'electrochemical', r'photocatal', r'photoox', r'photored',
        r'氧化(?!物质)', r'还原(?!性)', r'氧化还原', r'过氧化氢', r'电子转移',
        r'自发氧化', r'自发还原', r'电化学', r'光催化', r'析氢', r'析氧',
        r'活性氧', r'单线态氧',
    ],
    'Atmospheric / environmental': [
        r'atmospher', r'\baerosol', r'cloud droplet', r'sea[\s\-]?spray',
        r'pollutant', r'\bsoa\b', r'secondary organic aerosol',
        r'environmental', r'\bsulfate\b', r'\bnitrate\b', r'\bn2o5\b',
        r'\bozone\b', r'\bozonation\b', r'photoox.*aerosol',
        r'corrosion', r'sulfur dioxide', r'so2 oxid',
        r'particulate matter', r'pm2\.5', r'\bvoc\b',
        r'大气', r'气溶胶', r'云滴', r'海喷', r'污染', r'颗粒物', r'雾霾',
        r'二次有机', r'硫酸盐', r'硝酸盐', r'臭氧', r'腐蚀', r'颗粒物去除',
    ],
    'Biochemical / prebiotic': [
        r'peptide', r'protein', r'amino acid', r'enzyme', r'enzymatic',
        r'biochem', r'prebiotic', r'origin of life', r'\brna\b', r'\bdna\b',
        r'nucleoside', r'nucleotide', r'coacervate', r'protocell',
        r'antibody', r'\bide[s]\b protease', r'tcep', r'disulfide reduction',
        r'glycosylat', r'deglycosylat', r'proteol', r'digestion',
        r'肽', r'蛋白', r'氨基酸', r'酶', r'生化', r'前生命', r'生命起源',
        r'核酸', r'核糖', r'寡聚', r'蛋白质酶解', r'测序', r'抗体',
        r'二硫键', r'糖基化', r'去糖基化',
    ],
    'Polymerization / oligomerization': [
        r'polymeriz', r'oligomeriz', r'chain extension',
        r'polymer formation', r'oligomer', r'co[\s\-]?polymeriz',
        r'\bmof\b colloid', r'metal[\s\-]?organic framework',
        r'cross[\s\-]?link',
        r'聚合', r'寡聚物', r'寡聚化', r'交联', r'链增长',
    ],
    'Inorganic / nanomaterial synthesis': [
        r'nanoparticle', r'nanowire', r'nanocluster', r'quantum dot',
        r'\bqd[s]?\b\b synthes', r'metal nanoparticle', r'\bag\b.*nanopar',
        r'\bau\b.*nanopar', r'gold nanopar', r'silver nanopar',
        r'\bmof\b synthes', r'crystallization', r'crystallizat',
        r'纳米颗粒', r'纳米线', r'量子点', r'金纳米', r'银纳米', r'晶化',
    ],
}
REACTION_FIELDS = ['research_topic','reaction_or_process','paper_type',
                   'important_findings','key_information_summary',
                   'acceleration_related_description']

MECH_CATS = {
    'Interfacial reactivity (air–water interface)': [
        r'air[\s\-]?water interface', r'\binterfacial reaction', r'gas[\s\-]?liquid interface',
        r'reaction.*interface', r'interface.*reactivit', r'surface reaction',
        r'气[\s\-]?液界面', r'气液界面', r'界面反应', r'空气[\s\-]?水界面', r'界面反应性',
    ],
    'Interfacial electric field': [
        r'electric field', r'interfacial field', r'field[\s\-]?driven',
        r'strong field', r'charge separation', r'contact electrification',
        r'electric double layer', r'edl\b', r'high field', r'strong electric',
        r'电场', r'强电场', r'界面电场', r'电荷分离', r'接触起电', r'双电层',
    ],
    'Local pH / extreme acidity': [
        r'surface ph', r'local ph', r'interfacial ph', r'extreme ph',
        r'enhanced acidit', r'interfacial acid', r'hydronium enrich',
        r'hydroxide enrich', r'oh\- enrich', r'low ph at', r'acidic interface',
        r'表面pH', r'界面pH', r'局部pH', r'极端pH', r'界面酸度', r'局域酸性',
        r'pH富集',
    ],
    'Partial solvation / desolvation': [
        r'partial solvation', r'desolvation', r'incomplete solvation',
        r'reduced solvation', r'altered solvation', r'dehydrat', r'partial hydration',
        r'部分溶剂化', r'脱溶剂', r'不完全溶剂化', r'脱水', r'降低的溶剂化',
    ],
    'Enrichment & orientation': [
        r'enrichment', r'preferential adsorpt', r'surface accumulat',
        r'orientation', r'aligned at interface', r'molecular alignment',
        r'interface partition', r'reactant concentration at',
        r'富集', r'吸附', r'界面富集', r'取向', r'排布', r'有序排列',
    ],
    'Radical pathways': [
        r'\bradical', r'hydroxyl radical', r'hydrated electron',
        r'reactive oxygen species', r'\bros\b', r'singlet oxygen',
        r'thiyl radical', r'carbon radical', r'free radical',
        r'自由基', r'羟基自由基', r'水合电子', r'活性氧', r'单线态氧',
    ],
    'Evaporation-induced concentration': [
        r'evaporation', r'evaporative', r'concentration increase',
        r'solute enrichment.*evap', r'concentrating effect', r'evaporative concentration',
        r'蒸发', r'蒸发浓缩', r'蒸发诱导', r'浓缩效应',
    ],
    'Mass transfer / mixing / collision': [
        r'mass transfer', r'\bmixing\b', r'diffusion[\s\-]length',
        r'droplet collision', r'high surface[\s\-]to[\s\-]volume',
        r'short diffusion', r'rapid transport', r'surface[\s\-]to[\s\-]volume',
        r'传质', r'混合', r'扩散', r'液滴碰撞', r'高比表面积', r'快速传质',
    ],
    'Confinement / nanoscale geometry': [
        r'confinement', r'confined', r'nanoscale geometr', r'curvature',
        r'nano[\s\-]?confined', r'small size effect',
        r'限域', r'纳米限域', r'曲率', r'小尺寸效应',
    ],
}
MECH_FIELDS = ['proposed_mechanism','interface_related_factors',
               'acceleration_related_description','important_findings',
               'key_information_summary']

# ============== Helpers ==============
def norm_yn(v):
    if pd.isna(v): return 'Unknown'
    s = str(v).strip().lower()
    if s in ('yes','true','1','y','是'): return 'Yes'
    if s in ('no','false','0','n','否'): return 'No'
    if s in ('uncertain','unknown','none','nan',''): return 'Unknown'
    return s

def make_haystack(row, fields):
    parts = []
    for f in fields:
        v = row.get(f)
        if pd.isna(v): continue
        parts.append(str(v))
    return ' || '.join(parts).lower()

def match_categories(haystack, cats):
    hits = set()
    for cat, patterns in cats.items():
        for pat in patterns:
            if re.search(pat, haystack, re.I):
                hits.add(cat); break
    return hits

# ============== Layout ==============
RX_ORDER = list(REACTION_CATS.keys()) + ['Other / unclassified']
MH_ORDER = list(MECH_CATS.keys()) + ['No mechanism mentioned / unclassified']

RX_SHORT = {
    'Organic transformations': 'Organic',
    'Redox chemistry': 'Redox',
    'Atmospheric / environmental': 'Atmosphere',
    'Biochemical / prebiotic': 'Biochem',
    'Polymerization / oligomerization': 'Polymer',
    'Inorganic / nanomaterial synthesis': 'Inorg/Nano',
    'Other / unclassified': 'Other',
}
MH_SHORT = {
    'Interfacial reactivity (air–water interface)': 'Interfacial\nreactivity',
    'Interfacial electric field': 'Electric\nfield',
    'Local pH / extreme acidity': 'Local pH',
    'Partial solvation / desolvation': 'Partial\nsolvation',
    'Enrichment & orientation': 'Enrichment\n& orient.',
    'Radical pathways': 'Radical',
    'Evaporation-induced concentration': 'Evaporation',
    'Mass transfer / mixing / collision': 'Mass\ntransfer',
    'Confinement / nanoscale geometry': 'Confinement',
    'No mechanism mentioned / unclassified': 'No mech.',
}

def label_paper(row):
    rx_hits = match_categories(make_haystack(row, REACTION_FIELDS), REACTION_CATS)
    if not rx_hits: rx_hits = {'Other / unclassified'}
    mh_hits = match_categories(make_haystack(row, MECH_FIELDS), MECH_CATS)
    if not mh_hits: mh_hits = {'No mechanism mentioned / unclassified'}
    return rx_hits, mh_hits

def build_matrix(df_acc):
    M = np.zeros((len(RX_ORDER), len(MH_ORDER)), dtype=int)
    for _, row in df_acc.iterrows():
        rx_hits, mh_hits = label_paper(row)
        for rx in rx_hits:
            i = RX_ORDER.index(rx)
            for mh in mh_hits:
                j = MH_ORDER.index(mh)
                M[i, j] += 1
    return M

def draw_heatmap(M, rx_labels, mh_labels, title, fname, fmt='d', cmap='YlOrRd', vmax=None, suffix=''):
    fig, ax = plt.subplots(figsize=(11.5, 6.5))
    if vmax is None: vmax = M.max() if M.size else 1
    im = ax.imshow(M, aspect='auto', cmap=cmap, vmin=0, vmax=vmax if vmax > 0 else 1)
    ax.set_xticks(range(len(mh_labels)))
    ax.set_xticklabels(mh_labels, rotation=30, ha='right', fontsize=9)
    ax.set_yticks(range(len(rx_labels)))
    ax.set_yticklabels(rx_labels, fontsize=10)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            v = M[i, j]
            if fmt == 'd':
                txt = f'{v:.0f}' if v > 0 else ''
            else:
                txt = f'{v:.0%}' if v > 0 else ''
            t_color = 'white' if v > vmax*0.55 else 'black'
            ax.text(j, i, txt, ha='center', va='center', fontsize=9, color=t_color)
    ax.set_xlabel('Acceleration mechanism' + suffix)
    ax.set_ylabel('Reaction type')
    ax.set_title(title)
    cbar = plt.colorbar(im, ax=ax, shrink=0.85)
    cbar.set_label('Count' if fmt == 'd' else 'Fraction')
    plt.tight_layout(); plt.savefig(fname, dpi=150); plt.close()

# ============== Load three datasets ==============
gem = pd.read_excel(D/'Gemini/merged_results_for_final_use.xlsx', sheet_name='merged_results')
gem['_accel'] = gem['whether_acceleration_discussed'].apply(norm_yn)
gem_acc = gem[gem['_accel']=='Yes']

ds = pd.read_excel(D/'Deepseek/microdroplet_analysis_output/merged_results_clean.xlsx')
ds['_accel'] = ds['whether_acceleration_discussed'].apply(norm_yn)
ds_acc = ds[ds['_accel']=='Yes']

qw = pd.read_excel(D/'Qwen/microdroplet_analysis_output/merged_results_clean.xlsx')
qw['_accel'] = qw['whether_acceleration_discussed'].apply(norm_yn)
qw_acc = qw[qw['_accel']=='Yes']

print(f'Acceleration subsets: Gemini={len(gem_acc)}  Deepseek={len(ds_acc)}  Qwen={len(qw_acc)}')

datasets = {'Gemini': gem_acc, 'Deepseek': ds_acc, 'Qwen': qw_acc}

matrices_raw = {}
matrices_rownorm = {}
rx_lab = [RX_SHORT[r] for r in RX_ORDER]
mh_lab = [MH_SHORT[m] for m in MH_ORDER]

for name, df_acc in datasets.items():
    M = build_matrix(df_acc)
    matrices_raw[name] = M
    row_n = M.sum(axis=1, keepdims=True)
    row_n_safe = np.where(row_n==0, 1, row_n)
    Mr = M / row_n_safe
    matrices_rownorm[name] = Mr
    n_acc = len(df_acc)

    pd.DataFrame(M, index=RX_ORDER, columns=MH_ORDER).to_excel(OUT/f'matrix_raw_{name}.xlsx')
    pd.DataFrame(Mr, index=RX_ORDER, columns=MH_ORDER).to_excel(OUT/f'matrix_rownorm_{name}.xlsx')

    draw_heatmap(M, rx_lab, mh_lab,
        f'Reaction × Mechanism — {name} (acceleration subset, n={n_acc})\nAbsolute paper count (multi-label)',
        OUT/f'heatmap_raw_{name}.png', fmt='d', cmap='YlOrRd')
    draw_heatmap(Mr, rx_lab, mh_lab,
        f'Reaction × Mechanism — {name} (row-normalized)\nWithin each reaction type, fraction invoking each mechanism',
        OUT/f'heatmap_rownorm_{name}.png', fmt='%', cmap='Blues', vmax=1.0,
        suffix=' (row sums >100% because multi-label)')

# Consensus: mean of three row-normalized matrices
M_cons = np.mean([matrices_rownorm[n] for n in datasets], axis=0)
pd.DataFrame(M_cons, index=RX_ORDER, columns=MH_ORDER).to_excel(OUT/'matrix_consensus_rownorm.xlsx')
draw_heatmap(M_cons, rx_lab, mh_lab,
    'Reaction × Mechanism — three-model consensus (mean of row-normalized %)\n'
    'Read as: for a paper of <row reaction type>, what fraction invokes <column mechanism>?',
    OUT/'heatmap_consensus_rownorm.png', fmt='%', cmap='RdPu', vmax=1.0,
    suffix=' (row sums >100% because multi-label)')

# Sum heatmap
M_sum = np.sum([matrices_raw[n] for n in datasets], axis=0)
pd.DataFrame(M_sum, index=RX_ORDER, columns=MH_ORDER).to_excel(OUT/'matrix_sum_three_models.xlsx')
draw_heatmap(M_sum, rx_lab, mh_lab,
    f'Reaction × Mechanism — three-model count sum (G+D+Q, total accel papers={sum(len(d) for d in datasets.values())})',
    OUT/'heatmap_sum_three_models.png', fmt='d', cmap='YlOrRd')

# README
md = ['# 反应类型 × 加速机制 共现矩阵 (heatmap)','']
md.append('每篇 acceleration=Yes 文献同时打"反应类型"+"机制"多标签，统计共现频次。')
md.append('')
md.append('## 数据')
md.append('| 模型 | acceleration=Yes 篇数 |')
md.append('|---|---:|')
for name, df_ in datasets.items():
    md.append(f'| {name} | {len(df_)} |')
md.append('')
md.append('## 文件')
md.append('### 单模型')
for name in datasets:
    md.append(f'- {name}: `heatmap_raw_{name}.png`, `heatmap_rownorm_{name}.png` + 对应 xlsx')
md.append('### 三模型共识')
md.append('- `heatmap_consensus_rownorm.png` — 三模型行归一化均值（"对于某反应类型，多大比例文献援引某机制"）')
md.append('- `heatmap_sum_three_models.png` — 三模型计数累加（同一篇文献会被三模型分别计数）')
md.append('')
md.append('## 读图建议')
md.append('- **横看一行**：某类反应的机理叙事是否集中')
md.append('- **纵看一列**：某机制是"万金油"还是只用于特定反应')
md.append('- **空白格**：未被探索的反应×机制组合，是研究空白点')
(OUT/'README.md').write_text('\n'.join(md), encoding='utf-8')

print(f'\n=== Done. Outputs: {OUT} ===')
for p in sorted(OUT.iterdir()):
    print(f'  {p.name}')
