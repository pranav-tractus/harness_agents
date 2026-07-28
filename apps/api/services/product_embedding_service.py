import hashlib
import json

from apps.api.db import mongo, vectors
from core import embeddings

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
    code = doc["code"]
    flat = {k: str(v) for k, v in (doc.get("metadata") or {}).items()}
    base = {"code": code, "name": doc.get("name") or code, **flat}
    out = [(f"{code}#main", _render_main(doc), {**base, "kind": "main"})]
    spec_text = _render_spec(doc)
    if spec_text:
        out.append((f"{code}#spec", spec_text, {**base, "kind": "spec"}))
    aliases = [a for a in dict.fromkeys(doc.get("aliases") or []) if a]
    for i, alias in enumerate(aliases):
        text = f"{alias} — {doc.get('name') or code}"
        out.append((f"{code}#alias#{i}", text, {**base, "kind": "alias"}))
    return out


def _hash(payloads: list[tuple[str, str, dict]]) -> str:
    blob = json.dumps([(k, t) for k, t, _ in payloads], ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def build_from_doc(doc: dict, *, embed_fn=None, index=None) -> None:
    embed_fn = embed_fn or embeddings.embed
    if index is None:
        if not vectors.is_available():
            return
        index = vectors.default_index()
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
        {"_id": doc["code"]},
        {"$set": {"embedded_hash": _hash(payloads), "vector_keys": new_keys}},
    )


def status_for_doc(doc: dict) -> str:
    if not doc.get("embedded_hash"):
        return "not built"
    return "built" if doc["embedded_hash"] == _hash(_payloads(doc)) else "stale"


def remove_product(code: str, *, index=None) -> None:
    doc = mongo.products().find_one({"_id": code}) or {}
    keys = doc.get("vector_keys") or []
    if not keys:
        return
    if index is None:
        if not vectors.is_available():
            return
        index = vectors.default_index()
    index.delete(keys)
