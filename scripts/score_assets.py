#!/usr/bin/env python3
import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from PIL import Image

from common import ROOT, append_jsonl, image_to_data_url, read_jsonl
from observability import trace_vlm_call, push_to_annotation_queue, log_feedback_scores

DIMENSIONS = [
    "text_fidelity",
    "appearance",
    "surface_quality",
    "geometry_coherence",
    "texture_material",
    "multi_view_consistency",
    "overall",
]

# ── Prompt variants for A/B testing ────────────────────────────────────────
PROMPT_V1 = """你是一个严格的 3D 资产评测员。请基于多视角 RGB 图和法线图评价这个 3D 模型。

目标文本: {prompt}
类别: {category}

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
}}"""

PROMPT_V2 = """你是一位专业的 3D 资产评测专家。请基于多视角渲染图（前 4 张 = RGB，后 4 张 = 法线 Normal）对模型进行逐项评分。

【目标文本】{prompt}
【类别】{category}

请按以下 7 个维度评分（1-10 分），每个维度附简短理由。

评分标准：
1. text_fidelity：模型与目标文本的描述是否一致。检查对象/风格/细节是否准确还原。
2. appearance：渲染图的视觉美感、光照反应、阴影质量。该模型看起来是否"舒服"。
3. surface_quality：基于法线图判断。法线是否连续平滑、有无凹凸不平或破损区域。
4. geometry_coherence：几何结构是否合理、有无穿模、飘浮碎片、比例失真。
5. texture_material：贴图/材质是否细腻、有无模糊拉伸、是否有可信的表面质感。
6. multi_view_consistency：不同视角下是否一致。检查有无 Janus 现象（多头/正反矛盾）、背面崩坏。
7. overall：综合质量分。

请只输出 JSON，不要 Markdown：
{{
  "scores": {{
    "text_fidelity": <1-10>,
    "appearance": <1-10>,
    "surface_quality": <1-10>,
    "geometry_coherence": <1-10>,
    "texture_material": <1-10>,
    "multi_view_consistency": <1-10>,
    "overall": <1-10>
  }},
  "reason": "中文综合评价（100字内）",
  "issues": ["主要问题1", "主要问题2"],
  "strengths": ["亮点1"]
}}"""

PROMPT_VARIANTS: dict[str, str] = {"v1": PROMPT_V1, "v2": PROMPT_V2}


def _handle_low_score_trace(trace_id: str, result_text: str) -> None:
    parsed = extract_json(result_text)
    scores = parsed.get("scores", {})
    overall = scores.get("overall", 0)
    if not overall or float(overall) >= 6:
        return
    push_to_annotation_queue(trace_id, float(overall))
    log_feedback_scores(trace_id, {name: float(scores.get(name, 0)) for name in DIMENSIONS})


def find_images(uid: str, render_dir: Path) -> list[Path]:
    rgb = sorted((render_dir / uid / "rgb").glob("*.png"))[:4]
    normal = sorted((render_dir / uid / "normal").glob("*.png"))[:4]
    return rgb + normal


def extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def prepare_image(path: Path, image_size: int, tmp_dir: Path) -> Path:
    if image_size <= 0:
        return path
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out = tmp_dir / path.name
    with Image.open(path) as image:
        image.thumbnail((image_size, image_size))
        image.convert("RGB").save(out, "JPEG", quality=85)
    return out


def call_vlm(
    row: dict[str, Any],
    images: list[Path],
    model: str,
    base_url: str,
    api_key: str,
    image_size: int,
    timeout: int,
    prompt_variant: str = "v1",
    idx: int = 0,
) -> dict:
    content: list[dict[str, Any]] = []
    tmp_dir = ROOT / "data" / "processed" / "_vlm_tmp" / row["uid"]
    for image in images:
        prepared = prepare_image(image, image_size, tmp_dir)
        content.append({"type": "image_url", "image_url": {"url": image_to_data_url(prepared)}})

    prompt_tpl = PROMPT_VARIANTS.get(prompt_variant, PROMPT_V1)
    prompt = prompt_tpl.format(prompt=row.get("prompt", ""), category=row.get("category", ""))
    content.append({"type": "text", "text": prompt})
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "max_tokens": 1200,
    }
    endpoint = f"{base_url.rstrip('/')}/v1/chat/completions"
    safe_input = {
        "uid": row["uid"],
        "category": row.get("category"),
        "prompt": row.get("prompt", ""),
        "model": model,
        "image_count": len(images),
        "image_size": image_size,
        "dimensions": DIMENSIONS,
        "prompt_variant": prompt_variant,
        "trial": idx,
    }
    metadata = {
        "script": "score_assets.py",
        "endpoint_host": base_url.split("//")[-1].split("/")[0],
        "timeout": timeout,
        "prompt_variant": prompt_variant,
    }

    def request_vlm() -> str:
        resp = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def summarize(text: str, elapsed_ms: float) -> dict[str, Any]:
        parsed = extract_json(text)
        scores = parsed.get("scores", {})
        return {
            "latency_ms": elapsed_ms,
            "http_status": 200,
            **{f"score.{name}": scores.get(name) for name in DIMENSIONS},
            "issue_count": len(parsed.get("issues", [])),
            "strength_count": len(parsed.get("strengths", [])),
        }

    text = trace_vlm_call(
        name=f"gen3d.vlm.score_asset.{prompt_variant}",
        safe_input=safe_input,
        operation=request_vlm,
        output_summary=summarize,
        after_trace=_handle_low_score_trace,
        metadata=metadata,
        model=model,
        image_paths=images,
        glb_path=Path(row.get("local_path", "")) if row.get("local_path") else None,
    )
    return extract_json(text)


def _add_trial_output(
    out_rows: list[dict], row: dict, result: dict, variant: str,
    model: str, uid: str,
) -> None:
    out = {
        "uid": uid,
        "category": row.get("category"),
        "prompt": row.get("prompt"),
        "local_path": row.get("local_path"),
        "model": model,
        "prompt_variant": variant,
        "scored_at": time.time(),
        **result,
    }
    out_rows.append(out)


def run_single(
    rows: list[dict],
    model: str,
    base_url: str,
    api_key: str,
    image_size: int,
    timeout: int,
    render_dir: Path,
    max_images: int,
    output_path: Path,
    overwrite: bool,
    ab_test: bool = False,
) -> None:
    if overwrite and output_path.exists():
        output_path.unlink()

    variants = ["v1", "v2"] if ab_test else ["v2"]
    out_rows: list[dict] = []

    for trial, row in enumerate(rows):
        uid = row["uid"]
        images = find_images(uid, render_dir)[:max_images]
        if len(images) < 4:
            print(f"Skipping {uid}: expected rendered images under {render_dir}/{uid}")
            continue

        for variant in variants:
            try:
                result = call_vlm(
                    row, images, model, base_url, api_key, image_size, timeout,
                    prompt_variant=variant, idx=trial,
                )
                _add_trial_output(out_rows, row, result, variant, model, uid)
                print(f"{uid} [{variant}]: overall={result.get('scores', {}).get('overall', '?')}")
            except Exception as exc:
                print(f"{uid} [{variant}] FAILED: {exc}")

    for out in out_rows:
        append_jsonl(output_path, out)
    print(f"Wrote {len(out_rows)} rows to {output_path}")


def run_experiment(
    rows: list[dict],
    model: str,
    base_url: str,
    api_key: str,
    image_size: int,
    timeout: int,
    render_dir: Path,
    max_images: int,
) -> None:
    """Run A/B test via Opik evaluate(), creating two experiments for comparison."""
    try:
        import opik
        from opik import evaluate, opik_context
        from opik import Attachment
    except ImportError:
        print("opik required for A/B test; run `uv sync --extra observability`")
        return

    project = os.environ.get("OPIK_PROJECT_NAME", "gen3deval-replication")
    client = opik.Opik(project_name=project)
    dataset = client.get_or_create_dataset(
        name="score_assets",
        description="Objaverse-LVIS manifest for A/B prompt comparison",
    )

    for row in rows:
        dataset.insert([
            {
                "uid": row["uid"],
                "category": row.get("category", ""),
                "prompt": row.get("prompt", ""),
                "local_path": row.get("local_path", ""),
            }
        ])

    def make_task(variant: str):
        def task(item: dict) -> dict:
            uid = item["uid"]
            images = find_images(uid, render_dir)[:max_images]
            if len(images) < 4:
                return {"uid": uid, "error": "no images"}
            row = item
            result = call_vlm(
                row, images, model, base_url, api_key, image_size, timeout,
                prompt_variant=variant, idx=0,
            )
            scores = result.get("scores", {})
            return {"uid": uid, **scores}
        return task

    print("[A/B] Running experiment: prompt_v1 ...")
    e1 = evaluate(
        dataset=dataset,
        task=make_task("v1"),
        experiment_name="prompt_v1",
        project_name=project,
        task_threads=4,
        verbose=1,
    )
    print(f"[A/B] v1 done: {e1.results}")

    print("[A/B] Running experiment: prompt_v2 ...")
    e2 = evaluate(
        dataset=dataset,
        task=make_task("v2"),
        experiment_name="prompt_v2",
        project_name=project,
        task_threads=4,
        verbose=1,
    )
    print(f"[A/B] v2 done: {e2.results}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(ROOT / "data" / "processed" / "manifest_120.jsonl"))
    parser.add_argument("--render-dir", default=str(ROOT / "data" / "renders"))
    parser.add_argument("--output", default=str(ROOT / "data" / "results" / "asset_scores.jsonl"))
    parser.add_argument("--model", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-images", type=int, default=8)
    parser.add_argument("--image-size", type=int, default=512)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--ab-test", action="store_true",
                        help="A/B test: run v1+v2 prompts and compare via Opik experiments")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    model = args.model or os.environ.get("GEN3D_VLM_MODEL", "qwen3-vl-235b-a22b-thinking")
    base_url = os.environ.get("LITELLM_BASE_URL", "http://120.48.38.233:4000")
    api_key = os.environ.get("LITELLM_API_KEY", "")
    if not api_key:
        raise SystemExit("Missing LITELLM_API_KEY in .env")

    rows = read_jsonl(args.manifest)
    if args.limit:
        rows = rows[: args.limit]

    render_dir = Path(args.render_dir)
    if args.ab_test:
        run_experiment(rows, model, base_url, api_key, args.image_size, args.timeout, render_dir, args.max_images)
    else:
        run_single(rows, model, base_url, api_key, args.image_size, args.timeout, render_dir, args.max_images, Path(args.output), args.overwrite, ab_test=False)


if __name__ == "__main__":
    main()
