from pathlib import Path

import pytest

from mapper.pipeline import prepare_manual, report_from_mapping_files
from mapper.xyz import parse_xyz, write_xyz


@pytest.fixture
def ethanol_dme_paths():
    root = Path(__file__).resolve().parents[2] / "context"
    reactant = root / "reactant.xyz"
    product = root / "product.xyz"
    if not reactant.exists() or not product.exists():
        pytest.skip("context/reactant.xyz and product.xyz not present")
    return reactant, product


def test_ethanol_to_dme_manual_prep(ethanol_dme_paths):
    reactant_path, product_path = ethanol_dme_paths
    reactant = parse_xyz(reactant_path)
    product = parse_xyz(product_path)
    prep = prepare_manual(reactant, product)
    assert prep.reactant_norm.n_atoms == reactant.n_atoms
    assert prep.product_norm.n_atoms == product.n_atoms
    assert "mapping[i]" in prep.prompt
    assert any("manual prep" in line for line in prep.report_lines)


def test_manual_import_identity_mapped(ethanol_dme_paths, tmp_path):
    reactant_path, product_path = ethanol_dme_paths
    reactant = parse_xyz(reactant_path)
    product = parse_xyz(product_path)
    # Simulate ChatGPT already-remapped product via identity on same geometry pair
    # using reactant as both sides with identity mapping.json
    mapping = {"mapping": list(range(reactant.n_atoms)), "confidence": 1.0}
    r_xyz = write_xyz(reactant, "reactant")
    p_xyz = write_xyz(reactant, "product mapped")
    result = report_from_mapping_files(r_xyz.encode(), p_xyz.encode(), mapping)
    assert result.mapping == list(range(reactant.n_atoms))
    assert result.metrics.rmsd < 1e-6
    out = result.write(tmp_path)
    assert out["mapping.json"].exists()
    assert out["report.md"].exists()
