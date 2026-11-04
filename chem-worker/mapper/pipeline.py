from __future__ import annotations

from pathlib import Path

from mapper.bonds import assign_bonds
from mapper.candidates import generate_candidates
from mapper.llm import LLMProvider, OllamaProvider, RESPONSE_SCHEMA
from mapper.metrics import CandidateMetrics, rank_candidates
from mapper.molecule import Molecule
from mapper.output import MappingResult, aligned_product
from mapper.prompt import SYSTEM_PROMPT, build_user_prompt
from mapper.verifier import verify_llm_mapping
from mapper.xyz import assert_same_composition, parse_xyz


def _load(source: str | Path | bytes | Molecule, charge: int, multiplicity: int) -> Molecule:
    if isinstance(source, Molecule):
        mol = source.copy()
        mol.charge = charge
        mol.multiplicity = multiplicity
        return mol
    return parse_xyz(source, charge=charge, multiplicity=multiplicity)


def map_atoms(
    reactant_src: str | Path | bytes | Molecule,
    product_src: str | Path | bytes | Molecule,
    *,
    charge: int = 0,
    multiplicity: int = 1,
    top_k: int = 5,
    out_dir: str | Path | None = None,
    use_llm: bool = False,
    llm: LLMProvider | None = None,
) -> MappingResult:
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

    mappings = generate_candidates(reactant, product, top_k=top_k)
    report.append("")
    report.append("## candidates")
    report.append(f"- generated: {len(mappings)}")

    ranked = rank_candidates(reactant, product, mappings)
    for i, c in enumerate(ranked):
        report.append(
            f"- #{i}: rmsd={c.rmsd:.4f} maxΔ={c.max_displacement:.4f} "
            f"min_lerp={c.min_lerp_distance:.4f} "
            f"broken={c.broken_bonds} formed={c.formed_bonds}"
        )

    best = ranked[0]
    report.append("")
    report.append("## selection")

    if use_llm:
        provider = llm or OllamaProvider()
        try:
            answer = provider.chat_json(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(reactant, product, ranked)},
                ],
                schema=RESPONSE_SCHEMA,
            )
            report.append("- method: LLM + verifier")
            report.append(f"- llm raw: {answer}")
            chosen_idx = int(answer.get("chosen_candidate", 0))
            mapping = [int(x) for x in answer.get("mapping", ranked[0].mapping)]
            if 0 <= chosen_idx < len(ranked) and mapping == ranked[chosen_idx].mapping:
                mapping = ranked[chosen_idx].mapping
            verified = verify_llm_mapping(reactant, product, mapping, best_algorithmic=ranked[0])
            if verified.ok and verified.metrics is not None:
                best = verified.metrics
                report.append("- verifier: accepted")
                for step in answer.get("reasoning_steps", []):
                    report.append(f"- reason: {step}")
            else:
                best = ranked[0]
                report.append(f"- verifier: rejected ({verified.reason})")
                report.append("- fallback: best algorithmic candidate")
        except Exception as exc:
            best = ranked[0]
            report.append(f"- LLM failed: {exc}")
            report.append("- fallback: best algorithmic candidate")
    else:
        report.append("- method: deterministic rank (bond changes, then rmsd)")

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
        candidates=ranked,
        report_lines=report,
    )
    if out_dir is not None:
        result.write(out_dir)
    return result
