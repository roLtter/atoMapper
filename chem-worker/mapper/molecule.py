from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Molecule:
    symbols: list[str]
    coords: np.ndarray
    bonds: set[tuple[int, int]] = field(default_factory=set)
    charge: int = 0
    multiplicity: int = 1

    def __post_init__(self) -> None:
        self.coords = np.asarray(self.coords, dtype=float)
        if self.coords.ndim != 2 or self.coords.shape[1] != 3:
            raise ValueError("coords must have shape (n_atoms, 3)")
        if len(self.symbols) != len(self.coords):
            raise ValueError("symbols and coords length mismatch")

    @property
    def n_atoms(self) -> int:
        return len(self.symbols)

    def formula(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self.symbols:
            counts[s] = counts.get(s, 0) + 1
        return counts

    def heavy_indices(self) -> list[int]:
        return [i for i, s in enumerate(self.symbols) if s != "H"]

    def copy(self) -> Molecule:
        return Molecule(
            symbols=list(self.symbols),
            coords=self.coords.copy(),
            bonds=set(self.bonds),
            charge=self.charge,
            multiplicity=self.multiplicity,
        )

    def reorder(self, mapping: list[int]) -> Molecule:
        """mapping[i] = index in self that becomes new atom i (product->reactant order)."""
        symbols = [self.symbols[j] for j in mapping]
        coords = self.coords[np.asarray(mapping, dtype=int)]
        inv = {old: new for new, old in enumerate(mapping)}
        bonds = set()
        for a, b in self.bonds:
            na, nb = inv[a], inv[b]
            bonds.add((na, nb) if na < nb else (nb, na))
        return Molecule(
            symbols=symbols,
            coords=coords,
            bonds=bonds,
            charge=self.charge,
            multiplicity=self.multiplicity,
        )
