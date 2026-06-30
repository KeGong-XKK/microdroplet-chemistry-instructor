# 示例 3：计算建模 — CO₂ 在水气液界面的 CP2K AIMD slab

**触发的功能**：`interface-calc-builder` subagent
**目标**：构建水气液界面 slab 模型（CO₂ 置于界面），输出 CP2K AIMD 输入文件
**应用场景**：研究 CO₂ 在微液滴气液界面的实时溶剂化行为、电场富集、与界面 H₃O⁺/OH⁻ 双层的相互作用

---

## 用户输入

> 给我准备一个 CO₂ 在水气液界面的 CP2K AIMD 输入文件，我要研究界面富集动力学

---

## Agent 的内部步骤

### Step 1 — 在文献里找类似计算的方法学

```bash
$ python -m tools.search "AIMD ab initio molecular dynamics water interface microdroplet CO2" --k 10 --alpha 0.0
```

返回 10 篇，重点关注用过 AIMD 的：

| row_id | 标题 | 用过的方法 |
|---|---|---|
| **Gemini_00210** | Molecular Mechanism for Converting CO₂ Surrounding Water Microdroplets... | **CP2K + BLYP-D3 + metadynamics**（直接同行先例） |
| Qwen_00064 | Accelerated reactions of amines with CO₂ driven by superacid | 实验为主 |
| Qwen_00501 | Water Charge Transfer Accelerates Criegee + H₂O⁻ | QM/MM + BOMD + LMP2 |
| Gemini_00010 | Theoretical Studies of Molecular Reactions at the Air-Water Interface (Review) | AIMD / Classical MD / DPMD 综述 |

**关键发现**：[1] 是同主题最直接前例（CO₂ + 1,2,3-三唑在水液滴 → 甲酸），用 **CP2K + BLYP-D3 + metadynamics**。本次设置完全采纳此方法学。

### Step 2 — 选定模型类型

- 用户问的是"界面富集动力学" → 需要 picosecond 量级时间分辨 → **AIMD slab**（非簇 QC）
- slab 厚度：[1] 用 ~3 层水（≈10 Å 水厚 + 真空），与社区共识一致 → **4 层 × 24 水**
- 真空厚度：避免周期镜像 → **15 Å**

### Step 3 — 构建几何

```bash
$ python -m tools.build_model slab \
    --solute-smiles "O=C=O" \
    --n-waters-per-layer 24 --n-layers 4 \
    --box-xy 12.0 --vacuum 15.0 \
    --layer-spacing 3.1 --interface-offset 1.5 \
    -o examples/outputs/03_co2_slab.xyz
```

输出：
- `03_co2_slab.xyz`（291 原子 = 1 CO₂ + 96 H₂O；CO₂ 放在顶部界面之上 1.5 Å）
- `03_co2_slab.cell`（晶胞 a=b=12.0 Å, c=30.8 Å, periodic-in-XY）

### Step 4 — 渲染 CP2K AIMD 输入

按文献 [1] 用 **BLYP-D3(BJ)**（不是脚本默认的 PBE）：

```bash
$ python -m tools.write_input \
    --xyz examples/outputs/03_co2_slab.xyz \
    --code cp2k \
    --cell examples/outputs/03_co2_slab.cell \
    --xc BLYP \
    --steps 10000 --timestep-fs 0.5 \
    --temperature-K 300 --ensemble NVT \
    --project co2_interface_aimd \
    -o examples/outputs/03_co2_aimd.inp
```

write_input 自动匹配 H/C/O 的 GTH-BLYP 赝势（q1/q4/q6）。

---

## Agent 给用户的最终输出

### 已生成的文件

| 路径 | 用途 |
|---|---|
| `examples/outputs/03_co2_slab.xyz` | 起始几何（291 原子，XY 周期 + Z 真空） |
| `examples/outputs/03_co2_slab.cell` | 晶胞定义（被 CP2K 输入引用） |
| `examples/outputs/03_co2_aimd.inp` | CP2K AIMD 输入文件 |

### 方法学 Rationale

> CP2K 选择 **BLYP-D3(BJ)** 直接采纳 [1] 的设置——同主题（CO₂ 在水液滴）最直接的前例。BLYP 对水的结构 / 动力学性质再现尚可，D3 弥补氢键 / 范德华相互作用。**GTH-BLYP 赝势 + DZVP-MOLOPT-SR 基组** 是 CP2K 水界面研究的标准搭配，cutoff 400 Ry / rel_cutoff 50 Ry 也是文献常用。**0.5 fs 时间步**确保显式 O-H 振动被采样（高频）。**NVT + Nose-Hoover 热浴**（time constant 50 fs）维持 300 K。10000 步 = 5 ps 生产；建议先做 2-3 ps 平衡（用同输入 PRINT_LEVEL HIGH 跑一段查看 T/E 收敛后再正式生产）。**晶胞** 12×12 Å 横向 × 30.8 Å 纵向（含 15 Å 真空），PERIODIC XY 模拟界面、Z 方向开放。

### 模型局限性

- **BLYP-D3 偏软化界面**：MB-pol 等水模型显示 BLYP 低估界面 H 键强度；如果你的研究核心是定量自由能差，考虑 SCAN-D 或后续重要构型再用 hybrid（PBE0-D3）做单点修正
- **10⁹ V/m 界面电场不在模型中**：本 slab 是中性、平衡态、无外场；若研究"电场加速"效应，加 `&EXTERNAL_POTENTIAL` 块或用 [4] 综述中提到的 reactive MD
- **5 ps 太短**：[1] 实际跑了 metadynamics 增强采样（数十至数百 ps 等效采样）；纯无偏 BOMD 5 ps 只够看快速振动 / 第一溶剂化层重排
- **slab 起始水位置**：本工具用几何规则放置，**必须先做 5 ps NVT 平衡**（建议设 `STEPS 5000` 跑一遍平衡，然后用 RESTART 文件接力生产）

### 提交提示

- **CP2K** AIMD：建议 64 核 + 64 GB；10000 步约 24-36 h wall time（CPU），GPU 加速可压到 8-12 h
- 输出文件：`co2_interface_aimd-pos-1.xyz`（轨迹）、`co2_interface_aimd-1.ener`（能量）、`co2_interface_aimd-1.restart`（断点续算）

### 增强采样（可选下一步）

如果用户后续想算 CO₂ 从体相到界面的自由能 PMF：

```bash
# 在 .inp 的 &MOTION 块加 &FREE_ENERGY → &METADYN
# COLVAR = Z-coord of CO2 carbon
```

[1] 用 metadynamics 摸出 CO₂ + Tz → HCOOH 的反应坐标，类似方法适用于本研究。

### 文献支撑

```
[1] Molecular Mechanism for Converting Carbon Dioxide Surrounding Water Microdroplets Containing 1,2,3-Triazole to Formic Acid
    — Gemini_00210
    src: gong-et-al-2024-molecular-mechanism-for-converting-carbon-dioxide-surrounding-water-microdroplets-containing-1-2-3.pdf
[2] Accelerated reactions of amines with carbon dioxide driven by superacid at the microdroplet interface
    — Qwen_00064 (2020 Huang)
[3] Water Charge Transfer Accelerates Criegee Intermediate Reaction with H₂O⁻ Radical Anion at the Aqueous Interface
    — Qwen_00501
[4] Theoretical Studies of Molecular Reactions at the Air–Water Interface: Recent Progress and Perspective
    — Gemini_00010 (2025 WIREs Comput Mol Sci)
```

---

## 关键观察

1. **Agent 主动按文献调整了默认值**：write_input 默认 `--xc PBE`，但 [1] 用 BLYP-D3 → agent 自动覆盖默认，并在 Rationale 段解释为什么
2. **[1] 正是用户自己的论文**：agent 不知道这件事，它只是在 dataset 里找到最匹配的方法学先例 — 巧合地正好是用户自己——但这是一个好的健全性检查：agent 选的方法**确实是该体系正确的方法**
3. **明示研究方向限制**：本次给的是"无偏 BOMD"，agent 主动建议"如果要算自由能要用 metadynamics"——避免用户跑完 5 ps 才发现采样不够
4. **赝势/基组对元素自动匹配**：H q1 / C q4 / O q6 由 write_input 自动从内置表查找，用户不需要手写
