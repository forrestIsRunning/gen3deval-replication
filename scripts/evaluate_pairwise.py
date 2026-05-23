#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from common import ROOT, append_jsonl, read_jsonl
from observability import trace_model_eval_call
from vlm_agent import image_content, run_structured
from vlm_types import PairRow, PairwiseJudgeResult


DIMENSIONS = ["appearance", "surface", "text_fidelity"]


def images_for(uid: str, dimension: str, render_dir: Path) -> list[Path]:
    subdir = "normal" if dimension == "surface" else "rgb"
    return sorted((render_dir / uid / subdir).glob("*.png"))[:4]


def run_multimodal_judge(
    pair: PairRow, dimension: str, model: str, base_url: str, api_key: str, render_dir: Path,
) -> PairwiseJudgeResult:
    a = pair["object_a"]
    b = pair["object_b"]
    images = images_for(a["uid"], dimension, render_dir) + images_for(b["uid"], dimension, render_dir)
    if len(images) != 8:
        raise FileNotFoundError(f"Expected 8 images for pair {pair['pair_id']} dimension {dimension}")

    user_content = []
    for image in images:
        user_content.append(image_content(image))

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
    user_content.append(text)
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

    def request_multimodal_judge() -> PairwiseJudgeResult:
        return run_structured(
            model_name=model,
            base_url=base_url,
            api_key=api_key,
            instructions=(
                "你是 Gen3DEval 风格的 3D 资产偏好评测员。"
                "请只输出结构化结果，不要输出 Markdown。"
            ),
            output_type=PairwiseJudgeResult,
            user_content=user_content,
            temperature=0,
            max_tokens=800,
        )

    def summarize(result: PairwiseJudgeResult, elapsed_ms: float) -> dict[str, Any]:
        return {
            "latency_ms": elapsed_ms,
            "http_status": 200,
            "winner": result.get("winner", "tie"),
            "confidence": result.get("confidence", 0),
            "reason_chars": len(str(result.get("reason", ""))),
        }

    parsed = trace_model_eval_call(
        name="gen3d.vlm.pairwise_judge",
        safe_input=safe_input,
        operation=request_multimodal_judge,
        output_summary=summarize,
        metadata=metadata,
        model=model,
    )
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
    model = args.model or os.environ.get("GEN3D_VLM_MODEL", "qwen3-vl-plus")
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
            result = run_multimodal_judge(
                pair, dimension, model, base_url, api_key, Path(args.render_dir),
            )
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
