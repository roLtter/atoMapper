import numpy as np
import pytest

from mapper.llm import extract_json_object, strip_think
from mapper.pipeline import map_atoms
from mapper.verifier import verify_llm_mapping
from tests.helpers import FakeLLM, mol_from_smiles, oracle_llm, scramble


def test_strip_think_and_json():
    text = (
        '<think>secret</think>{"mapping": [0, 1], "bond_changes": {"broken": [], "formed": []}, '
        '"confidence": 1, "reasoning_steps": ["ok"]}'
    )
    assert "secret" not in strip_think(text)
    data = extract_json_object(text)
    assert data["mapping"] == [0, 1]


def test_verifier_rejects_element_mismatch():
    mol = mol_from_smiles("CO", seed=1)
    product, true = scramble(mol, np.random.default_rng(2))
    bad = list(true)
    c_idx = mol.symbols.index("C")
    o_idx = mol.symbols.index("O")
    bad[c_idx], bad[o_idx] = bad[o_idx], bad[c_idx]
    result = verify_llm_mapping(mol, product, bad)
    assert result.ok is False


def test_pipeline_rejects_bad_mapping():
    mol = mol_from_smiles("CO", seed=4)
    product, _true = scramble(mol, np.random.default_rng(5))
    c_idx = mol.symbols.index("C")
    o_idx = mol.symbols.index("O")
    bad_mapping = list(range(mol.n_atoms))
    bad_mapping[c_idx], bad_mapping[o_idx] = bad_mapping[o_idx], bad_mapping[c_idx]
    fake = FakeLLM(
        {
            "mapping": bad_mapping,
            "bond_changes": {"broken": [], "formed": []},
            "confidence": 0.1,
            "reasoning_steps": ["wrong on purpose"],
        }
    )
    with pytest.raises(ValueError, match="LLM mapping rejected"):
        map_atoms(mol, product, llm=fake)


def test_pipeline_llm_accepts_good_mapping():
    mol = mol_from_smiles("CO", seed=6)
    product, true = scramble(mol, np.random.default_rng(7))
    result = map_atoms(mol, product, llm=oracle_llm(true))
    assert result.mapping == true
    assert any("accepted" in line for line in result.report_lines)
