from __future__ import annotations

import json

from mapper.molecule import Molecule

SYSTEM_PROMPT = """Atom-mapping for ORCA NEB.
Reply with ONE JSON object only. First character must be '{'.
Required: {"mapping":[p0,p1,...]} length n, a permutation of 0..n-1.
Rules:
- mapping[i] = product atom index for reactant atom i
- element(reactant[i]) == element(product[mapping[i]])
- no markdown, no prose outside JSON
"""

def build_user_prompt(reactant: Molecule, product: Molecule, *, compact: bool = False) -> str:
    payload = {
        "n": reactant.n_atoms,
        "R_el": reactant.symbols,
        "P_el": product.symbols,
        "R_bonds": sorted(list(reactant.bonds)),
        "P_bonds": sorted(list(product.bonds)),
    }
    if not compact:
        payload["R_xyz"] = [[round(float(x), 3) for x in row] for row in reactant.coords.tolist()]
        payload["P_xyz"] = [[round(float(x), 3) for x in row] for row in product.coords.tolist()]
    return json.dumps(payload, separators=(",", ":"))

def sanitize_reject_reason(reason: str) -> str:
    low = reason.lower()
    if "element mismatch" in low:
        return "element mismatch: mapping[i] must keep the same element as reactant[i]"
    if "bijection" in low or "not a bijection" in low:
        return "mapping must be a bijection (permutation of 0..n-1)"
    if "length" in low:
        return "mapping length must equal n"
    if "chemically poor" in low or "bond_changes" in low or "rmsd" in low:
        return "chemically poor mapping: minimize bond broken/formed and geometric displacement"
    return "invalid mapping; output a new permutation obeying element equality"

def build_repair_prompt(
    reactant: Molecule,
    product: Molecule,
    *,
    bad_mapping: list[int],
    reason: str,
    compact: bool = True,
) -> str:
    base = json.loads(build_user_prompt(reactant, product, compact=compact))
    base["previous_mapping"] = bad_mapping
    base["reject_reason"] = sanitize_reject_reason(reason)
    return json.dumps(base, separators=(",", ":"))
