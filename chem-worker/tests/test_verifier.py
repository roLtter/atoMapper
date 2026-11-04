from mapper.llm import extract_json_object, strip_think
from mapper.metrics import evaluate_candidate
from mapper.pipeline import map_atoms
from mapper.verifier import verify_llm_mapping
from tests.helpers import mol_from_smiles, scramble
import numpy as np


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    def chat_json(self, messages, *, schema=None):
        return dict(self.payload)


def test_strip_think_and_json():
    text = "<think>secret</think>{\"chosen_candidate\": 0, \"mapping\": [0, 1], \"bond_changes\": {\"broken\": [], \"formed\": []}, \"confidence\": 1, \"reasoning_steps\": [\"ok\"]}"
    assert "secret" not in strip_think(text)
    data = extract_json_object(text)
    assert data["chosen_candidate"] == 0


def test_verifier_rejects_element_mismatch():
    mol = mol_from_smiles("CO", seed=1)
    product, true = scramble(mol, np.random.default_rng(2))
    ranked = evaluate_candidate(mol, product, true)
    bad = list(true)
    # swap two different elements if possible
    c_idx = mol.symbols.index("C")
    o_idx = mol.symbols.index("O")
    bad[c_idx], bad[o_idx] = bad[o_idx], bad[c_idx]
    result = verify_llm_mapping(mol, product, bad, best_algorithmic=ranked)
    assert result.ok is False


def test_pipeline_llm_fallback_on_bad_mapping():
    mol = mol_from_smiles("CO", seed=4)
    product, true = scramble(mol, np.random.default_rng(5))
    algo = map_atoms(mol, product, use_llm=False)
    bad_mapping = list(reversed(range(mol.n_atoms)))
    fake = FakeLLM(
        {
            "chosen_candidate": 0,
            "mapping": bad_mapping,
            "bond_changes": {"broken": [], "formed": []},
            "confidence": 0.1,
            "reasoning_steps": ["wrong on purpose"],
        }
    )
    result = map_atoms(mol, product, use_llm=True, llm=fake)
    assert result.mapping == algo.mapping
    assert any("rejected" in line or "fallback" in line for line in result.report_lines)


def test_pipeline_llm_accepts_good_candidate():
    mol = mol_from_smiles("CO", seed=6)
    product, true = scramble(mol, np.random.default_rng(7))
    algo = map_atoms(mol, product, use_llm=False)
    fake = FakeLLM(
        {
            "chosen_candidate": 0,
            "mapping": algo.mapping,
            "bond_changes": {"broken": [], "formed": []},
            "confidence": 0.9,
            "reasoning_steps": ["matches algorithm"],
        }
    )
    result = map_atoms(mol, product, use_llm=True, llm=fake)
    assert result.mapping == algo.mapping
    assert any("accepted" in line for line in result.report_lines)
