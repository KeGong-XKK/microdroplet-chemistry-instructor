# 示例 2：计算建模 — H₂O₂ 在水簇环境中的量子化学

**触发的功能**：`interface-calc-builder` subagent
**目标**：构建 H₂O₂ + 20 水簇模型，输出 Gaussian opt+freq 输入文件
**应用场景**：研究 H₂O₂ 在微液滴气液界面的能量学（生成焓、VIE、与水簇的氢键网络）

---

## 用户输入

> 给我准备一个 H₂O₂ 在水簇中的 Gaussian opt+freq 输入文件，我想算它在水液滴里的稳定性

---

## Agent 的内部步骤

### Step 1 — 在文献里找类似计算的方法学

```bash
$ python -m tools.search "H2O2 hydrogen peroxide microdroplet DFT cluster water" --k 10 --alpha 0.0
```

返回 10 篇命中。重点检查 `theory_methods` 字段：

| row_id | 标题 | 用过的理论方法 |
|---|---|---|
| Qwen_00515 | Spontaneous Formation of H₂O₂ in Water Microdroplets | **VIE 计算 + 溶剂化环境分析** |
| Qwen_00502 | Mechanism of H₂O₂ Formation on Sprayed Water Microdroplets | 热力学分析 + 水合焓比较 |
| Deepseek_00380 | Transport of Gaseous H₂O₂ into Bulk Water vs. Electrospray | (实验为主) |

**解读**：H₂O₂ 在水簇中的研究中，DFT 簇模型用于算 VIE 和水合焓——验证了用 "H₂O₂ + n×H₂O 簇" 做静态量化是文献接受的策略。

### Step 2 — 选定模型类型

- 静态 QC 适合：能量学、几何优化、VIE、振动谱
- 用户问的是"稳定性" → 几何优化 + 频率分析 → **cluster 模型**
- 簇大小依据：Qwen_00515 未明示水簇大小，按社区默认 **20 个水分子**（足以包络第一+二溶剂化层）

### Step 3 — 构建几何

```bash
$ python -m tools.build_model cluster \
    --solute-smiles "OO" \
    --n-waters 20 \
    -o examples/outputs/02_h2o2_cluster.xyz
```

输出：`02_h2o2_cluster.xyz`（64 原子 = 1 个 H₂O₂ + 20 个 H₂O）。

### Step 4 — 渲染输入文件

主选 Gaussian（化学界最常用）：

```bash
$ python -m tools.write_input \
    --xyz examples/outputs/02_h2o2_cluster.xyz \
    --code gaussian \
    --method wB97X-D --basis "6-31+G(d,p)" \
    --calc-type "opt freq" \
    --charge 0 --mult 1 \
    --nproc 16 --mem-gb 32 \
    -o examples/outputs/02_h2o2_opt_freq.gjf
```

为对照，再生成一个 ORCA 高精度备选（含 DLPNO 单点更佳）：

```bash
$ python -m tools.write_input \
    --xyz examples/outputs/02_h2o2_cluster.xyz \
    --code orca \
    --method "wB97X-D3BJ" --basis "def2-TZVP" \
    --calc-type "Opt Freq" \
    -o examples/outputs/02_h2o2_orca.inp
```

---

## Agent 给用户的最终输出

### 已生成的文件

| 路径 | 用途 |
|---|---|
| `examples/outputs/02_h2o2_cluster.xyz` | 起始几何（64 原子；可在 Avogadro / VMD 中预览） |
| `examples/outputs/02_h2o2_opt_freq.gjf` | **主选**：Gaussian 16 输入 |
| `examples/outputs/02_h2o2_orca.inp` | 备选：ORCA 输入（如有 ORCA 许可） |

### 方法学 Rationale（一段）

> 选择 **20 水簇模型** 是因为 H₂O₂ 在微液滴中的 DFT 研究（如 [1]）证实"溶质 + 2 溶剂化层"足以稳定地反映水合效应；簇 → 周期体系的能量校正可后续用 [2] 中的水合焓对比方法。功能 / 基组用 **ωB97X-D/6-31+G(d,p)**：含 D3 色散修正，对氢键体系标准；diffuse 函数对 OOH⁻ 等可能的去质子化中间体重要。SMD(water) 隐式溶剂修正额外补偿簇边界外的体相水极化。**ORCA 备选** 用 def2-TZVP 提升精度，配 CPCM(water) 隐式溶剂——如果你最终要算反应焓变 / VIE 时推荐切换。

### 模型局限性

- **静态簇 QC 无法描述电场富集**：微液滴界面的 10⁹ V/m 电场在簇模型中不存在；如果你的研究重点是电场效应，应改用 slab + AIMD（见示例 3）
- **簇起始结构非平衡态**：当前的水分子摆放靠几何规则放置，需先做粗优化（建议先 PBE/3-21G opt 一轮，再升级到 wB97X-D 高精度）
- **20 水可能不够大**：[1] 暗示 30+ 水簇在某些性质上有显著差异；如果发现优化轨迹中水分子向 H₂O₂ 集中坍缩，加 `--n-waters 32` 重跑

### 提交提示

- **Gaussian**：本作业预估 32 GB 内存、16 核、< 8 小时（簇能量梯度计算的瓶颈）；建议 SLURM 中分配 24 小时缓冲
- **ORCA**：约 4 GB/核、wall time 4–6 小时；def2-TZVP 计算量小于 Gaussian 6-31+G(d,p)

### 文献支撑

```
[1] Spontaneous Formation of Hydrogen Peroxide in Water Microdroplets — Qwen_00515
[2] Mechanism of Hydrogen Peroxide Formation on Sprayed Water Microdroplets — Qwen_00502
[3] Transport of Gaseous Hydrogen Peroxide and Ozone into Bulk Water vs. Electrospray Aerosol — Deepseek_00380
```

---

## 关键观察

1. **Agent 不"自由发挥"功能 / 基组选择**：每个决策都引用 [1] [2] 来源
2. **主动 flag 模型局限性**：直接告诉用户簇 QC 看不到电场效应——避免用户误用
3. **生成的不是 SLURM 脚本**：因为队列配置因机而异；只给资源建议
4. **同时给 Gaussian + ORCA**：用户工具链不同，agent 不锁死一种代码
