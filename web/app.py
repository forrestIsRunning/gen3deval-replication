from pathlib import Path
import subprocess
import sys

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

app = FastAPI(title="Gen3DEval Replication POC")
app.mount("/static", StaticFiles(directory=ROOT / "web" / "static"), name="static")
app.mount("/data", StaticFiles(directory=DATA), name="data")


MODELS = [
    "qwen3-vl-235b-a22b-thinking",
    "qwen3-vl-235b-a22b-instruct",
    "qwen2.5-vl-7b-instruct",
    "kimi-k2.6",
    "glm-5.1",
    "claude-sonnet-4-6",
]


class RunRequest(BaseModel):
    manifest: str
    model: str
    limit: int = 10
    mock: bool = False


class GeometryRequest(BaseModel):
    manifest: str
    limit: int = 50


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(ROOT / "web" / "static" / "index.html")


@app.get("/api/models")
def models() -> dict:
    return {"models": MODELS}


@app.get("/api/manifests")
def manifests() -> dict:
    files = sorted((DATA / "processed").glob("*.jsonl"))
    return {"manifests": [str(path.relative_to(ROOT)) for path in files]}


@app.get("/api/scores")
def scores() -> dict:
    path = DATA / "results" / "asset_scores.jsonl"
    if not path.exists():
        return {"scores": []}
    rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    import json

    return {"scores": [json.loads(line) for line in rows]}


@app.get("/api/geometry")
def geometry() -> dict:
    path = DATA / "results" / "geometry_metrics.jsonl"
    if not path.exists():
        return {"geometry": []}
    rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    import json

    return {"geometry": [json.loads(line) for line in rows]}


@app.get("/api/model/{uid}")
def model_file(uid: str):
    candidates = []
    for path in sorted((DATA / "processed").glob("*.jsonl")) + [DATA / "results" / "asset_scores.jsonl"]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            import json

            row = json.loads(line)
            if row.get("uid") == uid and row.get("local_path"):
                candidates.append(Path(row["local_path"]))
    for path in candidates:
        if path.exists():
            return FileResponse(path)
    return JSONResponse({"error": f"Model file not found for {uid}"}, status_code=404)


@app.post("/api/run")
def run(req: RunRequest) -> dict:
    manifest = ROOT / req.manifest
    if not manifest.exists():
        return {"ok": False, "error": f"Manifest not found: {req.manifest}"}
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "score_assets.py"),
        "--manifest",
        str(manifest),
        "--model",
        req.model,
        "--limit",
        str(req.limit),
    ]
    if req.mock:
        cmd.append("--mock")
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    ok = proc.returncode == 0
    return {"ok": ok, "stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode}


@app.post("/api/geometry/run")
def run_geometry(req: GeometryRequest) -> dict:
    manifest = ROOT / req.manifest
    if not manifest.exists():
        return {"ok": False, "error": f"Manifest not found: {req.manifest}"}
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "compute_geometry_metrics.py"),
        "--manifest",
        str(manifest),
        "--limit",
        str(req.limit),
    ]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    ok = proc.returncode == 0
    return {"ok": ok, "stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode}
