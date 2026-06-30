# Installation & Usage Guide / 安装与使用指南

[English](#english) · [中文](#中文)

---

## English

### 1. Prerequisites

- **Python 3.10+** (CI tests 3.10 / 3.11 / 3.12)
- **[Claude Code](https://claude.com/claude-code)** installed and authenticated
- **Git** to clone the repository

### 2. Install

```bash
git clone https://github.com/KeGong-XKK/microdroplet-chemistry-instructor.git
cd microdroplet-chemistry-instructor
pip install -r requirements.txt
```

That's it — the unified corpus (`data/unified_corpus.parquet`, ~6 MB) is
bundled in the repo, so no extra data step is required.

### 3. Verify (optional, < 15 seconds)

```bash
bash tests/smoke_test.sh
```

Expect: `passed: 11` / `failed: 0` and a trailing `OK`.

### 4. Use it

Launch Claude Code in the repo directory:

```bash
cd microdroplet-chemistry-instructor
claude
```

Then ask in natural language — **no slash commands required**:

```
> I want to do CO₂ reduction in water microdroplets
> Build me a Gaussian opt+freq input for H₂O₂ in a water cluster
> Prepare a CP2K AIMD slab for CO₂ at the air-water interface
> Have any papers studied aniline oxidation in charged microdroplets?
```

Claude Code reads `CLAUDE.md` automatically and routes each query to the
appropriate skill or subagent. The routing rules are visible in
`CLAUDE.md` if you ever want to inspect or modify them.

### 5. (Optional) Semantic-search upgrade

The default install uses keyword retrieval, which lands 8/12 top-score hits
on standard chemistry queries. If you want semantic similarity for
paraphrased or cross-lingual queries:

```bash
pip install -r requirements-semantic.txt      # +4 GB (torch + sentence-transformers + faiss)
python scripts/build_index.py                  # downloads BGE-M3 (~2.3 GB), 5-15 min
```

After this, `tools/search.py` can be invoked with `--alpha 0.7` for a
semantic + keyword blend.

### 6. Explicit invocation (advanced)

While Claude Code auto-routes from natural language, you can also force a
specific skill or subagent:

```
> /design-experiment "ozone uptake by water microdroplets"
```

```
> Use the interface-calc-builder agent to prepare an ORCA DLPNO-CCSD(T)
  input for the H₂O₂ + 12 water cluster.
```

Use `/agents` to list available subagents.

### 7. Where things live

- `.claude/skills/design-experiment.md` — experimental scheme generator (literature-first)
- `.claude/agents/interface-calc-builder.md` — QC/AIMD input file generator (literature-first)
- `tools/*.py` — 6 underlying Python tools (search, filter, combine, cite, build_model, write_input)
- `examples/zh/` and `examples/en/` — three worked end-to-end demos
- `CLAUDE.md` — project-level routing rules read by Claude Code on startup

---

## 中文

### 1. 前提

- **Python 3.10+**（CI 测试 3.10 / 3.11 / 3.12）
- 已安装并登录 **[Claude Code](https://claude.com/claude-code)**
- **Git**

### 2. 安装

```bash
git clone https://github.com/KeGong-XKK/microdroplet-chemistry-instructor.git
cd microdroplet-chemistry-instructor
pip install -r requirements.txt
```

就这么简单。语料库 `data/unified_corpus.parquet`（~6 MB）已打包进仓库，
不需要额外下载数据。

### 3. 验证（可选，< 15 秒）

```bash
bash tests/smoke_test.sh
```

期望输出：`passed: 11` / `failed: 0`，结尾打印 `OK`。

### 4. 使用

在仓库根目录启动 Claude Code：

```bash
cd microdroplet-chemistry-instructor
claude
```

然后**用自然语言提问**——**不需要写斜杠命令**：

```
> 我想在微液滴里做 CO₂ 还原
> 帮我准备 H₂O₂ 在水簇里的 Gaussian opt+freq 输入文件
> 给我做一个 CO₂ 在水气液界面的 CP2K AIMD slab 输入
> 文献里有没有人做过苯胺在带电液滴中的氧化？
```

Claude Code 启动时会自动读 `CLAUDE.md`，按里面的路由规则把每个问题
分到合适的 skill 或子代理。规则在 `CLAUDE.md` 里写明，可以随时查阅或修改。

### 5. （可选）语义检索升级

默认的关键词检索模式在标准化学查询上能命中 8/12 高分前例。
如果你想要语义相似度匹配（处理同义改写或跨语言查询）：

```bash
pip install -r requirements-semantic.txt      # +4 GB (torch + sentence-transformers + faiss)
python scripts/build_index.py                  # 下载 BGE-M3 (~2.3 GB), 5-15 分钟
```

之后 `tools/search.py` 可用 `--alpha 0.7` 调用语义+关键词混合模式。

### 6. 显式调用（进阶）

Claude Code 默认自然语言路由就够用，但你也可以强制指定某个 skill 或子代理：

```
> /design-experiment "ozone uptake by water microdroplets"
```

```
> 用 interface-calc-builder 子代理给我准备 H₂O₂ + 12 H₂O 簇的 ORCA DLPNO-CCSD(T) 单点输入
```

用 `/agents` 命令列出所有可用子代理。

### 7. 文件位置速查

- `.claude/skills/design-experiment.md` — 实验方案生成 skill（文献优先）
- `.claude/agents/interface-calc-builder.md` — 量化/AIMD 输入生成子代理（文献优先）
- `tools/*.py` — 6 个底层 Python 工具（search, filter, combine, cite, build_model, write_input）
- `examples/zh/` 和 `examples/en/` — 三个端到端示例（中英文各一份）
- `CLAUDE.md` — Claude Code 启动时自动加载的项目路由规则

---

## Troubleshooting / 常见问题

### "ModuleNotFoundError: No module named 'pandas'"

You didn't run `pip install -r requirements.txt`. Or you're in a different
virtual environment than where you installed. Activate the right venv and try again.

没装依赖，或者在错的 venv 里。激活正确的虚拟环境后重试。

### "data/unified_corpus.parquet not found"

The repo wasn't fully cloned, or the file was accidentally deleted.
Re-clone or `git checkout -- data/unified_corpus.parquet`.

仓库没克隆完整，或文件被误删。重新克隆，或 `git checkout -- data/unified_corpus.parquet`。

### Search returns no hits even though the topic should exist

The default search is keyword-based and is sensitive to exact term matching.
Try rephrasing the query, broadening the reaction-class filter, or installing
the semantic-search upgrade (Section 5).

默认是关键词检索，对术语精确度敏感。换种说法、放宽 reaction-class 过滤，
或安装语义升级（第 5 节）。

### Claude Code doesn't seem to invoke the skill / subagent

Verify `CLAUDE.md` exists at the repo root and you launched `claude` from
inside the repo (not from a parent directory). Run `/agents` to confirm
the subagent is discovered. If not, check `.claude/agents/` is present.

确认 `CLAUDE.md` 在仓库根目录、并且你是从仓库内（不是父目录）启动的 `claude`。
跑 `/agents` 命令确认子代理被发现；如果没列出，检查 `.claude/agents/` 是否存在。

---

## License

MIT — see [LICENSE](LICENSE).
