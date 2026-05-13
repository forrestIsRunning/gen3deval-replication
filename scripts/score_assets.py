#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import random
import re
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from common import ROOT, append_jsonl, image_to_data_url, read_jsonl


DIMENSIONS = [
    "text_fidelity",
    "appearance",
    "surface_quality",
    "geometry_coherence",
    "texture_material",
    "multi_view_consistency",
    "overall",
]


def find_images(uid: str, render_dir: Path) -> list[Path]:
    rgb = sorted((render_dir / uid / "rgb").glob("*.png"))[:4]
    normal = sorted((render_dir / uid / "normal").glob("*.png"))[:4]
    return rgb + normal


def mock_score(uid: str) -> dict[str, Any]:
    seed = int(hashlib.sha1(uid.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed)
    scores = {dim: round(rng.uniform(5.5, 8.8), 2) for dim in DIMENSIONS}
    scores["overall"] = round(sum(scores[d] for d in DIMENSIONS if d != "overall") / 6, 2)
    return {
        "scores": scores,
        "reason": "Mock score for UI and pipeline smoke testing.",
        "issues": ["mock result; do not use as experiment evidence"],
    }


def extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def call_vlm(row: dict[str, Any], images: list[Path], model: str, base_url: str, api_key: str) -> dict:
    content: list[dict[str, Any]] = []
    for image in images:
        content.append({"type": "image_url", "image_url": {"url": image_to_data_url(image)}})

    prompt = f"""
你是一个严格的 3D 资产评测员。请基于多视角 RGB 图和法线图评价这个 3D 模型。

目标文本: {row.get("prompt", "")}
类别: {row.get("category", "")}

请只输出 JSON，不要输出 Markdown。分数范围 1-10，10 最好。
字段:
{{
  "scores": {{
    "text_fidelity": number,
    "appearance": number,
    "surface_quality": number,
    "geometry_coherence": number,
    "texture_material": number,
    "multi_view_consistency": number,
    "overall": number
  }},
  "reason": "中文简短说明",
  "issues": ["主要问题1", "主要问题2"]
}}
"""
    content.append({"type": "text", "text": prompt})
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "max_tokens": 1200,
    }
    response = requests.post(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=180,
    )
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"]
    return extract_json(text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(ROOT / "data" / "processed" / "manifest_120.jsonl"))
    parser.add_argument("--render-dir", default=str(ROOT / "data" / "renders"))
    parser.add_argument("--output", default=str(ROOT / "data" / "results" / "asset_scores.jsonl"))
    parser.add_argument("--model", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    model = args.model or os.environ.get("GEN3D_VLM_MODEL", "qwen3-vl-235b-a22b-thinking")
    base_url = os.environ.get("LITELLM_BASE_URL", "http://120.48.38.233:4000")
    api_key = os.environ.get("LITELLM_API_KEY", "")

    rows = read_jsonl(args.manifest)
    if args.limit:
        rows = rows[: args.limit]

    output = Path(args.output)
    if output.exists():
        output.unlink()

    for row in rows:
        uid = row["uid"]
        images = find_images(uid, Path(args.render_dir))
        if args.mock:
            result = mock_score(uid)
        else:
            if len(images) < 4:
                print(f"Skipping {uid}: expected rendered images under {args.render_dir}/{uid}")
                continue
            if not api_key:
                raise SystemExit("Missing LITELLM_API_KEY in .env")
            result = call_vlm(row, images, model, base_url, api_key)

        out = {
            "uid": uid,
            "category": row.get("category"),
            "prompt": row.get("prompt"),
            "local_path": row.get("local_path"),
            "model": model if not args.mock else "mock",
            **result,
        }
        append_jsonl(output, out)
        print(f"Scored {uid}")

    print(f"Wrote scores to {output}")


if __name__ == "__main__":
    main()
