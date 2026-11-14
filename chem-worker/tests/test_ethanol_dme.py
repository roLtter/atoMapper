from pathlib import Path

import pytest

from mapper.pipeline import map_atoms
from mapper.xyz import parse_xyz


@pytest.fixture
def ethanol_dme_paths():
    root = Path(__file__).resolve().parents[2] / "context"
    reactant = root / "reactant.xyz"
    product = root / "product.xyz"
    if not reactant.exists() or not product.exists():
        pytest.skip("context/reactant.xyz and product.xyz not present")
    return reactant, product


def test_ethanol_to_dme_algo_only(ethanol_dme_paths):
    reactant_path, product_path = ethanol_dme_paths
    reactant = parse_xyz(reactant_path)
    product = parse_xyz(product_path)
    result = map_atoms(reactant, product, use_llm=False)
    assert sorted(result.mapping) == list(range(reactant.n_atoms))
    assert any("algorithmic" in line for line in result.report_lines)
