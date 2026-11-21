from __future__ import annotations

import os
import tempfile
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from mapper.pipeline import map_atoms, prepare_manual, report_from_mapping_files
from mapper.xyz import parse_xyz

app = FastAPI(title="atom-mapper chem-worker")

_JOBS: dict[str, dict] = {}
_ALLOWED_FILES = {
    "reactant_mapped.xyz",
    "product_mapped.xyz",
    "reactant_norm.xyz",
    "product_norm.xyz",
    "prompt.txt",
    "mapping.json",
    "report.md",
}


def _load_dotenv() -> None:
    path = Path(__file__).resolve().parents[2] / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


_load_dotenv()


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


class NormalizeResponse(BaseModel):
    job_id: str
    status: str
    report: str | None = None


def _fail(job_id: str, exc: Exception) -> None:
    err = str(exc) or repr(exc)
    _JOBS[job_id] = {
        "status": "failed",
        "step": "error",
        "error": err,
        "dir": None,
        "traceback": traceback.format_exc(),
    }
    print(f"[job] {job_id} failed: {err}\n{traceback.format_exc()}", flush=True)


def _read_pair(r_bytes: bytes, p_bytes: bytes):
    if len(r_bytes) > 2_000_000 or len(p_bytes) > 2_000_000:
        raise HTTPException(400, "file too large")
    reactant_mol = parse_xyz(r_bytes)
    product_mol = parse_xyz(p_bytes)
    if reactant_mol.n_atoms > 100 or product_mol.n_atoms > 100:
        raise HTTPException(400, "atom limit is 100")
    return reactant_mol, product_mol


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/llm")
def llm_status():
    from mapper.llm import LLMConfig

    _load_dotenv()
    cfg = LLMConfig.from_env()
    return {
        "provider": "polza",
        "model": cfg.model,
        "base_url": cfg.base_url,
        "max_tokens": cfg.max_tokens,
        "timeout_s": cfg.timeout_s,
        "api_key_set": bool(cfg.api_key),
        "http_proxy": cfg.http_proxy or "",
        "api_key_env": "POLZA_API_KEY",
    }


@app.post("/map", response_model=MapResponse)
async def map_endpoint(
    reactant: UploadFile = File(...),
    product: UploadFile = File(...),
    model: str | None = Form(None),
):
    job_id = str(uuid.uuid4())
    _JOBS[job_id] = {"status": "running", "step": "parse", "error": None, "dir": None}
    try:
        _load_dotenv()
        reactant_mol, product_mol = _read_pair(await reactant.read(), await product.read())
        out_dir = Path(tempfile.mkdtemp(prefix=f"atom-mapper-{job_id}-"))
        if model:
            os.environ["LLM_MODEL"] = model
        _JOBS[job_id]["step"] = "map"
        result = map_atoms(reactant_mol, product_mol, out_dir=out_dir)
        report = "\n".join(result.report_lines)
        _JOBS[job_id].update(
            {
                "status": "done",
                "step": "done",
                "dir": str(out_dir),
                "mapping": result.mapping,
                "rmsd": result.metrics.rmsd,
                "report": report,
                "kind": "map",
            }
        )
        return MapResponse(
            job_id=job_id,
            status="done",
            mapping=result.mapping,
            rmsd=result.metrics.rmsd,
            report=report,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _fail(job_id, exc)
        raise HTTPException(500, str(exc) or repr(exc)) from exc


@app.post("/normalize", response_model=NormalizeResponse)
async def normalize_endpoint(
    reactant: UploadFile = File(...),
    product: UploadFile = File(...),
):
    job_id = str(uuid.uuid4())
    _JOBS[job_id] = {"status": "running", "step": "normalize", "error": None, "dir": None}
    try:
        reactant_mol, product_mol = _read_pair(await reactant.read(), await product.read())
        out_dir = Path(tempfile.mkdtemp(prefix=f"atom-mapper-{job_id}-"))
        result = prepare_manual(reactant_mol, product_mol, out_dir=out_dir)
        report = "\n".join(result.report_lines)
        _JOBS[job_id].update(
            {
                "status": "done",
                "step": "done",
                "dir": str(out_dir),
                "report": report,
                "kind": "normalize",
            }
        )
        return NormalizeResponse(job_id=job_id, status="done", report=report)
    except HTTPException:
        raise
    except Exception as exc:
        _fail(job_id, exc)
        raise HTTPException(500, str(exc) or repr(exc)) from exc


@app.post("/from-mapping", response_model=MapResponse)
async def from_mapping_endpoint(
    reactant: UploadFile = File(...),
    product: UploadFile = File(...),
    mapping: UploadFile = File(...),
):
    job_id = str(uuid.uuid4())
    _JOBS[job_id] = {"status": "running", "step": "import", "error": None, "dir": None}
    try:
        r_bytes = await reactant.read()
        p_bytes = await product.read()
        m_bytes = await mapping.read()
        if len(m_bytes) > 2_000_000:
            raise HTTPException(400, "file too large")
        reactant_mol, product_mol = _read_pair(r_bytes, p_bytes)
        out_dir = Path(tempfile.mkdtemp(prefix=f"atom-mapper-{job_id}-"))
        result = report_from_mapping_files(reactant_mol, product_mol, m_bytes, out_dir=out_dir)
        report = "\n".join(result.report_lines)
        _JOBS[job_id].update(
            {
                "status": "done",
                "step": "done",
                "dir": str(out_dir),
                "mapping": result.mapping,
                "rmsd": result.metrics.rmsd,
                "report": report,
                "kind": "from-mapping",
            }
        )
        return MapResponse(
            job_id=job_id,
            status="done",
            mapping=result.mapping,
            rmsd=result.metrics.rmsd,
            report=report,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _fail(job_id, exc)
        raise HTTPException(500, str(exc) or repr(exc)) from exc


@app.get("/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return JobStatus(
        job_id=job_id,
        status=job["status"],
        step=job.get("step", ""),
        error=job.get("error"),
    )


@app.get("/jobs/{job_id}/files/{name}")
def job_file(job_id: str, name: str):
    job = _JOBS.get(job_id)
    if not job or not job.get("dir"):
        raise HTTPException(404, "job not found")
    if name not in _ALLOWED_FILES:
        raise HTTPException(400, "unknown file")
    path = Path(job["dir"]) / name
    if not path.exists():
        raise HTTPException(404, "file missing")
    return FileResponse(path)
