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
from PIL import Image, ImageStat
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
JOBS: dict[str, dict] = {}
QUALITY_CACHE: dict[str, tuple[tuple, dict]] = {}

app = FastAPI(title="Gen3DEval Replication POC")
app.mount("/static", StaticFiles(directory=ROOT / "web" / "static"), name="static")
app.mount("/data", StaticFiles(directory=DATA), name="data")


MODELS = [
    "qwen3-vl-plus",
    "qwen3-vl-flash",
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


def image_stats(path: Path) -> dict:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        gray = rgb.convert("L")
        stat = ImageStat.Stat(gray)
        rgb_stat = ImageStat.Stat(rgb)
        get_pixels = getattr(gray, "get_flattened_data", gray.getdata)
        pixels = list(get_pixels())
        total = max(1, len(pixels))
        return {
            "brightness": round(float(stat.mean[0]), 3),
            "contrast": round(float(stat.stddev[0]), 3),
            "nonwhite_ratio": round(sum(1 for value in pixels if value < 245) / total, 5),
            "nonblack_ratio": round(sum(1 for value in pixels if value > 10) / total, 5),
            "channel_std_mean": round(float(sum(rgb_stat.stddev) / 3), 3),
        }


def summarize_render_images(paths: list[Path]) -> dict:
    if not paths:
        return {
            "count": 0,
            "brightness": None,
            "contrast": None,
            "nonwhite_ratio": None,
            "nonblack_ratio": None,
            "channel_std_mean": None,
            "blank_views": 0,
        }
    stats = [image_stats(path) for path in paths]
    blank_views = sum(
        1
        for item in stats
        if item["contrast"] < 3 or item["nonwhite_ratio"] < 0.01 or item["nonblack_ratio"] < 0.01
    )
    keys = ["brightness", "contrast", "nonwhite_ratio", "nonblack_ratio", "channel_std_mean"]
    return {
        "count": len(paths),
        **{key: round(sum(item[key] for item in stats) / len(stats), 5) for key in keys},
        "blank_views": blank_views,
    }


def render_quality(uid: str) -> dict:
    base = DATA / "renders" / uid
    rgb_paths = sorted((base / "rgb").glob("*.png"))
    normal_paths = sorted((base / "normal").glob("*.png"))
    fingerprint = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in rgb_paths + normal_paths)
    cached = QUALITY_CACHE.get(uid)
    if cached and cached[0] == fingerprint:
        return cached[1]
    rgb = summarize_render_images(rgb_paths)
    normal = summarize_render_images(normal_paths)
    issues = []
    if rgb["count"] < 4:
        issues.append(f"RGB views missing: {rgb['count']}/4")
    if normal["count"] < 4:
        issues.append(f"Normal views missing: {normal['count']}/4")
    if rgb["blank_views"]:
        issues.append(f"RGB blank/low-information views: {rgb['blank_views']}")
    if normal["blank_views"]:
        issues.append(f"Normal blank/low-information views: {normal['blank_views']}")
    if normal["channel_std_mean"] is not None and normal["channel_std_mean"] < 5:
        issues.append("Normal color variation is too low")
    result = {"rgb": rgb, "normal": normal, "quality_pass": not issues, "issues": issues}
    QUALITY_CACHE[uid] = (fingerprint, result)
    return result


def geometry_status(uid: str) -> dict:
    rows = [row for row in read_jsonl(DATA / "results" / "geometry_metrics.jsonl") if row.get("uid") == uid]
    if not rows:
        return {"ok": False, "missing": True, "error": "geometry metrics missing"}
    row = rows[0]
    return {
        "ok": bool(row.get("ok")),
        "missing": False,
        "error": row.get("error"),
        "geometry": row.get("geometry"),
    }


def asset_readiness(row: dict) -> dict:
    uid = row.get("uid", "")
    blockers = []
    actions = []
    local_path = row.get("local_path")
    has_model = bool(local_path and Path(local_path).exists())
    geometry = geometry_status(uid)
    render = render_view_counts(uid)
    quality = render_quality(uid) if render["render_complete"] else None

    if not has_model:
        blockers.append("模型文件不存在或 local_path 为空")
        actions.append("download_assets")
    if not geometry["ok"]:
        blockers.append("几何指标缺失或计算失败")
        actions.append("run_geometry")
    if not render["render_complete"]:
        blockers.append(f"多视角渲染不完整：RGB {render['rgb_views']}/4，Normal {render['normal_views']}/4")
        actions.append("render_selected")
    elif quality and not quality["quality_pass"]:
        blockers.append("渲染质量自检未通过")
        actions.append("inspect_or_rerender")

    return {
        "ready_for_vlm": not blockers,
        "status": "ready" if not blockers else "blocked",
        "blockers": blockers,
        "actions": actions,
        "has_model": has_model,
        "geometry": geometry,
        "render": render,
        "render_quality": quality,
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
        readiness = asset_readiness(row)
        items.append(
            {
                "uid": uid,
                "category": row.get("category"),
                "prompt": row.get("prompt"),
                "local_path": row.get("local_path"),
                "has_model": readiness["has_model"],
                "has_render": readiness["render"]["render_complete"],
                "render": readiness["render"],
                "render_quality": readiness["render_quality"],
                "readiness": readiness,
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
        quality = render_quality(uid) if counts["render_complete"] else None
        render_rows.append(
            {
                "uid": uid,
                "rgb_views": counts["rgb_views"],
                "normal_views": counts["normal_views"],
                "render_complete": counts["render_complete"],
                "quality_pass": quality["quality_pass"] if quality else False,
                "quality_issues": "; ".join(quality["issues"]) if quality else "render incomplete",
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
        "readiness": asset_readiness({"uid": uid, "local_path": geometry_rows[0].get("local_path") if geometry_rows else None}),
        "views": views(uid),
    }


@app.get("/api/views/{uid}")
def views(uid: str) -> dict:
    base = DATA / "renders" / uid
    counts = render_view_counts(uid)
    quality = render_quality(uid) if counts["render_complete"] else None
    return {
        "uid": uid,
        **counts,
        "quality": quality,
        "rgb": [f"/data/renders/{uid}/rgb/{path.name}" for path in sorted((base / "rgb").glob("*.png"))],
        "normal": [f"/data/renders/{uid}/normal/{path.name}" for path in sorted((base / "normal").glob("*.png"))],
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
        readiness = asset_readiness(rows[0])
        if not readiness["ready_for_vlm"]:
            return {
                "ok": False,
                "error": "Selected asset is not ready for VLM evaluation.",
                "readiness": readiness,
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
