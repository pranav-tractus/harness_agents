"""Organization lookups: roster seeding, slugs, and per-org vector indexes.

Deliberately free of any `product_embedding_service` import — that module
imports this one to resolve its destination index, so a dependency the other
way would be a cycle. Anything needing a product's build status (the org
`unbuilt_count`, for example) computes it in the router.
"""
import re
from datetime import datetime, timezone

from apps.api import orgs
from apps.api.db import mongo, vectors
from apps.api.settings import get_settings


class MissingOrg(Exception):
    """A product or customer reached org-scoped code without an org_id."""


def index_name_for(slug: str) -> str:
    return f"{get_settings().vector_index}-{slug}"


def slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "org"
    slug = base
    n = 2
    while mongo.organizations().find_one({"_id": slug}):
        slug = f"{base}-{n}"
        n += 1
    return slug


def list_orgs() -> list[dict]:
    return list(mongo.organizations().find().sort("_id", 1))


def get_org(org_id: str) -> dict | None:
    return mongo.organizations().find_one({"_id": org_id})


def exists(org_id: str) -> bool:
    return get_org(org_id) is not None


def vector_index_name(org_id: str | None) -> str:
    """The index an org's vectors live in.

    Reads the stored name so that changing `S3_VECTOR_INDEX` later cannot
    orphan existing vectors. Falls back to the derived name when the org
    document is absent (fresh test databases, or a product pointing at a
    deleted org).
    """
    if not org_id:
        raise MissingOrg("no org_id")
    org = get_org(org_id)
    return (org or {}).get("vector_index") or index_name_for(org_id)


def vector_index_for(org_id: str):
    return vectors.index_named(vector_index_name(org_id))


def org_id_for_customer(customer_id: str) -> str:
    doc = mongo.customers().find_one({"_id": customer_id}, {"org_id": 1}) or {}
    org_id = doc.get("org_id")
    if not org_id:
        raise MissingOrg(f"customer {customer_id!r} has no organization")
    return org_id


def seed_roster() -> None:
    now = datetime.now(timezone.utc).isoformat()
    for org in orgs.ORG_SEEDS:
        mongo.organizations().update_one(
            {"_id": org["_id"]},
            {"$setOnInsert": {
                **org,
                "vector_index": index_name_for(org["_id"]),
                "created_at": now,
            }},
            upsert=True,
        )
