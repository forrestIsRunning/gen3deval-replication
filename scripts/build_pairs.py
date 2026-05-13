#!/usr/bin/env python3
import argparse
import itertools
import random

from common import ROOT, read_jsonl, write_jsonl


def slim(row: dict) -> dict:
    return {
        "uid": row["uid"],
        "category": row["category"],
        "prompt": row["prompt"],
        "local_path": row.get("local_path"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--max-pairs", type=int, default=180)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=str(ROOT / "data" / "processed" / "pairs.jsonl"))
    args = parser.parse_args()

    rows = read_jsonl(args.manifest)
    by_category: dict[str, list[dict]] = {}
    for row in rows:
        by_category.setdefault(row["category"], []).append(row)

    pairs = []
    for category, items in sorted(by_category.items()):
        for a, b in itertools.combinations(items, 2):
            pairs.append((a, b, category))

    if len(pairs) < args.max_pairs:
        all_pairs = list(itertools.combinations(rows, 2))
        random.Random(args.seed).shuffle(all_pairs)
        seen = {tuple(sorted((a["uid"], b["uid"]))) for a, b, _ in pairs}
        for a, b in all_pairs:
            key = tuple(sorted((a["uid"], b["uid"])))
            if key in seen:
                continue
            pairs.append((a, b, "mixed"))
            seen.add(key)
            if len(pairs) >= args.max_pairs:
                break

    random.Random(args.seed).shuffle(pairs)
    pairs = pairs[: args.max_pairs]
    rows_out = [
        {
            "pair_id": f"{idx:06d}",
            "pair_type": category,
            "object_a": slim(a),
            "object_b": slim(b),
        }
        for idx, (a, b, category) in enumerate(pairs, start=1)
    ]

    write_jsonl(args.output, rows_out)
    print(f"Wrote {len(rows_out)} pairs to {args.output}")


if __name__ == "__main__":
    main()
