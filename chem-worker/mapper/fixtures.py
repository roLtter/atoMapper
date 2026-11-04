from __future__ import annotations

import numpy as np

from mapper.geom import scramble
from mapper.molecule import Molecule


def _mol(symbols: list[str], coords: list[list[float]], bonds: set[tuple[int, int]], charge: int = 0) -> Molecule:
    return Molecule(
        symbols=symbols,
        coords=np.asarray(coords, dtype=float),
        bonds={(a, b) if a < b else (b, a) for a, b in bonds},
        charge=charge,
    )


def proton_transfer_pair(rng: np.random.Generator | None = None) -> tuple[Molecule, Molecule, list[int]]:
    symbols = ["N", "H", "H", "H", "O", "H", "H"]
    reactant = _mol(
        symbols,
        [
            [0.0, 0.0, 0.0],
            [-0.4, 0.85, 0.3],
            [-0.4, -0.85, 0.3],
            [-0.5, 0.0, -0.9],
            [2.7, 0.0, 0.0],
            [3.3, 0.75, 0.0],
            [1.75, 0.0, 0.0],
        ],
        {(0, 1), (0, 2), (0, 3), (4, 5), (4, 6)},
    )
    product = _mol(
        symbols,
        [
            [0.0, 0.0, 0.0],
            [-0.4, 0.85, 0.3],
            [-0.4, -0.85, 0.3],
            [-0.5, 0.0, -0.9],
            [2.9, 0.0, 0.0],
            [3.5, 0.75, 0.0],
            [1.05, 0.0, 0.0],
        ],
        {(0, 1), (0, 2), (0, 3), (0, 6), (4, 5)},
    )
    scrambled, true = scramble(product, rng or np.random.default_rng(101), keep_bonds=True)
    return reactant, scrambled, true


def sn2_pair(rng: np.random.Generator | None = None) -> tuple[Molecule, Molecule, list[int]]:
    symbols = ["C", "H", "H", "H", "Cl", "F"]
    reactant = _mol(
        symbols,
        [
            [0.0, 0.0, 0.0],
            [0.35, 0.35, 0.9],
            [0.35, -0.9, -0.2],
            [0.35, 0.55, -0.7],
            [1.8, 0.0, 0.0],
            [-3.0, 0.0, 0.0],
        ],
        {(0, 1), (0, 2), (0, 3), (0, 4)},
        charge=-1,
    )
    product = _mol(
        symbols,
        [
            [0.0, 0.0, 0.0],
            [-0.35, 0.35, 0.9],
            [-0.35, -0.9, -0.2],
            [-0.35, 0.55, -0.7],
            [3.0, 0.0, 0.0],
            [-1.8, 0.0, 0.0],
        ],
        {(0, 1), (0, 2), (0, 3), (0, 5)},
        charge=-1,
    )
    scrambled, true = scramble(product, rng or np.random.default_rng(202), keep_bonds=True)
    return reactant, scrambled, true


def keto_enol_pair(rng: np.random.Generator | None = None) -> tuple[Molecule, Molecule, list[int]]:
    symbols = ["C", "C", "O", "H", "H", "H", "H"]
    keto = _mol(
        symbols,
        [
            [-1.2, 0.0, 0.0],
            [0.2, 0.0, 0.0],
            [0.9, 1.0, 0.0],
            [0.7, -1.0, 0.0],
            [-1.6, 0.9, 0.3],
            [-1.6, -0.9, 0.3],
            [-1.7, 0.0, -1.0],
        ],
        {(0, 1), (1, 2), (1, 3), (0, 4), (0, 5), (0, 6)},
    )
    enol = _mol(
        symbols,
        [
            [-1.2, 0.0, 0.0],
            [0.1, 0.0, 0.0],
            [0.8, 1.15, 0.0],
            [-1.7, -0.95, 0.0],
            [-1.7, 0.95, 0.0],
            [0.6, -0.95, 0.0],
            [1.7, 1.0, 0.0],
        ],
        {(0, 1), (1, 2), (0, 3), (0, 4), (1, 5), (2, 6)},
    )
    scrambled, true = scramble(enol, rng or np.random.default_rng(303), keep_bonds=True)
    return keto, scrambled, true


CASES = {
    "proton_transfer": proton_transfer_pair,
    "sn2": sn2_pair,
    "keto_enol": keto_enol_pair,
}
