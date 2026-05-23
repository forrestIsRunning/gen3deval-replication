#!/usr/bin/env python3
import argparse

from common import read_jsonl, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--download-processes", type=int, default=4)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    try:
        import objaverse
    except ImportError as exc:
        raise SystemExit("Install dependencies first: uv sync") from exc

    rows = read_jsonl(args.manifest)
    uids = [row["uid"] for row in rows]
    paths = objaverse.load_objects(uids=uids, download_processes=args.download_processes)

    for row in rows:
        row["local_path"] = paths.get(row["uid"])

    missing = [row["uid"] for row in rows if not row.get("local_path")]
    output = args.output or args.manifest
    write_jsonl(output, rows)
    print(f"Updated manifest: {output}")
    print(f"Downloaded/found: {len(rows) - len(missing)} / {len(rows)}")
    if missing:
        print(f"Missing {len(missing)} assets. First few: {missing[:5]}")


if __name__ == "__main__":
    main()
