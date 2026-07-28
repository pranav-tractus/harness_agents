"""Sweep a folder of product spec PDFs into Mongo + the vector index.

Usage:
    python -m scripts.ingest_specs prod_specs/ [--model openai:5.5] [--dry-run] [--force]
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

from apps.api.services import spec_ingest_service


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="Folder containing *.pdf spec sheets")
    parser.add_argument("--model", default="openai:5.5", help="model_key for extraction")
    parser.add_argument("--dry-run", action="store_true",
                        help="extract and print, write nothing to Mongo/vectors")
    parser.add_argument("--force", action="store_true", help="re-ingest unchanged PDFs")
    args = parser.parse_args(argv)

    reports = spec_ingest_service.ingest_folder(
        args.folder, model_key=args.model, dry_run=args.dry_run, force=args.force
    )

    widths = (36, 22, 28, 8)
    print(f"{'file':<{widths[0]}} {'code':<{widths[1]}} {'name':<{widths[2]}} status")
    for r in reports:
        line = (f"{r.file:<{widths[0]}} {r.code:<{widths[1]}} "
                f"{r.name:<{widths[2]}} {r.status}")
        if r.error:
            line += f"  ({r.error})"
        print(line)
    counts = Counter(r.status for r in reports)
    print("\n" + ", ".join(f"{n} {status}" for status, n in sorted(counts.items())))
    return 1 if counts.get("failed") else 0


if __name__ == "__main__":
    sys.exit(main())
