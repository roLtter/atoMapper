from __future__ import annotations

import numpy as np

from mapper.bonds import assign_bonds
from mapper.molecule import Molecule
from tests.helpers import scramble


def _mol(symbols: list[str], coords: list[list[float]], bonds: set[tuple[int, int]], charge: int = 0) -> Molecule:
    m = Molecule(
        symbols=symbols,
        coords=np.asarray(coords, dtype=float),
        bonds={(a, b) if a < b else (b, a) for a, b in bonds},
        charge=charge,
    )
    return assign_bonds(m) if not bonds else m


def proton_transfer_pair(rng: np.random.Generator | None = None) -> tuple[Molecule, Molecule, list[int]]:
    """H3N···HOH → H4N+···OH− (same 7 atoms)."""
    symbols = ["N", "H", "H", "H", "O", "H", "H"]
    reactant = _mol(
        symbols,
        [
            [0.0, 0.0, 0.0],
            [0.95, 0.0, 0.0],
            [-0.3, 0.9, 0.0],
            [-0.3, -0.45, 0.85],
            [2.8, 0.0, 0.0],
            [3.3, 0.8, 0.0],
            [2.15, 0.0, 0.0],
        ],
        {(0, 1), (0, 2), (0, 3), (4, 5), (4, 6)},
        charge=0,
    )
    product = _mol(
        symbols,
        [
            [0.0, 0.0, 0.0],
            [0.95, 0.0, 0.0],
            [-0.3, 0.9, 0.0],
            [-0.3, -0.45, 0.85],
            [3.2, 0.0, 0.0],
            [3.7, 0.8, 0.0],
            [1.05, 0.05, 0.05],
        ],
        {(0, 1), (0, 2), (0, 3), (0, 6), (4, 5)},
        charge=0,
    )
    scrambled, true = scramble(product, rng or np.random.default_rng(101))
    return reactant, scrambled, true


def sn2_pair(rng: np.random.Generator | None = None) -> tuple[Molecule, Molecule, list[int]]:
    """F−···CH3Cl → FCH3···Cl−."""
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
    scrambled, true = scramble(product, rng or np.random.default_rng(202))
    return reactant, scrambled, true


def keto_enol_pair(rng: np.random.Generator | None = None) -> tuple[Molecule, Molecule, list[int]]:
    """Acetaldehyde ↔ vinyl alcohol with fixed atom correspondence."""
    symbols = ["C", "C", "O", "H", "H", "H", "H"]
    # 0 methyl-C, 1 carbonyl-C, 2 O, 3 aldehyde-H, 4-6 methyl-H (6 migrates to O in enol)
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
    scrambled, true = scramble(enol, rng or np.random.default_rng(303))
    return keto, scrambled, true


CASES = {
    "proton_transfer": proton_transfer_pair,
    "sn2": sn2_pair,
    "keto_enol": keto_enol_pair,
}
