from mapper.pipeline import map_atoms
from mapper.proline import proline_A, proline_A_double_prime, proline_A_prime, proline_pair


def test_proline_forms_same_composition():
    a = proline_A()
    ap = proline_A_prime()
    app = proline_A_double_prime()
    assert a.n_atoms == ap.n_atoms == app.n_atoms == 17
    assert a.formula() == ap.formula() == app.formula()
    assert a.symbols.count("N") == 1
    assert a.symbols.count("O") == 2


def test_proline_a_to_a_prime_mapping():
    reactant, product, true = proline_pair("a_to_a_prime")
    result = map_atoms(reactant, product)
    for i, sym in enumerate(reactant.symbols):
        if sym == "H":
            continue
        assert result.mapping[i] == true[i]
    assert result.metrics.n_bond_changes == 0


def test_proline_a_to_zwitterion_heavy_mapping():
    reactant, product, true = proline_pair("a_to_a_double_prime")
    result = map_atoms(reactant, product)
    for i, sym in enumerate(reactant.symbols):
        if sym == "H":
            continue
        assert result.mapping[i] == true[i]
    assert result.metrics.n_bond_changes >= 2
