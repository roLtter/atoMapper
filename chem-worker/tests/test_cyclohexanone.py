from mapper.pipeline import map_atoms
from tests.helpers import cyclohexanone_conformers


def _oxygen_index(symbols: list[str]) -> int:
    return symbols.index("O")


def _carbonyl_carbon(mol) -> int:
    o = _oxygen_index(mol.symbols)
    for a, b in mol.bonds:
        if a == o and mol.symbols[b] == "C":
            return b
        if b == o and mol.symbols[a] == "C":
            return a
    raise AssertionError("carbonyl carbon not found")


def test_chair_to_rotated_chair():
    chair, rotated, _ = cyclohexanone_conformers()
    result = map_atoms(chair, rotated)
    assert sorted(result.mapping) == list(range(chair.n_atoms))
    assert result.metrics.n_bond_changes == 0
    assert result.metrics.rmsd < 1e-3
    assert result.product_mapped.symbols[_oxygen_index(chair.symbols)] == "O"
    assert result.product_mapped.symbols[_carbonyl_carbon(chair)] == "C"


def test_chair_to_boat_like_conformer():
    chair, _, boat = cyclohexanone_conformers()
    result = map_atoms(chair, boat)
    assert sorted(result.mapping) == list(range(chair.n_atoms))
    assert result.metrics.n_bond_changes == 0
    assert result.product_mapped.symbols == chair.symbols

    o_r = _oxygen_index(chair.symbols)
    c_r = _carbonyl_carbon(chair)
    assert result.mapping[o_r] is not None
    assert boat.symbols[result.mapping[o_r]] == "O"
    assert boat.symbols[result.mapping[c_r]] == "C"

    # mapped product bonds should match reactant topology after reorder
    remapped_bonds = set()
    inv = {p: r for r, p in enumerate(result.mapping)}
    for a, b in boat.bonds:
        ra, rb = inv[a], inv[b]
        remapped_bonds.add((ra, rb) if ra < rb else (rb, ra))
    assert remapped_bonds == chair.bonds
