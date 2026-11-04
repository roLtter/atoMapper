from __future__ import annotations

import itertools

import networkx as nx
import numpy as np
from scipy.optimize import linear_sum_assignment

from mapper.align import apply_transform, hungarian_by_element, kabsch
from mapper.molecule import Molecule


def bond_graph(mol: Molecule, *, heavy_only: bool = False) -> nx.Graph:
    g = nx.Graph()
    for i, sym in enumerate(mol.symbols):
        if heavy_only and sym == "H":
            continue
        g.add_node(i, element=sym)
    for a, b in mol.bonds:
        if heavy_only and (mol.symbols[a] == "H" or mol.symbols[b] == "H"):
            continue
        if a in g and b in g:
            g.add_edge(a, b)
    return g


def _node_match(n1, n2) -> bool:
    return n1["element"] == n2["element"]


def isomorphic_mappings(
    reactant: Molecule,
    product: Molecule,
    *,
    max_isos: int = 64,
) -> list[list[int]]:
    g1 = bond_graph(reactant)
    g2 = bond_graph(product)
    if not nx.is_isomorphic(g1, g2, node_match=_node_match):
        return []

    matcher = nx.algorithms.isomorphism.GraphMatcher(g1, g2, node_match=_node_match)
    mappings: list[list[int]] = []
    for iso in itertools.islice(matcher.isomorphisms_iter(), max_isos):
        # iso: reactant_idx -> product_idx
        m = [-1] * reactant.n_atoms
        for r, p in iso.items():
            m[r] = p
        if all(x >= 0 for x in m):
            mappings.append(m)
    return mappings


def heavy_then_hydrogen_mapping(reactant: Molecule, product: Molecule) -> list[int]:
    heavy_r = reactant.heavy_indices()
    heavy_p = product.heavy_indices()
    if len(heavy_r) != len(heavy_p):
        raise ValueError("heavy atom count mismatch")

    g1 = bond_graph(reactant, heavy_only=True)
    g2 = bond_graph(product, heavy_only=True)

    heavy_map_r_to_p: dict[int, int] | None = None
    if nx.is_isomorphic(g1, g2, node_match=_node_match):
        matcher = nx.algorithms.isomorphism.GraphMatcher(g1, g2, node_match=_node_match)
        best = None
        best_rmsd = float("inf")
        for iso in itertools.islice(matcher.isomorphisms_iter(), 48):
            idxs_r = list(iso.keys())
            P = reactant.coords[idxs_r]
            Q = product.coords[[iso[i] for i in idxs_r]]
            _, _, r = kabsch(P, Q)
            if r < best_rmsd:
                best_rmsd = r
                best = iso
        heavy_map_r_to_p = best

    mapping = [-1] * reactant.n_atoms
    if heavy_map_r_to_p is not None:
        for r, p in heavy_map_r_to_p.items():
            mapping[r] = p
        R, t, _ = kabsch(
            reactant.coords[heavy_r],
            product.coords[[heavy_map_r_to_p[i] for i in heavy_r]],
        )
        prod_aligned = apply_transform(product.coords, R, t)
    else:
        # distance-matrix fingerprint matching per element among heavy atoms
        mapping_partial = _match_heavy_by_distance(reactant, product)
        for r, p in mapping_partial.items():
            mapping[r] = p
        R, t, _ = kabsch(
            reactant.coords[heavy_r],
            product.coords[[mapping_partial[i] for i in heavy_r]],
        )
        prod_aligned = apply_transform(product.coords, R, t)

    mapping = _assign_hydrogens(reactant, product, mapping, prod_aligned)
    mapping = _refine_mapping(reactant, product, mapping)
    return mapping


def _distance_fingerprint(mol: Molecule, idx: int, others: list[int]) -> np.ndarray:
    d = np.sort(np.linalg.norm(mol.coords[others] - mol.coords[idx], axis=1))
    return d


def _match_heavy_by_distance(reactant: Molecule, product: Molecule) -> dict[int, int]:
    heavy_r = reactant.heavy_indices()
    result: dict[int, int] = {}
    by_el: dict[str, list[int]] = {}
    for i in heavy_r:
        by_el.setdefault(reactant.symbols[i], []).append(i)

    used_p: set[int] = set()
    for el, refs in by_el.items():
        movs = [i for i in product.heavy_indices() if product.symbols[i] == el and i not in used_p]
        others_r = [i for i in heavy_r]
        others_p = [i for i in product.heavy_indices()]
        cost = np.zeros((len(refs), len(movs)))
        for a, ri in enumerate(refs):
            fr = _distance_fingerprint(reactant, ri, [j for j in others_r if j != ri])
            for b, mi in enumerate(movs):
                fp = _distance_fingerprint(product, mi, [j for j in others_p if j != mi])
                n = min(len(fr), len(fp))
                cost[a, b] = float(np.linalg.norm(fr[:n] - fp[:n])) if n else 0.0
        rows, cols = linear_sum_assignment(cost)
        for r, c in zip(rows, cols, strict=True):
            result[refs[r]] = movs[c]
            used_p.add(movs[c])
    return result


def _neighbors(mol: Molecule, idx: int) -> list[int]:
    out = []
    for a, b in mol.bonds:
        if a == idx:
            out.append(b)
        elif b == idx:
            out.append(a)
    return out


def _assign_hydrogens(
    reactant: Molecule,
    product: Molecule,
    mapping: list[int],
    prod_aligned: np.ndarray,
) -> list[int]:
    mapping = list(mapping)
    assigned_p = {p for p in mapping if p >= 0}
    h_r = [i for i, s in enumerate(reactant.symbols) if s == "H"]
    h_p = [i for i, s in enumerate(product.symbols) if s == "H" and i not in assigned_p]

    # group H by heavy neighbor if unique
    groups_r: dict[int, list[int]] = {}
    ungrouped_r: list[int] = []
    for hi in h_r:
        heavies = [n for n in _neighbors(reactant, hi) if reactant.symbols[n] != "H"]
        if len(heavies) == 1 and mapping[heavies[0]] >= 0:
            groups_r.setdefault(heavies[0], []).append(hi)
        else:
            ungrouped_r.append(hi)

    groups_p: dict[int, list[int]] = {}
    ungrouped_p: list[int] = []
    for hi in h_p:
        heavies = [n for n in _neighbors(product, hi) if product.symbols[n] != "H"]
        if len(heavies) == 1:
            groups_p.setdefault(heavies[0], []).append(hi)
        else:
            ungrouped_p.append(hi)

    for heavy_r, hrs in groups_r.items():
        heavy_p = mapping[heavy_r]
        candidates = list(groups_p.get(heavy_p, []))
        if len(candidates) < len(hrs):
            candidates = candidates + [h for h in ungrouped_p if h not in candidates]
        candidates = candidates[: len(hrs)] if len(candidates) >= len(hrs) else candidates + ungrouped_p
        # unique candidates
        seen = set()
        cand = []
        for c in candidates + ungrouped_p + h_p:
            if c not in seen and c not in assigned_p:
                seen.add(c)
                cand.append(c)
        cand = cand[: len(hrs)]
        if len(cand) != len(hrs):
            continue
        cost = np.zeros((len(hrs), len(cand)))
        for a, ri in enumerate(hrs):
            for b, mi in enumerate(cand):
                cost[a, b] = np.linalg.norm(reactant.coords[ri] - prod_aligned[mi])
        rows, cols = linear_sum_assignment(cost)
        for r, c in zip(rows, cols, strict=True):
            mapping[hrs[r]] = cand[c]
            assigned_p.add(cand[c])

    leftover_r = [i for i in h_r if mapping[i] < 0]
    leftover_p = [i for i in h_p if i not in assigned_p]
    if leftover_r:
        if len(leftover_r) != len(leftover_p):
            raise ValueError("hydrogen count mismatch after heavy mapping")
        cost = np.zeros((len(leftover_r), len(leftover_p)))
        for a, ri in enumerate(leftover_r):
            r_heavies = {mapping[n] for n in _neighbors(reactant, ri) if reactant.symbols[n] != "H" and mapping[n] >= 0}
            for b, mi in enumerate(leftover_p):
                p_heavies = {n for n in _neighbors(product, mi) if product.symbols[n] != "H"}
                dist = float(np.linalg.norm(reactant.coords[ri] - prod_aligned[mi]))
                preserve = len(r_heavies & p_heavies)
                cost[a, b] = dist + 5.0 * (len(r_heavies) - preserve)
        rows, cols = linear_sum_assignment(cost)
        for r, c in zip(rows, cols, strict=True):
            mapping[leftover_r[r]] = leftover_p[c]

    for i, v in enumerate(mapping):
        if v < 0:
            raise ValueError(f"unmapped atom {i}")
    return mapping


def _refine_mapping(reactant: Molecule, product: Molecule, mapping: list[int], rounds: int = 3) -> list[int]:
    mapping = list(mapping)
    heavy = reactant.heavy_indices()
    for _ in range(rounds):
        Q = product.coords[np.asarray(mapping)]
        R, t, _ = kabsch(reactant.coords, Q)
        aligned_full = apply_transform(product.coords, R, t)
        fixed = {i: mapping[i] for i in heavy}
        refreshed = [-1] * reactant.n_atoms
        for i, pidx in fixed.items():
            refreshed[i] = pidx
        mapping = _assign_hydrogens(reactant, product, refreshed, aligned_full)
    return mapping


def score_mapping_rmsd(reactant: Molecule, product: Molecule, mapping: list[int]) -> float:
    Q = product.coords[np.asarray(mapping)]
    _, _, r = kabsch(reactant.coords, Q)
    return r


def generate_candidates(reactant: Molecule, product: Molecule, *, top_k: int = 5) -> list[list[int]]:
    seen: set[tuple[int, ...]] = set()
    scored: list[tuple[float, list[int]]] = []

    def add(m: list[int]) -> None:
        key = tuple(m)
        if key in seen:
            return
        if sorted(m) != list(range(len(m))):
            return
        seen.add(key)
        scored.append((score_mapping_rmsd(reactant, product, m), m))

    for m in isomorphic_mappings(reactant, product):
        add(m)

    add(heavy_then_hydrogen_mapping(reactant, product))

    # identity as weak baseline when sizes match
    add(list(range(reactant.n_atoms)))

    scored.sort(key=lambda x: x[0])
    return [m for _, m in scored[:top_k]]
