#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import pandas as pd

from common import ROOT, read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(ROOT / "data" / "processed" / "manifest_120.jsonl"))
    parser.add_argument("--render-dir", default=str(ROOT / "data" / "renders"))
    parser.add_argument("--output", default=str(ROOT / "data" / "results" / "render_success.csv"))
    parser.add_argument("--expected-views", type=int, default=4)
    args = parser.parse_args()

    rows = []
    render_dir = Path(args.render_dir)
    for item in read_jsonl(args.manifest):
        uid = item["uid"]
        rgb = sorted((render_dir / uid / "rgb").glob("*.png"))
        normal = sorted((render_dir / uid / "normal").glob("*.png"))
        rows.append(
            {
                "uid": uid,
                "category": item.get("category"),
                "rgb_views": len(rgb),
                "normal_views": len(normal),
                "render_complete": len(rgb) >= args.expected_views
                and len(normal) >= args.expected_views,
            }
        )

    df = pd.DataFrame(rows)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    report = {
        "assets": int(len(df)),
        "complete": int(df["render_complete"].sum()),
        "success_rate": float(df["render_complete"].mean()) if len(df) else 0,
    }
    Path(args.output).with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
