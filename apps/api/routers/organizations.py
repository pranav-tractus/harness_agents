from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response

from apps.api.db import mongo
from apps.api.models import OrgCreate, OrgOut, OrgUpdate
from apps.api.services import org_service, product_embedding_service

router = APIRouter(prefix="/api/orgs", tags=["organizations"])


def _counts(org_id: str) -> tuple[int, int, int]:
    products = list(mongo.products().find({"org_id": org_id}))
    unbuilt = sum(
        1 for d in products if product_embedding_service.status_for_doc(d) != "built"
    )
    customers = mongo.customers().count_documents({"org_id": org_id})
    return len(products), customers, unbuilt


def _out(doc: dict) -> OrgOut:
    products, customers, unbuilt = _counts(doc["_id"])
    return OrgOut(
        id=doc["_id"],
        name=doc["name"],
        tagline=doc.get("tagline"),
        is_catchall=bool(doc.get("is_catchall")),
        product_count=products,
        customer_count=customers,
        unbuilt_count=unbuilt,
    )


def _require(org_id: str) -> dict:
    doc = org_service.get_org(org_id)
    if not doc:
        raise HTTPException(404, "organization not found")
    return doc


@router.get("")
def list_organizations() -> list[OrgOut]:
    return [_out(d) for d in org_service.list_orgs()]


@router.post("", status_code=201)
def create_organization(body: OrgCreate) -> OrgOut:
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "name is required")
    slug = org_service.slugify(name)
    mongo.organizations().insert_one({
        "_id": slug,
        "name": name,
        "tagline": (body.tagline or "").strip() or None,
        "is_catchall": False,
        "vector_index": org_service.index_name_for(slug),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return _out(_require(slug))


@router.get("/{org_id}")
def get_organization(org_id: str) -> OrgOut:
    return _out(_require(org_id))


@router.put("/{org_id}")
def update_organization(org_id: str, body: OrgUpdate) -> OrgOut:
    _require(org_id)
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if "name" in changes:
        if not (changes["name"] or "").strip():
            raise HTTPException(422, "name is required")
        changes["name"] = changes["name"].strip()
    if changes:
        mongo.organizations().update_one({"_id": org_id}, {"$set": changes})
    return _out(_require(org_id))


@router.delete("/{org_id}", status_code=204)
def delete_organization(org_id: str) -> Response:
    doc = _require(org_id)
    if doc.get("is_catchall"):
        products, customers, _ = _counts(org_id)
        raise HTTPException(409, {
            "message": "the catch-all organization cannot be deleted",
            "product_count": products,
            "customer_count": customers,
        })
    products, customers, _ = _counts(org_id)
    if products or customers:
        raise HTTPException(409, {
            "message": "organization still has products or customers attached",
            "product_count": products,
            "customer_count": customers,
        })
    mongo.organizations().delete_one({"_id": org_id})
    return Response(status_code=204)


@router.post("/{org_id}/build")
def build_organization(org_id: str) -> OrgOut:
    _require(org_id)
    for doc in mongo.products().find({"org_id": org_id}).sort("code", 1):
        product_embedding_service.build_from_doc(doc)
    return _out(_require(org_id))
