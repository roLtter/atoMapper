from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from mapper.bonds import assign_bonds
from mapper.llm import LLMConfig, LLMProvider, RESPONSE_SCHEMA, make_llm_provider
from mapper.metrics import CandidateMetrics
from mapper.molecule import Molecule
from mapper.normalize import normalize_molecule
from mapper.output import MappingResult, aligned_product
from mapper.prompt import (
    MANUAL_CHAT_PROMPT,
    SYSTEM_PROMPT,
    build_repair_prompt,
    build_user_prompt,
)
from mapper.verifier import verify_llm_mapping
from mapper.xyz import assert_same_composition, parse_xyz, write_xyz


def _load(source: str | Path | bytes | Molecule) -> Molecule:
    if isinstance(source, Molecule):
        return source.copy()
    return parse_xyz(source)


def _finish(
    reactant: Molecule,
    product: Molecule,
    mapping: list[int],
    metrics: CandidateMetrics,
    report: list[str],
    out_dir: str | Path | None,
) -> MappingResult:
    product_mapped = aligned_product(reactant, product.reorder(mapping))
    result = MappingResult(
        reactant=reactant,
        product_mapped=product_mapped,
        mapping=mapping,
        metrics=metrics,
        candidates=[metrics],
        report_lines=report,
    )
    if out_dir is not None:
        result.write(out_dir)
    return result


def map_atoms(
    reactant_src: str | Path | bytes | Molecule,
    product_src: str | Path | bytes | Molecule,
    *,
    out_dir: str | Path | None = None,
    llm: LLMProvider | None = None,
) -> MappingResult:
    report: list[str] = ["# atom-mapper report", ""]

    reactant = _load(reactant_src)
    product = _load(product_src)
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

    cfg = LLMConfig.from_env()
    provider = llm or make_llm_provider(cfg)
    report.append("")
    report.append("## selection")
    report.append(f"- method: LLM ({cfg.provider}/{cfg.model})")

    answer: dict = {}
    mapping: list[int] = []
    last_reason = ""
    max_attempts = max(2, cfg.max_retries)
    verified = None
    for attempt in range(max_attempts):
        if attempt == 0:
            user = build_user_prompt(reactant_view, product_view, compact=False)
        else:
            user = build_repair_prompt(
                reactant_view,
                product_view,
                bad_mapping=mapping,
                reason=last_reason,
                compact=False,
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
        if verified.ok and verified.metrics is not None:
            break
        last_reason = verified.reason
        report.append(f"- verifier rejected: {last_reason}")

    if verified is None or not verified.ok or verified.metrics is None:
        raise ValueError(f"LLM mapping rejected: {last_reason or 'unknown'}")

    best = verified.metrics
    report.append("- verifier: accepted LLM (bijection + element match)")
    for step in answer.get("reasoning_steps", [])[:12]:
        report.append(f"- llm: {step}")
    report.append(f"- chosen mapping: {best.mapping}")
    report.append(
        f"- metrics: rmsd={best.rmsd:.4f} broken={best.broken_bonds} formed={best.formed_bonds}"
    )
    return _finish(reactant, product, best.mapping, best, report, out_dir)


@dataclass
class ManualPrepResult:
    reactant_norm: Molecule
    product_norm: Molecule
    prompt: str
    report_lines: list[str]

    def write(self, out_dir: str | Path) -> dict[str, Path]:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths = {
            "reactant_norm.xyz": out / "reactant_norm.xyz",
            "product_norm.xyz": out / "product_norm.xyz",
            "prompt.txt": out / "prompt.txt",
            "report.md": out / "report.md",
        }
        paths["reactant_norm.xyz"].write_text(
            write_xyz(self.reactant_norm, "reactant normalized"), encoding="utf-8"
        )
        paths["product_norm.xyz"].write_text(
            write_xyz(self.product_norm, "product normalized"), encoding="utf-8"
        )
        paths["prompt.txt"].write_text(self.prompt, encoding="utf-8")
        paths["report.md"].write_text("\n".join(self.report_lines) + "\n", encoding="utf-8")
        return paths


def prepare_manual(
    reactant_src: str | Path | bytes | Molecule,
    product_src: str | Path | bytes | Molecule,
    *,
    out_dir: str | Path | None = None,
) -> ManualPrepResult:
    report = ["# atom-mapper report", "", "## parse"]
    reactant = _load(reactant_src)
    product = _load(product_src)
    report.append(f"- reactant atoms: {reactant.n_atoms}, formula: {reactant.formula()}")
    report.append(f"- product atoms: {product.n_atoms}, formula: {product.formula()}")
    assert_same_composition(reactant, product)

    reactant = assign_bonds(reactant)
    product = assign_bonds(product)
    report.append("")
    report.append("## bonds")
    report.append(f"- reactant bonds: {len(reactant.bonds)}")
    report.append(f"- product bonds: {len(product.bonds)}")

    reactant_norm = normalize_molecule(reactant)
    product_norm = normalize_molecule(product)
    report.append("")
    report.append("## normalize")
    report.append("- method: manual prep (normalize only, no mapping)")
    report.append("- download reactant_norm.xyz, product_norm.xyz, prompt.txt")
    report.append("- send them to your chat model, then upload the 3 result files here")

    result = ManualPrepResult(
        reactant_norm=reactant_norm,
        product_norm=product_norm,
        prompt=MANUAL_CHAT_PROMPT.strip() + "\n",
        report_lines=report,
    )
    if out_dir is not None:
        result.write(out_dir)
    return result


def report_from_mapping_files(
    reactant_src: str | Path | bytes | Molecule,
    product_src: str | Path | bytes | Molecule,
    mapping_src: str | Path | bytes | dict,
    *,
    out_dir: str | Path | None = None,
) -> MappingResult:
    report = ["# atom-mapper report", "", "## parse"]
    reactant = _load(reactant_src)
    product = _load(product_src)
    report.append(f"- reactant atoms: {reactant.n_atoms}, formula: {reactant.formula()}")
    report.append(f"- product atoms: {product.n_atoms}, formula: {product.formula()}")
    assert_same_composition(reactant, product)

    if isinstance(mapping_src, dict):
        payload = mapping_src
    elif isinstance(mapping_src, bytes):
        payload = json.loads(mapping_src.decode("utf-8"))
    else:
        path = Path(mapping_src)
        text = path.read_text(encoding="utf-8") if path.exists() else str(mapping_src)
        payload = json.loads(text)

    reported = [int(x) for x in payload["mapping"]]
    report.append("")
    report.append("## selection")
    report.append("- method: manual import (user-provided mapping.json + mapped xyz)")
    report.append(f"- mapping.json: {reported}")

    reactant = assign_bonds(reactant)
    product = assign_bonds(product)

    identity = list(range(reactant.n_atoms))
    verified = verify_llm_mapping(reactant, product, identity)
    apply_map = identity
    if verified.ok and verified.metrics is not None:
        report.append("- product xyz looks already remapped; evaluating identity order")
    else:
        verified = verify_llm_mapping(reactant, product, reported)
        apply_map = reported
        if not verified.ok or verified.metrics is None:
            raise ValueError(f"imported mapping rejected: {verified.reason}")
        report.append("- applied mapping.json to product xyz")

    best = verified.metrics
    assert best is not None
    report.append("- verifier: accepted (bijection + element match)")
    report.append(f"- chosen mapping: {reported}")
    report.append(
        f"- metrics: rmsd={best.rmsd:.4f} broken={best.broken_bonds} formed={best.formed_bonds}"
    )
    finished = _finish(reactant, product, apply_map, best, report, None)
    finished.mapping = reported
    if out_dir is not None:
        finished.write(out_dir)
    return finished
