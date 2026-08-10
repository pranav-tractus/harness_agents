import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response

from apps.api.db import falkor, mongo
from apps.api.models import CustomerCreate, CustomerOut, ProfileUpdate
from apps.api.services import org_service, profile_graph_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/customers", tags=["customers"])


def _org_for_graph(org_id: str | None) -> dict | None:
    org = org_service.get_org(org_id) if org_id else None
    return {"id": org["_id"], "name": org["name"]} if org else None


def _out(doc: dict) -> CustomerOut:
    return CustomerOut(id=doc["_id"], name=doc["name"], profile=doc["profile"],
                       last_contract_seq=doc["last_contract_seq"],
                       org_id=doc.get("org_id"))


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "customer"
    cid = base
    n = 2
    while mongo.customers().find_one({"_id": cid}):
        cid = f"{base}-{n}"
        n += 1
    return cid


@router.get("")
def list_customers() -> list[CustomerOut]:
    return [_out(d) for d in mongo.customers().find().sort("_id", 1)]


@router.post("", status_code=201)
def create_customer(body: CustomerCreate) -> CustomerOut:
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "name is required")
    if not org_service.exists(body.org_id):
        raise HTTPException(422, f"unknown organization {body.org_id!r}")
    cid = _slug(name)
    doc = {
        "_id": cid,
        "name": name,
        "profile": {},
        "last_contract_seq": 0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "org_id": body.org_id,
    }
    mongo.customers().insert_one(doc)
    try:
        profile_graph_service.resync(cid, name, {}, org=_org_for_graph(body.org_id))
    except Exception:
        logger.warning("Failed to resync profile graph for %s", cid, exc_info=True)
    return _out(mongo.customers().find_one({"_id": cid}))


@router.get("/{customer_id}")
def get_customer(customer_id: str) -> CustomerOut:
    doc = mongo.customers().find_one({"_id": customer_id})
    if not doc:
        raise HTTPException(404, "customer not found")
    return _out(doc)


@router.put("/{customer_id}")
def update_profile(customer_id: str, body: ProfileUpdate) -> CustomerOut:
    doc = mongo.customers().find_one({"_id": customer_id})
    if not doc:
        raise HTTPException(404, "customer not found")
    profile = body.profile.model_dump()
    mongo.customers().update_one(
        {"_id": customer_id},
        {"$set": {"profile": profile, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if body.org_id and body.org_id != doc.get("org_id"):
        if not org_service.exists(body.org_id):
            raise HTTPException(422, f"unknown organization {body.org_id!r}")
        mongo.customers().update_one({"_id": customer_id}, {"$set": {"org_id": body.org_id}})
    updated = mongo.customers().find_one({"_id": customer_id})
    try:
        profile_graph_service.resync(customer_id, doc["name"], profile,
                                     org=_org_for_graph(updated.get("org_id")))
    except Exception:
        logger.warning("Failed to resync profile graph for %s", customer_id, exc_info=True)
    return _out(updated)


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: str) -> Response:
    res = mongo.customers().delete_one({"_id": customer_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "customer not found")
    mongo.messages().delete_many({"customer_id": customer_id})
    mongo.summaries().delete_many({"customer_id": customer_id})
    mongo.chats().delete_many({"customer_id": customer_id})
    if falkor.is_available():
        try:
            falkor.customer_graph(customer_id).delete()
        except Exception:
            pass
    return Response(status_code=204)
