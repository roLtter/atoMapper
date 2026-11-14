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
) -> VerifyResult:
    n = reactant.n_atoms
    if len(mapping) != n:
        return VerifyResult(False, f"mapping length {len(mapping)} != {n}")
    if sorted(mapping) != list(range(n)):
        return VerifyResult(False, "mapping is not a bijection")
    for i, j in enumerate(mapping):
        if reactant.symbols[i] != product.symbols[j]:
            return VerifyResult(
                False,
                f"element mismatch at reactant {i}: {reactant.symbols[i]} vs {product.symbols[j]}",
            )

    metrics = evaluate_candidate(reactant, product, mapping)
    return VerifyResult(True, "ok", metrics)
