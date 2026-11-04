import numpy as np

from mapper.pipeline import map_atoms
from tests.helpers import mol_from_smiles, scramble


def _assert_mapping_recovers(true_mapping: list[int], got: list[int], reactant_symbols: list[str]) -> None:
    assert sorted(got) == list(range(len(got)))
    for i, (t, g) in enumerate(zip(true_mapping, got, strict=True)):
        if reactant_symbols[i] != "H":
            assert t == g, f"heavy atom {i} expected {t}, got {g}"


def test_methanol_random_permutation():
    mol = mol_from_smiles("CO", seed=3)
    product, true = scramble(mol, np.random.default_rng(11))
    result = map_atoms(mol, product)
    _assert_mapping_recovers(true, result.mapping, mol.symbols)
    assert result.metrics.rmsd < 1e-4


def test_cyclohexanone_random_permutation():
    mol = mol_from_smiles("O=C1CCCCC1", seed=5)
    product, true = scramble(mol, np.random.default_rng(21))
    result = map_atoms(mol, product)
    _assert_mapping_recovers(true, result.mapping, mol.symbols)
    assert result.metrics.rmsd < 1e-3
    assert result.metrics.n_bond_changes == 0
