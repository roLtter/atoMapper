import pytest

from mapper.fixtures import CASES
from mapper.pipeline import map_atoms


@pytest.mark.parametrize("name", sorted(CASES))
def test_reaction_mapping_recovers_heavy_atoms(name: str):
    reactant, product, true = CASES[name]()
    result = map_atoms(reactant, product, charge=reactant.charge)
    assert sorted(result.mapping) == list(range(reactant.n_atoms))
    for i, sym in enumerate(reactant.symbols):
        if sym == "H":
            continue
        assert result.mapping[i] == true[i], f"{name}: heavy {sym}#{i}"
        assert product.symbols[result.mapping[i]] == sym


def test_proton_transfer_bond_change_pattern():
    reactant, product, _true = CASES["proton_transfer"]()
    result = map_atoms(reactant, product)
    assert result.metrics.n_bond_changes >= 2
    assert any(4 in pair for pair in result.metrics.broken_bonds)
    assert any(0 in pair for pair in result.metrics.formed_bonds)


def test_sn2_swaps_halogen_bonds():
    reactant, product, true = CASES["sn2"]()
    result = map_atoms(reactant, product, charge=-1)
    assert result.mapping[0] == true[0]
    assert result.mapping[4] == true[4]
    assert result.mapping[5] == true[5]
    assert result.metrics.n_bond_changes >= 2


def test_keto_enol_migrating_hydrogen():
    reactant, product, true = CASES["keto_enol"]()
    result = map_atoms(reactant, product)
    assert result.mapping[0] == true[0]
    assert result.mapping[1] == true[1]
    assert result.mapping[2] == true[2]
    assert result.metrics.n_bond_changes >= 2
