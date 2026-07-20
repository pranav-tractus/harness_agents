import logging

from fastapi import APIRouter, HTTPException, Response

from apps.api.db import mongo
from apps.api.models import ProductCreate, ProductOut, ProductUpdate
from apps.api.services import product_graph_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/products", tags=["products"])


def _out(doc: dict) -> ProductOut:
    return ProductOut(id=doc["_id"], code=doc["code"], description=doc["description"],
                      spec=doc.get("spec"),
                      build_status=product_graph_service.status(doc["code"], doc["description"], doc.get("spec")))


@router.get("")
def list_products() -> list[ProductOut]:
    return [_out(d) for d in mongo.products().find().sort("_id", 1)]


@router.post("", status_code=201)
def create_product(body: ProductCreate) -> ProductOut:
    code = body.code.strip()
    if not code:
        raise HTTPException(422, "code is required")
    if mongo.products().find_one({"_id": code}):
        raise HTTPException(409, "product already exists")
    doc = {"_id": code, "code": code, "description": body.description, "spec": body.spec}
    mongo.products().insert_one(doc)
    return _out(mongo.products().find_one({"_id": code}))


@router.get("/{product_id}")
def get_product(product_id: str) -> ProductOut:
    doc = mongo.products().find_one({"_id": product_id})
    if not doc:
        raise HTTPException(404, "product not found")
    return _out(doc)


@router.put("/{product_id}")
def update_product(product_id: str, body: ProductUpdate) -> ProductOut:
    doc = mongo.products().find_one({"_id": product_id})
    if not doc:
        raise HTTPException(404, "product not found")
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if changes:
        mongo.products().update_one({"_id": product_id}, {"$set": changes})
    updated = mongo.products().find_one({"_id": product_id})
    return _out(updated)


@router.post("/build-all")
def build_all() -> list[ProductOut]:
    for doc in mongo.products().find():
        product_graph_service.build(doc["code"], doc["description"], doc.get("spec"))
    return [_out(d) for d in mongo.products().find().sort("_id", 1)]


@router.post("/{product_id}/build")
def build_product(product_id: str) -> ProductOut:
    doc = mongo.products().find_one({"_id": product_id})
    if not doc:
        raise HTTPException(404, "product not found")
    product_graph_service.build(doc["code"], doc["description"], doc.get("spec"))
    return _out(mongo.products().find_one({"_id": product_id}))


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: str) -> Response:
    res = mongo.products().delete_one({"_id": product_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "product not found")
    try:
        product_graph_service.remove_product(product_id)
    except Exception:
        logger.warning("Failed to remove product graph for %s", product_id, exc_info=True)
    return Response(status_code=204)
