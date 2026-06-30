"""Render an .xyz geometry into a ready-to-submit input file for a QC code.

Supports three codes that together cover the microdroplet-interface use case:

  gaussian  — finite molecular QC; static opt/freq/single-point. Most common
              in organic chemistry. Hybrid + dispersion functionals.
  orca      — finite molecular QC; same use case, free, increasingly popular.
              Use for high-accuracy thermochemistry (DLPNO-CCSD(T)).
  cp2k      — periodic AIMD on slabs; the only one of the three suited to
              picosecond-scale interface dynamics. Hybrid Gaussian/plane-wave
              with GTH pseudopotentials.

Each writer takes the parsed .xyz, a few high-level options (method, basis,
calc type), and emits a sensible default input file. The agent is expected
to read the file afterwards and tweak project-specific settings (memory,
queue, etc.) before submitting.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def _read_xyz(path: Path) -> tuple[list[str], np.ndarray, str]:
    with open(path, encoding='utf-8') as f:
        lines = f.read().splitlines()
    n = int(lines[0].strip())
    comment = lines[1]
    atoms: list[str] = []
    coords = []
    for ln in lines[2 : 2 + n]:
        parts = ln.split()
        atoms.append(parts[0])
        coords.append([float(parts[1]), float(parts[2]), float(parts[3])])
    return atoms, np.array(coords), comment


def _read_cell(path: Path) -> dict | None:
    if not path.exists():
        return None
    cell: dict = {}
    for ln in path.read_text().splitlines():
        k, _, v = ln.partition(' ')
        if v.strip():
            cell[k.strip()] = float(v.strip())
    return cell


# ---------- Gaussian ----------

def write_gaussian(
    atoms: list[str], coords: np.ndarray, out: Path,
    *, charge: int = 0, mult: int = 1,
    method: str = 'wB97X-D', basis: str = '6-31+G(d,p)',
    calc_type: str = 'opt freq',
    nproc: int = 16, mem_gb: int = 32,
    title: str = 'Microdroplet cluster model',
) -> None:
    """Emit a Gaussian 16 .gjf input."""
    lines: list[str] = []
    lines.append(f'%NProcShared={nproc}')
    lines.append(f'%Mem={mem_gb}GB')
    lines.append(f'%Chk={out.stem}.chk')
    lines.append(f'# {method}/{basis} {calc_type} SCRF=(SMD,Solvent=Water) EmpiricalDispersion=GD3BJ')
    lines.append('')
    lines.append(title)
    lines.append('')
    lines.append(f'{charge} {mult}')
    for a, (x, y, z) in zip(atoms, coords):
        lines.append(f'{a:2s} {x:14.6f} {y:14.6f} {z:14.6f}')
    lines.append('')
    out.write_text('\n'.join(lines), encoding='utf-8')


# ---------- ORCA ----------

def write_orca(
    atoms: list[str], coords: np.ndarray, out: Path,
    *, charge: int = 0, mult: int = 1,
    method: str = 'wB97X-D3BJ', basis: str = 'def2-TZVP',
    calc_type: str = 'Opt Freq',
    nproc: int = 16, mem_mb: int = 4000,
    extras: str = 'CPCM(water) RIJCOSX def2/J',
) -> None:
    """Emit an ORCA 5/6 .inp input."""
    lines: list[str] = []
    lines.append(f'! {method} {basis} {calc_type} {extras}')
    lines.append(f'%PAL NPROCS {nproc} END')
    lines.append(f'%MaxCore {mem_mb}')
    lines.append('')
    lines.append(f'* xyz {charge} {mult}')
    for a, (x, y, z) in zip(atoms, coords):
        lines.append(f'{a:2s} {x:14.6f} {y:14.6f} {z:14.6f}')
    lines.append('*')
    lines.append('')
    out.write_text('\n'.join(lines), encoding='utf-8')


# ---------- CP2K AIMD ----------

_CP2K_TEMPLATE = """\
&GLOBAL
  PROJECT {project}
  RUN_TYPE MD
  PRINT_LEVEL LOW
&END GLOBAL

&MOTION
  &MD
    ENSEMBLE {ensemble}
    STEPS {n_steps}
    TIMESTEP {timestep_fs}
    TEMPERATURE {temperature_K}
    &THERMOSTAT
      TYPE NOSE
      &NOSE
        TIMECON 50.0
      &END
    &END THERMOSTAT
  &END MD
  &PRINT
    &TRAJECTORY ON
      &EACH
        MD 5
      &END
    &END
    &VELOCITIES ON
      &EACH
        MD 50
      &END
    &END
  &END PRINT
&END MOTION

&FORCE_EVAL
  METHOD QS
  &DFT
    BASIS_SET_FILE_NAME BASIS_MOLOPT
    POTENTIAL_FILE_NAME GTH_POTENTIALS
    &MGRID
      CUTOFF 400
      REL_CUTOFF 50
    &END MGRID
    &QS
      EPS_DEFAULT 1.0E-12
    &END QS
    &XC
      &XC_FUNCTIONAL {xc}
      &END XC_FUNCTIONAL
      &VDW_POTENTIAL
        POTENTIAL_TYPE PAIR_POTENTIAL
        &PAIR_POTENTIAL
          TYPE DFTD3(BJ)
          PARAMETER_FILE_NAME dftd3.dat
          REFERENCE_FUNCTIONAL {xc}
        &END PAIR_POTENTIAL
      &END VDW_POTENTIAL
    &END XC
    &SCF
      SCF_GUESS ATOMIC
      EPS_SCF 1.0E-6
      MAX_SCF 50
      &OT
        MINIMIZER DIIS
        PRECONDITIONER FULL_SINGLE_INVERSE
      &END OT
      &OUTER_SCF
        EPS_SCF 1.0E-6
        MAX_SCF 20
      &END OUTER_SCF
    &END SCF
  &END DFT

  &SUBSYS
    &CELL
      ABC {a:.6f} {b:.6f} {c:.6f}
      ALPHA_BETA_GAMMA {alpha:.2f} {beta:.2f} {gamma:.2f}
      PERIODIC XY
    &END CELL
    &TOPOLOGY
      COORD_FILE_NAME {xyz_basename}
      COORD_FILE_FORMAT XYZ
    &END TOPOLOGY
{kinds_block}
  &END SUBSYS
&END FORCE_EVAL
"""

_CP2K_KIND_TEMPLATE = """    &KIND {element}
      BASIS_SET DZVP-MOLOPT-SR-GTH
      POTENTIAL GTH-{xc_short}-q{q}
    &END KIND"""

# Element → effective core charge for GTH pseudopotentials (PBE-fitted set)
_GTH_VALENCE = {
    'H': 1, 'Li': 3, 'C': 4, 'N': 5, 'O': 6, 'F': 7, 'Na': 9, 'Mg': 2,
    'Al': 3, 'Si': 4, 'P': 5, 'S': 6, 'Cl': 7, 'K': 9, 'Ca': 10,
    'Fe': 16, 'Cu': 11, 'Zn': 12, 'Br': 7, 'I': 7,
}


def write_cp2k_aimd(
    atoms: list[str], coords: np.ndarray, out: Path, xyz_path: Path,
    *, cell: dict,
    xc: str = 'PBE', n_steps: int = 5000,
    timestep_fs: float = 0.5, temperature_K: float = 300.0,
    ensemble: str = 'NVT',
    project: str = 'interface_aimd',
) -> None:
    """Emit a CP2K AIMD input plus copy the xyz next to it.

    Geometry is referenced via COORD_FILE_NAME so the .inp stays small.
    """
    elements = sorted(set(atoms))
    xc_short = xc.lower()
    kinds = []
    for e in elements:
        q = _GTH_VALENCE.get(e)
        if q is None:
            raise SystemExit(
                f'[abort] No GTH valence charge tabulated for {e}; '
                'add it to _GTH_VALENCE in write_input.py or replace this kind block manually.')
        kinds.append(_CP2K_KIND_TEMPLATE.format(element=e, xc_short=xc_short.upper(), q=q))
    kinds_block = '\n'.join(kinds)

    content = _CP2K_TEMPLATE.format(
        project=project, ensemble=ensemble,
        n_steps=n_steps, timestep_fs=timestep_fs,
        temperature_K=temperature_K, xc=xc,
        a=cell['a'], b=cell['b'], c=cell['c'],
        alpha=cell.get('alpha', 90.0), beta=cell.get('beta', 90.0),
        gamma=cell.get('gamma', 90.0),
        xyz_basename=xyz_path.name,
        kinds_block=kinds_block,
    )
    out.write_text(content, encoding='utf-8')


# ---------- CLI ----------

def _cli() -> None:
    ap = argparse.ArgumentParser(description='Render an .xyz into a QC input file.')
    ap.add_argument('--xyz', required=True, help='input .xyz path')
    ap.add_argument('--code', required=True, choices=['gaussian', 'orca', 'cp2k'])
    ap.add_argument('--output', '-o', required=True, help='output input-file path')

    # Common QC options
    ap.add_argument('--charge', type=int, default=0)
    ap.add_argument('--mult', type=int, default=1)
    ap.add_argument('--method', default=None, help='functional or method name')
    ap.add_argument('--basis', default=None, help='basis set name (Gaussian/ORCA)')
    ap.add_argument('--calc-type', default=None,
                    help='e.g. "opt freq" for Gaussian, "Opt Freq" for ORCA')
    ap.add_argument('--nproc', type=int, default=16)
    ap.add_argument('--mem-gb', type=int, default=32, help='Gaussian only')
    ap.add_argument('--mem-mb', type=int, default=4000, help='ORCA only')

    # CP2K AIMD options
    ap.add_argument('--cell', default=None,
                    help='sidecar .cell file from build_model.py slab; required for cp2k')
    ap.add_argument('--xc', default='PBE')
    ap.add_argument('--steps', type=int, default=5000)
    ap.add_argument('--timestep-fs', type=float, default=0.5)
    ap.add_argument('--temperature-K', type=float, default=300.0)
    ap.add_argument('--ensemble', default='NVT', choices=['NVT', 'NVE', 'NPT_F'])
    ap.add_argument('--project', default='interface_aimd')

    args = ap.parse_args()
    xyz_path = Path(args.xyz)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    atoms, coords, _ = _read_xyz(xyz_path)

    if args.code == 'gaussian':
        write_gaussian(
            atoms, coords, out,
            charge=args.charge, mult=args.mult,
            method=args.method or 'wB97X-D', basis=args.basis or '6-31+G(d,p)',
            calc_type=args.calc_type or 'opt freq',
            nproc=args.nproc, mem_gb=args.mem_gb,
        )
    elif args.code == 'orca':
        write_orca(
            atoms, coords, out,
            charge=args.charge, mult=args.mult,
            method=args.method or 'wB97X-D3BJ', basis=args.basis or 'def2-TZVP',
            calc_type=args.calc_type or 'Opt Freq',
            nproc=args.nproc, mem_mb=args.mem_mb,
        )
    elif args.code == 'cp2k':
        cell_path = Path(args.cell) if args.cell else xyz_path.with_suffix('.cell')
        cell = _read_cell(cell_path)
        if cell is None:
            raise SystemExit(f'[abort] CP2K needs a sidecar .cell file; tried {cell_path}')
        write_cp2k_aimd(
            atoms, coords, out, xyz_path, cell=cell,
            xc=args.xc, n_steps=args.steps,
            timestep_fs=args.timestep_fs, temperature_K=args.temperature_K,
            ensemble=args.ensemble, project=args.project,
        )

    print(f'[done] wrote {out}')


if __name__ == '__main__':
    _cli()
