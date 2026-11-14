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

def _load_dotenv() -> None:
    import os
    from pathlib import Path

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

def _reload_llm_env() -> None:
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

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/llm")
def llm_status():
    import httpx

    from mapper.llm import LLMConfig

    _reload_llm_env()
    cfg = LLMConfig.from_env()
    ollama_ok = None
    ollama_has_model = None
    if cfg.provider in {"ollama", "local"}:
        try:
            with httpx.Client(timeout=3.0) as client:
                tags = client.get(f"{cfg.base_url}/api/tags").json()
            names = {m.get("name", "") for m in tags.get("models", [])}
            ollama_ok = True
            ollama_has_model = cfg.model in names or any(
                n.startswith(f"{cfg.model}:") or n == cfg.model for n in names
            )
        except Exception:
            ollama_ok = False
            ollama_has_model = False
    return {
        "provider": cfg.provider,
        "model": cfg.model,
        "base_url": cfg.base_url,
        "reasoning_effort": cfg.reasoning_effort,
        "num_ctx": cfg.num_ctx,
        "max_tokens": cfg.max_tokens,
        "timeout_s": cfg.timeout_s,
        "api_key_set": bool(cfg.api_key) if cfg.provider != "ollama" else True,
        "http_proxy": cfg.http_proxy or "",
        "ollama_ok": ollama_ok,
        "ollama_has_model": ollama_has_model,
        "api_key_env": (
            "GEMINI_API_KEY"
            if cfg.provider in {"gemini", "google"}
            else "OPENROUTER_API_KEY"
            if cfg.provider == "openrouter"
            else "(local ollama — no key)"
        ),
    }

@app.post("/map", response_model=MapResponse)
async def map_endpoint(
    reactant: UploadFile = File(...),
    product: UploadFile = File(...),
    charge: int = Form(0),
    multiplicity: int = Form(1),
    use_llm: bool = Form(True),
    model: str | None = Form(None),
):
    job_id = str(uuid.uuid4())
    _JOBS[job_id] = {"status": "running", "step": "parse", "error": None, "dir": None}
    try:
        _reload_llm_env()
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
        import traceback

        err = str(exc) or repr(exc)
        _JOBS[job_id] = {
            "status": "failed",
            "step": "error",
            "error": err,
            "dir": None,
            "traceback": traceback.format_exc(),
        }
        print(f"[map] job {job_id} failed: {err}\n{traceback.format_exc()}", flush=True)
        raise HTTPException(500, err) from exc

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
