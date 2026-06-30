# Example 1: Experimental design — CO₂ reduction in microdroplets (literature-first)

**Triggered**: `/design-experiment` skill
**Key behaviour**: searches literature first, finds direct precedents → **returns the paper list, does not generate a new scheme**

---

## User input

> I want to do CO₂ reduction in microdroplets.

---

## Agent's internal steps

### Step 1 — Search the corpus

```bash
$ python -m tools.search "CO2 reduction water microdroplets" --k 10
```

Returns 10 hits, 8 at top score (1.0). Reading title / reaction_or_process /
reactants of each, the agent decides: **multiple papers directly study CO₂
reduction in microdroplets → go to Branch A.**

---

## Final user-facing output (Branch A — precedents exist)

### Published precedents found

> The corpus contains **8 papers** that directly study this reaction.
> Recommend reading the following first; they cover spontaneous reduction,
> photocatalysis, and electron-mediated routes.

---

### Paper 1: Spontaneously Generated Electrons for CO₂ Hydrogenation to Formate at the Microinterface of Air-Water

- **Reaction**: CO₂ → HCOO⁻ (formate)
- **Reactants**: CO₂ (gas-phase) + H₂O (intrinsic electron source)
- **Droplet system**: water microdroplets at the air-water microinterface
- **Generation**: spraying
- **Solvent**: water
- **Conditions**: room temperature, ambient pressure; CO₂-saturated
- **Products**: formate
- **Key finding**: spontaneously generated electrons drive CO₂ → HCOO⁻; the air-water microinterface is the principal reaction zone
- **Source**: csv_input  ·  row_id: Deepseek_00498

### Paper 2: Significant Acceleration of Photocatalytic CO₂ Reduction at the Gas-Liquid Interface of Microdroplets

- **Reaction**: photocatalytic CO₂ reduction (CO₂RR)
- **Reactants**: CO₂ or NaHCO₃ + sulfite (SO₃²⁻) as hydrated-electron source
- **Droplet system**: water microdroplets; smaller droplets = higher activity
- **Generation**: sprayed onto a hydrophobic substrate
- **Solvent**: water (or water/acetonitrile mixtures)
- **Conditions**: light 0.77–1.79 mW/cm²; ~90% RH; Ar or CO₂ atmosphere
- **Products**: HCOOH + CH₃OH (4–7 orders of magnitude faster than bulk)
- **Key finding**: 10⁹ V/m interfacial field extends hydrated-electron lifetime; droplet size < 10 μm gives highest selectivity
- **Source**: 2023_Qiuyue Ge_Significant Acceleration of Photocatalytic CO2 Reduction at the Gas-Liquid Interface of Microdroplets.pdf  ·  row_id: Qwen_00131

### Paper 3: Catalyst-Free Transformation of Carbon Dioxide to Small Organic Compounds in Water Microdroplets

- **Reaction**: CO₂ → formic acid, acetic acid, ethylene glycol, etc.
- **Reactants**: CO₂ + H₂O
- **Droplet system**: water microdroplets, multiple nebulisation modes
- **Generation**: various atomisation methods
- **Conditions**: catalyst-free; ambient temperature and pressure
- **Products**: HCOOH, CH₃COOH, ethylene glycol
- **Key finding**: no external catalyst required; pure water microdroplets reduce CO₂
- **Source**: Advanced Science 2024 Mehrgardi.pdf  ·  row_id: Gemini_00167

### Paper 4: Spraying Water Microdroplets Containing 1,2,3-Triazole Converts CO₂ to Formic Acid

- **Reaction**: CO₂ → HCOOH (formic acid)
- **Reactants**: CO₂ + 1,2,3-triazole (Tz) as proton/electron shuttle
- **Droplet system**: water microdroplets
- **Generation**: spraying
- **Solvent**: water (containing Tz)
- **Products**: HCOOH
- **Key finding**: adding 1,2,3-triazole as mediator substantially raises yield; molecular mechanism in Gemini_00210 (same group, follow-up paper)
- **Source**: 2022_Xiaowei Song_Spraying Water Microdroplets Containing 1,2,3-Triazole Converts Carbon Dioxide into Formic Acid.pdf  ·  row_id: Gemini_00106

---

### Bibliography

```
[1] Spontaneously Generated Electrons for CO2 Hydrogenation to Formate at the Microinterface of Air-Water — Deepseek_00498
[2] Significant Acceleration of Photocatalytic CO2 Reduction at the Gas-Liquid Interface of Microdroplets — Qwen_00131
[3] Catalyst-Free Transformation of Carbon Dioxide to Small Organic Compounds in Water Microdroplets — Gemini_00167
[4] Spraying Water Microdroplets Containing 1,2,3-Triazole Converts Carbon Dioxide into Formic Acid — Gemini_00106
```

(Four more top-score hits exist: Gemini_00497 (α-C-H carboxylation of ketones); Qwen_00500 (transition-metal-ion reduction);
Qwen_00108 (simultaneous oxidation/reduction); Deepseek_00509 (spontaneous one-electron reduction). Tell me if you want them.)

---

### Suggested next step

> Read [1, 2, 3, 4] directly for full experimental details (spray parameters, quantitative data, MS m/z probes, etc.).
>
> If you want:
> - a **variant** of an existing scheme (different solvent, droplet generation, anion additive)
> - the **mechanism** rather than the synthesis route
> - a **side-by-side comparison** of two implementation routes
>
> Tell me the direction — I can extend from these precedents.

---

## Things to notice

The agent's behaviour differs from earlier versions:

1. **No "recommended scheme" table** — the literature already contains schemes; the user should read the originals
2. **Each paper card directly presents that paper's experimental details** (reactants / droplet / solvent / conditions / products) — the user can scan at a glance
3. **row_id + source both provided** — the user can find the original PDF using the source filename
4. **Capped at 4 detailed cards, rest just listed by name** — avoids screen overflow, but offers follow-up
5. **Open-ended trailing prompt** — only if the user wants a variant does the agent enter "design by analogy" mode

This literature-first behaviour aligns with the actual research workflow: researchers don't really want an AI-generated scheme — they want to know **what has already been done and what was found.**
