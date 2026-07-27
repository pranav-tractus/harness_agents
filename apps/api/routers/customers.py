import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response

from apps.api.db import falkor, mongo
from apps.api.models import CustomerCreate, CustomerOut, ProfileUpdate
from apps.api.services import profile_graph_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/customers", tags=["customers"])


def _out(doc: dict) -> CustomerOut:
    return CustomerOut(id=doc["_id"], name=doc["name"], profile=doc["profile"],
                       last_contract_seq=doc["last_contract_seq"])


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
    cid = _slug(name)
    doc = {
        "_id": cid,
        "name": name,
        "profile": {},
        "last_contract_seq": 0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    mongo.customers().insert_one(doc)
    try:
        profile_graph_service.resync(cid, name, {})
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
    try:
        profile_graph_service.resync(customer_id, doc["name"], profile)
    except Exception:
        logger.warning("Failed to resync profile graph for %s", customer_id, exc_info=True)
    return _out(mongo.customers().find_one({"_id": customer_id}))


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
