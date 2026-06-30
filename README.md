# Microdroplet Chemistry Instructor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

A literature-first AI helper for microdroplet chemistry, designed to run
inside [Claude Code](https://claude.com/claude-code).

Two simple tracks:

- **`/design-experiment` skill** — given a target reaction in microdroplets,
  first checks whether a published precedent exists. **If yes**, returns the
  paper details (reactants, droplet system, solvent, conditions, products,
  source PDF) so you can read the originals. **If no**, proposes one
  experimental scheme by analogy from the closest related work.

- **`interface-calc-builder` subagent** — given a reaction at the air-water
  interface, first checks whether someone has already computed the system.
  **If yes**, points you to the methodology paper and offers to build an
  equivalent input file. **If no**, builds a QC (Gaussian / ORCA) cluster or
  AIMD (CP2K) slab input following the closest analog calculation.

Both share one evidence base: **2,433 records (~896 unique papers)** extracted
independently by three LLMs (Gemini, Deepseek, Qwen). When the same paper
appears in all three extractions, that itself is a calibration signal.

---

## Installation

```bash
git clone https://github.com/KeGong-XKK/microdroplet-chemistry-instructor.git
cd microdroplet-chemistry-instructor

# Core install — works out of the box (~100 MB)
pip install -r requirements.txt

# Optional: semantic-search upgrade (+ 4 GB torch & friends, + 2.3 GB BGE-M3)
pip install -r requirements-semantic.txt
python scripts/build_index.py
```

> The unified literature corpus (`data/unified_corpus.parquet`, ~6 MB) is
> bundled in the repo — no extra data-fetching step is required. The agent
> runs fine with **just the core install**: keyword retrieval lands 8/12
> top-score hits on direct chemistry queries like "CO2 reduction water
> microdroplets". The semantic upgrade adds ~10-15% recall on paraphrased
> or cross-lingual queries; it is not required.

---

## Usage in Claude Code

```bash
cd microdroplet-chemistry-instructor
claude
```

Then ask naturally, in Chinese or English:

```
> 我想在微液滴里做 CO₂ 还原                              # → literature-first design
> Build a Gaussian cluster model for H₂O₂ in water    # → calc agent
> 准备一个 CO₂ 水气液界面的 CP2K AIMD 输入文件          # → calc agent
> 文献里有没有人做过苯胺在带电液滴中的氧化？             # → direct search
```

See [`examples/`](examples/) for three worked end-to-end demos in Chinese
and English with real outputs.

---

## Repository layout

```
microdroplet-chemistry-instructor/
├── CLAUDE.md                              # project-level routing
├── README.md, LICENSE, .gitignore
├── requirements.txt                       # core (~100 MB)
├── requirements-semantic.txt              # optional semantic upgrade
├── .claude/
│   ├── skills/
│   │   └── design-experiment.md           # literature-first experimental skill
│   ├── agents/
│   │   └── interface-calc-builder.md      # literature-first calc-input agent
│   └── settings.json
├── data/
│   ├── unified_corpus.parquet              # bundled with repo (~6 MB)
│   └── embeddings.npy / faiss.index        # gitignored; built by scripts/build_index.py
├── tools/
│   ├── search.py        # hybrid semantic + keyword retrieval
│   ├── filter.py        # taxonomy classification + filters
│   ├── combine.py       # parameter pattern aggregation
│   ├── cite.py          # numbered / inline citations
│   ├── build_model.py   # cluster + interface-slab geometry builder
│   └── write_input.py   # Gaussian / ORCA / CP2K input writer
├── scripts/
│   ├── merge_datasets.py
│   └── build_index.py
└── examples/
    ├── README.md
    ├── zh/  01_design_experiment_co2.md, 02_calc_h2o2_gaussian.md, 03_calc_co2_cp2k_aimd.md
    ├── en/  (same three, English)
    └── outputs/  (generated .xyz, .gjf, .inp files)
```

---

## Design philosophy

**Literature first; design only as fallback.** Researchers do not really
want an AI-fabricated scheme — they want to know *what has already been
done and what was found*. The agent's first action on any query is to
check the corpus and report what was published. Only when no precedent
exists does it propose a new design (experimental track) or build an
input file (computational track) by analogy.

The agent does NOT predict microdroplet acceleration mechanisms. Mechanism
in this literature remains contested; treating "the most commonly claimed
mechanism" as a prediction would launder unvalidated narratives. Mechanism
appears only as literature attribution ("[1] proposes interfacial electric
field"), never as the agent's verdict.

---

## License

MIT — see [LICENSE](LICENSE).

## Citation

A methods paper is in preparation. Until then:

```bibtex
@misc{gong2026instructor,
  author = {Gong, Ke},
  title  = {Microdroplet Chemistry Instructor: a literature-first agent for
            experimental design and interface-calculation setup},
  year   = {2026},
  url    = {https://github.com/KeGong-XKK/microdroplet-chemistry-instructor}
}
```

## Acknowledgements

The structural design of the `interface-calc-builder` subagent is inspired
by the SKILL.md format and the *literature-first → method-template → input-file*
workflow established in:

> Ding, M.; Huang, C.; Hu, Y. et al. *Automating Computational Chemistry Workflows
> via OpenClaw and Domain-Specific Skills*. **J. Chem. Theory Comput.** 2026.
> DOI: [10.1021/acs.jctc.6c00622](https://doi.org/10.1021/acs.jctc.6c00622).
> Repository: [jinzhezenggroup/computational-chemistry-agent-skills](https://github.com/jinzhezenggroup/computational-chemistry-agent-skills).

K.G. acknowledges support from the China Postdoctoral Science Foundation
(Grant 2025M781029).
