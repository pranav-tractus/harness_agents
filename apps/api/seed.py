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
    ("TG-BPPC", "Rumen bypass Phosphotidyl Choline for High Yielding Dairy Cattle"),
    ("TG-MGL8", "Lecithin activated Fat Powder"),
    ("GIIOFINE-UP-SF", "De-Oiled Sunflower Lecithin Powder"),
    ("GIIOFINE-L-nGM", "Liquid Soyabean Lecithin made from GMO Free Soybeans"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    for code, desc in _PRODUCTS:
        mongo.products().update_one(
            {"_id": code},
            {
                "$setOnInsert": {
                    "_id": code,
                    "code": code,
                    "description": desc,
                    "spec": None,
                }
            },
            upsert=True,
        )
