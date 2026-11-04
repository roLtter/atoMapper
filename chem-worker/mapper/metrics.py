from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from mapper.align import apply_transform, kabsch
from mapper.molecule import Molecule


@dataclass
class CandidateMetrics:
    mapping: list[int]
    rmsd: float
    max_displacement: float
    min_lerp_distance: float
    broken_bonds: list[tuple[int, int]]
    formed_bonds: list[tuple[int, int]]

    @property
    def n_bond_changes(self) -> int:
        return len(self.broken_bonds) + len(self.formed_bonds)


def bond_changes(reactant: Molecule, product_reordered: Molecule) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    rb = reactant.bonds
    pb = product_reordered.bonds
    broken = sorted(rb - pb)
    formed = sorted(pb - rb)
    return broken, formed


def min_distance_along_lerp(P: np.ndarray, Q: np.ndarray, frames: int = 8) -> float:
    n = len(P)
    best = float("inf")
    for f in range(frames + 1):
        t = f / frames
        X = (1 - t) * P + t * Q
        for i in range(n):
            for j in range(i + 1, n):
                d = float(np.linalg.norm(X[i] - X[j]))
                if d < best:
                    best = d
    return best


def evaluate_candidate(reactant: Molecule, product: Molecule, mapping: list[int]) -> CandidateMetrics:
    reordered = product.reorder(mapping)
    R, t, rmsd = kabsch(reactant.coords, reordered.coords)
    aligned = apply_transform(reordered.coords, R, t)
    disp = np.linalg.norm(reactant.coords - aligned, axis=1)
    broken, formed = bond_changes(reactant, reordered)
    return CandidateMetrics(
        mapping=list(mapping),
        rmsd=rmsd,
        max_displacement=float(disp.max()) if len(disp) else 0.0,
        min_lerp_distance=min_distance_along_lerp(reactant.coords, aligned),
        broken_bonds=broken,
        formed_bonds=formed,
    )


def rank_candidates(reactant: Molecule, product: Molecule, mappings: list[list[int]]) -> list[CandidateMetrics]:
    ranked = [evaluate_candidate(reactant, product, m) for m in mappings]
    ranked.sort(key=lambda c: (c.n_bond_changes, c.rmsd, c.max_displacement))
    return ranked
