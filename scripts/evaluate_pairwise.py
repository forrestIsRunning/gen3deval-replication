#!/usr/bin/env python3
import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from common import ROOT, append_jsonl, image_to_data_url, read_jsonl
from observability import trace_vlm_call


DIMENSIONS = ["appearance", "surface", "text_fidelity"]


def extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def images_for(uid: str, dimension: str, render_dir: Path) -> list[Path]:
    subdir = "normal" if dimension == "surface" else "rgb"
    return sorted((render_dir / uid / subdir).glob("*.png"))[:4]


def judge(pair: dict, dimension: str, model: str, base_url: str, api_key: str, render_dir: Path) -> dict:
    a = pair["object_a"]
    b = pair["object_b"]
    images = images_for(a["uid"], dimension, render_dir) + images_for(b["uid"], dimension, render_dir)
    if len(images) != 8:
        raise FileNotFoundError(f"Expected 8 images for pair {pair['pair_id']} dimension {dimension}")

    content: list[dict[str, Any]] = []
    for image in images:
        content.append({"type": "image_url", "image_url": {"url": image_to_data_url(image)}})

    prompt_line = ""
    if dimension == "text_fidelity":
        prompt_line = f"目标文本 A: {a.get('prompt', '')}\n目标文本 B: {b.get('prompt', '')}"

    text = f"""
你是 Gen3DEval 风格的 3D 资产偏好评测员。
前 4 张图是 Object A，后 4 张图是 Object B。
评测维度: {dimension}
{prompt_line}

请只输出 JSON:
{{
  "winner": "A" 或 "B" 或 "tie",
  "confidence": 0.0到1.0,
  "reason": "中文简短理由"
}}
"""
    content.append({"type": "text", "text": text})
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "max_tokens": 800,
    }
    safe_input = {
        "pair_id": pair["pair_id"],
        "dimension": dimension,
        "model": model,
        "object_a_uid": a["uid"],
        "object_b_uid": b["uid"],
        "object_a_category": a.get("category"),
        "object_b_category": b.get("category"),
        "image_count": len(images),
    }
    metadata = {
        "script": "evaluate_pairwise.py",
        "endpoint_host": base_url.split("//")[-1].split("/")[0],
        "timeout": 180,
    }

    def request_vlm() -> requests.Response:
        response = requests.post(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=180,
        )
        response.raise_for_status()
        return response

    def summarize(response: requests.Response, elapsed_ms: float) -> dict[str, Any]:
        parsed = extract_json(response.json()["choices"][0]["message"]["content"])
        return {
            "latency_ms": elapsed_ms,
            "http_status": response.status_code,
            "winner": parsed.get("winner", "tie"),
            "confidence": parsed.get("confidence", 0),
            "reason_chars": len(str(parsed.get("reason", ""))),
        }

    response = trace_vlm_call(
        name="gen3d.vlm.pairwise_judge",
        safe_input=safe_input,
        operation=request_vlm,
        output_summary=summarize,
        metadata=metadata,
        model=model,
    )
    parsed = extract_json(response.json()["choices"][0]["message"]["content"])
    parsed["winner"] = parsed.get("winner", "tie")
    if parsed["winner"] not in {"A", "B", "tie"}:
        parsed["winner"] = "tie"
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", default=str(ROOT / "data" / "processed" / "pairs.jsonl"))
    parser.add_argument("--render-dir", default=str(ROOT / "data" / "renders"))
    parser.add_argument("--output", default=str(ROOT / "data" / "results" / "comparisons.jsonl"))
    parser.add_argument("--model", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    model = args.model or os.environ.get("GEN3D_VLM_MODEL", "qwen3-vl-235b-a22b-thinking")
    base_url = os.environ.get("LITELLM_BASE_URL", "http://120.48.38.233:4000")
    api_key = os.environ.get("LITELLM_API_KEY", "")
    if not api_key:
        raise SystemExit("Missing LITELLM_API_KEY in .env")

    pairs = read_jsonl(args.pairs)
    if args.limit:
        pairs = pairs[: args.limit]

    output = Path(args.output)
    if output.exists():
        output.unlink()

    for pair in pairs:
        for dimension in DIMENSIONS:
            result = judge(pair, dimension, model, base_url, api_key, Path(args.render_dir))
            row = {
                "pair_id": pair["pair_id"],
                "dimension": dimension,
                "object_a_uid": pair["object_a"]["uid"],
                "object_b_uid": pair["object_b"]["uid"],
                "winner": result.get("winner", "tie"),
                "confidence": result.get("confidence", 0),
                "reason": result.get("reason", ""),
                "model": model,
            }
            append_jsonl(output, row)
            print(f"{pair['pair_id']} {dimension}: {row['winner']}")

    print(f"Wrote comparisons to {output}")


if __name__ == "__main__":
    main()
