"""Geometry builder for QC and AIMD interface models.

Two model styles:

  cluster  — solute embedded in or near an N-water cluster, no periodicity.
             Use for finite QC (Gaussian, ORCA): static optimisation,
             frequency, single-point energy on small to medium models.

  slab     — water slab with a vacuum gap above, solute placed near the
             air-water interface. Use for AIMD with CP2K / VASP / Q-Chem.
             Periodic in x-y, finite in z.

Outputs an .xyz file (standard XMol format) that the input-file writers
in tools/write_input.py can consume.

The geometry routine is intentionally simple: water molecules are placed
on a body-centred grid with random orientations, then any waters within
1.4 Å of the solute are removed. The result is acceptable as a starting
point for QC optimisation or AIMD equilibration — it is NOT pre-equilibrated.
For production-quality cluster sampling, pass --shake to add random
perturbations and emit multiple replicas.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


# ---------- atomic geometry primitives ----------

# Water geometry (rigid, ~SPC/E): r(O-H)=0.9572 Å, ∠HOH=104.52°.
_WATER_TEMPLATE = np.array([
    [ 0.000000,  0.000000,  0.000000],   # O
    [ 0.757000,  0.000000,  0.586000],   # H1
    [-0.757000,  0.000000,  0.586000],   # H2
])
_WATER_ATOMS = ['O', 'H', 'H']


def _random_rotation_matrix(rng: np.random.Generator) -> np.ndarray:
    """Uniform rotation in SO(3) via QR of a Gaussian matrix."""
    M = rng.normal(size=(3, 3))
    Q, R = np.linalg.qr(M)
    Q *= np.sign(np.diag(R))
    if np.linalg.det(Q) < 0:
        Q[:, 0] *= -1
    return Q


def _place_water(center: np.ndarray, rng: np.random.Generator) -> tuple[list[str], np.ndarray]:
    R = _random_rotation_matrix(rng)
    coords = (_WATER_TEMPLATE @ R.T) + center
    return list(_WATER_ATOMS), coords


# ---------- solute placement ----------

def _parse_xyz_block(text: str) -> tuple[list[str], np.ndarray]:
    """Accept either a full .xyz file or a coordinate-only block.

    Returns (atom_symbols, coords[N,3]) with coords in Å.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    # Standard XYZ: line 0 = N, line 1 = comment, lines 2+ = atom rows
    try:
        n = int(lines[0].strip())
        rows = lines[2 : 2 + n]
    except (ValueError, IndexError):
        rows = lines
    atoms: list[str] = []
    coords = []
    for ln in rows:
        parts = re.split(r'\s+', ln.strip())
        if len(parts) < 4:
            continue
        atoms.append(parts[0])
        coords.append([float(parts[1]), float(parts[2]), float(parts[3])])
    return atoms, np.array(coords, dtype=float)


def _solute_from_smiles(smiles: str) -> tuple[list[str], np.ndarray]:
    """SMILES → 3D coords via RDKit ETKDG."""
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except ImportError as e:
        raise SystemExit('[abort] RDKit not installed. Install with `pip install rdkit`, '
                         'or pass a pre-built --solute-xyz file instead.') from e
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise SystemExit(f'[abort] Invalid SMILES: {smiles}')
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, randomSeed=42) != 0:
        raise SystemExit('[abort] RDKit failed to embed 3D geometry. Provide --solute-xyz manually.')
    AllChem.MMFFOptimizeMolecule(mol, maxIters=500)
    conf = mol.GetConformer()
    atoms = [a.GetSymbol() for a in mol.GetAtoms()]
    coords = np.array([[conf.GetAtomPosition(i).x,
                        conf.GetAtomPosition(i).y,
                        conf.GetAtomPosition(i).z]
                       for i in range(mol.GetNumAtoms())])
    coords -= coords.mean(axis=0)
    return atoms, coords


# ---------- cluster model ----------

def build_cluster(
    solute_atoms: list[str], solute_xyz: np.ndarray,
    n_waters: int = 20,
    spacing: float = 3.1,
    cutoff: float = 1.4,
    seed: int = 0,
) -> tuple[list[str], np.ndarray]:
    """Solute centred at origin; waters placed on a BCC grid around it.

    Waters too close to solute (any-atom distance < cutoff) are dropped;
    additional grid points are added until n_waters is reached or the
    grid is exhausted.
    """
    rng = np.random.default_rng(seed)

    # Build a candidate grid large enough to host n_waters * 2 oxygens
    side = int(math.ceil(((n_waters * 2) ** (1 / 3)) / 2)) + 1
    grid = []
    for i in range(-side, side + 1):
        for j in range(-side, side + 1):
            for k in range(-side, side + 1):
                # BCC: corner + body-centre sites
                grid.append(np.array([i, j, k]) * spacing)
                grid.append((np.array([i, j, k]) + np.array([0.5, 0.5, 0.5])) * spacing)
    # Sort grid by distance to origin (solute centre) so closest sites first
    grid.sort(key=lambda v: float(np.linalg.norm(v)))

    atoms = list(solute_atoms)
    coords = list(solute_xyz)
    placed = 0
    for site in grid:
        if placed >= n_waters:
            break
        # Skip sites that collide with solute or already-placed waters
        too_close = False
        for c in coords:
            if np.linalg.norm(site - c) < cutoff + 1.2:
                too_close = True
                break
        if too_close:
            continue
        w_atoms, w_coords = _place_water(site, rng)
        atoms.extend(w_atoms)
        coords.extend(w_coords)
        placed += 1

    if placed < n_waters:
        print(f'[warn] only placed {placed}/{n_waters} waters; '
              f'enlarge --spacing or reduce --n-waters', file=sys.stderr)
    return atoms, np.array(coords)


# ---------- interface slab model ----------

def build_interface_slab(
    solute_atoms: list[str], solute_xyz: np.ndarray,
    n_waters_per_layer: int = 24,
    n_layers: int = 4,
    layer_spacing: float = 3.1,
    box_xy: float = 12.0,
    vacuum: float = 15.0,
    interface_offset: float = 1.5,
    seed: int = 0,
) -> tuple[list[str], np.ndarray, dict]:
    """Periodic-in-xy water slab + vacuum above; solute placed at top interface.

    Returns (atoms, coords, cell_dict). cell_dict gives a/b/c lengths that
    the input-file writer can use to declare the simulation cell.
    """
    rng = np.random.default_rng(seed)

    # Place waters on an in-plane grid, repeat through n_layers
    nx = ny = int(math.ceil(math.sqrt(n_waters_per_layer)))
    dx = box_xy / nx
    dy = box_xy / ny

    atoms: list[str] = []
    coords: list[np.ndarray] = []

    for layer in range(n_layers):
        z = layer * layer_spacing
        count = 0
        for ix in range(nx):
            for iy in range(ny):
                if count >= n_waters_per_layer:
                    break
                # Stagger alternate layers
                shift_x = 0.5 * dx if layer % 2 else 0.0
                shift_y = 0.5 * dy if layer % 2 else 0.0
                center = np.array([
                    (ix + 0.5) * dx + shift_x - box_xy / 2,
                    (iy + 0.5) * dy + shift_y - box_xy / 2,
                    z,
                ])
                w_atoms, w_coords = _place_water(center, rng)
                atoms.extend(w_atoms)
                coords.append(w_coords)
                count += 1

    # Solute centred above the top water layer
    top_z = (n_layers - 1) * layer_spacing
    solute_centred = solute_xyz - solute_xyz.mean(axis=0)
    solute_placed = solute_centred + np.array([0.0, 0.0, top_z + interface_offset])
    atoms = list(solute_atoms) + atoms
    coords = [solute_placed] + coords

    all_coords = np.concatenate(coords, axis=0)

    cell = {
        'a': box_xy,
        'b': box_xy,
        'c': (n_layers - 1) * layer_spacing + vacuum + interface_offset + 5.0,
        'alpha': 90.0, 'beta': 90.0, 'gamma': 90.0,
    }
    return atoms, all_coords, cell


# ---------- I/O ----------

def write_xyz(path: Path, atoms: list[str], coords: np.ndarray, comment: str = '') -> None:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'{len(atoms)}\n')
        f.write(f'{comment}\n')
        for a, (x, y, z) in zip(atoms, coords):
            f.write(f'{a:2s} {x:14.6f} {y:14.6f} {z:14.6f}\n')


def _cli() -> None:
    ap = argparse.ArgumentParser(description='Build cluster or interface-slab geometries for QC/AIMD.')
    sub = ap.add_subparsers(dest='cmd', required=True)

    common = argparse.ArgumentParser(add_help=False)
    g = common.add_mutually_exclusive_group(required=True)
    g.add_argument('--solute-smiles', help='SMILES for the solute (RDKit will embed)')
    g.add_argument('--solute-xyz',    help='path to an .xyz file with the solute geometry')
    common.add_argument('--output', '-o', required=True, help='output .xyz path')
    common.add_argument('--seed', type=int, default=0)

    p1 = sub.add_parser('cluster', parents=[common], help='solute + water cluster (no periodicity)')
    p1.add_argument('--n-waters', type=int, default=20)
    p1.add_argument('--spacing', type=float, default=3.1)

    p2 = sub.add_parser('slab', parents=[common], help='water slab + solute at top interface')
    p2.add_argument('--n-waters-per-layer', type=int, default=24)
    p2.add_argument('--n-layers', type=int, default=4)
    p2.add_argument('--box-xy', type=float, default=12.0)
    p2.add_argument('--vacuum', type=float, default=15.0)
    p2.add_argument('--layer-spacing', type=float, default=3.1)
    p2.add_argument('--interface-offset', type=float, default=1.5)

    args = ap.parse_args()

    if args.solute_smiles:
        solute_atoms, solute_xyz = _solute_from_smiles(args.solute_smiles)
        src_desc = f'SMILES={args.solute_smiles}'
    else:
        with open(args.solute_xyz, encoding='utf-8') as f:
            solute_atoms, solute_xyz = _parse_xyz_block(f.read())
        src_desc = f'XYZ={args.solute_xyz}'

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.cmd == 'cluster':
        atoms, coords = build_cluster(
            solute_atoms, solute_xyz,
            n_waters=args.n_waters, spacing=args.spacing, seed=args.seed,
        )
        comment = f'cluster: solute({src_desc}) + {args.n_waters} H2O; spacing={args.spacing}'
        write_xyz(out, atoms, coords, comment)
        print(f'[done] {out}  atoms={len(atoms)}')
    elif args.cmd == 'slab':
        atoms, coords, cell = build_interface_slab(
            solute_atoms, solute_xyz,
            n_waters_per_layer=args.n_waters_per_layer,
            n_layers=args.n_layers,
            box_xy=args.box_xy, vacuum=args.vacuum,
            layer_spacing=args.layer_spacing,
            interface_offset=args.interface_offset, seed=args.seed,
        )
        comment = (f'slab: solute({src_desc}) + {args.n_waters_per_layer}*{args.n_layers} H2O; '
                   f'cell a={cell["a"]:.3f} b={cell["b"]:.3f} c={cell["c"]:.3f}')
        write_xyz(out, atoms, coords, comment)
        # Sidecar cell file for the input-file writer
        cell_path = out.with_suffix('.cell')
        with open(cell_path, 'w', encoding='utf-8') as f:
            for k, v in cell.items():
                f.write(f'{k} {v}\n')
        print(f'[done] {out}  atoms={len(atoms)}')
        print(f'[done] {cell_path}  (a/b/c/angles for input-file writer)')


if __name__ == '__main__':
    _cli()
