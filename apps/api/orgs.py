"""The fictional selling organizations the catalog is divided across.

Seeded idempotently into the `organizations` collection. Editing a name here
does not overwrite an org that has been renamed through the API — `seed_roster`
uses `$setOnInsert`, matching how `seed.py` handles products and customers.
"""

CATCHALL_ID = "damage-control"

ORG_SEEDS = [
    {
        "_id": "roxxon",
        "name": "Roxxon Energy Corporation",
        "tagline": "Lecithins, phospholipids, choline and energy fats",
        "is_catchall": False,
    },
    {
        "_id": "pym",
        "name": "Pym Technologies",
        "tagline": "Amino acids, enzymes and probiotics",
        "is_catchall": False,
    },
    {
        "_id": "alchemax",
        "name": "Alchemax",
        "tagline": "Vitamins, minerals, organic acids and preservatives",
        "is_catchall": False,
    },
    {
        "_id": CATCHALL_ID,
        "name": "Damage Control",
        "tagline": "Catch-all for products no rule or classifier could place",
        "is_catchall": True,
    },
]
