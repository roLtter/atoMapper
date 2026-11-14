from __future__ import annotations

import itertools

import networkx as nx
import numpy as np
from scipy.optimize import linear_sum_assignment

from mapper.align import apply_transform, kabsch
from mapper.metrics import evaluate_candidate
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
        m = [-1] * reactant.n_atoms
        for r, p in iso.items():
            m[r] = p
        if all(x >= 0 for x in m):
            mappings.append(m)
    return mappings

def _neighbors(mol: Molecule, idx: int) -> list[int]:
    out = []
    for a, b in mol.bonds:
        if a == idx:
            out.append(b)
        elif b == idx:
            out.append(a)
    return out

def _heavy_bond_changes(reactant: Molecule, product: Molecule, heavy_map: dict[int, int]) -> int:
    inv = {p: r for r, p in heavy_map.items()}
    rb = {
        (a, b) if a < b else (b, a)
        for a, b in reactant.bonds
        if reactant.symbols[a] != "H" and reactant.symbols[b] != "H"
    }
    pb = set()
    for a, b in product.bonds:
        if product.symbols[a] == "H" or product.symbols[b] == "H":
            continue
        if a not in inv or b not in inv:
            continue
        ra, rb_ = inv[a], inv[b]
        pb.add((ra, rb_) if ra < rb_ else (rb_, ra))
    return len(rb - pb) + len(pb - rb)

def enumerate_heavy_maps(reactant: Molecule, product: Molecule, *, max_maps: int = 256) -> list[dict[int, int]]:
    by_r: dict[str, list[int]] = {}
    by_p: dict[str, list[int]] = {}
    for i, s in enumerate(reactant.symbols):
        if s != "H":
            by_r.setdefault(s, []).append(i)
    for i, s in enumerate(product.symbols):
        if s != "H":
            by_p.setdefault(s, []).append(i)
    if set(by_r) != set(by_p):
        return []
    for el in by_r:
        if len(by_r[el]) != len(by_p[el]):
            return []

    import math

    elements = sorted(by_r.keys())
    total = 1
    for el in elements:
        total *= math.factorial(len(by_r[el]))
    if total > max_maps:
        return []

    per_el = []
    for el in elements:
        refs = by_r[el]
        movs = by_p[el]
        per_el.append([(refs, perm) for perm in itertools.permutations(movs)])

    out: list[dict[int, int]] = []
    for combo in itertools.product(*per_el):
        m: dict[int, int] = {}
        for refs, perm in combo:
            for r, p in zip(refs, perm, strict=True):
                m[r] = p
        out.append(m)
    out.sort(key=lambda hm: _heavy_bond_changes(reactant, product, hm))
    return out[:max_maps]

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
        others_r = list(heavy_r)
        others_p = product.heavy_indices()
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

def _assign_hydrogens_min_bond_changes(
    reactant: Molecule,
    product: Molecule,
    heavy_map: dict[int, int],
) -> list[int]:
    n = reactant.n_atoms
    mapping = [-1] * n
    for r, p in heavy_map.items():
        mapping[r] = p

    heavy_r = list(heavy_map.keys())
    R, t, _ = kabsch(
        reactant.coords[heavy_r],
        product.coords[[heavy_map[i] for i in heavy_r]],
    )
    aligned = apply_transform(product.coords, R, t)

    h_r = [i for i, s in enumerate(reactant.symbols) if s == "H"]
    h_p = [i for i, s in enumerate(product.symbols) if s == "H"]

    stable_r: list[int] = []
    stable_pairs: list[tuple[int, list[int]]] = []
    migrating_r: list[int] = []
    for hi in h_r:
        heavies = [x for x in _neighbors(reactant, hi) if reactant.symbols[x] != "H"]
        if len(heavies) == 1 and heavies[0] in heavy_map:
            target = heavy_map[heavies[0]]
            cand = [
                pj
                for pj in h_p
                if target in [x for x in _neighbors(product, pj) if product.symbols[x] != "H"]
            ]
            stable_pairs.append((hi, cand))
            stable_r.append(hi)
        else:
            migrating_r.append(hi)

    used: set[int] = set()
    by_target: dict[int, list[int]] = {}
    for hi, cand in stable_pairs:
        heavies = [x for x in _neighbors(reactant, hi) if reactant.symbols[x] != "H"]
        by_target.setdefault(heavy_map[heavies[0]], []).append(hi)

    for target, hrs in by_target.items():
        cand = [
            pj
            for pj in h_p
            if pj not in used
            and target in [x for x in _neighbors(product, pj) if product.symbols[x] != "H"]
        ]
        if len(cand) < len(hrs):
            for hi in hrs[len(cand) :]:
                if hi not in migrating_r:
                    migrating_r.append(hi)
            hrs = hrs[: len(cand)]
        if not hrs:
            continue
        cost = np.zeros((len(hrs), len(cand)))
        for a, ri in enumerate(hrs):
            for b, mi in enumerate(cand):
                cost[a, b] = np.linalg.norm(reactant.coords[ri] - aligned[mi])
        rows, cols = linear_sum_assignment(cost)
        for r, c in zip(rows, cols, strict=True):
            mapping[hrs[r]] = cand[c]
            used.add(cand[c])

    leftover_r = [i for i in h_r if mapping[i] < 0]
    leftover_p = [j for j in h_p if j not in used]
    if len(leftover_r) != len(leftover_p):
        raise ValueError("hydrogen count mismatch")

    if not leftover_r:
        return mapping

    import math

    if math.factorial(len(leftover_r)) <= 120:
        best_m = None
        best_score = None
        for perm in itertools.permutations(leftover_p):
            trial = list(mapping)
            for ri, pj in zip(leftover_r, perm, strict=True):
                trial[ri] = pj
            metrics = evaluate_candidate(reactant, product, trial)
            score = (metrics.n_bond_changes, metrics.rmsd, metrics.max_displacement)
            if best_score is None or score < best_score:
                best_score = score
                best_m = trial
        assert best_m is not None
        return best_m

    cost = np.zeros((len(leftover_r), len(leftover_p)))
    for a, ri in enumerate(leftover_r):
        r_heavies = {heavy_map[n] for n in _neighbors(reactant, ri) if reactant.symbols[n] != "H" and n in heavy_map}
        for b, mi in enumerate(leftover_p):
            p_heavies = {n for n in _neighbors(product, mi) if product.symbols[n] != "H"}
            dist = float(np.linalg.norm(reactant.coords[ri] - aligned[mi]))
            preserve = len(r_heavies & p_heavies)
            cost[a, b] = dist + 8.0 * (len(r_heavies) - preserve)
    rows, cols = linear_sum_assignment(cost)
    for r, c in zip(rows, cols, strict=True):
        mapping[leftover_r[r]] = leftover_p[c]
    return mapping

def mapping_from_heavy_map(reactant: Molecule, product: Molecule, heavy_map: dict[int, int]) -> list[int]:
    return _assign_hydrogens_min_bond_changes(reactant, product, heavy_map)

def heavy_then_hydrogen_mapping(reactant: Molecule, product: Molecule) -> list[int]:
    g1 = bond_graph(reactant, heavy_only=True)
    g2 = bond_graph(product, heavy_only=True)
    if nx.is_isomorphic(g1, g2, node_match=_node_match):
        matcher = nx.algorithms.isomorphism.GraphMatcher(g1, g2, node_match=_node_match)
        best = None
        best_rmsd = float("inf")
        for iso in itertools.islice(matcher.isomorphisms_iter(), 48):
            idxs_r = list(iso.keys())
            _, _, r = kabsch(reactant.coords[idxs_r], product.coords[[iso[i] for i in idxs_r]])
            if r < best_rmsd:
                best_rmsd = r
                best = iso
        if best is not None:
            return mapping_from_heavy_map(reactant, product, best)
    return mapping_from_heavy_map(reactant, product, _match_heavy_by_distance(reactant, product))

def generate_candidates(reactant: Molecule, product: Molecule, *, top_k: int = 8) -> list[list[int]]:
    seen: set[tuple[int, ...]] = set()
    mappings: list[list[int]] = []

    def add(m: list[int]) -> None:
        key = tuple(m)
        if key in seen:
            return
        if sorted(m) != list(range(len(m))):
            return
        seen.add(key)
        mappings.append(m)

    for m in isomorphic_mappings(reactant, product):
        add(m)

    heavy_maps = enumerate_heavy_maps(reactant, product)
    if not heavy_maps:
        heavy_maps = [_match_heavy_by_distance(reactant, product)]
        g1 = bond_graph(reactant, heavy_only=True)
        g2 = bond_graph(product, heavy_only=True)
        if nx.is_isomorphic(g1, g2, node_match=_node_match):
            matcher = nx.algorithms.isomorphism.GraphMatcher(g1, g2, node_match=_node_match)
            for iso in itertools.islice(matcher.isomorphisms_iter(), 24):
                heavy_maps.append(dict(iso))

    heavy_maps = sorted(heavy_maps, key=lambda hm: _heavy_bond_changes(reactant, product, hm))[:12]
    for hm in heavy_maps:
        add(mapping_from_heavy_map(reactant, product, hm))

    add(heavy_then_hydrogen_mapping(reactant, product))
    add(list(range(reactant.n_atoms)))

    ranked = sorted(
        (evaluate_candidate(reactant, product, m) for m in mappings),
        key=lambda c: (c.n_bond_changes, c.rmsd, c.max_displacement),
    )
    return [c.mapping for c in ranked[:top_k]]
