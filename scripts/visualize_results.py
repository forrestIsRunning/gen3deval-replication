#!/usr/bin/env python3
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from common import ROOT, read_jsonl


def plot_asset_scores(path: Path, out_dir: Path) -> None:
    if not path.exists():
        return
    rows = read_jsonl(path)
    flat = []
    for row in rows:
        for dim, score in row.get("scores", {}).items():
            flat.append({"uid": row["uid"], "dimension": dim, "score": score})
    if not flat:
        return
    df = pd.DataFrame(flat)
    mean = df.groupby("dimension")["score"].mean().sort_values()
    plt.figure(figsize=(10, 5))
    mean.plot(kind="barh", color="#2563eb")
    plt.xlabel("Average score")
    plt.title("Average VLM Asset Scores")
    plt.tight_layout()
    plt.savefig(out_dir / "asset_score_means.png", dpi=180)
    plt.close()


def plot_elo(path: Path, out_dir: Path) -> None:
    if not path.exists():
        return
    df = pd.read_csv(path)
    if df.empty:
        return
    for dim, group in df.groupby("dimension"):
        top = group.sort_values("elo", ascending=False).head(15)
        plt.figure(figsize=(10, 6))
        plt.barh(top["uid"], top["elo"], color="#16a34a")
        plt.gca().invert_yaxis()
        plt.xlabel("ELO")
        plt.title(f"Top ELO: {dim}")
        plt.tight_layout()
        plt.savefig(out_dir / f"elo_{dim}.png", dpi=180)
        plt.close()


def main() -> None:
    out_dir = ROOT / "data" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_asset_scores(out_dir / "asset_scores.jsonl", out_dir)
    plot_elo(out_dir / "elo_scores.csv", out_dir)
    print(f"Wrote visualizations to {out_dir}")


if __name__ == "__main__":
    main()
