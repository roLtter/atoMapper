from __future__ import annotations

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem

from mapper.geom import scramble
from mapper.molecule import Molecule


def _from_rdkit(m: Chem.Mol) -> Molecule:
    conf = m.GetConformer()
    symbols = [a.GetSymbol() for a in m.GetAtoms()]
    coords = np.array(
        [[conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y, conf.GetAtomPosition(i).z] for i in range(m.GetNumAtoms())],
        dtype=float,
    )
    bonds = set()
    for b in m.GetBonds():
        i, j = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
        bonds.add((i, j) if i < j else (j, i))
    return Molecule(symbols=symbols, coords=coords, bonds=bonds)


def proline_A(seed: int = 42) -> Molecule:
    m = Chem.MolFromSmiles("N1CCC[C@H]1C(=O)O")
    m = Chem.AddHs(m)
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    if AllChem.EmbedMolecule(m, params) != 0:
        raise RuntimeError("proline embed failed")
    AllChem.MMFFOptimizeMolecule(m)
    return _from_rdkit(m)


def _acid_h_index(mol: Molecule) -> int:
    for i, sym in enumerate(mol.symbols):
        if sym != "H":
            continue
        for a, b in mol.bonds:
            other = b if a == i else a if b == i else None
            if other is None:
                continue
            if mol.symbols[other] == "O":
                return i
    raise ValueError("carboxylic H not found")


def _n_h_index(mol: Molecule) -> int:
    n_idx = mol.symbols.index("N")
    for a, b in mol.bonds:
        if a == n_idx and mol.symbols[b] == "H":
            return b
        if b == n_idx and mol.symbols[a] == "H":
            return a
    raise ValueError("N-H not found")


def proline_A_prime(seed: int = 42) -> Molecule:
    base = proline_A(seed)
    out = base.copy()
    n = out.symbols.index("N")
    nh = _n_h_index(out)
    carbons = [i for i in range(out.n_atoms) if out.symbols[i] == "C" and ((n, i) in out.bonds or (i, n) in out.bonds)]
    if len(carbons) < 2:
        raise RuntimeError("proline ring carbons missing")
    c1, c2 = carbons[0], carbons[1]
    origin = out.coords[n]
    v1 = out.coords[c1] - origin
    v2 = out.coords[c2] - origin
    normal = np.cross(v1, v2)
    normal = normal / (np.linalg.norm(normal) + 1e-12)
    rel = out.coords[nh] - origin
    out.coords[nh] = origin + rel - 2.0 * np.dot(rel, normal) * normal
    return out


def proline_A_double_prime(seed: int = 42) -> Molecule:
    base = proline_A(seed)
    out = base.copy()
    n = out.symbols.index("N")
    acid_h = _acid_h_index(out)
    oxygen = None
    for a, b in list(out.bonds):
        if a == acid_h and out.symbols[b] == "O":
            oxygen = b
        elif b == acid_h and out.symbols[a] == "O":
            oxygen = a
    if oxygen is None:
        raise RuntimeError("acid oxygen missing")
    out.bonds.discard((acid_h, oxygen) if acid_h < oxygen else (oxygen, acid_h))
    out.bonds.add((n, acid_h) if n < acid_h else (acid_h, n))
    direction = out.coords[n] - out.coords[oxygen]
    direction = direction / (np.linalg.norm(direction) + 1e-12)
    out.coords[acid_h] = out.coords[n] + 1.02 * direction
    out.charge = 0
    return out


def proline_pair(kind: str, rng: np.random.Generator | None = None) -> tuple[Molecule, Molecule, list[int]]:
    a = proline_A()
    if kind == "a_to_a_prime":
        product = proline_A_prime()
    elif kind == "a_to_a_double_prime":
        product = proline_A_double_prime()
    else:
        raise ValueError(kind)
    scrambled, true = scramble(product, rng or np.random.default_rng(404), keep_bonds=True)
    return a, scrambled, true
