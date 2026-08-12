"""Assign catalog products to organizations.

Usage:
    python -m scripts.assign_orgs --dry-run
    python -m scripts.assign_orgs
    python -m scripts.assign_orgs --all --rebuild-vectors --model openai:5.5

Rules place most products for free; anything a rule misses goes to the LLM,
and anything the LLM cannot place lands in the catch-all organization.
"""
import argparse
import sys
from collections import Counter

from apps.api.db import mongo
from apps.api.services import org_classifier_service, org_service, product_embedding_service
from core.utils import DEFAULT_MODEL_KEY


def assign(*, only_unassigned: bool = True, dry_run: bool = False,
           rebuild: bool = False, model_key: str = DEFAULT_MODEL_KEY,
           llm=None, build_fn=None) -> list[tuple[str, str, str]]:
    org_service.seed_roster()
    build_fn = build_fn or product_embedding_service.build_from_doc
    query = {"org_id": {"$exists": False}} if only_unassigned else {}
    rows: list[tuple[str, str, str]] = []
    for doc in mongo.products().find(query).sort("code", 1):
        result = org_classifier_service.classify(doc, llm=llm, model_key=model_key)
        rows.append((doc.get("code") or str(doc["_id"]), result.org_id, result.via))
        if dry_run:
            continue
        mongo.products().update_one({"_id": doc["_id"]}, {"$set": {"org_id": result.org_id}})
        if rebuild:
            build_fn(mongo.products().find_one({"_id": doc["_id"]}))
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="print the assignment and write nothing")
    parser.add_argument("--all", action="store_true",
                        help="reclassify every product, not just unassigned ones")
    parser.add_argument("--rebuild-vectors", action="store_true",
                        help="re-embed each assigned product into its org's index")
    parser.add_argument("--model", default=DEFAULT_MODEL_KEY,
                        help="model_key for the classifier LLM")
    args = parser.parse_args(argv)

    rows = assign(only_unassigned=not args.all, dry_run=args.dry_run,
                  rebuild=args.rebuild_vectors, model_key=args.model)

    print("\n" + "-" * 70)
    print(f"{'code':<30} {'organization':<20} via")
    print("-" * 70)
    for code, org_id, via in rows:
        print(f"{code:<30} {org_id:<20} {via}")
    counts = Counter(org_id for _, org_id, _ in rows)
    print("\n" + ", ".join(f"{n} {org}" for org, n in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
