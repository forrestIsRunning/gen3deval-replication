#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from common import ROOT, write_jsonl, read_jsonl


def metrics_for_mesh(path: str, deep: bool = False) -> dict[str, Any]:
    import numpy as np
    import trimesh

    loaded = trimesh.load(path, force="scene")
    if isinstance(loaded, trimesh.Scene):
        meshes = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not meshes:
            raise ValueError("No mesh geometry found")
        mesh = trimesh.util.concatenate(meshes)
    else:
        mesh = loaded

    bbox = mesh.bounding_box.extents
    bbox = np.asarray(bbox, dtype=float)
    longest = float(np.max(bbox)) if bbox.size else 0.0
    shortest = float(np.min(bbox)) if bbox.size else 0.0
    aspect_ratio = longest / shortest if shortest > 1e-9 else None

    degenerate_faces = int(np.sum(mesh.area_faces <= 1e-12)) if len(mesh.faces) else 0
    component_count = None
    if deep:
        component_count = int(len(mesh.split(only_watertight=False)))

    return {
        "vertex_count": int(len(mesh.vertices)),
        "face_count": int(len(mesh.faces)),
        "component_count": component_count,
        "bbox_x": round(float(bbox[0]), 6) if len(bbox) == 3 else None,
        "bbox_y": round(float(bbox[1]), 6) if len(bbox) == 3 else None,
        "bbox_z": round(float(bbox[2]), 6) if len(bbox) == 3 else None,
        "aspect_ratio": round(aspect_ratio, 6) if aspect_ratio else None,
        "surface_area": round(float(mesh.area), 6),
        "volume": round(float(mesh.volume), 6) if mesh.is_watertight else None,
        "is_watertight": bool(mesh.is_watertight),
        "is_winding_consistent": bool(mesh.is_winding_consistent),
        "euler_number": int(mesh.euler_number),
        "degenerate_face_count": degenerate_faces,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(ROOT / "data" / "processed" / "manifest_120.jsonl"))
    parser.add_argument("--output", default=str(ROOT / "data" / "results" / "geometry_metrics.jsonl"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--worker-path", default=None)
    parser.add_argument("--deep", action="store_true")
    args = parser.parse_args()

    if args.worker_path:
        print(json.dumps(metrics_for_mesh(args.worker_path, deep=args.deep), ensure_ascii=False))
        return

    rows = read_jsonl(args.manifest)
    if args.limit:
        rows = rows[: args.limit]

    out = []
    for row in rows:
        local_path = row.get("local_path")
        result = {
            "uid": row["uid"],
            "category": row.get("category"),
            "prompt": row.get("prompt"),
            "local_path": local_path,
        }
        try:
            if not local_path or not Path(local_path).exists():
                raise FileNotFoundError("local_path missing or not found")
            worker_cmd = [sys.executable, __file__, "--worker-path", local_path]
            if args.deep:
                worker_cmd.append("--deep")
            proc = subprocess.run(
                worker_cmd,
                text=True,
                capture_output=True,
                timeout=args.timeout,
                check=False,
            )
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "worker failed")
            result["geometry"] = json.loads(proc.stdout)
            result["ok"] = True
        except subprocess.TimeoutExpired:
            result["ok"] = False
            result["error"] = f"timed out after {args.timeout}s"
        except Exception as exc:
            result["ok"] = False
            result["error"] = str(exc)
        out.append(result)
        print(f"{row['uid']}: {'ok' if result['ok'] else result['error']}")

    write_jsonl(args.output, out)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
