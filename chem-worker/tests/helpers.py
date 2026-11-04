from __future__ import annotations

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem

from mapper.bonds import assign_bonds
from mapper.geom import scramble as scramble
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


def cyclohexanone_conformers() -> tuple[Molecule, Molecule, Molecule]:
    chair = mol_from_smiles("O=C1CCCCC1", seed=1)
    rotated, _ = scramble(chair, np.random.default_rng(7))
    boat = mol_from_smiles("O=C1CCCCC1", seed=99)
    return chair, rotated, boat
