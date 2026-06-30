# 示例 1：实验设计 — 微液滴中的 CO₂ 还原（文献优先）

**触发的功能**：`/design-experiment` skill
**关键行为**：先检索文献，发现有直接前例 → **直接返回论文清单**，不生成新方案

---

## 用户输入

> 我想在微液滴里做 CO₂ 还原

---

## Agent 的内部步骤

### Step 1 — 检索文献

```bash
$ python -m tools.search "CO2 reduction water microdroplets" --k 10
```

返回 10 篇命中，其中 8 篇满分（score=1.0）。Agent 读完 title / reaction_or_process /
reactants 字段后判定：**多篇论文直接研究 CO₂ 在微液滴中的还原 → 进入 Branch A**。

---

## Agent 给用户的最终输出（Branch A：有前例）

### 已有相关发表工作

> 本仓库中已有 **8 篇** 直接研究该反应的论文。建议直接阅读以下文献，
> 这些研究覆盖了从自发还原、光催化、到电催化等多种实施路线。

---

### Paper 1: Spontaneously Generated Electrons for CO₂ Hydrogenation to Formate at the Microinterface of Air-Water

- **反应**: CO₂ 加氢生成甲酸盐 / HCOO⁻
- **反应物**: CO₂（气相） + H₂O（自身电子源）
- **微液滴体系**: 水微液滴气液微界面
- **生成方法**: 喷雾
- **溶剂**: 水
- **典型条件**: 室温常压；CO₂ 鼓泡饱和
- **产物**: HCOO⁻ 甲酸根
- **关键发现**: 微液滴自发产生的电子驱动 CO₂ → HCOO⁻，气液微界面是主要反应区
- **来源**: csv_input  ·  row_id: Deepseek_00498

### Paper 2: Significant Acceleration of Photocatalytic CO₂ Reduction at the Gas-Liquid Interface of Microdroplets

- **反应**: 光催化 CO₂ 还原 (CO₂RR)
- **反应物**: CO₂ 或 NaHCO₃ + 亚硫酸盐 (SO₃²⁻) 作水合电子源
- **微液滴体系**: 水微液滴；液滴尺寸越小活性越强
- **生成方法**: 在疏水基底上喷雾
- **溶剂**: 水（或乙腈/水混合）
- **典型条件**: 光照 0.77–1.79 mW/cm²；相对湿度 ~90%；Ar 或 CO₂ 气氛
- **产物**: HCOOH + CH₃OH（相对体相提升 4-7 数量级）
- **关键发现**: 界面 10⁹ V/m 强电场延长水合电子寿命；液滴 < 10 μm 选择性最高
- **来源**: 2023_Qiuyue Ge_Significant Acceleration of Photocatalytic CO2 Reduction at the Gas-Liquid Interface of Microdroplets.pdf  ·  row_id: Qwen_00131

### Paper 3: Catalyst-Free Transformation of Carbon Dioxide to Small Organic Compounds in Water Microdroplets

- **反应**: CO₂ → 甲酸 / 乙酸 / 乙二醇 等小分子有机产物
- **反应物**: CO₂ + H₂O
- **微液滴体系**: 水微液滴，多种喷雾方式
- **生成方法**: 雾化（多种）
- **典型条件**: 无催化剂；常温常压
- **产物**: HCOOH、CH₃COOH、乙二醇
- **关键发现**: 不需要任何外加催化剂；纯水液滴体系即可还原 CO₂
- **来源**: Advanced Science 2024 Mehrgardi.pdf  ·  row_id: Gemini_00167

### Paper 4: Spraying Water Microdroplets Containing 1,2,3-Triazole Converts CO₂ to Formic Acid

- **反应**: CO₂ → HCOOH（甲酸）
- **反应物**: CO₂ + 1,2,3-三唑（Tz）作质子/电子穿梭剂
- **微液滴体系**: 水微液滴
- **生成方法**: 喷雾
- **溶剂**: 水（含 Tz）
- **产物**: HCOOH
- **关键发现**: 加入 1,2,3-三唑作传递媒介后产率显著提升；分子机理见 Gemini_00210（同作者后续工作）
- **来源**: 2022_Xiaowei Song_Spraying Water Microdroplets Containing 1,2,3-Triazole Converts Carbon Dioxide into Formic Acid.pdf  ·  row_id: Gemini_00106

---

### 完整文献清单

```
[1] Spontaneously Generated Electrons for CO2 Hydrogenation to Formate at the Microinterface of Air-Water — Deepseek_00498
[2] Significant Acceleration of Photocatalytic CO2 Reduction at the Gas-Liquid Interface of Microdroplets — Qwen_00131
[3] Catalyst-Free Transformation of Carbon Dioxide to Small Organic Compounds in Water Microdroplets — Gemini_00167
[4] Spraying Water Microdroplets Containing 1,2,3-Triazole Converts Carbon Dioxide into Formic Acid — Gemini_00106
```

（另外 4 篇满分命中：Gemini_00497 α-C-H carboxylation of ketones；Qwen_00500 transition metal ion reduction；
Qwen_00108 simultaneous oxidation/reduction；Deepseek_00509 spontaneous reduction by one electron。
若想看全部，告诉我）

---

### 建议下一步

> 直接阅读 [1, 2, 3, 4] 的原文获取完整实验细节（喷雾参数、定量数据、MS 探针 m/z 选择等）。
>
> 如果你想要：
> - 在已有方案上做**变体**（换溶剂、换液滴生成方式、改用阴离子助剂等）
> - 想看**机理研究**（不只是合成路线）
> - 想比较**两种实施路线的优劣**
>
> 告诉我具体方向，我可以基于这些前例做扩展。

---

## 关键观察

注意这次 agent 的行为与早期版本不同：

1. **不再给"推荐方案表格"**——文献里已经有，用户应该读原论文
2. **每篇 paper 卡片直接呈现该论文的实验细节**（反应物 / 液滴 / 溶剂 / 条件 / 产物），用户一目了然
3. **row_id + source 都给出**——用户可以拿着 source 名称去本地 PDF 库找原文
4. **降到 4 篇细卡片，其余仅列名**——避免单屏溢出，但允许用户追问更多
5. **结尾留扩展接口**——如果用户想做变体，agent 才会基于这些前例做设计（进入"设计 by analogy"模式）

这种"文献优先"行为更贴合科研工作流：研究者真正需要的不是 AI 生成的方案，而是知道**别人已经做了什么、做到了什么**。
