from pathlib import Path
import json
import subprocess
import sys
import threading
import time
import uuid

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
JOBS: dict[str, dict] = {}

app = FastAPI(title="Gen3DEval Replication POC")
app.mount("/static", StaticFiles(directory=ROOT / "web" / "static"), name="static")
app.mount("/data", StaticFiles(directory=DATA), name="data")


MODELS = [
    "qwen3-vl-235b-a22b-instruct",
    "qwen3-vl-235b-a22b-thinking",
]


class RunRequest(BaseModel):
    manifest: str
    model: str
    limit: int = 10


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
    items = []
    descriptions = {
        "manifest_120.jsonl": {
            "role": "主数据集",
            "use": "120 个真实 Objaverse-LVIS 资产。用于全量几何指标、全量渲染和正式评测。",
            "recommended": True,
        },
        "manifest_render10.jsonl": {
            "role": "已渲染小批量",
            "use": "10 个真实资产，已经生成 RGB/Normal。当前最适合直接跑 Run VLM。",
            "recommended": True,
        },
        "manifest_smoke3.jsonl": {
            "role": "渲染冒烟测试",
            "use": "3 个真实资产，仅用于验证 Blender 渲染脚本。",
            "recommended": False,
        },
        "pairs_smoke3.jsonl": {
            "role": "成对评测冒烟测试",
            "use": "pairwise/ELO 测试输入，不适合 Run VLM 单资产评分。",
            "recommended": False,
        },
        "sample_manifest.jsonl": {
            "role": "旧 demo",
            "use": "没有真实 local_path，不用于正式评测。",
            "recommended": False,
        },
    }
    for path in files:
        rel = str(path.relative_to(ROOT))
        meta = descriptions.get(path.name, {"role": "其他", "use": "未分类 manifest。", "recommended": False})
        rows = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        items.append({"path": rel, "name": path.name, "rows": rows, **meta})
    return {"manifests": items}


def run_job(job_id: str, cmd: list[str]) -> None:
    JOBS[job_id].update({"status": "running", "started_at": time.time()})
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    JOBS[job_id].update(
        {
            "status": "complete" if proc.returncode == 0 else "failed",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.returncode,
            "finished_at": time.time(),
        }
    )


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    return JOBS.get(job_id, {"status": "missing", "error": f"job not found: {job_id}"})


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
    return {"geometry": [json.loads(line) for line in rows]}


@app.get("/api/render-success")
def render_success() -> dict:
    path = DATA / "results" / "render_success_10.json"
    csv_path = DATA / "results" / "render_success_10.csv"
    summary = {"assets": 0, "complete": 0, "success_rate": 0}
    if path.exists():
        summary = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    if csv_path.exists():
        import csv

        with csv_path.open("r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    return {"summary": summary, "rows": rows}


@app.get("/api/literature")
def literature() -> dict:
    path = ROOT / "paper" / "arxiv_survey" / "papers.json"
    if not path.exists():
        return {"papers": [], "by_direction": {}}
    papers = json.loads(path.read_text(encoding="utf-8"))
    by_direction: dict[str, int] = {}
    for paper in papers:
        direction = paper.get("direction", "unknown")
        by_direction[direction] = by_direction.get(direction, 0) + 1
    return {
        "papers": papers,
        "by_direction": by_direction,
        "download_ok": sum(1 for paper in papers if paper.get("download_ok")),
    }


@app.get("/api/dashboard")
def dashboard() -> dict:
    geometry_path = DATA / "results" / "geometry_metrics.jsonl"
    score_path = DATA / "results" / "asset_scores.jsonl"
    render_path = DATA / "results" / "render_success_10.json"
    literature_path = ROOT / "paper" / "arxiv_survey" / "papers.json"

    geometry_rows = []
    if geometry_path.exists():
        geometry_rows = [
            json.loads(line)
            for line in geometry_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    ok_geometry = [row for row in geometry_rows if row.get("ok")]
    watertight = sum(1 for row in ok_geometry if row.get("geometry", {}).get("is_watertight"))
    degenerate = sum(
        row.get("geometry", {}).get("degenerate_face_count") or 0 for row in ok_geometry
    )

    scores = []
    if score_path.exists():
        scores = [
            json.loads(line)
            for line in score_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    score_sums: dict[str, float] = {}
    score_counts: dict[str, int] = {}
    for row in scores:
        for key, value in (row.get("scores") or {}).items():
            score_sums[key] = score_sums.get(key, 0) + float(value)
            score_counts[key] = score_counts.get(key, 0) + 1
    score_means = {
        key: round(score_sums[key] / score_counts[key], 3) for key in sorted(score_sums)
    }

    render = {"assets": 0, "complete": 0, "success_rate": 0}
    if render_path.exists():
        render = json.loads(render_path.read_text(encoding="utf-8"))

    literature = []
    if literature_path.exists():
        literature = json.loads(literature_path.read_text(encoding="utf-8"))
    by_direction: dict[str, int] = {}
    for paper in literature:
        direction = paper.get("direction", "unknown")
        by_direction[direction] = by_direction.get(direction, 0) + 1

    return {
        "geometry": {
            "assets": len(geometry_rows),
            "ok": len(ok_geometry),
            "watertight": watertight,
            "degenerate_faces": int(degenerate),
        },
        "render": render,
        "scores": {"assets": len(scores), "means": score_means},
        "literature": {
            "papers": len(literature),
            "download_ok": sum(1 for paper in literature if paper.get("download_ok")),
            "by_direction": by_direction,
        },
    }


@app.get("/api/model/{uid}")
def model_file(uid: str):
    candidates = []
    for path in sorted((DATA / "processed").glob("*.jsonl")) + [DATA / "results" / "asset_scores.jsonl"]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("uid") == uid and row.get("local_path"):
                candidates.append(Path(row["local_path"]))
    for path in candidates:
        if path.exists():
            media_type = "model/gltf-binary" if path.suffix.lower() == ".glb" else None
            return FileResponse(path, media_type=media_type)
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
        "--max-images",
        "4",
        "--image-size",
        "384",
        "--timeout",
        "240",
    ]
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {
        "id": job_id,
        "kind": "vlm",
        "status": "queued",
        "stdout": "",
        "stderr": "",
        "returncode": None,
        "created_at": time.time(),
    }
    thread = threading.Thread(target=run_job, args=(job_id, cmd), daemon=True)
    thread.start()
    return {"ok": True, "job_id": job_id, "status": "queued"}


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
