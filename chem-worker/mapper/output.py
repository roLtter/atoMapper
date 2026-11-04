from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from mapper.align import apply_transform, kabsch
from mapper.metrics import CandidateMetrics
from mapper.molecule import Molecule
from mapper.xyz import write_xyz


@dataclass
class MappingResult:
    reactant: Molecule
    product_mapped: Molecule
    mapping: list[int]
    metrics: CandidateMetrics
    candidates: list[CandidateMetrics]
    report_lines: list[str]

    def write(self, out_dir: str | Path) -> dict[str, Path]:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths = {
            "reactant_mapped.xyz": out / "reactant_mapped.xyz",
            "product_mapped.xyz": out / "product_mapped.xyz",
            "mapping.json": out / "mapping.json",
            "report.md": out / "report.md",
        }
        paths["reactant_mapped.xyz"].write_text(write_xyz(self.reactant, "reactant"), encoding="utf-8")
        paths["product_mapped.xyz"].write_text(
            write_xyz(self.product_mapped, "product mapped+aligned"),
            encoding="utf-8",
        )
        payload = {
            "mapping": self.mapping,
            "rmsd": self.metrics.rmsd,
            "max_displacement": self.metrics.max_displacement,
            "min_lerp_distance": self.metrics.min_lerp_distance,
            "broken_bonds": self.metrics.broken_bonds,
            "formed_bonds": self.metrics.formed_bonds,
            "candidates": [
                {
                    "mapping": c.mapping,
                    "rmsd": c.rmsd,
                    "max_displacement": c.max_displacement,
                    "min_lerp_distance": c.min_lerp_distance,
                    "broken_bonds": c.broken_bonds,
                    "formed_bonds": c.formed_bonds,
                }
                for c in self.candidates
            ],
        }
        paths["mapping.json"].write_text(json.dumps(payload, indent=2), encoding="utf-8")
        paths["report.md"].write_text("\n".join(self.report_lines) + "\n", encoding="utf-8")
        return paths


def aligned_product(reactant: Molecule, product_reordered: Molecule) -> Molecule:
    R, t, _ = kabsch(reactant.coords, product_reordered.coords)
    out = product_reordered.copy()
    out.coords = apply_transform(product_reordered.coords, R, t)
    return out
