#!/usr/bin/env python3
import argparse
import random
from collections import defaultdict

from common import ROOT, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-assets", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    try:
        import objaverse
    except ImportError as exc:
        raise SystemExit("Install dependencies first: uv sync") from exc

    random.seed(args.seed)
    print("Loading Objaverse-LVIS annotations. First run may download metadata.")
    lvis = objaverse.load_lvis_annotations()

    categories = sorted(lvis.keys())
    random.shuffle(categories)

    rows = []
    per_category = defaultdict(int)
    category_index = 0
    while len(rows) < args.num_assets and category_index < len(categories) * 3:
        category = categories[category_index % len(categories)]
        uids = list(lvis[category])
        random.shuffle(uids)
        for uid in uids:
            if per_category[category] >= 4:
                break
            if any(row["uid"] == uid for row in rows):
                continue
            clean_category = category.replace("_", " ")
            rows.append(
                {
                    "uid": uid,
                    "category": clean_category,
                    "prompt": f"A high-quality 3D model of a {clean_category}.",
                    "source": "objaverse-lvis",
                    "local_path": None,
                }
            )
            per_category[category] += 1
            if len(rows) >= args.num_assets:
                break
        category_index += 1

    if len(rows) < args.num_assets:
        raise SystemExit(f"Only sampled {len(rows)} assets; requested {args.num_assets}.")

    output = args.output or ROOT / "data" / "processed" / f"manifest_{args.num_assets}.jsonl"
    write_jsonl(output, rows)
    print(f"Wrote {len(rows)} rows to {output}")


if __name__ == "__main__":
    main()
