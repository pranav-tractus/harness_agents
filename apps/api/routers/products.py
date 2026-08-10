import logging

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Response

from apps.api.db import mongo
from apps.api.models import ProductCreate, ProductOut, ProductUpdate
from apps.api.services import org_service, product_embedding_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/products", tags=["products"])


def _oid(product_id: str) -> ObjectId:
    try:
        return ObjectId(product_id)
    except (InvalidId, TypeError):
        raise HTTPException(404, "product not found") from None


def _out(doc: dict) -> ProductOut:
    return ProductOut(id=str(doc["_id"]), code=doc["code"],
                      name=doc.get("name"),
                      short_description=doc.get("short_description") or doc.get("description") or "",
                      long_description=doc.get("long_description"),
                      spec=doc.get("spec"),
                      metadata=doc.get("metadata") or {},
                      build_status=product_embedding_service.status_for_doc(doc),
                      source_label=doc.get("source_label"),
                      org_id=doc.get("org_id"))


def _require_org(org_id: str) -> None:
    if not org_service.exists(org_id):
        raise HTTPException(422, f"unknown organization {org_id!r}")


@router.get("")
def list_products(org_id: str | None = None) -> list[ProductOut]:
    query = {"org_id": org_id} if org_id else {}
    return [_out(d) for d in mongo.products().find(query).sort("code", 1)]


@router.post("", status_code=201)
def create_product(body: ProductCreate) -> ProductOut:
    code = body.code.strip()
    if not code:
        raise HTTPException(422, "code is required")
    _require_org(body.org_id)
    if mongo.products().find_one({"code": code}):
        raise HTTPException(409, "product already exists")
    doc = {"code": code, "name": body.name,
           "short_description": body.short_description, "long_description": body.long_description,
           "spec": body.spec, "metadata": body.metadata or {}, "org_id": body.org_id}
    inserted = mongo.products().insert_one(doc).inserted_id
    return _out(mongo.products().find_one({"_id": inserted}))


@router.get("/{product_id}")
def get_product(product_id: str) -> ProductOut:
    doc = mongo.products().find_one({"_id": _oid(product_id)})
    if not doc:
        raise HTTPException(404, "product not found")
    return _out(doc)


@router.put("/{product_id}")
def update_product(product_id: str, body: ProductUpdate) -> ProductOut:
    oid = _oid(product_id)
    doc = mongo.products().find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "product not found")
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    new_org = changes.pop("org_id", None)
    if changes:
        mongo.products().update_one({"_id": oid}, {"$set": changes})
    if new_org and new_org != doc.get("org_id"):
        _require_org(new_org)
        product_embedding_service.move_org(mongo.products().find_one({"_id": oid}), new_org)
    return _out(mongo.products().find_one({"_id": oid}))


@router.post("/build-all")
def build_all() -> list[ProductOut]:
    for doc in mongo.products().find().sort("code", 1):
        if not doc.get("org_id"):
            logger.warning("skipping %s: no organization", doc.get("code"))
            continue
        product_embedding_service.build_from_doc(doc)
    return [_out(d) for d in mongo.products().find().sort("code", 1)]


@router.post("/{product_id}/build")
def build_product(product_id: str) -> ProductOut:
    oid = _oid(product_id)
    doc = mongo.products().find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "product not found")
    product_embedding_service.build_from_doc(doc)
    return _out(mongo.products().find_one({"_id": oid}))


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: str) -> Response:
    oid = _oid(product_id)
    if not mongo.products().find_one({"_id": oid}):
        raise HTTPException(404, "product not found")
    # Vectors first: remove_product reads vector_keys off the document, so
    # deleting the document first would silently orphan every vector.
    try:
        product_embedding_service.remove_product(oid)
    except Exception:
        logger.warning("Failed to remove product embeddings for %s", product_id, exc_info=True)
    mongo.products().delete_one({"_id": oid})
    return Response(status_code=204)
