from __future__ import annotations

import argparse
import time
from dataclasses import dataclass

import numpy as np

from mapper.fixtures import CASES
from mapper.geom import scramble
from mapper.llm import LLMConfig, OllamaProvider
from mapper.pipeline import map_atoms


@dataclass
class Row:
    case: str
    model: str
    ok: bool
    fallback: bool
    rmsd: float
    bond_changes: int
    seconds: float
    detail: str = ""


def _heavy_ok(symbols: list[str], got: list[int], true: list[int]) -> bool:
    return all(got[i] == true[i] for i, s in enumerate(symbols) if s != "H")


def _mol_from_smiles(smiles: str, seed: int):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from mapper.bonds import assign_bonds
    from mapper.molecule import Molecule

    m = Chem.MolFromSmiles(smiles)
    m = Chem.AddHs(m)
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    AllChem.EmbedMolecule(m, params)
    AllChem.MMFFOptimizeMolecule(m)
    conf = m.GetConformer()
    symbols = [a.GetSymbol() for a in m.GetAtoms()]
    coords = np.array(
        [[conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y, conf.GetAtomPosition(i).z] for i in range(m.GetNumAtoms())],
        dtype=float,
    )
    return assign_bonds(Molecule(symbols=symbols, coords=coords))


def run_case(name: str, model: str, use_llm: bool) -> Row:
    t0 = time.perf_counter()
    llm = None
    if use_llm:
        cfg = LLMConfig.from_env()
        cfg.model = model
        llm = OllamaProvider(cfg)

    if name == "cyclohexanone_perm":
        mol = _mol_from_smiles("O=C1CCCCC1", seed=5)
        product, true = scramble(mol, np.random.default_rng(21))
        result = map_atoms(mol, product, use_llm=use_llm, llm=llm)
        ok = _heavy_ok(mol.symbols, result.mapping, true)
    elif name == "chair_boat":
        chair = _mol_from_smiles("O=C1CCCCC1", seed=1)
        boat = _mol_from_smiles("O=C1CCCCC1", seed=99)
        result = map_atoms(chair, boat, use_llm=use_llm, llm=llm)
        ok = result.metrics.n_bond_changes == 0 and result.product_mapped.symbols == chair.symbols
    elif name in CASES:
        reactant, product, true = CASES[name]()
        result = map_atoms(
            reactant,
            product,
            charge=reactant.charge,
            use_llm=use_llm,
            llm=llm,
        )
        ok = _heavy_ok(reactant.symbols, result.mapping, true)
    else:
        raise ValueError(name)

    fallback = any("fallback" in line or "rejected" in line for line in result.report_lines)
    return Row(
        case=name,
        model=model if use_llm else "algorithm",
        ok=ok,
        fallback=fallback,
        rmsd=result.metrics.rmsd,
        bond_changes=result.metrics.n_bond_changes,
        seconds=time.perf_counter() - t0,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mapper.bench")
    parser.add_argument("--model", default="neb-fast")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument(
        "--cases",
        default="cyclohexanone_perm,chair_boat,proton_transfer,sn2,keto_enol",
    )
    args = parser.parse_args(argv)
    use_llm = not args.no_llm
    rows: list[Row] = []
    for name in [c.strip() for c in args.cases.split(",") if c.strip()]:
        try:
            rows.append(run_case(name, args.model, use_llm=use_llm))
        except Exception as exc:
            rows.append(
                Row(
                    case=name,
                    model=args.model if use_llm else "algorithm",
                    ok=False,
                    fallback=True,
                    rmsd=float("nan"),
                    bond_changes=-1,
                    seconds=0.0,
                    detail=str(exc),
                )
            )

    print(f"{'case':20s} {'model':12s} {'ok':4s} {'fb':4s} {'rmsd':8s} {'bonds':6s} {'sec':8s} detail")
    for r in rows:
        print(
            f"{r.case:20s} {r.model:12s} {str(r.ok):4s} {str(r.fallback):4s} "
            f"{r.rmsd:8.4f} {r.bond_changes:6d} {r.seconds:8.2f} {r.detail}"
        )
    n_ok = sum(1 for r in rows if r.ok)
    print(f"passed {n_ok}/{len(rows)}")
    return 0 if n_ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
