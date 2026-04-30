"""
Expected contract extraction results per chat file.
Aligned with how results show up in md/results/*.md (Contract summary format).
Used by summarize_results.py to compare actual LLM output vs expected.
Key: chat filename as it appears in result sections (e.g. long_multi_product_single_shipment.json).
Value: expected SOExtractContractList-shaped dict (data = list of contracts).

For payment_date, shipping_address, billing_address: use a string or a list of acceptable
values; the summarizer matches if actual matches any one of the expected values.
"""

# Structure matches model.SOExtractContractList / SalesOrderExtractContractKeyDetails.
# payment_date / shipping_address / billing_address can be str or list[str] for flexible matching.

EXPECTED_BY_CHAT = {
    # --- Chats from chats/ (single_product_*, multiple_product_*) ---
    "single_product_single_shipment_simple.json": {
        "data": [
            {
                "items": [
                    {
                        "description": "KNM Coffee",
                        "quantity": 5.0,
                        "quantity_unit": "bags",
                        "unit_price": 25.0,
                        "pricing_unit": "USD/bag",
                        "total": 125.0,
                        "ship_term": "",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-11-25",
                "po_ref_no": None,
                "vendor_name": "flamingos",
                "payment_date": ["Net 30", "Net 30 Days"],
                "shipping_address": [
                    "100 Finance Ave Singapore 018989",
                    "100 Finance Ave",
                    "100 Finance Ave.",
                ],
                "billing_address": None,
                "delivery_terms": "",
                "po_date": "",
                "shipping_method": None,
            }
        ]
    },
    "single_product_single_shipment_medium.json": {
        "data": [
            {
                "items": [
                    {
                        "description": "KNM Coffee",
                        "quantity": 8.0,
                        "quantity_unit": "bags",
                        "unit_price": 23.75,
                        "pricing_unit": "USD/bag",
                        "total": 190.0,
                        "ship_term": "",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-02-28",  # end of this month
                "po_ref_no": "PO-2025-11-101",
                "vendor_name": "flamingos",
                "payment_date": ["Net 30 from delivery", "Net 30", "Net 30 Days"],
                "shipping_address": [
                    "100 Finance Ave Singapore 018989",
                    "100 Finance Ave",
                    "100 Finance Ave.",
                ],
                "billing_address": "",
                "delivery_terms": "",
                "po_date": "",
                "shipping_method": "",
            }
        ]
    },
    "single_product_single_shipment_complex.json": {
        "data": [
            {
                "items": [
                    {
                        "description": "KNM Coffee",
                        "quantity": 10.0,
                        "quantity_unit": "bags",
                        "unit_price": 23.75,
                        "pricing_unit": "USD/bag",
                        "total": 237.5,
                        "ship_term": "FOB",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-11-28",
                "po_ref_no": "PO-2025-11-501",
                "vendor_name": "flamingos",
                "payment_date": ["Net 30 from delivery", "Net 30", "Net 30 Days"],
                "shipping_address": [
                    "352 Indiana Jones St.",
                    "Indiana Jones St.",
                ],
                "billing_address": "",
                "delivery_terms": "FOB Singapore",
                "po_date": "",
                "shipping_method": "",
            }
        ]
    },
    "single_product_multiple_shipment_simple.json": {
        "data": [
            {
                "items": [
                    {
                        "description": "KNM Coffee",
                        "quantity": 8.0,
                        "quantity_unit": "bags",
                        "unit_price": 25.0,
                        "pricing_unit": "USD/bag",
                        "total": 375.0,
                        "ship_term": "",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-02-28",
                "po_ref_no": "PO-2024-11-150",
                "vendor_name": "flamingos",
                "payment_date": [
                    "Net 30 from last delivery",
                    "Net 30",
                    "Net 30 from delivery",
                    "2026-04-30",
                ],
                "shipping_address": [
                    "100 Finance Ave",
                    "100 Finance Ave Singapore 018989",
                ],
                "billing_address": "",
                "delivery_terms": "",
                "po_date": "",
                "shipping_method": "",
            },
            {
                "items": [
                    {
                        "description": "KNM Coffee",
                        "quantity": 7.0,
                        "quantity_unit": "bags",
                        "unit_price": 25.0,
                        "pricing_unit": "USD/bag",
                        "total": 375.0,
                        "ship_term": "",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-03-31",
                "po_ref_no": "PO-2024-11-150",
                "vendor_name": "flamingos",
                "payment_date": [
                    "Net 30 from last delivery",
                    "Net 30",
                    "Net 30 from delivery",
                    "2026-04-30",
                ],
                "shipping_address": [
                    "100 Finance Ave",
                    "100 Finance Ave Singapore 018989",
                ],
                "billing_address": "",
                "delivery_terms": "",
                "po_date": "",
                "shipping_method": "",
            },
        ]
    },
    "single_product_multiple_shipment_medium.json": {
        "data": [
            {
                "items": [
                    {
                        "description": "KNM Coffee",
                        "quantity": 12.0,
                        "quantity_unit": "bags",
                        "unit_price": 23.75,
                        "pricing_unit": "USD/bag",
                        "total": 285.0,
                        "ship_term": "CIF Singapore",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-04-30",
                "po_ref_no": "PO-2025-11-180",
                "vendor_name": "flamingos",
                "payment_date": ["Net 30 from last delivery", "Net 30"],
                "shipping_address": [
                    "100 Finance Ave",
                    "100 Finance Ave Singapore 018989",
                ],
                "billing_address": [],
                "delivery_terms": "CIF",
                "po_date": "",
                "shipping_method": "",
            },
            {
                "items": [
                    {
                        "description": "KNM Coffee",
                        "quantity": 8.0,
                        "quantity_unit": "bags",
                        "unit_price": 23.75,
                        "pricing_unit": "USD/bag",
                        "total": 190.0,
                        "ship_term": "CIF Singapore",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-03-12",
                "po_ref_no": "PO-2024-11-180",
                "vendor_name": "flamingos",
                "payment_date": ["Net 30 from last delivery", "Net 30"],
                "shipping_address": ["50 Changi Business Park", "Changi Business Park"],
                "billing_address": [],
                "delivery_terms": "CIF",
                "po_date": "",
                "shipping_method": "",
            },
        ]
    },
    "single_product_multiple_shipment_complex.json": {
        "data": [
            {
                "items": [
                    {
                        "description": "KNM Coffee",
                        "quantity": 14.0,
                        "quantity_unit": "bags",
                        "unit_price": 22.75,
                        "pricing_unit": "USD/bag",
                        "total": 318.5,
                        "ship_term": "FOB Singapore",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-02-28",
                "po_ref_no": "PO-2025-11-280",
                "vendor_name": "flamingos",
                "payment_date": ["Net 30 from last delivery", "Net 30", "2026-04-08"],
                "shipping_address": [
                    "100 Finance Ave",
                    "100 Finance Ave Singapore 018989",
                ],
                "billing_address": [],
                "delivery_terms": "FOB",
                "po_date": "",
                "shipping_method": "",
            },
            {
                "items": [
                    {
                        "description": "KNM Coffee",
                        "quantity": 10.0,
                        "quantity_unit": "bags",
                        "unit_price": 22.75,
                        "pricing_unit": "USD/bag",
                        "total": 227.5,
                        "ship_term": "FOB Singapore",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-03-04",
                "po_ref_no": "PO-2025-11-280",
                "vendor_name": "flamingos",
                "payment_date": ["Net 30 from last delivery", "Net 30", "2026-04-08"],
                "shipping_address": ["200 Warehouse Lane", "Warehouse Lane"],
                "billing_address": [],
                "delivery_terms": "FOB",
                "po_date": "",
                "shipping_method": "",
            },
            {
                "items": [
                    {
                        "description": "KNM Coffee",
                        "quantity": 8.0,
                        "quantity_unit": "bags",
                        "unit_price": 22.75,
                        "pricing_unit": "USD/bag",
                        "total": 182.0,
                        "ship_term": "FOB Singapore",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-03-18",
                "po_ref_no": "PO-2025-11-280",
                "vendor_name": "flamingos",
                "payment_date": ["Net 30 from last delivery", "Net 30", "2026-04-08"],
                "shipping_address": ["15 New Branch Rd", "New Branch Rd"],
                "billing_address": [],
                "delivery_terms": "FOB",
                "po_date": "",
                "shipping_method": "",
            },
        ]
    },
    "multiple_product_multiple_shipment_simple.json": {
        "data": [
            {
                "items": [
                    {
                        "description": "KNM Coffee",
                        "quantity": 10.0,
                        "quantity_unit": "bags",
                        "unit_price": 25.0,
                        "pricing_unit": "USD/bag",
                        "total": 250.0,
                        "ship_term": "CIF Singapore",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-04-30",
                "po_ref_no": "PO-2024-11-200",
                "vendor_name": "flamingos",
                "payment_date": [
                    "Net 30 from last delivery",
                    "Net 30",
                    "Net 30 from delivery",
                    "2026-04-30",
                ],
                "shipping_address": [
                    "100 Finance Ave",
                    "100 Finance Ave Singapore 018989",
                ],
                "billing_address": "",
                "delivery_terms": "CIF",
                "po_date": "",
                "shipping_method": "",
            },
            {
                "items": [
                    {
                        "description": "Assam tea",
                        "quantity": 20.0,
                        "quantity_unit": "boxes",
                        "unit_price": 12.0,
                        "pricing_unit": "USD/box",
                        "total": 240.0,
                        "ship_term": "CIF Singapore",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-05-31",
                "po_ref_no": "PO-2024-11-200",
                "vendor_name": "flamingos",
                "payment_date": [
                    "Net 30 from last delivery",
                    "Net 30",
                    "Net 30 from delivery",
                    "2026-04-30",
                ],
                "shipping_address": [
                    "100 Finance Ave",
                    "100 Finance Ave Singapore 018989",
                ],
                "billing_address": "",
                "delivery_terms": "CIF",
                "po_date": "",
                "shipping_method": "",
            },
        ]
    },
    "multiple_product_multiple_shipment_medium.json": {
        "data": [
            {
                "items": [
                    {
                        "description": "KNM Coffee",
                        "quantity": 12.0,
                        "quantity_unit": "bags",
                        "unit_price": 23.75,
                        "pricing_unit": "USD/bag",
                        "total": 285.0,
                        "ship_term": "EXW Singapore",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-02-28",
                "po_ref_no": "PO-2025-11-250",
                "vendor_name": "flamingos",
                "payment_date": ["Net 30 from last delivery", "Net 30", "2026-04-30"],
                "shipping_address": [
                    "100 Finance Ave",
                    "100 Finance Ave Singapore 018989",
                ],
                "billing_address": [],
                "delivery_terms": "EXW",
                "po_date": "",
                "shipping_method": "",
            },
            {
                "items": [
                    {
                        "description": "Assam tea",
                        "quantity": 30.0,
                        "quantity_unit": "boxes",
                        "unit_price": 11.40,
                        "pricing_unit": "USD/box",
                        "total": 342.0,
                        "ship_term": "EXW Singapore",
                        "packing": "",
                        "loading": "",
                    },
                    {
                        "description": "paper",
                        "quantity": 50.0,
                        "quantity_unit": "reams",
                        "unit_price": 3.80,
                        "pricing_unit": "USD/ream",
                        "total": 190.0,
                        "ship_term": "EXW Singapore",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-03-05",
                "po_ref_no": "PO-2025-11-250",
                "vendor_name": "flamingos",
                "payment_date": [
                    "Net 30 from last delivery",
                    "Net 30",
                    "Net 30 from delivery",
                    "2026-04-30",
                ],
                "shipping_address": [
                    "100 Finance Ave",
                    "100 Finance Ave Singapore 018989",
                ],
                "billing_address": [],
                "delivery_terms": "EXW",
                "po_date": "",
                "shipping_method": "",
            },
        ]
    },
    "multiple_product_multiple_shipment_complex.json": {
        "data": [
            {
                "items": [
                    {
                        "description": "KNM Coffee",
                        "quantity": 12.0,
                        "quantity_unit": "bags",
                        "unit_price": 23.0,
                        "pricing_unit": "USD/bag",
                        "total": 276.0,
                        "ship_term": "FOB Singapore",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-02-28",
                "po_ref_no": "PO-2025-11-301",
                "vendor_name": "flamingos",
                "payment_date": ["Net 30 from first delivery", "Net 30", "2026-03-30"],
                "shipping_address": [
                    "100 Finance Ave",
                    "100 Finance Ave Singapore 018989",
                ],
                "billing_address": [],
                "delivery_terms": "FOB",
                "po_date": "",
                "shipping_method": "",
            },
            {
                "items": [
                    {
                        "description": "Assam tea",
                        "quantity": 30.0,
                        "quantity_unit": "boxes",
                        "unit_price": 11.04,
                        "pricing_unit": "USD/box",
                        "total": 331.20,
                        "ship_term": "FOB Singapore",
                        "packing": "",
                        "loading": "",
                    },
                    {
                        "description": "paper",
                        "quantity": 50.0,
                        "quantity_unit": "reams",
                        "unit_price": 3.68,
                        "pricing_unit": "USD/ream",
                        "total": 184.0,
                        "ship_term": "FOB Singapore",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-03-05",
                "po_ref_no": "PO-2025-11-301",
                "vendor_name": "flamingos",
                "payment_date": ["Net 30 from first delivery", "Net 30", "2026-03-30"],
                "shipping_address": [
                    "100 Finance Ave",
                    "100 Finance Ave Singapore 018989",
                ],
                "billing_address": [],
                "delivery_terms": "FOB",
                "po_date": "",
                "shipping_method": "",
            },
            {
                "items": [
                    {
                        "description": "Red Balloons",
                        "quantity": 3000,
                        "quantity_unit": "1000",
                        "unit_price": 2670.0,
                        "pricing_unit": "USD/1000",
                        "total": 8280.0,
                        "ship_term": "FOB Singapore",
                        "packing": "",
                        "loading": "",
                    },
                    {
                        "description": "Sanitizer",
                        "quantity": 100.0,
                        "quantity_unit": "boxes",
                        "unit_price": 9.2,
                        "pricing_unit": "USD/box",
                        "total": 920.0,
                    },
                ],
                "do_date": "2026-03-12",
                "po_ref_no": "PO-2025-11-301",
                "vendor_name": "flamingos",
                "payment_date": ["Net 30 from first delivery", "Net 30", "2026-03-30"],
                "shipping_address": [
                    "Changi Hospital Way Singapore 700339",
                ],
                "billing_address": [],
                "delivery_terms": "FOB",
                "po_date": "",
                "shipping_method": "",
            },
        ]
    },
    # --- Real-world chat tests (chats/) ---
    "real_world_msgs_test_v1.json": {
        "data": [
            {
                "items": [
                    {
                        "description": ["soy lecithin powder", "Soy lecithin powder"],
                        "quantity": 24.0,
                        "quantity_unit": "MT",
                        "unit_price": 4.1,
                        "pricing_unit": "USD/kg",
                        "total": 98400.0,
                        "ship_term": "CIF Busan",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": None,
                "po_ref_no": None,
                "payment_date": None,
                "shipping_address": ["CIF Busan", "Busan"],
                "billing_address": None,
            },
        ]
    },
    "real_world_msgs_test_v2.json": {
        "data": [
            {
                "items": [
                    {
                        "description": ["BP102"],
                        "quantity": 23.0,
                        "quantity_unit": "MT",
                        "unit_price": 1325.0,
                        "pricing_unit": "USD/MT",
                        "total": 30475.0,
                        "ship_term": "CIF Busan",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-02-28",
                "po_ref_no": None,
                "payment_date": None,
                "shipping_address": ["CIF Busan", "Busan"],
                "billing_address": None,
            },
            {
                "items": [
                    {
                        "description": ["DOL-97", "lecithin", "DOL-97 lecithin"],
                        "quantity": 18.0,
                        "quantity_unit": "MT",
                        "unit_price": 4.2,
                        "pricing_unit": "USD/kg",
                        "total": 75600.0,
                        "ship_term": "CIF Busan",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-02-28",
                "po_ref_no": None,
                "payment_date": None,
                "shipping_address": ["CIF Busan", "Busan"],
                "billing_address": None,
            },
        ]
    },
    "real_world_msgs_test_v3.json": {
        "data": [
            {
                "items": [
                    {
                        "description": ["lecithin fat powder", "Lecithin fat powder"],
                        "quantity": 8.0,
                        "quantity_unit": "MT",
                        "unit_price": 12.0,
                        "pricing_unit": "USD/kg",
                        "total": 96000.0,
                        "ship_term": "",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-03-31",
                "po_ref_no": None,
                "payment_date": None,
                "shipping_address": None,
                "billing_address": None,
            },
            {
                "items": [
                    {
                        "description": ["lecithin fat powder", "Lecithin fat powder"],
                        "quantity": 12.0,
                        "quantity_unit": "MT",
                        "unit_price": 12.0,
                        "pricing_unit": "USD/kg",
                        "total": 144000.0,
                        "ship_term": "",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-05-31",
                "po_ref_no": None,
                "payment_date": None,
                "shipping_address": None,
                "billing_address": None,
            },
        ]
    },
    # --- Email conversations (emails/) ---
    "single_product_single_shipment.json": {
        "data": [
            {
                "items": [
                    {
                        "description": ["BP102"],
                        "quantity": 23.0,
                        "quantity_unit": "MT",
                        "unit_price": 1325.0,
                        "pricing_unit": "USD/MT",
                        "total": 30475.0,
                        "ship_term": "",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-03-31",
                "po_ref_no": None,
                "payment_date": None,
                "shipping_address": ["CIF Busan", "Busan"],
                "billing_address": None,
            },
        ]
    },
    "single_product_multiple_shipments.json": {
        "data": [
            {
                "items": [
                    {
                        "description": ["lecithin fat powder", "Lecithin fat powder"],
                        "quantity": 8.0,
                        "quantity_unit": "MT",
                        "unit_price": 12.0,
                        "pricing_unit": "USD/kg",
                        "total": 96000.0,
                        "ship_term": "",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-04-30",
                "po_ref_no": None,
                "payment_date": None,
                "shipping_address": None,
                "billing_address": None,
            },
            {
                "items": [
                    {
                        "description": ["lecithin fat powder", "Lecithin fat powder"],
                        "quantity": 12.0,
                        "quantity_unit": "MT",
                        "unit_price": 12.0,
                        "pricing_unit": "USD/kg",
                        "total": 144000.0,
                        "ship_term": "",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-05-31",
                "po_ref_no": None,
                "payment_date": None,
                "shipping_address": None,
                "billing_address": None,
            },
        ]
    },
    "multiple_products_multiple_shipments.json": {
        "data": [
            {
                "items": [
                    {
                        "description": ["BP102"],
                        "quantity": 23.0,
                        "quantity_unit": "MT",
                        "unit_price": 1325.0,
                        "pricing_unit": "USD/MT",
                        "total": 30475.0,
                        "ship_term": "",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-03-31",
                "po_ref_no": None,
                "payment_date": None,
                "shipping_address": ["CIF Busan", "Busan"],
                "billing_address": None,
            },
            {
                "items": [
                    {
                        "description": ["DOL-97", "DOL-97 lecithin", "lecithin"],
                        "quantity": 18.0,
                        "quantity_unit": "MT",
                        "unit_price": 4.1,
                        "pricing_unit": "USD/kg",
                        "total": 73800.0,
                        "ship_term": "",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-05-31",
                "po_ref_no": None,
                "payment_date": None,
                "shipping_address": ["CIF Busan", "Busan"],
                "billing_address": None,
            },
            {
                "items": [
                    {
                        "description": ["DOL-97", "DOL-97 lecithin", "lecithin"],
                        "quantity": 5.0,
                        "quantity_unit": "MT",
                        "unit_price": 4.1,
                        "pricing_unit": "USD/kg",
                        "total": 20500.0,
                        "ship_term": "",
                        "packing": "",
                        "loading": "",
                    },
                ],
                "do_date": "2026-05-31",
                "po_ref_no": None,
                "payment_date": None,
                "shipping_address": ["CIF Busan", "Busan"],
                "billing_address": None,
            },
        ]
    },
}


def get_expected_for_chat(chat_filename: str) -> dict | None:
    """Return expected contract data for a chat file, or None if not defined."""
    name = chat_filename if chat_filename.endswith(".json") else f"{chat_filename}.json"
    return EXPECTED_BY_CHAT.get(name)
