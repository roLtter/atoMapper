from __future__ import annotations

from pathlib import Path

import numpy as np

from mapper.molecule import Molecule

_VALID = set(
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar "
    "K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr "
    "Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe".split()
)


def parse_xyz(source: str | Path | bytes, *, charge: int = 0, multiplicity: int = 1) -> Molecule:
    if isinstance(source, bytes):
        text = source.decode("utf-8")
    else:
        path = Path(source)
        text = path.read_text(encoding="utf-8") if path.exists() or isinstance(source, Path) else str(source)

    raw = text.splitlines()
    if len(raw) < 3:
        raise ValueError("xyz too short")

    try:
        n = int(raw[0].strip())
    except ValueError as exc:
        raise ValueError("first line must be atom count") from exc

    body = raw[2 : 2 + n]
    if len(body) < n:
        raise ValueError(f"expected {n} atom lines, got {len(body)}")

    symbols: list[str] = []
    coords = np.zeros((n, 3), dtype=float)
    for i, line in enumerate(body):
        parts = line.split()
        if len(parts) < 4:
            raise ValueError(f"bad atom line {i + 1}: {line!r}")
        sym = parts[0]
        if sym.isdigit():
            raise ValueError(f"invalid element token {sym!r}")
        if sym not in _VALID and sym.title() not in _VALID:
            sym_try = sym.title()
            if sym_try not in _VALID:
                raise ValueError(f"unsupported element {sym!r}")
            sym = sym_try
        else:
            sym = sym if sym in _VALID else sym.title()
        try:
            xyz = [float(parts[1]), float(parts[2]), float(parts[3])]
        except ValueError as exc:
            raise ValueError(f"non-numeric coordinates on atom {i + 1}") from exc
        if not all(np.isfinite(xyz)):
            raise ValueError(f"NaN/Inf coordinates on atom {i + 1}")
        symbols.append(sym)
        coords[i] = xyz

    return Molecule(symbols=symbols, coords=coords, charge=charge, multiplicity=multiplicity)


def write_xyz(mol: Molecule, comment: str = "") -> str:
    lines = [str(mol.n_atoms), comment]
    for sym, (x, y, z) in zip(mol.symbols, mol.coords, strict=True):
        lines.append(f"{sym:2s} {x:14.8f} {y:14.8f} {z:14.8f}")
    return "\n".join(lines) + "\n"


def assert_same_composition(a: Molecule, b: Molecule) -> None:
    if a.n_atoms != b.n_atoms:
        raise ValueError(f"atom count mismatch: {a.n_atoms} vs {b.n_atoms}")
    if a.formula() != b.formula():
        raise ValueError(f"formula mismatch: {a.formula()} vs {b.formula()}")
