from datetime import datetime, timezone

from apps.api.db import mongo

_CUSTOMERS = ["dummy-01", "dummy-02", "dummy-03"]

_EMPTY_PROFILE = {
    "email": None, "phone": None,
    "business_address": None, "delivery_address": None, "contact_point": None,
    "approved_credit_term": None, "approved_white_label": None,
    "latest_packing_and_loading": None,
}

_PRODUCTS = [
    {"code": "TG-BPPC",
     "short_description": "Rumen bypass Phosphotidyl Choline for High Yielding Dairy Cattle",
     "metadata": {"form": "powder", "category": "Dairy nutrition"}},
    {"code": "TG-MGL8", "short_description": "Lecithin activated Fat Powder",
     "metadata": {"form": "powder"}},
    {"code": "GIIOFINE-UP-SF", "short_description": "De-Oiled Sunflower Lecithin Powder",
     "metadata": {"form": "powder", "density": "0.5 g/cm3"}},
    {"code": "GIIOFINE-L-nGM", "short_description": "Liquid Soyabean Lecithin made from GMO Free Soybeans",
     "metadata": {"form": "liquid", "density": "0.92 g/cm3"}},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def migrate_products() -> None:
    """Idempotently upgrade legacy product docs: description -> short_description + defaults."""
    for doc in mongo.products().find({"short_description": {"$exists": False}}):
        mongo.products().update_one(
            {"_id": doc["_id"]},
            {"$set": {"short_description": doc.get("description", ""),
                      "name": doc.get("name"),
                      "long_description": doc.get("long_description"),
                      "metadata": doc.get("metadata") or {}},
             "$unset": {"description": ""}})


def seed_all() -> None:
    for cid in _CUSTOMERS:
        mongo.customers().update_one(
            {"_id": cid},
            {
                "$setOnInsert": {
                    "_id": cid,
                    "name": cid.replace("dummy", "Dummy"),
                    "profile": dict(_EMPTY_PROFILE),
                    "last_contract_seq": 0,
                    "updated_at": _now(),
                }
            },
            upsert=True,
        )
    for p in _PRODUCTS:
        mongo.products().update_one(
            {"_id": p["code"]},
            {"$setOnInsert": {
                "_id": p["code"], "code": p["code"], "name": p.get("name"),
                "short_description": p["short_description"],
                "long_description": p.get("long_description"),
                "spec": p.get("spec"), "metadata": p.get("metadata", {}),
            }},
            upsert=True,
        )
    migrate_products()
