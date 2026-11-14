from mapper.candidates import generate_candidates
from mapper.metrics import rank_candidates
from mapper.pipeline import map_atoms
from tests.helpers import cyclohexanone_conformers, oracle_llm


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


def _best_algorithmic(reactant, product):
    ranked = rank_candidates(reactant, product, generate_candidates(reactant, product, top_k=8))
    return ranked[0].mapping


def test_chair_to_rotated_chair():
    chair, rotated, _ = cyclohexanone_conformers()
    true = _best_algorithmic(chair, rotated)
    result = map_atoms(chair, rotated, llm=oracle_llm(true))
    assert sorted(result.mapping) == list(range(chair.n_atoms))
    assert result.metrics.n_bond_changes == 0
    assert result.metrics.rmsd < 1e-3
    assert result.product_mapped.symbols[_oxygen_index(chair.symbols)] == "O"
    assert result.product_mapped.symbols[_carbonyl_carbon(chair)] == "C"


def test_chair_to_boat_like_conformer():
    chair, _, boat = cyclohexanone_conformers()
    true = _best_algorithmic(chair, boat)
    result = map_atoms(chair, boat, llm=oracle_llm(true))
    assert sorted(result.mapping) == list(range(chair.n_atoms))
    assert result.metrics.n_bond_changes == 0
    assert result.product_mapped.symbols == chair.symbols

    o_r = _oxygen_index(chair.symbols)
    c_r = _carbonyl_carbon(chair)
    assert boat.symbols[result.mapping[o_r]] == "O"
    assert boat.symbols[result.mapping[c_r]] == "C"

    remapped_bonds = set()
    inv = {p: r for r, p in enumerate(result.mapping)}
    for a, b in boat.bonds:
        ra, rb = inv[a], inv[b]
        remapped_bonds.add((ra, rb) if ra < rb else (rb, ra))
    assert remapped_bonds == chair.bonds


def test_normalize_is_deterministic():
    from mapper.normalize import normalize_molecule

    chair, _, _ = cyclohexanone_conformers()
    a = normalize_molecule(chair)
    b = normalize_molecule(chair)
    assert (a.coords == b.coords).all()
