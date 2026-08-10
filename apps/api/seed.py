from datetime import datetime, timezone

from apps.api.db import mongo
from apps.api.orgs import CATCHALL_ID
from apps.api.services import org_classifier_service, org_service

_CUSTOMERS = ["dummy-01", "dummy-02", "dummy-03"]

_EMPTY_PROFILE = {
    "email": None,
    "phone": None,
    "business_address": None,
    "delivery_address": None,
    "contact_point": None,
    "approved_credit_term": None,
    "approved_white_label": None,
    "latest_packing_and_loading": None,
}

_PRODUCTS = [
    # --- Choline / phospholipid products ---
    {
        "code": "TG-BPPC",
        "name": "Bypass Choline",
        "short_description": "Rumen bypass Phosphotidyl Choline for High Yielding Dairy Cattle",
        "long_description": "Rumen-protected phosphatidylcholine formulated for high-yielding dairy cows. "
        "Supports liver function, reduces fatty liver incidence, and improves milk production "
        "in the transition period.",
        "spec": "Choline chloride equivalent ≥60%, bypass efficiency ≥70%",
        "metadata": {
            "form": "powder",
            "category": "Dairy nutrition",
            "packing": "25kg bag",
        },
    },
    {
        "code": "TG-MGL8",
        "name": "Lecithin Fat Powder",
        "short_description": "Lecithin activated Fat Powder",
        "long_description": "Calcium salt of fatty acids enriched with lecithin for enhanced palatability "
        "and energy density in dairy and poultry diets.",
        "spec": "Fat ≥84%, moisture ≤3%",
        "metadata": {"form": "powder", "energy": "6.5 Mcal/kg", "packing": "25kg bag"},
    },
    # --- Lecithin products ---
    {
        "code": "GIIOFINE-UP-SF",
        "name": "Sunflower Lecithin Powder",
        "short_description": "De-Oiled Sunflower Lecithin Powder",
        "long_description": "Free-flowing de-oiled sunflower lecithin powder produced by solvent extraction. "
        "Non-GMO, allergen-free alternative to soy lecithin for aquafeed and pet food applications.",
        "spec": "Acetone insoluble ≥95%, moisture ≤2%",
        "metadata": {
            "form": "powder",
            "density": "0.5 g/cm3",
            "origin": "Ukraine",
            "packing": "25kg bag",
        },
    },
    {
        "code": "GIIOFINE-L-nGM",
        "name": "GMO-Free Soy Lecithin Liquid",
        "short_description": "Liquid Soyabean Lecithin made from GMO Free Soybeans",
        "long_description": "Fluid soy lecithin sourced from Identity Preserved non-GMO soybeans. "
        "Suitable for emulsification in aquafeed pellets and compound feed mash.",
        "spec": "Acetone insoluble ≥62%, moisture ≤1%, viscosity 8000–12000 cP at 25°C",
        "metadata": {
            "form": "liquid",
            "density": "0.92 g/cm3",
            "packing": "200kg drum",
        },
    },
    {
        "code": "GIIOFINE-L-SY",
        "name": "Standard Soy Lecithin Liquid",
        "short_description": "Liquid Soyabean Lecithin (standard grade)",
        "long_description": "Conventional fluid soy lecithin for use as emulsifier, lubricant, and energy source "
        "in poultry, swine, and aquafeed. Cost-effective for large-scale compound feed mills.",
        "spec": "Acetone insoluble ≥62%, moisture ≤1%",
        "metadata": {
            "form": "liquid",
            "density": "0.92 g/cm3",
            "packing": "200kg drum / flexi bag",
        },
    },
    {
        "code": "GIIOFINE-UP-SY",
        "name": "Soy Lecithin Powder",
        "short_description": "De-Oiled Soyabean Lecithin Powder",
        "spec": "Acetone insoluble ≥95%, moisture ≤2%",
        "metadata": {"form": "powder", "density": "0.5 g/cm3", "packing": "25kg bag"},
    },
    {
        "code": "GIIOFINE-UP-RPK",
        "name": "Rapeseed Lecithin Powder",
        "short_description": "De-Oiled Rapeseed Lecithin Powder",
        "long_description": "High-phospholipid rapeseed lecithin powder, soy-free, suitable for salmon, "
        "trout, and specialty aquafeed where soy allergens are a concern.",
        "spec": "Acetone insoluble ≥95%, moisture ≤2%",
        "metadata": {"form": "powder", "origin": "Europe", "packing": "25kg bag"},
    },
    # --- Rumen-protected amino acids ---
    {
        "code": "TG-RPMT",
        "name": "Rumen Protected Methionine",
        "short_description": "Rumen-protected DL-Methionine for dairy cattle",
        "long_description": "Encapsulated DL-methionine with ≥85% rumen bypass efficiency for precision "
        "amino acid supplementation in TMR diets. Improves milk protein yield and body "
        "condition score during early lactation.",
        "spec": "Methionine ≥65%, rumen bypass ≥85%",
        "metadata": {
            "form": "granule",
            "packing": "25kg bag",
            "category": "Amino acids",
        },
    },
    {
        "code": "TG-RPLYS",
        "name": "Rumen Protected Lysine",
        "short_description": "Rumen-protected L-Lysine for high-producing dairy cows",
        "spec": "Lysine ≥50%, rumen bypass ≥80%",
        "metadata": {
            "form": "granule",
            "packing": "25kg bag",
            "category": "Amino acids",
        },
    },
    # --- Feed-grade amino acids ---
    {
        "code": "TG-LMONO",
        "name": "Lysine HCl 98.5%",
        "short_description": "L-Lysine Monohydrochloride feed grade",
        "long_description": "Fermentation-derived L-Lysine HCl 98.5% for swine, poultry, and aquafeed. "
        "Formulated to meet ideal protein ratios and reduce crude protein in least-cost diets.",
        "spec": "L-Lysine HCl ≥98.5%, moisture ≤1%",
        "metadata": {
            "form": "granule",
            "packing": "25kg bag",
            "category": "Amino acids",
        },
    },
    {
        "code": "TG-THREONINE",
        "name": "L-Threonine 98.5%",
        "short_description": "L-Threonine feed grade 98.5%",
        "spec": "L-Threonine ≥98.5%, moisture ≤0.5%",
        "metadata": {
            "form": "powder",
            "packing": "25kg bag",
            "category": "Amino acids",
        },
    },
    {
        "code": "TG-TRYPTOPHAN",
        "name": "L-Tryptophan 98%",
        "short_description": "L-Tryptophan feed grade 98%",
        "long_description": "Fermentation-derived L-tryptophan for swine diets to reduce aggression and "
        "improve feed conversion in grow-finish pigs.",
        "spec": "L-Tryptophan ≥98%, moisture ≤0.5%",
        "metadata": {
            "form": "powder",
            "packing": "25kg bag",
            "category": "Amino acids",
        },
    },
    # --- Enzymes ---
    {
        "code": "TG-ENZYME-P",
        "name": "Phytase 10000",
        "short_description": "Granular Phytase enzyme 10,000 FTU/g",
        "long_description": "Thermostable 6-phytase produced by fermentation. Releases phosphorus from "
        "phytate in plant-based feed ingredients, reducing inorganic phosphate inclusion "
        "and environmental phosphorus excretion.",
        "spec": "Activity ≥10,000 FTU/g, thermostable to 85°C pellet conditioning",
        "metadata": {"form": "granule", "packing": "25kg bag", "category": "Enzymes"},
    },
    {
        "code": "TG-ENZYME-X",
        "name": "Xylanase + Beta-glucanase Complex",
        "short_description": "NSP enzyme complex (xylanase + beta-glucanase) for wheat/barley diets",
        "spec": "Xylanase ≥15,000 BXU/g, beta-glucanase ≥10,000 BGU/g",
        "metadata": {"form": "granule", "packing": "25kg bag", "category": "Enzymes"},
    },
    # --- Yeast / probiotics ---
    {
        "code": "TG-YEAST-SC",
        "name": "Live Yeast (S. cerevisiae)",
        "short_description": "Saccharomyces cerevisiae live yeast for ruminant diets",
        "long_description": "Dried live yeast culture standardised at ≥5×10⁹ CFU/g. Stabilises rumen pH, "
        "increases fibre digestibility, and improves milk fat percentage in dairy cows.",
        "spec": "Viable count ≥5×10⁹ CFU/g, moisture ≤8%",
        "metadata": {"form": "powder", "packing": "25kg bag", "category": "Probiotics"},
    },
    # --- Vitamins / minerals ---
    {
        "code": "TG-VITAE",
        "name": "Vitamin E 50%",
        "short_description": "Vitamin E (dl-alpha-tocopheryl acetate) 50% powder",
        "long_description": "Spray-dried vitamin E powder on silica carrier. Used in poultry, swine, and "
        "dairy premixes to prevent oxidative stress and improve meat/egg quality.",
        "spec": "dl-alpha-tocopheryl acetate 50%, moisture ≤5%",
        "metadata": {"form": "powder", "packing": "25kg bag", "category": "Vitamins"},
    },
    {
        "code": "TG-BETAINE",
        "name": "Betaine Anhydrous 98%",
        "short_description": "Betaine anhydrous 98% feed grade",
        "long_description": "Natural osmoprotectant and methyl donor sourced from sugar beet molasses. "
        "Partially replaces DL-methionine and choline chloride, improving water retention "
        "and FCR in broilers and shrimp.",
        "spec": "Betaine ≥98%, moisture ≤0.5%",
        "metadata": {"form": "granule", "packing": "25kg bag", "category": "Vitamins"},
    },
    {
        "code": "TG-CALCITE",
        "name": "Feed Grade Calcite",
        "short_description": "Micronised calcite powder for feed calcium supplementation",
        "spec": "CaCO₃ ≥98%, Ca ≥39%, particle size D50 ≈ 50 µm",
        "metadata": {
            "form": "powder",
            "density": "2.7 g/cm3",
            "packing": "50kg bag",
            "category": "Minerals",
        },
    },
    # --- Organic acids ---
    {
        "code": "TG-ACIDBLEND",
        "name": "Organic Acid Blend",
        "short_description": "Buffered formic + propionic acid blend for feed preservation",
        "long_description": "Liquid blend of formic acid (45%) and propionic acid (25%) buffered with "
        "ammonium formate. Reduces mould, yeast, and Salmonella counts in mash feed "
        "and raw materials.",
        "spec": "Formic acid 45%, propionic acid 25%, pH 3.5–4.0",
        "metadata": {
            "form": "liquid",
            "density": "1.18 g/cm3",
            "packing": "25kg can / 250kg drum",
            "category": "Organic acids",
        },
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def migrate_products() -> None:
    """Idempotently upgrade legacy product docs: description -> short_description + defaults."""
    for doc in mongo.products().find({"short_description": {"$exists": False}}):
        mongo.products().update_one(
            {"_id": doc["_id"]},
            {
                "$set": {
                    "short_description": doc.get("description", ""),
                    "name": doc.get("name"),
                    "long_description": doc.get("long_description"),
                    "metadata": doc.get("metadata") or {},
                },
                "$unset": {"description": ""},
            },
        )


_CUSTOMER_ORGS = {
    "dummy-01": "roxxon",
    "dummy-02": "pym",
    "dummy-03": "alchemax",
}


def migrate_orgs() -> None:
    """Seed the org roster and give every org-less customer an organization.

    Idempotent and cheap — four upserts plus one pass over org-less customers —
    so it is safe to run on every boot. Products are deliberately NOT classified
    here: classification can call an LLM, so it lives in
    `scripts/assign_orgs.py` where it is explicit and reviewable.
    """
    org_service.seed_roster()
    for doc in mongo.customers().find({"org_id": {"$exists": False}}, {"_id": 1}):
        mongo.customers().update_one(
            {"_id": doc["_id"]},
            {"$set": {"org_id": _CUSTOMER_ORGS.get(doc["_id"], CATCHALL_ID)}},
        )


def seed_all() -> None:
    org_service.seed_roster()      # roster first: the classifier reads it
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
            {"code": p["code"]},
            {
                "$setOnInsert": {
                    "code": p["code"],
                    "name": p.get("name"),
                    "short_description": p["short_description"],
                    "long_description": p.get("long_description"),
                    "spec": p.get("spec"),
                    "metadata": p.get("metadata", {}),
                    "org_id": org_classifier_service.classify(p).org_id,
                }
            },
            upsert=True,
        )
    migrate_products()
    migrate_orgs()                 # last: assigns the customers just created
