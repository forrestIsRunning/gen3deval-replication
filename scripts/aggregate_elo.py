#!/usr/bin/env python3
import argparse
from collections import defaultdict

import pandas as pd

from common import ROOT, read_jsonl


def expected(ra: float, rb: float) -> float:
    return 1 / (1 + 10 ** ((rb - ra) / 400))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparisons", default=str(ROOT / "data" / "results" / "comparisons.jsonl"))
    parser.add_argument("--output", default=str(ROOT / "data" / "results" / "elo_scores.csv"))
    parser.add_argument("--k", type=float, default=32)
    parser.add_argument("--initial", type=float, default=1000)
    args = parser.parse_args()

    rows = read_jsonl(args.comparisons)
    ratings: dict[str, dict[str, float]] = defaultdict(dict)

    for row in rows:
        dim = row["dimension"]
        a = row["object_a_uid"]
        b = row["object_b_uid"]
        ratings[dim].setdefault(a, args.initial)
        ratings[dim].setdefault(b, args.initial)
        ra = ratings[dim][a]
        rb = ratings[dim][b]
        ea = expected(ra, rb)
        eb = expected(rb, ra)
        winner = row.get("winner")
        if winner == "A":
            sa, sb = 1.0, 0.0
        elif winner == "B":
            sa, sb = 0.0, 1.0
        else:
            sa, sb = 0.5, 0.5
        ratings[dim][a] = ra + args.k * (sa - ea)
        ratings[dim][b] = rb + args.k * (sb - eb)

    out = []
    for dim, items in ratings.items():
        for uid, rating in items.items():
            out.append({"dimension": dim, "uid": uid, "elo": round(rating, 3)})
    df = pd.DataFrame(out).sort_values(["dimension", "elo"], ascending=[True, False])
    df.to_csv(args.output, index=False)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
