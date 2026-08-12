import hashlib
import json
import logging

from apps.api.db import mongo, vectors
from apps.api.services import org_service
from core import embeddings

logger = logging.getLogger(__name__)

_SNIPPET_LEN = 300


def _meta_text(metadata: dict) -> str:
    return " · ".join(f"{k}: {v}" for k, v in sorted((metadata or {}).items()))


def _render_main(doc: dict) -> str:
    parts = [
        doc.get("name") or doc["code"],
        doc.get("short_description") or doc.get("description") or "",
        doc.get("long_description") or "",
        _meta_text(doc.get("metadata") or {}),
    ]
    return "\n".join(p for p in parts if p)


def _render_spec(doc: dict) -> str:
    parts = [doc.get("spec") or "", _meta_text(doc.get("metadata") or {})]
    return "\n".join(p for p in parts if p)


def _payloads(doc: dict) -> list[tuple[str, str, dict]]:
    """(key, text-to-embed, metadata) for every vector this product owns."""
    pid = str(doc["_id"])
    flat = {k: str(v) for k, v in (doc.get("metadata") or {}).items()}
    # Keep only essential filterable keys; pack product attributes into non-filterable "attrs"
    # to stay within the S3 Vectors 2048-byte filterable metadata limit.
    code = doc.get("code") or pid
    base = {"code": code, "name": doc.get("name") or code, "attrs": json.dumps(flat)}
    out = [(f"{pid}#main", _render_main(doc), {**base, "kind": "main"})]
    spec_text = _render_spec(doc)
    if spec_text:
        out.append((f"{pid}#spec", spec_text, {**base, "kind": "spec"}))
    return out


def _hash(payloads: list[tuple[str, str, dict]], org_id: str | None) -> str:
    blob = json.dumps([(k, t) for k, t, _ in payloads] + [org_id], ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def build_from_doc(doc: dict, *, embed_fn=None, index=None) -> None:
    embed_fn = embed_fn or embeddings.embed
    org_id = doc.get("org_id")
    if not org_id:
        raise org_service.MissingOrg(
            f"product {doc.get('code')!r} has no organization; run scripts/assign_orgs.py"
        )
    index_name = org_service.vector_index_name(org_id)
    if index is None:
        if not vectors.is_available():
            return
        index = org_service.vector_index_for(org_id)
        index.ensure()
    payloads = _payloads(doc)
    vecs = embed_fn([text for _, text, _ in payloads], mode="document")
    records = [
        vectors.VectorRecord(
            key=key, embedding=vec, metadata={**meta, "snippet": text[:_SNIPPET_LEN]}
        )
        for (key, text, meta), vec in zip(payloads, vecs)
    ]
    new_keys = [r.key for r in records]
    stale = [k for k in (doc.get("vector_keys") or []) if k not in set(new_keys)]
    if stale:
        index.delete(stale)
    index.put(records)
    mongo.products().update_one(
        {"_id": doc["_id"]},
        {"$set": {"embedded_hash": _hash(payloads, org_id),
                  "vector_keys": new_keys,
                  "vector_index": index_name}},
    )


def status_for_doc(doc: dict) -> str:
    if not doc.get("embedded_hash"):
        return "not built"
    expected = _hash(_payloads(doc), doc.get("org_id"))
    return "built" if doc["embedded_hash"] == expected else "stale"


def remove_product(product_id, *, index=None) -> None:
    """Delete a product's vectors. `product_id` is the Mongo `_id`.

    Must be called while the product document still exists — both the keys and
    the index they live in are read from it. `vector_index` is preferred over
    the org's current index so that a product whose org changed without a
    rebuild still cleans up correctly.
    """
    doc = mongo.products().find_one({"_id": product_id}) or {}
    keys = doc.get("vector_keys") or []
    if not keys:
        return
    if index is None:
        if not vectors.is_available():
            return
        name = doc.get("vector_index")
        if not name:
            if not doc.get("org_id"):
                logger.warning("product %s has vectors but no index to delete them from",
                               product_id)
                return
            name = org_service.vector_index_name(doc["org_id"])
        index = vectors.index_named(name)
    index.delete(keys)


def move_org(doc: dict, new_org_id: str, *, embed_fn=None, index=None) -> dict:
    """Move a product to another org: drop old vectors, re-embed into the new index.

    The document is left explicitly unbuilt between the two halves, so a
    failed rebuild surfaces as "not built" in the UI rather than as a product
    that looks embedded but has no vectors anywhere.
    """
    if doc.get("org_id") == new_org_id:
        return doc
    try:
        remove_product(doc["_id"])
    except Exception:
        logger.warning("failed to remove vectors while moving %s", doc.get("code"),
                       exc_info=True)
    mongo.products().update_one(
        {"_id": doc["_id"]},
        {"$set": {"org_id": new_org_id},
         "$unset": {"embedded_hash": "", "vector_keys": "", "vector_index": ""}},
    )
    fresh = mongo.products().find_one({"_id": doc["_id"]})
    if index is not None or vectors.is_available():
        build_from_doc(fresh, embed_fn=embed_fn, index=index)
    return mongo.products().find_one({"_id": doc["_id"]})
