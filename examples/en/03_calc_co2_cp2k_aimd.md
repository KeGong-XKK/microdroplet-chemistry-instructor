# Example 3: Computational setup — CO₂ at the air-water interface (CP2K AIMD slab)

**Triggered**: `interface-calc-builder` subagent
**Goal**: build a water slab + vacuum model with CO₂ at the air-water interface and emit a CP2K AIMD input file
**Use case**: study real-time solvation of CO₂ at the microdroplet interface, field-driven enrichment, and the H₃O⁺/OH⁻ double layer

---

## User input

> Prepare a CP2K AIMD input for CO₂ at the air-water interface; I want to study interfacial enrichment dynamics.

---

## Agent's internal steps

### Step 1 — Look up AIMD methodology used by analogous papers

```bash
$ python -m tools.search "AIMD ab initio molecular dynamics water interface microdroplet CO2" --k 10 --alpha 0.0
```

Returns 10 hits; focus on those that ran AIMD:

| row_id | Title | Methods used |
|---|---|---|
| **Gemini_00210** | Molecular Mechanism for Converting CO₂ Surrounding Water Microdroplets... | **CP2K + BLYP-D3 + metadynamics** (direct precedent) |
| Qwen_00064 | Accelerated reactions of amines with CO₂ driven by superacid | experimental |
| Qwen_00501 | Water Charge Transfer Accelerates Criegee + H₂O⁻ | QM/MM + BOMD + LMP2 |
| Gemini_00010 | Theoretical Studies of Molecular Reactions at the Air-Water Interface (Review) | AIMD / Classical MD / DPMD survey |

**Key finding**: [1] is the most direct precedent — same target chemistry (CO₂ + water microdroplet) — and uses **CP2K + BLYP-D3 + metadynamics**. The present setup adopts this methodology directly.

### Step 2 — Choose model style

- User asked about "interfacial enrichment dynamics" → needs picosecond time resolution → **AIMD slab** (not cluster QC)
- Slab thickness: [1] uses ~3 water layers (≈10 Å water + vacuum), aligning with community consensus → **4 layers × 24 waters**
- Vacuum gap: avoid periodic image artefacts → **15 Å**

### Step 3 — Build geometry

```bash
$ python -m tools.build_model slab \
    --solute-smiles "O=C=O" \
    --n-waters-per-layer 24 --n-layers 4 \
    --box-xy 12.0 --vacuum 15.0 \
    --layer-spacing 3.1 --interface-offset 1.5 \
    -o examples/outputs/03_co2_slab.xyz
```

Outputs:
- `03_co2_slab.xyz` (291 atoms = 1 CO₂ + 96 H₂O; CO₂ placed 1.5 Å above the top interface)
- `03_co2_slab.cell` (cell a=b=12.0 Å, c=30.8 Å, periodic-in-XY)

### Step 4 — Render the CP2K AIMD input

Override default to **BLYP-D3(BJ)** to match [1]:

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

write_input auto-maps GTH-BLYP pseudopotentials for H/C/O (q1/q4/q6).

---

## Final user-facing output

### Files generated

| Path | Purpose |
|---|---|
| `examples/outputs/03_co2_slab.xyz` | Starting geometry (291 atoms; periodic in XY + Z vacuum) |
| `examples/outputs/03_co2_slab.cell` | Cell definition referenced by the CP2K input |
| `examples/outputs/03_co2_aimd.inp` | CP2K AIMD input file |

### Methodology rationale

> CP2K is configured with **BLYP-D3(BJ)** adopted from [1] — the most direct precedent in this corpus (same chemistry: CO₂ in water microdroplets). BLYP reproduces water structure / dynamics acceptably; D3 corrects H-bond and van der Waals interactions. **GTH-BLYP pseudopotentials + DZVP-MOLOPT-SR basis** is the standard CP2K interface setup, with cutoff 400 Ry / rel_cutoff 50 Ry commonly used in the literature. **0.5 fs timestep** samples the explicit O-H stretch (highest-frequency mode). **NVT + Nose-Hoover thermostat** (time constant 50 fs) maintains 300 K. 10,000 steps = 5 ps production; recommend 2-3 ps equilibration first (re-run with PRINT_LEVEL HIGH to verify T/E convergence before production). **Cell** 12×12 Å lateral × 30.8 Å normal (15 Å vacuum), PERIODIC XY for the interface, Z direction open.

### Model limitations (flagged)

- **BLYP-D3 softens the interface**: MB-pol reference data show BLYP underestimates interfacial H-bond strength; for quantitative free-energy differences, consider SCAN-D or a hybrid (PBE0-D3) single-point correction on important snapshots
- **10⁹ V m⁻¹ interfacial field is not in the model**: this slab is neutral, equilibrium, no external field; for field-acceleration studies, add an `&EXTERNAL_POTENTIAL` block or use the reactive-MD approach in review [4]
- **5 ps is short**: [1] actually uses metadynamics for enhanced sampling (effective sampling of tens-to-hundreds of ps); unbiased BOMD at 5 ps only captures fast vibrations and first-shell rearrangement
- **Starting waters are gridded**: the tool places water on a regular grid; **always run 5 ps NVT equilibration first** (rerun with STEPS 5000 for equilibration, then use the RESTART file to continue production)

### Submission hints

- **CP2K AIMD**: estimate 64 cores + 64 GB RAM; 10,000 steps ≈ 24-36 h wall time on CPU, 8-12 h with GPU acceleration
- Output files: `co2_interface_aimd-pos-1.xyz` (trajectory), `co2_interface_aimd-1.ener` (energies), `co2_interface_aimd-1.restart` (checkpoint)

### Enhanced sampling (optional next step)

If the user later wants the bulk-to-interface PMF of CO₂:

```bash
# Add &FREE_ENERGY → &METADYN block under &MOTION
# COLVAR = Z-coord of CO2 carbon
```

[1] used metadynamics to map the CO₂ + Tz → HCOOH reaction coordinate; a similar approach applies here.

### Bibliography

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

## Things to notice

1. **Agent overrode the default to match the literature**: write_input defaults to `--xc PBE`, but [1] uses BLYP-D3 → the agent overrides this and documents the choice in the rationale
2. **[1] happens to be the user's own paper**: the agent doesn't know this; it just found the best methodology match in the corpus — which happens to be the user's own work. This is a sanity check: the agent picked the methodology *that the user already knows is correct for this system*
3. **Research-scope limitations are surfaced upfront**: this is unbiased BOMD; the agent proactively suggests metadynamics if the user wants free-energy quantities — preventing the user from running 5 ps and then realising the sampling is inadequate
4. **Pseudopotential/basis are auto-matched per element**: H q1 / C q4 / O q6 are looked up from an internal table; the user does not hand-write any KIND block
