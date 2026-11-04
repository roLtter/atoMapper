from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import rdDetermineBonds

from mapper.molecule import Molecule

_COVALENT = {
    "H": 0.31,
    "C": 0.76,
    "N": 0.71,
    "O": 0.66,
    "F": 0.57,
    "P": 1.07,
    "S": 1.05,
    "Cl": 1.02,
    "Br": 1.20,
    "I": 1.39,
    "B": 0.84,
    "Si": 1.11,
}


def _radius(sym: str) -> float:
    return _COVALENT.get(sym, 0.8)


def bonds_from_radii(mol: Molecule, tol: float = 0.45) -> set[tuple[int, int]]:
    bonds: set[tuple[int, int]] = set()
    coords = mol.coords
    n = mol.n_atoms
    for i in range(n):
        for j in range(i + 1, n):
            cutoff = _radius(mol.symbols[i]) + _radius(mol.symbols[j]) + tol
            if float(((coords[i] - coords[j]) ** 2).sum()) ** 0.5 <= cutoff:
                bonds.add((i, j))
    return bonds


def bonds_from_rdkit(mol: Molecule) -> set[tuple[int, int]] | None:
    rw = Chem.RWMol()
    for sym in mol.symbols:
        atom = Chem.Atom(sym)
        rw.AddAtom(atom)
    conf = Chem.Conformer(mol.n_atoms)
    for i, (x, y, z) in enumerate(mol.coords):
        conf.SetAtomPosition(i, (float(x), float(y), float(z)))
    m = rw.GetMol()
    m.AddConformer(conf)
    try:
        rdDetermineBonds.DetermineBonds(m, charge=mol.charge)
    except Exception:
        return None
    bonds: set[tuple[int, int]] = set()
    for b in m.GetBonds():
        i, j = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
        bonds.add((i, j) if i < j else (j, i))
    if not bonds and mol.n_atoms > 1:
        return None
    return bonds


def assign_bonds(mol: Molecule, *, force: bool = False) -> Molecule:
    out = mol.copy()
    if out.bonds and not force:
        return out
    bonds = bonds_from_rdkit(out)
    if bonds is None:
        bonds = bonds_from_radii(out)
    out.bonds = bonds
    return out
