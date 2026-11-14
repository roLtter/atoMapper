from __future__ import annotations

import numpy as np

from mapper.molecule import Molecule

def orient_principal_axes(coords: np.ndarray) -> np.ndarray:
    if len(coords) == 0:
        return coords.copy()
    X = coords - coords.mean(axis=0)
    if len(X) < 2:
        return X
    _u, _s, vt = np.linalg.svd(X, full_matrices=False)
    Y = X @ vt.T
    for ax in range(min(3, Y.shape[1])):
        if float(np.abs(Y[:, ax]).sum()) < 1e-12:
            continue
        if float(Y[:, ax].sum()) < 0.0:
            Y[:, ax] *= -1.0
    if Y.shape[1] == 3:
        R = vt.T.copy()
        for ax in range(3):
            if float(np.abs((X @ R)[:, ax]).sum()) < 1e-12:
                continue
            if float((X @ R)[:, ax].sum()) < 0.0:
                R[:, ax] *= -1.0
        if np.linalg.det(R) < 0.0:
            R[:, -1] *= -1.0
        Y = X @ R
    return Y

def normalize_molecule(mol: Molecule) -> Molecule:
    out = mol.copy()
    out.coords = orient_principal_axes(mol.coords)
    return out
