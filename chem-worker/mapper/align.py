from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment


def kabsch(P: np.ndarray, Q: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Rotate/translate Q onto P. Returns R, t, rmsd with Q @ R.T + t ≈ P."""
    if len(P) == 0:
        return np.eye(3), np.zeros(3), 0.0
    Pc = P.mean(axis=0)
    Qc = Q.mean(axis=0)
    P0 = P - Pc
    Q0 = Q - Qc
    H = Q0.T @ P0
    U, _, Vt = np.linalg.svd(H)
    d = np.linalg.det(Vt.T @ U.T)
    S = np.diag([1.0, 1.0, np.sign(d) if d != 0 else 1.0])
    R = Vt.T @ S @ U.T
    t = Pc - Qc @ R.T
    aligned = Q @ R.T + t
    rmsd = float(np.sqrt(((P - aligned) ** 2).sum() / len(P)))
    return R, t, rmsd


def apply_transform(coords: np.ndarray, R: np.ndarray, t: np.ndarray) -> np.ndarray:
    return coords @ R.T + t


def hungarian_by_element(
    symbols: list[str],
    ref_coords: np.ndarray,
    mov_coords: np.ndarray,
    indices: list[int] | None = None,
) -> list[int]:
    """Map mov indices -> ref indices within element classes. Returns mapping mov_idx -> ref_idx for all atoms if indices is None.
    Actually returns full mapping array M where M[ref_i] = mov_j (which mov atom sits at reactant slot i).
    """
    n = len(symbols)
    if indices is None:
        indices = list(range(n))

    mapping = [-1] * n
    used_mov = set()

    by_el: dict[str, list[int]] = {}
    for i in indices:
        by_el.setdefault(symbols[i], []).append(i)

    for el, ref_idxs in by_el.items():
        mov_idxs = [i for i in indices if symbols[i] == el and i not in used_mov]
        if len(ref_idxs) != len(mov_idxs):
            raise ValueError(f"element count mismatch for {el}")
        if not ref_idxs:
            continue
        cost = np.zeros((len(ref_idxs), len(mov_idxs)))
        for a, ri in enumerate(ref_idxs):
            for b, mi in enumerate(mov_idxs):
                cost[a, b] = np.linalg.norm(ref_coords[ri] - mov_coords[mi])
        rows, cols = linear_sum_assignment(cost)
        for r, c in zip(rows, cols, strict=True):
            mapping[ref_idxs[r]] = mov_idxs[c]
            used_mov.add(mov_idxs[c])

    for i in range(n):
        if mapping[i] < 0:
            mapping[i] = i
    return mapping


def rmsd(P: np.ndarray, Q: np.ndarray) -> float:
    return float(np.sqrt(((P - Q) ** 2).sum() / len(P)))
