---
name: design-experiment
description: Answer "怎么在微液滴里做 X / how to do X in microdroplets" queries. ALWAYS check the literature corpus first. If a published precedent exists, return paper details and tell the user to read them. Only when no precedent exists, propose an experimental scheme by analogy. Trigger on any reaction-design question, in Chinese or English.
---

# /design-experiment

## Core rule

**Literature first, design only as fallback.** The user has asked about a
reaction. Your first job is to find out whether someone has already published
on it. Only when no one has, you propose a design.

---

## Step 1 — Search the corpus

```bash
python -m tools.search "<user query in user's own language>" --k 10
```

Read the top hits. For each, check the `title`, `reaction_or_process`,
`reactants`, and `microdroplet_type` fields. Ask yourself:

> *Does this paper study the same reaction the user asked about, in
> microdroplets?*

A match means: same target transformation (e.g., CO₂ reduction →
HCOOH), same substrate family (or close), in microdroplets (any type).

---

## Step 2 — Branch on what you found

### Branch A: 1+ direct precedent → return papers, don't design

If at least one top hit is a clear match, your job is done. Output:

```
## 已有相关发表工作 / Published precedents found

本仓库中已有 **N 篇** 直接研究该反应的论文。建议直接阅读以下文献：
(The corpus contains N papers that directly study this reaction.
Recommend reading the following first:)

### Paper 1: <title>
- **反应 / Reaction**: <reaction_or_process>
- **反应物 / Reactants**: <reactants>
- **微液滴体系 / Droplet system**: <microdroplet_type>
- **生成方法 / Generation**: <droplet_generation_method>
- **溶剂 / Solvent**: <solvent_or_medium>
- **典型条件 / Conditions**: <experimental_conditions>
- **产物 / Products**: <products>
- **关键发现 / Key findings**: <key_information_summary (trimmed)>
- **来源 / Source**: <source_name>  ·  row_id: <_row_id>

### Paper 2: ... (repeat for each direct precedent, up to ~4)

---

**建议下一步 / Suggested next step**: 直接阅读 [1, 2, ...] 的原文获取
完整实验细节。如果你想要某个方案的进一步对比、或者尝试改变某个参数（溶剂 /
液滴生成方式 / 反应物比例），告诉我，我可以基于这些前例做变体设计。
(Read [1, 2, ...] directly for full experimental details. If you want
comparison or want to vary a parameter, tell me — I can design a variant
based on these precedents.)
```

Then render the numbered bibliography:
```bash
python -m tools.cite <row_id_1> <row_id_2> ... --style numbered
```

**Stop here.** Do not invent a new design when the answer is already in the literature.

---

### Branch B: No direct precedent → propose a design by analogy

If **none** of the top hits clearly matches the user's exact target, broaden
the search to find analogous reactions:

```bash
# Classify the target reaction class
python -m tools.filter classify-query "<user query>" --taxonomy reaction

# Broader search restricted to that class
python -m tools.search "<broader query>" --k 20 --reaction-class "<class>"

# Aggregate parameter patterns
python -m tools.search "<broader query>" --k 20 --reaction-class "<class>" \
    | python -m tools.combine --top-n 5
```

Then output ONE recommended scheme:

```
## 无直接前例，基于类似反应的实验方案
## No direct precedent — proposed scheme by analogy

本仓库中**没有**直接研究该反应的论文。以下方案基于 N 篇类似反应的前例
（同类型反应在微液滴中的实验设置），属于探索性建议，需实验验证。

(The corpus contains NO paper studying this exact reaction. The following
scheme is extrapolated from N analogous reactions in microdroplets and is
exploratory — experimental validation required.)

**反应物 / Reactants**: <suggested reactants> [cite analog row_ids]
**微液滴体系 / Droplet system**: <type> [cite]
**生成方法 / Generation**: <method> [cite]
**溶剂 / Solvent**: <solvent> [cite]
**典型条件 / Conditions**: <T / voltage / flow / distance> [cite]
**期望产物 / Expected products**: <products> [cite]
**关键风险 / Key risks**: <2-3 sentences on what might go wrong>
**类比来源 / Analog basis**: 本方案的核心参数来自 N 篇类似反应（[1, 2, ...]）
```

Render bibliography.

---

## Rules

- **Never skip Step 1.** No matter how confident the chemistry seems, search first.
- **Branch A is the win condition.** When precedents exist, the user wants
  references, not your design. Don't add a "but here's also a proposal" tail
  unless they ask.
- **Cite by `_row_id` in every claim.** No row_id, no claim.
- **Match the user's language.** Mixed Chinese/English query → mixed-language reply is fine.
- **Mechanism stays as literature attribution.** "[1] proposes interfacial
  electric field" — never the agent's own claim about mechanism.
- **Keep replies tight.** Branch A: ≤ 4 paper cards. Branch B: 1 scheme.
