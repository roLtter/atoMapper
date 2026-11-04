from __future__ import annotations

import json

from mapper.metrics import CandidateMetrics
from mapper.molecule import Molecule

SYSTEM_PROMPT = """You map atoms between a reactant and a product for ORCA NEB.
You are given compact topology and top candidate mappings from an algorithm.
Choose the chemically best candidate (or a corrected mapping if clearly wrong).
Do not invent atoms. Prefer preserving heavy-atom skeleton and sensible bond changes.
Reply with JSON only.

Few-shot:
1) Cyclohexanone chair -> boat: graphs isomorphic, choose lowest RMSD candidate that keeps carbonyl O/C and ring adjacency.
2) Proton transfer HA-B -> A BH: one H moves; exactly one broken and one formed bond involving that H.
"""


def build_user_prompt(
    reactant: Molecule,
    product: Molecule,
    candidates: list[CandidateMetrics],
) -> str:
    payload = {
        "formula": reactant.formula(),
        "n_atoms": reactant.n_atoms,
        "reactant_elements": [{"index": i, "element": s} for i, s in enumerate(reactant.symbols)],
        "product_elements": [{"index": i, "element": s} for i, s in enumerate(product.symbols)],
        "reactant_bonds": sorted(list(reactant.bonds)),
        "product_bonds": sorted(list(product.bonds)),
        "candidates": [
            {
                "id": i,
                "mapping": c.mapping,
                "rmsd": round(c.rmsd, 5),
                "max_displacement": round(c.max_displacement, 5),
                "min_lerp_distance": round(c.min_lerp_distance, 5),
                "broken_bonds": c.broken_bonds,
                "formed_bonds": c.formed_bonds,
            }
            for i, c in enumerate(candidates)
        ],
        "ambiguous_groups": _ambiguous_groups(candidates),
    }
    return (
        "Select the best atom mapping candidate for NEB.\n"
        "mapping[i] = product atom index corresponding to reactant atom i.\n"
        + json.dumps(payload, indent=2)
    )


def _ambiguous_groups(candidates: list[CandidateMetrics]) -> list[dict]:
    if len(candidates) < 2:
        return []
    n = len(candidates[0].mapping)
    ambiguous = []
    for i in range(n):
        values = {c.mapping[i] for c in candidates}
        if len(values) > 1:
            ambiguous.append({"reactant_index": i, "product_choices": sorted(values)})
    return ambiguous[:40]
