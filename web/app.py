from pathlib import Path
import json
import shutil
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
    uid: str | None = None
    limit: int | None = None


class GeometryRequest(BaseModel):
    manifest: str
    limit: int | None = None


class RenderRequest(BaseModel):
    manifest: str
    uid: str | None = None
    views: int = 4
    resolution: int = 768


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
        "manifest_render1.jsonl": {
            "role": "单资产调试",
            "use": "1 个真实资产，用于快速验证渲染或 VLM 调用链路。正式观察优先用 manifest_render10 或 manifest_120。",
            "recommended": False,
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


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def latest_scores(rows: list[dict]) -> list[dict]:
    latest: dict[tuple[str, str], dict] = {}
    for index, row in enumerate(rows):
        key = (row.get("uid", ""), row.get("model", ""))
        previous = latest.get(key)
        row_order = row.get("scored_at") or index
        previous_order = (previous or {}).get("scored_at") or -1
        if previous is None or row_order >= previous_order:
            latest[key] = row
    return list(latest.values())


def manifest_rows(manifest: str) -> list[dict]:
    path = ROOT / manifest
    if not path.exists():
        return []
    return read_jsonl(path)


def render_view_counts(uid: str) -> dict:
    base = DATA / "renders" / uid
    rgb = sorted((base / "rgb").glob("*.png"))
    normal = sorted((base / "normal").glob("*.png"))
    return {
        "rgb_views": len(rgb),
        "normal_views": len(normal),
        "render_complete": len(rgb) >= 4 and len(normal) >= 4,
    }


@app.get("/api/assets")
def assets(manifest: str = "data/processed/manifest_render10.jsonl") -> dict:
    rows = manifest_rows(manifest)
    scores = latest_scores(read_jsonl(DATA / "results" / "asset_scores.jsonl"))
    scored_by_uid: dict[str, list[str]] = {}
    for row in scores:
        scored_by_uid.setdefault(row.get("uid"), []).append(row.get("model"))
    items = []
    for row in rows:
        uid = row.get("uid")
        if not uid:
            continue
        render = render_view_counts(uid)
        items.append(
            {
                "uid": uid,
                "category": row.get("category"),
                "prompt": row.get("prompt"),
                "local_path": row.get("local_path"),
                "has_model": bool(row.get("local_path") and Path(row["local_path"]).exists()),
                "has_render": render["render_complete"],
                "render": render,
                "scored_models": sorted(m for m in scored_by_uid.get(uid, []) if m),
            }
        )
    return {"assets": items}


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
    return {"scores": latest_scores(read_jsonl(DATA / "results" / "asset_scores.jsonl"))}


@app.get("/api/geometry")
def geometry() -> dict:
    return {"geometry": read_jsonl(DATA / "results" / "geometry_metrics.jsonl")}


@app.get("/api/evaluation")
def evaluation(
    manifest: str = "data/processed/manifest_render10.jsonl",
    model: str | None = None,
) -> dict:
    rows = manifest_rows(manifest)
    uids = {row.get("uid") for row in rows}
    geometry_rows = [row for row in read_jsonl(DATA / "results" / "geometry_metrics.jsonl") if row.get("uid") in uids]
    score_rows = [row for row in latest_scores(read_jsonl(DATA / "results" / "asset_scores.jsonl")) if row.get("uid") in uids]
    if model:
        score_rows = [row for row in score_rows if row.get("model") == model]

    render_rows = []
    for row in rows:
        uid = row.get("uid")
        if not uid:
            continue
        counts = render_view_counts(uid)
        render_rows.append(
            {
                "uid": uid,
                "rgb_views": counts["rgb_views"],
                "normal_views": counts["normal_views"],
                "render_complete": counts["render_complete"],
            }
        )
    render_complete = sum(1 for row in render_rows if str(row.get("render_complete")).lower() == "true")

    score_sums: dict[str, float] = {}
    score_counts: dict[str, int] = {}
    for row in score_rows:
        for key, value in (row.get("scores") or {}).items():
            score_sums[key] = score_sums.get(key, 0) + float(value)
            score_counts[key] = score_counts.get(key, 0) + 1
    score_means = {key: round(score_sums[key] / score_counts[key], 3) for key in score_sums}

    return {
        "manifest": manifest,
        "model": model,
        "assets": rows,
        "geometry": geometry_rows,
        "scores": score_rows,
        "score_means": score_means,
        "render": {
            "rows": render_rows,
            "assets": len(render_rows),
            "complete": render_complete,
            "success_rate": render_complete / len(render_rows) if render_rows else 0,
        },
    }


@app.get("/api/asset-evaluation/{uid}")
def asset_evaluation(uid: str, model: str | None = None) -> dict:
    geometry_rows = [row for row in read_jsonl(DATA / "results" / "geometry_metrics.jsonl") if row.get("uid") == uid]
    score_rows = [row for row in latest_scores(read_jsonl(DATA / "results" / "asset_scores.jsonl")) if row.get("uid") == uid]
    if model:
        score_rows = [row for row in score_rows if row.get("model") == model]
    return {
        "uid": uid,
        "geometry": geometry_rows[0] if geometry_rows else None,
        "scores": score_rows,
        "views": views(uid),
    }


@app.get("/api/views/{uid}")
def views(uid: str) -> dict:
    base = DATA / "renders" / uid
    counts = render_view_counts(uid)
    return {
        "uid": uid,
        **counts,
        "rgb": [f"/data/renders/{uid}/rgb/{path.name}" for path in sorted((base / "rgb").glob("*.png"))],
        "normal": [f"/data/renders/{uid}/normal/{path.name}" for path in sorted((base / "normal").glob("*.png"))],
    }


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


@app.get("/api/literature-ideas")
def literature_ideas() -> dict:
    ideas = [
        {
            "paper": "Gen3DEval",
            "direction": "text_to_3d_eval",
            "idea": "多视角 RGB/Normal + VLM 按 appearance/surface/text fidelity 评测。",
            "implemented": "score_assets.py 的多维 VLM rubric；evaluate_pairwise.py + ELO 保留论文式路径。",
        },
        {
            "paper": "T3Bench",
            "direction": "text_to_3d_eval",
            "idea": "把视觉质量和文本对齐分开，不用一个总分掩盖问题。",
            "implemented": "前端分开展示 text_fidelity、appearance、surface_quality、geometry_coherence。",
        },
        {
            "paper": "GPT-4V Eval3D",
            "direction": "text_to_3d_eval",
            "idea": "使用 VLM 做人类偏好式判断，并保留自然语言 reason。",
            "implemented": "asset_scores.jsonl 保存 scores、reason、issues 和 model。",
        },
        {
            "paper": "Eval3D",
            "direction": "text_to_3d_eval",
            "idea": "细粒度可解释评测，组合多个 probes，而不是只依赖单一黑盒分数。",
            "implemented": "几何指标、渲染成功率、VLM 分数、论文覆盖分区展示。",
        },
        {
            "paper": "PointFlow / point cloud generation metrics",
            "direction": "point_cloud_generation_metrics",
            "idea": "MMD/Coverage/1-NNA/JSD 适合模型级生成分布评估。",
            "implemented": "文档中列为 Research Eval，当前 POC 先实现单资产几何门禁。",
        },
        {
            "paper": "Point-E",
            "direction": "point_cloud_generation_metrics",
            "idea": "CLIP R-Precision/P-FID/P-IS 等渲染或点云代理指标可作为低成本筛查。",
            "implemented": "当前保留接口设计，后续接 CLIP/OpenShape；前端已有对应指标蓝图。",
        },
        {
            "paper": "Textured Mesh Quality Assessment",
            "direction": "mesh_texture_quality",
            "idea": "纹理 mesh 的主观质量需要单独评估，不能只看几何。",
            "implemented": "VLM rubric 增加 texture_material，几何表不替代材质评分。",
        },
        {
            "paper": "GET3D / Text2Tex / TEXTure",
            "direction": "mesh_texture_quality",
            "idea": "几何和纹理是两个不同失败面，需要拆开看。",
            "implemented": "前端同时展示 geometry table 和 VLM texture/material score。",
        },
        {
            "paper": "ULIP / OpenShape",
            "direction": "multimodal_3d_alignment",
            "idea": "3D-text/image embedding 可做语义对齐和检索评测。",
            "implemented": "文档纳入下一阶段指标；当前用 VLM text_fidelity 先覆盖语义还原。",
        },
        {
            "paper": "TripoSR",
            "direction": "text_to_3d_eval",
            "idea": "单图到 3D 场景需要 image_fidelity，而不只是 text_fidelity。",
            "implemented": "Tripo3D 蓝图和 VLM rubric 预留 image_fidelity 维度。",
        },
    ]
    return {
        "ideas": ideas,
        "coverage": {
            "text_to_3d_eval": ["Gen3DEval", "T3Bench", "GPT-4V Eval3D", "Eval3D", "TripoSR"],
            "point_cloud_generation_metrics": ["PointFlow", "Point-E", "Shap-E", "Occupancy Networks"],
            "mesh_texture_quality": ["Textured Mesh Quality Assessment", "GET3D", "Text2Tex", "TEXTure", "Fantasia3D"],
            "multimodal_3d_alignment": ["ULIP", "OpenShape", "PointCLIP", "Uni3D", "ShapeLLM"],
        },
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
        scores = latest_scores([
            json.loads(line)
            for line in score_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ])
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
    run_manifest = manifest
    if req.uid:
        rows = [row for row in manifest_rows(req.manifest) if row.get("uid") == req.uid]
        if not rows:
            return {"ok": False, "error": f"UID not found in manifest: {req.uid}"}
        counts = render_view_counts(req.uid)
        if not counts["render_complete"]:
            return {
                "ok": False,
                "error": (
                    "Selected asset is not ready for VLM evaluation: "
                    f"RGB views={counts['rgb_views']}, Normal views={counts['normal_views']}. "
                    "Render it first."
                ),
                "render": counts,
            }
        run_manifest = DATA / "processed" / "_vlm_tmp" / "manifests" / f"_run_{req.uid}.jsonl"
        run_manifest.parent.mkdir(parents=True, exist_ok=True)
        run_manifest.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "score_assets.py"),
        "--manifest",
        str(run_manifest),
        "--model",
        req.model,
        "--max-images",
        "4",
        "--image-size",
        "384",
        "--timeout",
        "240",
    ]
    if not req.uid and req.limit:
        cmd.extend(["--limit", str(req.limit)])
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


@app.post("/api/render/run")
def run_render(req: RenderRequest) -> dict:
    manifest = ROOT / req.manifest
    if not manifest.exists():
        return {"ok": False, "error": f"Manifest not found: {req.manifest}"}
    if not shutil.which("blender"):
        return {"ok": False, "error": "Blender executable not found. Install Blender before rendering."}

    run_manifest = manifest
    if req.uid:
        rows = [row for row in manifest_rows(req.manifest) if row.get("uid") == req.uid]
        if not rows:
            return {"ok": False, "error": f"UID not found in manifest: {req.uid}"}
        run_manifest = DATA / "processed" / "_vlm_tmp" / "manifests" / f"_render_{req.uid}.jsonl"
        run_manifest.parent.mkdir(parents=True, exist_ok=True)
        run_manifest.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")

    cmd = [
        "blender",
        "-b",
        "--python",
        str(ROOT / "scripts" / "render_blender.py"),
        "--",
        "--manifest",
        str(run_manifest),
        "--output-dir",
        str(DATA / "renders"),
        "--views",
        str(req.views),
        "--resolution",
        str(req.resolution),
    ]
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {
        "id": job_id,
        "kind": "render",
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
    ]
    if req.limit:
        cmd.extend(["--limit", str(req.limit)])
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    ok = proc.returncode == 0
    return {"ok": ok, "stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode}
