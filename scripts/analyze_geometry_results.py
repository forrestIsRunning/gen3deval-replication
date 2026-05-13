#!/usr/bin/env python3
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from common import ROOT


def main() -> None:
    path = ROOT / "data" / "results" / "geometry_metrics.jsonl"
    out_dir = ROOT / "data" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        flat = {
            "uid": row["uid"],
            "category": row.get("category"),
            "ok": row.get("ok", False),
            "error": row.get("error"),
        }
        flat.update(row.get("geometry") or {})
        rows.append(flat)

    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "geometry_metrics.csv", index=False)

    numeric = [
        "vertex_count",
        "face_count",
        "aspect_ratio",
        "surface_area",
        "volume",
        "degenerate_face_count",
    ]
    summary = df[numeric].describe(percentiles=[0.25, 0.5, 0.75, 0.9, 0.95]).T
    summary.to_csv(out_dir / "geometry_summary.csv")

    report = [
        "# 几何指标实验报告",
        "",
        f"- 样本数: {len(df)}",
        f"- 成功计算: {int(df['ok'].sum())}",
        f"- watertight 数量: {int(df['is_watertight'].sum()) if 'is_watertight' in df else 0}",
        "",
        "## 数值摘要",
        "",
        summary.to_markdown(),
        "",
        "## 解释",
        "",
        "- `face_count` / `vertex_count` 衡量复杂度和推理/渲染成本。",
        "- `aspect_ratio` 可用于发现尺度异常或极端扁长模型。",
        "- `is_watertight` 和 `volume` 对 CAD、打印、仿真更重要；对普通展示资产不是硬性要求。",
        "- `degenerate_face_count` 是 mesh 清洁度门禁，适合自动化质量检查。",
    ]
    (out_dir / "geometry_report.md").write_text("\n".join(report), encoding="utf-8")

    for col in ["face_count", "vertex_count", "aspect_ratio", "surface_area"]:
        clean = df[col].dropna()
        if clean.empty:
            continue
        plt.figure(figsize=(8, 4))
        clean.clip(upper=clean.quantile(0.98)).hist(bins=30, color="#2563eb")
        plt.title(f"{col} distribution")
        plt.xlabel(col)
        plt.ylabel("count")
        plt.tight_layout()
        plt.savefig(out_dir / f"geometry_{col}.png", dpi=180)
        plt.close()

    print(f"Wrote {out_dir / 'geometry_report.md'}")
    print(f"Wrote {out_dir / 'geometry_summary.csv'}")
    print(f"Wrote {out_dir / 'geometry_metrics.csv'}")


if __name__ == "__main__":
    main()
