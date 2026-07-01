"""Three-analysis pipeline v2 — bilingual keywords + acceleration filter.
Filter: keep rows where whether_acceleration_discussed == 'Yes'.
Then categorize multi-label with broadened EN/中文 patterns.
Save unclassified subset for user inspection.
"""
import re, sys, io, json
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = Path(r'E:/中国海洋大学工作/2026/课题/微液滴有关课题/微液滴AI多智能体工作')
D = ROOT/'04_数据'

# ============== Bilingual categories ==============
REACTION_CATS = {
    'Organic transformations': [
        # English
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
        r'mannich', r'urea synthesis', r'amidation', r'methylation',
        r'epoxide', r'ring[\s\-]?open',
        # Chinese
        r'合成', r'有机', r'缩合', r'偶联', r'环加成', r'环化', r'开环',
        r'酯化', r'酰胺化', r'胺化', r'醛醇', r'迈克尔', r'迈克加成',
        r'脱羧', r'水解(?!氨)', r'异构化', r'重排', r'吲哚',
        r'点击反应', r'硫醇', r'迪尔斯', r'C[\-—]N', r'C[\-—]C', r'C[\-—]O',
        r'胺基化', r'酯', r'酰胺', r'肽键', r'选择性烷基化',
    ],
    'Redox chemistry': [
        # English
        r'\bredox\b', r'\boxidation\b', r'\breduction\b',
        r'h2o2', r'hydrogen peroxide', r'\bperoxide\b',
        r'electron transfer', r'\bo2\b.*reduction', r'h2 generation', r'h2 evolution',
        r'singlet oxygen', r'\boh\b.*radical', r'reactive oxygen',
        r'spontaneous oxidation', r'spontaneous reduction',
        r'electrochemical', r'photocatal', r'photoox', r'photored',
        # Chinese
        r'氧化(?!物质)', r'还原(?!性)', r'氧化还原', r'过氧化氢', r'电子转移',
        r'自发氧化', r'自发还原', r'电化学', r'光催化', r'析氢', r'析氧',
        r'活性氧', r'单线态氧',
    ],
    'Atmospheric / environmental': [
        # English
        r'atmospher', r'\baerosol', r'cloud droplet', r'sea[\s\-]?spray',
        r'pollutant', r'\bsoa\b', r'secondary organic aerosol',
        r'environmental', r'\bsulfate\b', r'\bnitrate\b', r'\bn2o5\b',
        r'\bozone\b', r'\bozonation\b', r'photoox.*aerosol',
        r'corrosion', r'sulfur dioxide', r'so2 oxid',
        r'particulate matter', r'pm2\.5', r'\bvoc\b',
        # Chinese
        r'大气', r'气溶胶', r'云滴', r'海喷', r'污染', r'颗粒物', r'雾霾',
        r'二次有机', r'硫酸盐', r'硝酸盐', r'臭氧', r'腐蚀', r'颗粒物去除',
    ],
    'Biochemical / prebiotic': [
        # English
        r'peptide', r'protein', r'amino acid', r'enzyme', r'enzymatic',
        r'biochem', r'prebiotic', r'origin of life', r'\brna\b', r'\bdna\b',
        r'nucleoside', r'nucleotide', r'coacervate', r'protocell',
        r'antibody', r'\bide[s]\b protease', r'tcep', r'disulfide reduction',
        r'glycosylat', r'deglycosylat', r'proteol', r'digestion',
        # Chinese
        r'肽', r'蛋白', r'氨基酸', r'酶', r'生化', r'前生命', r'生命起源',
        r'核酸', r'核糖', r'寡聚', r'蛋白质酶解', r'测序', r'抗体',
        r'二硫键', r'糖基化', r'去糖基化',
    ],
    'Polymerization / oligomerization': [
        r'polymeriz', r'oligomeriz', r'chain extension',
        r'polymer formation', r'oligomer', r'co[\s\-]?polymeriz',
        r'\bmof\b colloid', r'metal[\s\-]?organic framework',
        r'cross[\s\-]?link',
        # Chinese
        r'聚合', r'寡聚物', r'寡聚化', r'交联', r'链增长',
    ],
    'Inorganic / nanomaterial synthesis': [
        # English (new category — many papers do this)
        r'nanoparticle', r'nanowire', r'nanocluster', r'quantum dot',
        r'\bqd[s]?\b\b synthes', r'metal nanoparticle', r'\bag\b.*nanopar',
        r'\bau\b.*nanopar', r'gold nanopar', r'silver nanopar',
        r'\bmof\b synthes', r'crystallization', r'crystallizat',
        # Chinese
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
        # Chinese
        r'气[\s\-]?液界面', r'气液界面', r'界面反应', r'空气[\s\-]?水界面', r'界面反应性',
    ],
    'Interfacial electric field': [
        r'electric field', r'interfacial field', r'field[\s\-]?driven',
        r'strong field', r'charge separation', r'contact electrification',
        r'electric double layer', r'edl\b', r'high field', r'strong electric',
        # Chinese
        r'电场', r'强电场', r'界面电场', r'电荷分离', r'接触起电', r'双电层',
    ],
    'Local pH / extreme acidity': [
        r'surface ph', r'local ph', r'interfacial ph', r'extreme ph',
        r'enhanced acidit', r'interfacial acid', r'hydronium enrich',
        r'hydroxide enrich', r'oh\- enrich', r'low ph at', r'acidic interface',
        # Chinese
        r'表面pH', r'界面pH', r'局部pH', r'极端pH', r'界面酸度', r'局域酸性',
        r'pH富集',
    ],
    'Partial solvation / desolvation': [
        r'partial solvation', r'desolvation', r'incomplete solvation',
        r'reduced solvation', r'altered solvation', r'dehydrat', r'partial hydration',
        # Chinese
        r'部分溶剂化', r'脱溶剂', r'不完全溶剂化', r'脱水', r'降低的溶剂化',
    ],
    'Enrichment & orientation': [
        r'enrichment', r'preferential adsorpt', r'surface accumulat',
        r'orientation', r'aligned at interface', r'molecular alignment',
        r'interface partition', r'reactant concentration at',
        # Chinese
        r'富集', r'吸附', r'界面富集', r'取向', r'排布', r'有序排列',
    ],
    'Radical pathways': [
        r'\bradical', r'hydroxyl radical', r'hydrated electron',
        r'reactive oxygen species', r'\bros\b', r'singlet oxygen',
        r'thiyl radical', r'carbon radical', r'free radical',
        r'\b\xc2\xb7oh\b', r'\boh\xe2\x80\xa2\b',
        # Chinese
        r'自由基', r'羟基自由基', r'水合电子', r'活性氧', r'单线态氧',
    ],
    'Evaporation-induced concentration': [
        r'evaporation', r'evaporative', r'concentration increase',
        r'solute enrichment.*evap', r'concentrating effect', r'evaporative concentration',
        # Chinese
        r'蒸发', r'蒸发浓缩', r'蒸发诱导', r'浓缩效应',
    ],
    'Mass transfer / mixing / collision': [
        r'mass transfer', r'\bmixing\b', r'diffusion[\s\-]length',
        r'droplet collision', r'high surface[\s\-]to[\s\-]volume',
        r'short diffusion', r'rapid transport', r'surface[\s\-]to[\s\-]volume',
        # Chinese
        r'传质', r'混合', r'扩散', r'液滴碰撞', r'高比表面积', r'快速传质',
    ],
    'Confinement / nanoscale geometry': [
        # new category
        r'confinement', r'confined', r'nanoscale geometr', r'curvature',
        r'nano[\s\-]?confined', r'small size effect',
        # Chinese
        r'限域', r'纳米限域', r'曲率', r'小尺寸效应',
    ],
}
MECH_FIELDS = ['proposed_mechanism','interface_related_factors',
               'acceleration_related_description','important_findings',
               'key_information_summary']

THEORY_METHODS = {
    'DFT (static)': [r'\bdft\b', r'density functional', r'b3lyp', r'm06', r'wb97', r'b3pw91', r'\bpbe\b', r'\bmp2\b',
                     r'密度泛函', r'静态DFT'],
    'AIMD (ab initio MD)': [r'ab[\s\-]?initio molecular dynamics', r'\baimd\b', r'born[\s\-]?oppenheimer md', r'\bbomd\b',
                            r'第一性原理分子动力学', r'从头算分子动力学'],
    'Classical / force-field MD': [r'molecular dynamics', r'\bmd simulation', r'classical md', r'force field',
                                   r'\bgromacs\b', r'\blammps\b', r'\bnamd\b', r'\bamber\b',
                                   r'经典分子动力学', r'力场', r'分子动力学'],
    'Semi-empirical / xTB': [r'\bxtb\b', r'gfn\d?', r'semi[\s\-]?empirical', r'\bpm[367]\b', r'\bam1\b', r'\bdftb\b',
                             r'半经验'],
    'Enhanced sampling (metadynamics etc.)': [r'metadynamic', r'umbrella sampling', r'enhanced sampling',
                                              r'free energy.*sampling', r'\bwham\b', r'thermodynamic integration',
                                              r'元动力学', r'伞形采样', r'增强采样'],
    'Kinetic / rate model / TST': [r'kinetic model', r'rate equation', r'transition state theory', r'\btst\b',
                                   r'master equation', r'微观动力学', r'过渡态理论', r'速率方程'],
    'CFD / fluid dynamics': [r'\bcfd\b', r'computational fluid', r'navier[\s\-]?stokes', r'计算流体'],
    'Machine learning / NN': [r'machine learning', r'\bml potential', r'neural network potential', r'\bnnp\b',
                              r'graph neural', r'机器学习', r'神经网络'],
    'Other quantum chemistry (CCSD, CASSCF, etc.)': [r'\bccsd', r'casscf', r'caspt2', r'mrci\b', r'coupled cluster',
                                                     r'多参考方法'],
}

# ============== Normalizers ==============
def norm_yn(v):
    if pd.isna(v): return 'Unknown'
    s = str(v).strip().lower()
    if s in ('yes','true','1','y','是'): return 'Yes'
    if s in ('no','false','0','n','否'): return 'No'
    if s in ('uncertain','unknown','none','nan',''): return 'Unknown'
    return s

def norm_relevance(v):
    if pd.isna(v): return None
    s = str(v).strip().lower()
    if s in ('high','medium','low'): return s.capitalize()
    if s in ('not_relevant','irrelevant','unrelated','none','indirect','0'): return 'Low'
    try:
        n = int(float(s))
        return {0:'Low',1:'Low',2:'Medium',3:'Medium',4:'High',5:'High'}.get(n)
    except Exception:
        return None

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

# ============== Analyzer ==============
def analyze(model_name: str, df_in: pd.DataFrame, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    # Normalize and FILTER to acceleration-related papers
    df = df_in.copy()
    df['_accel_yn'] = df['whether_acceleration_discussed'].apply(norm_yn)
    df['_theory_yn'] = df['whether_theory_computation_involved'].apply(norm_yn)

    df_acc = df[df['_accel_yn'] == 'Yes'].copy()
    n_total = len(df)
    n_acc = len(df_acc)
    print(f'{model_name}: total={n_total}, acceleration=Yes -> {n_acc} papers analyzed')

    # 1. Reaction types (on acceleration subset)
    recs, others = [], []
    for _, row in df_acc.iterrows():
        hay = make_haystack(row, REACTION_FIELDS)
        hits = match_categories(hay, REACTION_CATS)
        if not hits:
            others.append({'title': row['title'],
                           'research_topic': row.get('research_topic'),
                           'reaction_or_process': row.get('reaction_or_process'),
                           'key_information_summary': row.get('key_information_summary')})
            hits = {'Other / unclassified'}
        for cat in hits:
            recs.append({'title': row['title'], 'category': cat,
                         'reaction_or_process': row.get('reaction_or_process'),
                         'research_topic': row.get('research_topic')})
    rx_long = pd.DataFrame(recs)
    rx_counts = rx_long['category'].value_counts().reindex(
        list(REACTION_CATS.keys()) + ['Other / unclassified'], fill_value=0)
    rx_long.to_excel(out_dir/'1_reaction_types_long.xlsx', index=False)
    rx_counts.to_frame('count').to_excel(out_dir/'1_reaction_types_counts.xlsx')
    pd.DataFrame(others).to_excel(out_dir/'1_reaction_types_UNCLASSIFIED.xlsx', index=False)

    fig, ax = plt.subplots(figsize=(8.5, 5))
    color_pal = ['#4F81BD','#C0504D','#9BBB59','#8064A2','#F79646','#13B5B1','#9E9E9E']
    ax.barh(rx_counts.index[::-1], rx_counts.values[::-1], color=color_pal[:len(rx_counts)][::-1])
    for i, v in enumerate(rx_counts.values[::-1]):
        ax.text(v+max(rx_counts.values)*0.01, i, str(v), va='center', fontsize=9)
    ax.set_xlabel(f'Number of papers (out of {n_acc} acceleration-Yes; multi-label)')
    ax.set_title(f'Reaction types — {model_name} (acceleration subset, n={n_acc})')
    plt.tight_layout(); plt.savefig(out_dir/'1_reaction_types.png', dpi=150); plt.close()

    # 2. Mechanisms (on acceleration subset)
    recs, others = [], []
    for _, row in df_acc.iterrows():
        hay = make_haystack(row, MECH_FIELDS)
        hits = match_categories(hay, MECH_CATS)
        if not hits:
            others.append({'title': row['title'],
                           'proposed_mechanism': row.get('proposed_mechanism'),
                           'interface_related_factors': row.get('interface_related_factors'),
                           'acceleration_related_description': row.get('acceleration_related_description')})
            hits = {'No mechanism mentioned / unclassified'}
        for m in hits:
            recs.append({'title': row['title'], 'mechanism': m,
                         'proposed_mechanism': row.get('proposed_mechanism'),
                         'interface_related_factors': row.get('interface_related_factors')})
    mh_long = pd.DataFrame(recs)
    mh_counts = mh_long['mechanism'].value_counts().reindex(
        list(MECH_CATS.keys()) + ['No mechanism mentioned / unclassified'], fill_value=0)
    mh_long.to_excel(out_dir/'2_mechanisms_long.xlsx', index=False)
    mh_counts.to_frame('count').to_excel(out_dir/'2_mechanisms_counts.xlsx')
    pd.DataFrame(others).to_excel(out_dir/'2_mechanisms_UNCLASSIFIED.xlsx', index=False)

    fig, ax = plt.subplots(figsize=(9.5, 6))
    colors2 = ['#1F77B4','#FF7F0E','#2CA02C','#D62728','#9467BD','#8C564B','#E377C2','#7F7F7F','#BCBD22','#17BECF']
    ax.barh(mh_counts.index[::-1], mh_counts.values[::-1], color=colors2[:len(mh_counts)][::-1])
    for i, v in enumerate(mh_counts.values[::-1]):
        ax.text(v+max(mh_counts.values)*0.01, i, str(v), va='center', fontsize=9)
    ax.set_xlabel(f'Number of papers (out of {n_acc} acceleration-Yes; multi-label)')
    ax.set_title(f'Acceleration mechanisms — {model_name} (n={n_acc})')
    plt.tight_layout(); plt.savefig(out_dir/'2_mechanisms.png', dpi=150); plt.close()

    # 3. Theory studies (on acceleration subset)
    theory_counts = df_acc['_theory_yn'].value_counts()
    n_theory_yes = int(theory_counts.get('Yes', 0))
    theory_df = df_acc[df_acc['_theory_yn']=='Yes']

    recs = []
    for _, row in theory_df.iterrows():
        hay = ((str(row.get('theory_methods','') or '') + ' ' +
                str(row.get('proposed_mechanism','') or '') + ' ' +
                str(row.get('important_findings','') or '') + ' ' +
                str(row.get('key_information_summary','') or ''))).lower()
        hits = set()
        for m, pats in THEORY_METHODS.items():
            for pat in pats:
                if re.search(pat, hay, re.I):
                    hits.add(m); break
        if not hits: hits = {'Other / unspecified method'}
        for m in hits:
            recs.append({'title': row['title'], 'method_category': m,
                         'theory_methods_field': row.get('theory_methods')})
    meth_long = pd.DataFrame(recs)
    meth_counts = meth_long['method_category'].value_counts().reindex(
        list(THEORY_METHODS.keys()) + ['Other / unspecified method'], fill_value=0) if len(meth_long) else pd.Series(dtype=int)
    if len(meth_long): meth_long.to_excel(out_dir/'3_theory_methods_long.xlsx', index=False)
    meth_counts.to_frame('count').to_excel(out_dir/'3_theory_methods_counts.xlsx')

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5), gridspec_kw={'width_ratios':[1, 2]})
    pie_labels = list(theory_counts.index)
    pie_values = list(theory_counts.values)
    color_map = {'Yes':'#2CA02C','No':'#D62728','Unknown':'#7F7F7F'}
    pie_colors = [color_map.get(l, '#BBBBBB') for l in pie_labels]
    ax1.pie(pie_values, labels=[f'{l}\n({v}, {v/sum(pie_values):.0%})' for l,v in zip(pie_labels, pie_values)],
            colors=pie_colors, startangle=90)
    ax1.set_title(f'Theory involved? — {model_name} (acceleration subset, n={n_acc})')
    if len(meth_counts):
        ax2.barh(meth_counts.index[::-1], meth_counts.values[::-1], color='#4F81BD')
        for i, v in enumerate(meth_counts.values[::-1]):
            ax2.text(v+max(meth_counts.values)*0.01, i, str(v), va='center', fontsize=9)
        ax2.set_xlabel(f'Papers (among {n_theory_yes} with theory; multi-label)')
        ax2.set_title(f'Theoretical methods — {model_name}')
    plt.tight_layout(); plt.savefig(out_dir/'3_theory_methods.png', dpi=150); plt.close()

    # Markdown
    md = [f'# 微液滴加速文献统计分析 — {model_name}', '']
    md.append(f'**总记录数 (clean)**：{n_total}')
    md.append(f'**讨论加速 (whether_acceleration_discussed = Yes)**：{n_acc}')
    md.append('\n后续分析仅在这 {} 篇加速相关文献上进行。\n'.format(n_acc))
    md.append('## 1. 反应类型分布（多标签）')
    md.append('| 类别 | 文献数 | 占加速子集 |')
    md.append('|---|---:|---:|')
    for c, v in rx_counts.items():
        md.append(f'| {c} | {v} | {v/max(n_acc,1):.1%} |')
    md.append('\n未分类细目见 `1_reaction_types_UNCLASSIFIED.xlsx`。')
    md.append('\n![](1_reaction_types.png)\n')
    md.append('## 2. 加速机制分布（多标签）')
    md.append('| 类别 | 文献数 | 占加速子集 |')
    md.append('|---|---:|---:|')
    for c, v in mh_counts.items():
        md.append(f'| {c} | {v} | {v/max(n_acc,1):.1%} |')
    md.append('\n未分类细目见 `2_mechanisms_UNCLASSIFIED.xlsx`。')
    md.append('\n![](2_mechanisms.png)\n')
    md.append('## 3. 理论研究分布')
    md.append(f'- 涉及理论计算 (Yes)：**{n_theory_yes}** ({n_theory_yes/max(n_acc,1):.1%})')
    md.append(f'- 未涉及 (No)：{int(theory_counts.get("No",0))}')
    md.append(f'- Unknown：{int(theory_counts.get("Unknown",0))}')
    md.append(f'\n### 理论方法分布（在 {n_theory_yes} 篇含理论计算的文献中，多标签）')
    md.append('| 方法 | 文献数 | 占理论子集 |')
    md.append('|---|---:|---:|')
    for c, v in meth_counts.items():
        md.append(f'| {c} | {v} | {v/max(n_theory_yes,1):.1%} |')
    md.append('\n![](3_theory_methods.png)')
    (out_dir/f'统计分析_报告_{model_name}.md').write_text('\n'.join(md), encoding='utf-8')

    return {
        'model': model_name, 'n_total': n_total, 'n_acc': n_acc,
        'reaction_counts': rx_counts.to_dict(),
        'mechanism_counts': mh_counts.to_dict(),
        'theory_yes': n_theory_yes,
        'theory_no': int(theory_counts.get('No',0)),
        'theory_unknown': int(theory_counts.get('Unknown',0)),
        'method_counts': meth_counts.to_dict(),
    }

# ============== Load and run ==============
# Gemini: use the curated 'final-use' file (859 rows, sheet='merged_results')
gem_clean = pd.read_excel(D/'Gemini/merged_results_for_final_use.xlsx', sheet_name='merged_results')
print(f'Gemini final-use: {len(gem_clean)} rows (from sheet merged_results)')

ds = pd.read_excel(D/'Deepseek/microdroplet_analysis_output/merged_results_clean.xlsx')
qw = pd.read_excel(D/'Qwen/microdroplet_analysis_output/merged_results_clean.xlsx')

summaries = []
for name, df_, out in [
    ('Gemini',   gem_clean, D/'Gemini/统计分析'),
    ('Deepseek', ds,        D/'Deepseek/统计分析'),
    ('Qwen',     qw,        D/'Qwen/统计分析'),
]:
    s = analyze(name, df_, out)
    summaries.append(s)

# Cross-model comparison
cmp_dir = D/'三模型对齐/统计对比'
cmp_dir.mkdir(parents=True, exist_ok=True)

rx_cats_all = list(REACTION_CATS.keys()) + ['Other / unclassified']
rx_df = pd.DataFrame({
    s['model']+f' (n_acc={s["n_acc"]})': [s['reaction_counts'].get(c,0) for c in rx_cats_all]
    for s in summaries
}, index=rx_cats_all)
rx_df.to_excel(cmp_dir/'反应类型对比.xlsx')

mh_cats_all = list(MECH_CATS.keys()) + ['No mechanism mentioned / unclassified']
mh_df = pd.DataFrame({
    s['model']+f' (n_acc={s["n_acc"]})': [s['mechanism_counts'].get(c,0) for c in mh_cats_all]
    for s in summaries
}, index=mh_cats_all)
mh_df.to_excel(cmp_dir/'机制对比.xlsx')

th_cats_all = list(THEORY_METHODS.keys()) + ['Other / unspecified method']
th_df = pd.DataFrame({
    s['model']+f' (theory={s["theory_yes"]})': [s['method_counts'].get(c,0) for c in th_cats_all]
    for s in summaries
}, index=th_cats_all)
th_df.to_excel(cmp_dir/'理论方法对比.xlsx')

theory_overview = pd.DataFrame({
    'Total clean':            [s['n_total'] for s in summaries],
    'Acceleration=Yes':       [s['n_acc'] for s in summaries],
    'Theory=Yes':             [s['theory_yes'] for s in summaries],
    'Theory / Acceleration':  [f'{s["theory_yes"]/max(s["n_acc"],1):.1%}' for s in summaries],
}, index=[s['model'] for s in summaries])
theory_overview.to_excel(cmp_dir/'理论参与率对比.xlsx')

def grouped_bar(df_, title, fname):
    fig, ax = plt.subplots(figsize=(12, 6))
    cats = df_.index.tolist()
    x = range(len(cats))
    w = 0.28
    for i, col in enumerate(df_.columns):
        ax.bar([xi + (i-1)*w for xi in x], df_[col].values, w, label=col)
    ax.set_xticks(list(x))
    ax.set_xticklabels(cats, rotation=30, ha='right', fontsize=9)
    ax.set_ylabel('Number of papers (multi-label)')
    ax.set_title(title)
    ax.legend(fontsize=8)
    plt.tight_layout(); plt.savefig(cmp_dir/fname, dpi=150); plt.close()

grouped_bar(rx_df, 'Reaction types — three-model comparison (acceleration subset only)', 'cmp_reaction_types.png')
grouped_bar(mh_df, 'Acceleration mechanisms — three-model comparison', 'cmp_mechanisms.png')
grouped_bar(th_df, 'Theoretical methods — three-model comparison', 'cmp_theory_methods.png')

md = ['# 三模型统计对比 (在各自的"加速 = Yes"子集上)','']
md.append('## 数据规模与理论参与率')
md.append('| 模型 | clean 行数 | acceleration=Yes | theory=Yes | theory/accel 占比 |')
md.append('|---|---:|---:|---:|---:|')
for s in summaries:
    md.append(f'| {s["model"]} | {s["n_total"]} | {s["n_acc"]} | {s["theory_yes"]} | {s["theory_yes"]/max(s["n_acc"],1):.1%} |')
md.append('\n## 反应类型对比')
md.append('![](cmp_reaction_types.png)\n详见 `反应类型对比.xlsx`\n')
md.append('## 加速机制对比')
md.append('![](cmp_mechanisms.png)\n详见 `机制对比.xlsx`\n')
md.append('## 理论方法对比')
md.append('![](cmp_theory_methods.png)\n详见 `理论方法对比.xlsx`\n')
(cmp_dir/'三模型对比_报告.md').write_text('\n'.join(md), encoding='utf-8')

print('\n=== Done ===')
for s in summaries:
    print(f'{s["model"]:8s} n_total={s["n_total"]:4d} acc={s["n_acc"]:4d} theory={s["theory_yes"]:4d}')
print(f'\nOutputs per model: 04_数据/<Model>/统计分析/')
print(f'Cross-model:       04_数据/三模型对齐/统计对比/')
