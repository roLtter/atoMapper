from __future__ import annotations

from pathlib import Path

from mapper.bonds import assign_bonds
from mapper.candidates import generate_candidates
from mapper.llm import LLMConfig, LLMProvider, RESPONSE_SCHEMA, make_llm_provider
from mapper.metrics import CandidateMetrics, evaluate_candidate
from mapper.molecule import Molecule
from mapper.normalize import normalize_molecule
from mapper.output import MappingResult, aligned_product
from mapper.prompt import SYSTEM_PROMPT, build_repair_prompt, build_user_prompt
from mapper.verifier import verify_llm_mapping
from mapper.xyz import assert_same_composition, parse_xyz

def _load(source: str | Path | bytes | Molecule, charge: int, multiplicity: int) -> Molecule:
    if isinstance(source, Molecule):
        mol = source.copy()
        mol.charge = charge
        mol.multiplicity = multiplicity
        return mol
    return parse_xyz(source, charge=charge, multiplicity=multiplicity)

def _algo_best(reactant: Molecule, product: Molecule) -> CandidateMetrics:
    cands = generate_candidates(reactant, product, top_k=8)
    if not cands:
        raise ValueError("algorithmic fallback produced no candidates")
    ranked = sorted(
        (evaluate_candidate(reactant, product, m) for m in cands),
        key=lambda c: (c.n_bond_changes, c.rmsd, c.max_displacement),
    )
    return ranked[0]

def _score(m: CandidateMetrics) -> tuple[int, float, float]:
    return (m.n_bond_changes, m.rmsd, m.max_displacement)

def _llm_worse_than_algo(llm: CandidateMetrics, algo: CandidateMetrics) -> bool:
    if llm.n_bond_changes > algo.n_bond_changes + 1:
        return True
    if llm.n_bond_changes >= algo.n_bond_changes and llm.rmsd > algo.rmsd + 0.25:
        return True
    return _score(llm) > _score(algo)

def map_atoms(
    reactant_src: str | Path | bytes | Molecule,
    product_src: str | Path | bytes | Molecule,
    *,
    charge: int = 0,
    multiplicity: int = 1,
    top_k: int = 5,
    out_dir: str | Path | None = None,
    use_llm: bool = True,
    llm: LLMProvider | None = None,
) -> MappingResult:
    del top_k
    report: list[str] = ["# atom-mapper report", ""]

    reactant = _load(reactant_src, charge, multiplicity)
    product = _load(product_src, charge, multiplicity)
    report.append("## parse")
    report.append(f"- reactant atoms: {reactant.n_atoms}, formula: {reactant.formula()}")
    report.append(f"- product atoms: {product.n_atoms}, formula: {product.formula()}")
    assert_same_composition(reactant, product)

    reactant = assign_bonds(reactant)
    product = assign_bonds(product)
    report.append("")
    report.append("## bonds")
    report.append(f"- reactant bonds: {len(reactant.bonds)}")
    report.append(f"- product bonds: {len(product.bonds)}")

    reactant_view = normalize_molecule(reactant)
    product_view = normalize_molecule(product)
    report.append("")
    report.append("## normalize")
    report.append("- centered + principal-axis orientation for LLM input")
    report.append("- original geometries kept for NEB output / Kabsch")

    algo = _algo_best(reactant, product)
    report.append("")
    report.append("## selection")

    if not use_llm:
        report.append("- method: algorithmic (no LLM)")
        report.append(
            f"- chosen mapping: {algo.mapping}"
        )
        report.append(
            f"- metrics: rmsd={algo.rmsd:.4f} broken={algo.broken_bonds} formed={algo.formed_bonds}"
        )
        product_mapped = aligned_product(reactant, product.reorder(algo.mapping))
        result = MappingResult(
            reactant=reactant,
            product_mapped=product_mapped,
            mapping=algo.mapping,
            metrics=algo,
            candidates=[algo],
            report_lines=report,
        )
        if out_dir is not None:
            result.write(out_dir)
        return result

    cfg = LLMConfig.from_env()
    provider = llm or make_llm_provider(cfg)
    report.append(f"- method: LLM ({cfg.provider}/{cfg.model})")
    report.append(
        f"- algo baseline: mapping={algo.mapping} "
        f"rmsd={algo.rmsd:.4f} bond_changes={algo.n_bond_changes}"
    )

    compact_prompt = cfg.provider in {"ollama", "local"} or cfg.model.lower().endswith(":free")
    local_soft = cfg.provider in {"ollama", "local"}
    max_attempts = 3 if local_soft else 2

    answer: dict = {}
    mapping: list[int] = []
    llm_metrics: CandidateMetrics | None = None
    last_reason = ""
    for attempt in range(max_attempts):
        if attempt == 0:
            user = build_user_prompt(reactant_view, product_view, compact=compact_prompt)
        else:
            user = build_repair_prompt(
                reactant_view,
                product_view,
                bad_mapping=mapping,
                reason=last_reason,
                compact=compact_prompt,
            )
            report.append(f"- retry {attempt}: feeding verifier error back to LLM")

        answer = provider.chat_json(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            schema=RESPONSE_SCHEMA,
        )
        report.append(f"- llm raw (attempt {attempt + 1}): {answer}")
        mapping = [int(x) for x in answer["mapping"]]
        verified = verify_llm_mapping(reactant, product, mapping)
        if not verified.ok or verified.metrics is None:
            last_reason = verified.reason
            report.append(f"- verifier rejected: {last_reason}")
            continue

        if _llm_worse_than_algo(verified.metrics, algo):
            report.append(
                f"- quality gate rejected: llm bc={verified.metrics.n_bond_changes} "
                f"rmsd={verified.metrics.rmsd:.3f} vs algo bc={algo.n_bond_changes} "
                f"rmsd={algo.rmsd:.3f}"
            )
            last_reason = "chemically poor mapping"
            llm_metrics = verified.metrics
            continue

        llm_metrics = verified.metrics
        break

    used_fallback = False
    if llm_metrics is None or _llm_worse_than_algo(llm_metrics, algo):
        report.append("- selecting algorithmic baseline (LLM missing or worse)")
        best = algo
        used_fallback = True
    else:
        best = llm_metrics
        if _score(algo) < _score(best):
            report.append("- algo slightly better; preferring algorithmic mapping")
            best = algo
            used_fallback = True

    if used_fallback:
        report.append("- verifier: accepted algorithmic mapping")
    else:
        report.append("- verifier: accepted LLM (bijection + element + quality vs algo)")
    for step in answer.get("reasoning_steps", [])[:12]:
        report.append(f"- llm: {step}")

    report.append(f"- chosen mapping: {best.mapping}")
    report.append(
        f"- metrics: rmsd={best.rmsd:.4f} broken={best.broken_bonds} formed={best.formed_bonds}"
    )

    product_mapped = aligned_product(reactant, product.reorder(best.mapping))
    result = MappingResult(
        reactant=reactant,
        product_mapped=product_mapped,
        mapping=best.mapping,
        metrics=best,
        candidates=[best, algo] if best.mapping != algo.mapping else [best],
        report_lines=report,
    )
    if out_dir is not None:
        result.write(out_dir)
    return result
