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

MANUAL_CHAT_PROMPT = """Atom mapping for ORCA NEB.

I attach two XYZ files:
- reactant_norm.xyz
- product_norm.xyz

Same elemental composition, possibly different atom order / orientation.
Your job: find a bijection mapping from reactant atoms to product atoms.

Rules:
1) mapping[i] = index of the product atom that corresponds to reactant atom i
2) mapping is a permutation of 0..n-1
3) element(reactant[i]) must equal element(product[mapping[i]])
4) Prefer chemically sensible bond changes (minimal broken/formed bonds)

Return exactly three artifacts (no extra commentary outside the files):

1) mapping.json with shape:
{"mapping":[...],"confidence":0.0}

2) reactant_mapped.xyz
   Same atom order and coordinates as reactant_norm.xyz

3) product_mapped.xyz
   Product atoms reordered so that atom i in this file matches reactant atom i
   (i.e. product_mapped atom i = product_norm atom mapping[i])
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
    return "invalid mapping; output a new permutation obeying element equality"


def build_repair_prompt(
    reactant: Molecule,
    product: Molecule,
    *,
    bad_mapping: list[int],
    reason: str,
    compact: bool = False,
) -> str:
    base = json.loads(build_user_prompt(reactant, product, compact=compact))
    base["previous_mapping"] = bad_mapping
    base["reject_reason"] = sanitize_reject_reason(reason)
    return json.dumps(base, separators=(",", ":"))
