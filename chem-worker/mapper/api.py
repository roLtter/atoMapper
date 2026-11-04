from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from mapper.pipeline import map_atoms

app = FastAPI(title="atom-mapper chem-worker")

_JOBS: dict[str, dict] = {}


class JobStatus(BaseModel):
    job_id: str
    status: str
    step: str = ""
    error: str | None = None


class MapResponse(BaseModel):
    job_id: str
    status: str
    mapping: list[int] = Field(default_factory=list)
    rmsd: float | None = None
    report: str | None = None


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/map", response_model=MapResponse)
async def map_endpoint(
    reactant: UploadFile = File(...),
    product: UploadFile = File(...),
    charge: int = Form(0),
    multiplicity: int = Form(1),
    use_llm: bool = Form(False),
    model: str | None = Form(None),
):
    job_id = str(uuid.uuid4())
    _JOBS[job_id] = {"status": "running", "step": "parse", "error": None, "dir": None}
    try:
        r_bytes = await reactant.read()
        p_bytes = await product.read()
        if len(r_bytes) > 2_000_000 or len(p_bytes) > 2_000_000:
            raise HTTPException(400, "file too large")

        from mapper.xyz import parse_xyz

        reactant_mol = parse_xyz(r_bytes, charge=charge, multiplicity=multiplicity)
        product_mol = parse_xyz(p_bytes, charge=charge, multiplicity=multiplicity)
        if reactant_mol.n_atoms > 100 or product_mol.n_atoms > 100:
            raise HTTPException(400, "atom limit is 100")

        out_dir = Path(tempfile.mkdtemp(prefix=f"atom-mapper-{job_id}-"))
        if model:
            import os

            os.environ["LLM_MODEL"] = model

        _JOBS[job_id]["step"] = "map"
        result = map_atoms(
            reactant_mol,
            product_mol,
            charge=charge,
            multiplicity=multiplicity,
            use_llm=use_llm,
            out_dir=out_dir,
        )

        _JOBS[job_id].update(
            {
                "status": "done",
                "step": "done",
                "dir": str(out_dir),
                "mapping": result.mapping,
                "rmsd": result.metrics.rmsd,
                "report": "\n".join(result.report_lines),
            }
        )
        return MapResponse(
            job_id=job_id,
            status="done",
            mapping=result.mapping,
            rmsd=result.metrics.rmsd,
            report="\n".join(result.report_lines),
        )
    except HTTPException:
        raise
    except Exception as exc:
        _JOBS[job_id] = {"status": "failed", "step": "error", "error": str(exc), "dir": None}
        raise HTTPException(500, str(exc)) from exc


@app.get("/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return JobStatus(job_id=job_id, status=job["status"], step=job.get("step", ""), error=job.get("error"))


@app.get("/jobs/{job_id}/files/{name}")
def job_file(job_id: str, name: str):
    job = _JOBS.get(job_id)
    if not job or not job.get("dir"):
        raise HTTPException(404, "job not found")
    allowed = {
        "reactant_mapped.xyz",
        "product_mapped.xyz",
        "mapping.json",
        "report.md",
    }
    if name not in allowed:
        raise HTTPException(400, "unknown file")
    path = Path(job["dir"]) / name
    if not path.exists():
        raise HTTPException(404, "file missing")
    return FileResponse(path)
