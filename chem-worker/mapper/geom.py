from __future__ import annotations

import numpy as np

from mapper.bonds import assign_bonds
from mapper.molecule import Molecule


def random_rotation(rng: np.random.Generator) -> np.ndarray:
    v = rng.normal(size=3)
    v = v / np.linalg.norm(v)
    x, y, z = v
    K = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]], dtype=float)
    theta = float(rng.uniform(0, 2 * np.pi))
    return np.eye(3) + np.sin(theta) * K + (1 - np.cos(theta)) * (K @ K)


def scramble(
    mol: Molecule,
    rng: np.random.Generator | None = None,
    *,
    keep_bonds: bool = False,
) -> tuple[Molecule, list[int]]:
    rng = rng or np.random.default_rng(0)
    n = mol.n_atoms
    perm = rng.permutation(n)
    R = random_rotation(rng)
    t = rng.normal(scale=2.0, size=3)
    coords = (mol.coords[perm] @ R.T) + t
    symbols = [mol.symbols[i] for i in perm]
    out = Molecule(symbols=symbols, coords=coords, charge=mol.charge, multiplicity=mol.multiplicity)
    if keep_bonds and mol.bonds:
        inv = {int(old): int(new) for new, old in enumerate(perm)}
        remapped = set()
        for a, b in mol.bonds:
            na, nb = inv[a], inv[b]
            remapped.add((na, nb) if na < nb else (nb, na))
        out.bonds = remapped
    else:
        out = assign_bonds(out)
    true_mapping = [int(np.where(perm == i)[0][0]) for i in range(n)]
    return out, true_mapping
