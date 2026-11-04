from __future__ import annotations

from dataclasses import dataclass

from mapper.metrics import CandidateMetrics, evaluate_candidate
from mapper.molecule import Molecule


@dataclass
class VerifyResult:
    ok: bool
    reason: str
    metrics: CandidateMetrics | None = None


def verify_llm_mapping(
    reactant: Molecule,
    product: Molecule,
    mapping: list[int],
    *,
    best_algorithmic: CandidateMetrics,
    rmsd_slack: float = 0.75,
    bond_change_slack: int = 4,
) -> VerifyResult:
    n = reactant.n_atoms
    if len(mapping) != n:
        return VerifyResult(False, f"mapping length {len(mapping)} != {n}")
    if sorted(mapping) != list(range(n)):
        return VerifyResult(False, "mapping is not a bijection")
    for i, j in enumerate(mapping):
        if reactant.symbols[i] != product.symbols[j]:
            return VerifyResult(False, f"element mismatch at reactant {i}: {reactant.symbols[i]} vs {product.symbols[j]}")

    metrics = evaluate_candidate(reactant, product, mapping)
    if metrics.rmsd > best_algorithmic.rmsd + rmsd_slack:
        return VerifyResult(
            False,
            f"rmsd {metrics.rmsd:.4f} worse than algorithmic {best_algorithmic.rmsd:.4f}+{rmsd_slack}",
            metrics,
        )
    if metrics.n_bond_changes > best_algorithmic.n_bond_changes + bond_change_slack:
        return VerifyResult(
            False,
            f"too many bond changes ({metrics.n_bond_changes}) vs algorithmic {best_algorithmic.n_bond_changes}",
            metrics,
        )
    return VerifyResult(True, "ok", metrics)
