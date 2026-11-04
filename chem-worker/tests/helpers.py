from __future__ import annotations

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem

from mapper.bonds import assign_bonds
from mapper.molecule import Molecule


def mol_from_smiles(smiles: str, seed: int = 0xC0FFEE) -> Molecule:
    m = Chem.MolFromSmiles(smiles)
    if m is None:
        raise ValueError(smiles)
    m = Chem.AddHs(m)
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    if AllChem.EmbedMolecule(m, params) != 0:
        raise RuntimeError("embed failed")
    AllChem.MMFFOptimizeMolecule(m)
    conf = m.GetConformer()
    symbols = [a.GetSymbol() for a in m.GetAtoms()]
    coords = np.array(
        [
            [conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y, conf.GetAtomPosition(i).z]
            for i in range(m.GetNumAtoms())
        ],
        dtype=float,
    )
    mol = Molecule(symbols=symbols, coords=coords)
    return assign_bonds(mol)


def random_rotation(rng: np.random.Generator) -> np.ndarray:
    v = rng.normal(size=3)
    v = v / np.linalg.norm(v)
    x, y, z = v
    K = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]], dtype=float)
    theta = float(rng.uniform(0, 2 * np.pi))
    return np.eye(3) + np.sin(theta) * K + (1 - np.cos(theta)) * (K @ K)


def scramble(mol: Molecule, rng: np.random.Generator | None = None) -> tuple[Molecule, list[int]]:
    rng = rng or np.random.default_rng(0)
    n = mol.n_atoms
    perm = rng.permutation(n)
    R = random_rotation(rng)
    t = rng.normal(scale=2.0, size=3)
    coords = (mol.coords[perm] @ R.T) + t
    symbols = [mol.symbols[i] for i in perm]
    out = Molecule(symbols=symbols, coords=coords, charge=mol.charge, multiplicity=mol.multiplicity)
    out = assign_bonds(out)
    true_mapping = [int(np.where(perm == i)[0][0]) for i in range(n)]
    return out, true_mapping


def cyclohexanone_conformers() -> tuple[Molecule, Molecule, Molecule]:
    chair = mol_from_smiles("O=C1CCCCC1", seed=1)
    rotated, _ = scramble(chair, np.random.default_rng(7))
    boat = mol_from_smiles("O=C1CCCCC1", seed=99)
    return chair, rotated, boat
