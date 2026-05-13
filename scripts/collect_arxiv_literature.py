#!/usr/bin/env python3
import argparse
import csv
import json
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from common import ROOT


DIRECTIONS = {
    "text_to_3d_eval": {
        "query": 'all:"text-to-3D" AND (all:evaluation OR all:benchmark OR all:metric)',
        "meaning": "Text/Image-to-3D 端到端评测、prompt benchmark、VLM judge。",
    },
    "point_cloud_generation_metrics": {
        "query": 'all:"point cloud generation" AND (all:evaluation OR all:Chamfer OR all:coverage OR all:MMD)',
        "meaning": "有参考分布或点云输出时的 CD/EMD/MMD/Coverage/1-NNA/JSD。",
    },
    "mesh_texture_quality": {
        "query": 'all:"mesh quality" OR all:"textured mesh quality" OR all:"3D mesh" AND all:quality',
        "meaning": "mesh 清洁度、拓扑、法线、纹理质量、可用性门禁。",
    },
    "multimodal_3d_alignment": {
        "query": 'all:"3D" AND (all:"CLIP" OR all:"text-image-3D" OR all:"language") AND (all:retrieval OR all:alignment)',
        "meaning": "3D-text/image embedding、zero-shot 分类、text-3D retrieval。",
    },
}

FALLBACK_PAPERS = {
    "text_to_3d_eval": [
        ("2504.08125", "Gen3DEval: Using vLLMs for Automatic Evaluation of Generated 3D Objects"),
        ("2310.02977", "T3Bench: Benchmarking Current Progress in Text-to-3D Generation"),
        ("2401.04092", "GPT-4V as a Human-Aligned Evaluator for Text-to-3D Generation"),
        ("2504.18509", "Eval3D: Interpretable and Fine-grained Evaluation for 3D Generation"),
        ("2212.08751", "Point-E: A System for Generating 3D Point Clouds from Complex Prompts"),
        ("2209.14988", "DreamFusion: Text-to-3D using 2D Diffusion"),
        ("2211.10440", "Magic3D: High-Resolution Text-to-3D Content Creation"),
        ("2303.11328", "Fantasia3D: Disentangling Geometry and Appearance for High-quality Text-to-3D Content Creation"),
        ("2306.17843", "ProlificDreamer: High-Fidelity and Diverse Text-to-3D Generation with Variational Score Distillation"),
        ("2403.02151", "TripoSR: Fast 3D Object Reconstruction from a Single Image"),
    ],
    "point_cloud_generation_metrics": [
        ("1707.02392", "Learning Representations and Generative Models for 3D Point Clouds"),
        ("1810.05795", "PointFlow: 3D Point Cloud Generation with Continuous Normalizing Flows"),
        ("2106.05304", "Diffusion Probabilistic Models for 3D Point Cloud Generation"),
        ("2103.01458", "ShapeGF: Learning Generative Shape Priors for 3D Shape Completion and Reconstruction"),
        ("2203.01424", "LION: Latent Point Diffusion Models for 3D Shape Generation"),
        ("2212.08751", "Point-E: A System for Generating 3D Point Clouds from Complex Prompts"),
        ("2305.16213", "Shap-E: Generating Conditional 3D Implicit Functions"),
        ("1906.12320", "Occupancy Networks: Learning 3D Reconstruction in Function Space"),
        ("2002.08397", "Diverse and Plausible 3D Shape Completions from Ambiguous Depth Images"),
        ("2104.02602", "Score-Based Point Cloud Denoising"),
    ],
    "mesh_texture_quality": [
        ("2202.02397", "Textured Mesh Quality Assessment"),
        ("2302.01560", "MeshDiffusion: Score-based Generative 3D Mesh Modeling"),
        ("2206.07695", "GET3D: A Generative Model of High Quality 3D Textured Shapes"),
        ("2303.13508", "Text2Tex: Text-driven Texture Synthesis via Diffusion Models"),
        ("2308.09787", "TEXTure: Text-Guided Texturing of 3D Shapes"),
        ("2303.11328", "Fantasia3D: Disentangling Geometry and Appearance for High-quality Text-to-3D Content Creation"),
        ("2209.14988", "DreamFusion: Text-to-3D using 2D Diffusion"),
        ("2211.10440", "Magic3D: High-Resolution Text-to-3D Content Creation"),
        ("2403.02151", "TripoSR: Fast 3D Object Reconstruction from a Single Image"),
        ("2306.17843", "ProlificDreamer: High-Fidelity and Diverse Text-to-3D Generation with Variational Score Distillation"),
    ],
    "multimodal_3d_alignment": [
        ("2211.12524", "ULIP: Learning a Unified Representation of Language, Images, and Point Clouds for 3D Understanding"),
        ("2305.10764", "OpenShape: Scaling Up 3D Shape Representation Towards Open-World Understanding"),
        ("2212.08751", "Point-E: A System for Generating 3D Point Clouds from Complex Prompts"),
        ("2305.16213", "Shap-E: Generating Conditional 3D Implicit Functions"),
        ("2307.04780", "CLIP2Point: Transfer CLIP to Point Cloud Classification with Image-Depth Pre-training"),
        ("2203.13591", "PointCLIP: Point Cloud Understanding by CLIP"),
        ("2309.00615", "Uni3D: Exploring Unified 3D Representation at Scale"),
        ("2401.07577", "Point-Bind: Multi-modality 3D Understanding"),
        ("2402.17766", "ULIP-2: Towards Scalable Multimodal Pre-training for 3D Understanding"),
        ("2401.02955", "ShapeLLM: Universal 3D Object Understanding for Embodied Interaction"),
    ],
}


def arxiv_search(query: str, max_results: int) -> list[dict]:
    encoded = urllib.parse.urlencode(
        {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    url = f"https://export.arxiv.org/api/query?{encoded}"
    response = requests.get(url, timeout=60)
    if response.status_code == 429:
        raise RuntimeError("arXiv API rate limited")
    response.raise_for_status()
    root = ET.fromstring(response.text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    rows = []
    for entry in root.findall("atom:entry", ns):
        arxiv_url = entry.findtext("atom:id", default="", namespaces=ns)
        arxiv_id = arxiv_url.rstrip("/").split("/")[-1]
        title = " ".join(entry.findtext("atom:title", default="", namespaces=ns).split())
        summary = " ".join(entry.findtext("atom:summary", default="", namespaces=ns).split())
        published = entry.findtext("atom:published", default="", namespaces=ns)
        authors = [
            a.findtext("atom:name", default="", namespaces=ns)
            for a in entry.findall("atom:author", ns)
        ]
        pdf_url = ""
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href", "")
        rows.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "authors": "; ".join(authors[:8]),
                "published": published[:10],
                "abs_url": arxiv_url,
                "pdf_url": pdf_url or arxiv_url.replace("/abs/", "/pdf/"),
                "summary": summary,
            }
        )
    return rows


def fallback_rows(direction: str, max_results: int) -> list[dict]:
    rows = []
    for arxiv_id, title in FALLBACK_PAPERS[direction][:max_results]:
        abs_url = f"https://arxiv.org/abs/{arxiv_id}"
        rows.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "authors": "",
                "published": "",
                "abs_url": abs_url,
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
                "summary": "",
            }
        )
    return rows


def download_pdf(row: dict, out_dir: Path) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_id = row["arxiv_id"].replace("/", "_")
    path = out_dir / f"{safe_id}.pdf"
    if path.exists() and path.stat().st_size > 10_000:
        return str(path)
    response = requests.get(row["pdf_url"], timeout=180)
    response.raise_for_status()
    path.write_bytes(response.content)
    return str(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-direction", type=int, default=10)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--output-dir", default=str(ROOT / "paper" / "arxiv_survey"))
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for direction, meta in DIRECTIONS.items():
        print(f"Searching {direction}: {meta['query']}")
        try:
            rows = arxiv_search(meta["query"], args.per_direction)
        except Exception as exc:
            print(f"Search failed for {direction}: {exc}. Using fallback seed list.")
            rows = fallback_rows(direction, args.per_direction)
        for row in rows:
            row["direction"] = direction
            row["direction_meaning"] = meta["meaning"]
            if args.download:
                try:
                    row["local_pdf"] = download_pdf(row, out_dir / direction)
                    row["download_ok"] = True
                except Exception as exc:
                    row["local_pdf"] = ""
                    row["download_ok"] = False
                    row["download_error"] = str(exc)
                time.sleep(0.5)
        all_rows.extend(rows)
        time.sleep(1)

    json_path = out_dir / "papers.json"
    csv_path = out_dir / "papers.csv"
    json_path.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=sorted({k for r in all_rows for k in r}))
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Wrote {len(all_rows)} papers to {json_path}")
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
