#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from common import ROOT, read_jsonl, write_jsonl


def image_stats(path: Path) -> dict[str, float]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        gray = rgb.convert("L")
        stat = ImageStat.Stat(gray)
        rgb_stat = ImageStat.Stat(rgb)
        get_pixels = getattr(gray, "get_flattened_data", gray.getdata)
        pixels = list(get_pixels())
        total = max(1, len(pixels))
        nonwhite = sum(1 for value in pixels if value < 245) / total
        nonblack = sum(1 for value in pixels if value > 10) / total
        return {
            "brightness": round(float(stat.mean[0]), 3),
            "contrast": round(float(stat.stddev[0]), 3),
            "nonwhite_ratio": round(float(nonwhite), 5),
            "nonblack_ratio": round(float(nonblack), 5),
            "channel_std_mean": round(float(sum(rgb_stat.stddev) / 3), 3),
        }


def summarize(paths: list[Path]) -> dict[str, Any]:
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


def quality_for_uid(uid: str, render_dir: Path) -> dict[str, Any]:
    base = render_dir / uid
    rgb_paths = sorted((base / "rgb").glob("*.png"))
    normal_paths = sorted((base / "normal").glob("*.png"))
    rgb = summarize(rgb_paths)
    normal = summarize(normal_paths)
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
    return {
        "uid": uid,
        "rgb": rgb,
        "normal": normal,
        "quality_pass": not issues,
        "issues": issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(ROOT / "data" / "processed" / "manifest_render10.jsonl"))
    parser.add_argument("--render-dir", default=str(ROOT / "data" / "renders"))
    parser.add_argument("--output", default=str(ROOT / "data" / "results" / "render_quality.jsonl"))
    args = parser.parse_args()

    rows = read_jsonl(args.manifest)
    render_dir = Path(args.render_dir)
    out = [quality_for_uid(row["uid"], render_dir) for row in rows if row.get("uid")]
    write_jsonl(args.output, out)
    passed = sum(1 for row in out if row["quality_pass"])
    print(f"Render quality pass: {passed}/{len(out)}")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
