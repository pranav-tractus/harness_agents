"""
Expected contract extraction results per chat file.
Auto-updated by tests/benchmark_fewshot.py --update-expected.
"""

EXPECTED_BY_CHAT = {
    "single_product_single_shipment_simple.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "KNM Coffee",
                        "quantity": 5.0,
                        "quantity_unit": "BAGS",
                        "unit_price": 25.0,
                        "pricing_unit": "USD/BAG",
                        "ship_term": "",
                        "delivery_terms": "",
                        "shipment_date": "2026-11-25",
                        "shipping_address": "100 Finance Ave Singapore 018989",
                        "packing": "",
                        "loading": "",
                        "total": 125.0,
                    }
                ],
                "do_date": "2026-11-25",
                "po_date": "",
                "po_ref_no": "",
                "vendor_name": "Van Beethoven",
                "payment_date": "",
                "delivery_terms": "",
                "billing_address": "",
                "shipping_method": "",
                "shipping_address": "100 Finance Ave Singapore 018989",
            }
        ]
    },
    "single_product_single_shipment_medium.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "KNM Coffee",
                        "quantity": 8.0,
                        "quantity_unit": "BAGS",
                        "unit_price": 23.75,
                        "pricing_unit": "USD/BAG",
                        "ship_term": "",
                        "delivery_terms": "",
                        "shipment_date": "2026-05-28",
                        "shipping_address": "100 Finance Ave Singapore 018989",
                        "packing": "",
                        "loading": "",
                        "total": 190.0,
                    }
                ],
                "do_date": "2026-05-28",
                "po_date": "",
                "po_ref_no": "PO-2025-11-101",
                "vendor_name": "Van Beethoven",
                "payment_date": "Net 30 from delivery",
                "delivery_terms": "",
                "billing_address": "",
                "shipping_method": "",
                "shipping_address": "100 Finance Ave Singapore 018989",
            }
        ]
    },
    "single_product_single_shipment_complex.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "KNM Coffee",
                        "quantity": 10.0,
                        "quantity_unit": "bags",
                        "unit_price": 23.75,
                        "pricing_unit": "USD/bag",
                        "ship_term": "FOB",
                        "delivery_terms": "FOB Singapore",
                        "shipment_date": "2025-11-28",
                        "shipping_address": "352 Indiana Jones St.",
                        "packing": "",
                        "loading": "",
                        "total": 237.5,
                    }
                ],
                "do_date": "2025-11-28",
                "po_date": "",
                "po_ref_no": "PO-2025-11-501",
                "vendor_name": "Van Beethoven",
                "payment_date": "",
                "delivery_terms": "FOB Singapore",
                "billing_address": "",
                "shipping_method": "",
                "shipping_address": "352 Indiana Jones St.",
            }
        ]
    },
    "single_product_multiple_shipment_simple.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "KNM Coffee",
                        "quantity": 8.0,
                        "quantity_unit": "BAGS",
                        "unit_price": 25.0,
                        "pricing_unit": "USD/BAG",
                        "ship_term": "",
                        "delivery_terms": "",
                        "shipment_date": "2026-05-31",
                        "shipping_address": "100 Finance Ave",
                        "packing": "",
                        "loading": "",
                        "total": 200.0,
                    },
                    {
                        "sr_no": 2,
                        "description": "KNM Coffee",
                        "quantity": 7.0,
                        "quantity_unit": "BAGS",
                        "unit_price": 25.0,
                        "pricing_unit": "USD/BAG",
                        "ship_term": "",
                        "delivery_terms": "",
                        "shipment_date": "2026-06-30",
                        "shipping_address": "100 Finance Ave",
                        "packing": "",
                        "loading": "",
                        "total": 175.0,
                    },
                ],
                "do_date": "2026-06-30",
                "po_date": "",
                "po_ref_no": "PO-2025-11-150",
                "vendor_name": "Van Beethoven",
                "payment_date": "",
                "delivery_terms": "",
                "billing_address": "",
                "shipping_method": "",
                "shipping_address": "100 Finance Ave",
            }
        ]
    },
    "single_product_multiple_shipment_medium.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "KNM Coffee",
                        "quantity": 12.0,
                        "quantity_unit": "BAGS",
                        "unit_price": 23.75,
                        "pricing_unit": "USD/BAG",
                        "ship_term": "CIF",
                        "delivery_terms": "CIF Singapore",
                        "shipment_date": "2026-05-31",
                        "shipping_address": "100 Finance Ave",
                        "packing": "",
                        "loading": "",
                        "total": 285.0,
                    },
                    {
                        "sr_no": 2,
                        "description": "KNM Coffee",
                        "quantity": 8.0,
                        "quantity_unit": "BAGS",
                        "unit_price": 23.75,
                        "pricing_unit": "USD/BAG",
                        "ship_term": "CIF",
                        "delivery_terms": "CIF Singapore",
                        "shipment_date": "2026-03-12",
                        "shipping_address": "50 Changi Business Park",
                        "packing": "",
                        "loading": "",
                        "total": 190.0,
                    },
                ],
                "do_date": "2026-05-31",
                "po_date": "",
                "po_ref_no": "",
                "vendor_name": "Van Beethoven",
                "payment_date": "",
                "delivery_terms": "CIF Singapore",
                "billing_address": "",
                "shipping_method": "",
                "shipping_address": "",
            }
        ]
    },
    "single_product_multiple_shipment_complex.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "KNM Coffee",
                        "quantity": 14.0,
                        "quantity_unit": "BAGS",
                        "unit_price": 22.75,
                        "pricing_unit": "USD/BAG",
                        "ship_term": "FOB",
                        "delivery_terms": "FOB Singapore",
                        "shipment_date": "2026-02-28",
                        "shipping_address": "100 Finance Ave",
                        "packing": "",
                        "loading": "",
                        "total": 318.5,
                    },
                    {
                        "sr_no": 2,
                        "description": "KNM Coffee",
                        "quantity": 10.0,
                        "quantity_unit": "BAGS",
                        "unit_price": 22.75,
                        "pricing_unit": "USD/BAG",
                        "ship_term": "FOB",
                        "delivery_terms": "FOB Singapore",
                        "shipment_date": "2026-03-04",
                        "shipping_address": "200 Warehouse Lane",
                        "packing": "",
                        "loading": "",
                        "total": 227.5,
                    },
                    {
                        "sr_no": 3,
                        "description": "KNM Coffee",
                        "quantity": 8.0,
                        "quantity_unit": "BAGS",
                        "unit_price": 22.75,
                        "pricing_unit": "USD/BAG",
                        "ship_term": "FOB",
                        "delivery_terms": "FOB Singapore",
                        "shipment_date": "2026-03-10",
                        "shipping_address": "15 New Branch Rd",
                        "packing": "",
                        "loading": "",
                        "total": 182.0,
                    },
                ],
                "do_date": "2026-03-10",
                "po_date": "",
                "po_ref_no": "PO-2025-11-280",
                "vendor_name": "Van Beethoven",
                "payment_date": "",
                "delivery_terms": "FOB Singapore",
                "billing_address": "",
                "shipping_method": "",
                "shipping_address": "",
            }
        ]
    },
    "multiple_product_multiple_shipment_simple.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "KNM Coffee",
                        "quantity": 10.0,
                        "quantity_unit": "BAGS",
                        "unit_price": 25.0,
                        "pricing_unit": "USD/BAG",
                        "ship_term": "CIF",
                        "delivery_terms": "CIF Singapore",
                        "shipment_date": "2026-05-31",
                        "shipping_address": "100 Finance Ave",
                        "packing": "",
                        "loading": "",
                        "total": 250.0,
                    },
                    {
                        "sr_no": 2,
                        "description": "Assam tea",
                        "quantity": 20.0,
                        "quantity_unit": "BOXES",
                        "unit_price": 12.0,
                        "pricing_unit": "USD/BOX",
                        "ship_term": "CIF",
                        "delivery_terms": "CIF Singapore",
                        "shipment_date": "2026-06-30",
                        "shipping_address": "100 Finance Ave",
                        "packing": "",
                        "loading": "",
                        "total": 240.0,
                    },
                ],
                "do_date": "2026-06-30",
                "po_date": "",
                "po_ref_no": "PO-2025-11-200",
                "vendor_name": "Van Beethoven",
                "payment_date": "",
                "delivery_terms": "CIF Singapore",
                "billing_address": "",
                "shipping_method": "",
                "shipping_address": "100 Finance Ave",
            }
        ]
    },
    "multiple_product_multiple_shipment_medium.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "KNM Coffee",
                        "quantity": 12.0,
                        "quantity_unit": "bags",
                        "unit_price": None,
                        "pricing_unit": "",
                        "ship_term": "EXW",
                        "delivery_terms": "EXW Singapore",
                        "shipment_date": "2026-02-28",
                        "shipping_address": "100 Finance Ave Singapore 018989",
                        "packing": "",
                        "loading": "",
                        "total": None,
                    },
                    {
                        "sr_no": 2,
                        "description": "Assam tea",
                        "quantity": 30.0,
                        "quantity_unit": "boxes",
                        "unit_price": None,
                        "pricing_unit": "",
                        "ship_term": "EXW",
                        "delivery_terms": "EXW Singapore",
                        "shipment_date": "2026-03-05",
                        "shipping_address": "100 Finance Ave Singapore 018989",
                        "packing": "",
                        "loading": "",
                        "total": None,
                    },
                    {
                        "sr_no": 3,
                        "description": "Copy paper",
                        "quantity": 50.0,
                        "quantity_unit": "reams",
                        "unit_price": None,
                        "pricing_unit": "",
                        "ship_term": "EXW",
                        "delivery_terms": "EXW Singapore",
                        "shipment_date": "2026-03-05",
                        "shipping_address": "100 Finance Ave Singapore 018989",
                        "packing": "",
                        "loading": "",
                        "total": None,
                    },
                ],
                "do_date": "2026-03-05",
                "po_date": "",
                "po_ref_no": "PO-2025-11-250",
                "vendor_name": "Van Beethoven",
                "payment_date": "",
                "delivery_terms": "EXW Singapore",
                "billing_address": "",
                "shipping_method": "",
                "shipping_address": "100 Finance Ave Singapore 018989",
            }
        ]
    },
    "multiple_product_multiple_shipment_complex.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "KNM Coffee",
                        "quantity": 12.0,
                        "quantity_unit": "bags",
                        "unit_price": 25.0,
                        "pricing_unit": "USD/bag",
                        "ship_term": "FOB",
                        "delivery_terms": "FOB Singapore",
                        "shipment_date": "2026-02-28",
                        "shipping_address": "100 Finance Ave",
                        "packing": "",
                        "loading": "",
                        "total": 300.0,
                    },
                    {
                        "sr_no": 2,
                        "description": "Assam tea",
                        "quantity": 30.0,
                        "quantity_unit": "boxes",
                        "unit_price": 12.0,
                        "pricing_unit": "USD/box",
                        "ship_term": "FOB",
                        "delivery_terms": "FOB Singapore",
                        "shipment_date": "2026-03-05",
                        "shipping_address": "100 Finance Ave",
                        "packing": "",
                        "loading": "",
                        "total": 360.0,
                    },
                    {
                        "sr_no": 3,
                        "description": "Copy paper",
                        "quantity": 50.0,
                        "quantity_unit": "reams",
                        "unit_price": 4.0,
                        "pricing_unit": "USD/ream",
                        "ship_term": "FOB",
                        "delivery_terms": "FOB Singapore",
                        "shipment_date": "2026-03-05",
                        "shipping_address": "100 Finance Ave",
                        "packing": "",
                        "loading": "",
                        "total": 200.0,
                    },
                    {
                        "sr_no": 4,
                        "description": "Red Balloons",
                        "quantity": 3000.0,
                        "quantity_unit": "PCS",
                        "unit_price": 3.0,
                        "pricing_unit": "USD/PC",
                        "ship_term": "FOB",
                        "delivery_terms": "FOB Singapore",
                        "shipment_date": "2026-03-12",
                        "shipping_address": "Changi Hospital Way Singapore 700339",
                        "packing": "",
                        "loading": "",
                        "total": 9000.0,
                    },
                    {
                        "sr_no": 5,
                        "description": "Sanitizer",
                        "quantity": 100.0,
                        "quantity_unit": "boxes",
                        "unit_price": 10.0,
                        "pricing_unit": "USD/box",
                        "ship_term": "FOB",
                        "delivery_terms": "FOB Singapore",
                        "shipment_date": "2026-03-12",
                        "shipping_address": "Changi Hospital Way Singapore 700339",
                        "packing": "",
                        "loading": "",
                        "total": 1000.0,
                    },
                ],
                "do_date": "2026-02-28",
                "po_date": "",
                "po_ref_no": "PO-2025-11-301",
                "vendor_name": "Van Beethoven",
                "payment_date": "",
                "delivery_terms": "FOB Singapore",
                "billing_address": "",
                "shipping_method": "",
                "shipping_address": "",
            }
        ]
    },
    "real_world_msgs_test_v1.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "soy lecithin powder",
                        "quantity": 24.0,
                        "quantity_unit": "MT",
                        "unit_price": 4.1,
                        "pricing_unit": "USD/KG",
                        "ship_term": "CIF",
                        "delivery_terms": "CIF Busan",
                        "shipment_date": "2026-11-15",
                        "shipping_address": "",
                        "packing": "",
                        "loading": "12MT/20'FCL",
                        "total": 98400.0,
                    }
                ],
                "do_date": "2026-11-15",
                "po_date": "",
                "po_ref_no": "",
                "vendor_name": "Van Beethoven",
                "payment_date": "",
                "delivery_terms": "CIF Busan",
                "billing_address": "",
                "shipping_method": "",
                "shipping_address": "",
            }
        ]
    },
    "real_world_msgs_test_v2.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "BP102",
                        "quantity": 23.0,
                        "quantity_unit": "MT",
                        "unit_price": 1325.0,
                        "pricing_unit": "USD/MT",
                        "ship_term": "CIF",
                        "delivery_terms": "CIF Busan",
                        "shipment_date": "2026-02-28",
                        "shipping_address": "",
                        "packing": "",
                        "loading": "",
                        "total": 30475.0,
                    }
                ],
                "do_date": "2026-02-28",
                "po_date": "",
                "po_ref_no": "",
                "vendor_name": "AG Lipids Pte Ltd",
                "payment_date": "",
                "delivery_terms": "CIF Busan",
                "billing_address": "",
                "shipping_method": "",
                "shipping_address": "",
            },
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "DOL-97",
                        "quantity": 23.0,
                        "quantity_unit": "MT",
                        "unit_price": 4.2,
                        "pricing_unit": "USD/KG",
                        "ship_term": "CIF",
                        "delivery_terms": "CIF Busan",
                        "shipment_date": "2026-02-28",
                        "shipping_address": "",
                        "packing": "",
                        "loading": "",
                        "total": 96600.0,
                    }
                ],
                "do_date": "2026-02-28",
                "po_date": "",
                "po_ref_no": "",
                "vendor_name": "AG Lipids Pte Ltd",
                "payment_date": "",
                "delivery_terms": "CIF Busan",
                "billing_address": "",
                "shipping_method": "",
                "shipping_address": "",
            },
        ]
    },
    "real_world_msgs_test_v3.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "lecithin fat powder",
                        "quantity": 8.0,
                        "quantity_unit": "MT",
                        "unit_price": 12.0,
                        "pricing_unit": "USD/KG",
                        "ship_term": "",
                        "delivery_terms": "",
                        "shipment_date": "2026-03-31",
                        "shipping_address": "",
                        "packing": "",
                        "loading": "23MT/40'FCL",
                        "total": 96000.0,
                    },
                    {
                        "sr_no": 2,
                        "description": "lecithin fat powder",
                        "quantity": 12.0,
                        "quantity_unit": "MT",
                        "unit_price": 12.0,
                        "pricing_unit": "USD/KG",
                        "ship_term": "",
                        "delivery_terms": "",
                        "shipment_date": "2027-05-31",
                        "shipping_address": "",
                        "packing": "",
                        "loading": "23MT/40'FCL",
                        "total": 144000.0,
                    },
                ],
                "do_date": "",
                "po_date": "",
                "po_ref_no": "",
                "vendor_name": "Van Beethoven",
                "payment_date": "",
                "delivery_terms": "",
                "billing_address": "",
                "shipping_method": "",
                "shipping_address": "",
            }
        ]
    },
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
                    }
                ],
                "do_date": "2026-03-31",
                "po_ref_no": None,
                "payment_date": None,
                "shipping_address": ["CIF Busan", "Busan"],
                "billing_address": None,
            }
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
                    }
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
                    }
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
                    }
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
                    }
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
                    }
                ],
                "do_date": "2026-05-31",
                "po_ref_no": None,
                "payment_date": None,
                "shipping_address": ["CIF Busan", "Busan"],
                "billing_address": None,
            },
        ]
    },
    "01__2026-02-24__120363421131250401_g_us__e05574ec-b110-4554-9fc3-3abb4f9011a8.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "GIIOFINE - P - S",
                        "quantity": 1800.0,
                        "quantity_unit": "kg",
                        "unit_price": 3250.0,
                        "pricing_unit": "usd/mt",
                        "ship_term": "EXW",
                        "delivery_terms": "",
                        "shipment_date": "",
                        "shipping_address": "",
                        "packing": "Unknown",
                        "loading": "Unknown",
                        "total": 5850.0,
                    }
                ],
                "do_date": "2026-03-31",
                "po_date": "2026-02-24",
                "po_ref_no": "GIIOFINE - P - S-2026-6",
                "vendor_name": "GIIAVA Singapore Pte Ltd",
                "payment_date": "Advanced payment",
                "delivery_terms": "EXW",
                "billing_address": "Epic Chemicals Sdn Bhd, 17 Jalan Industri Mas 12,Taman Mas Sepang,47130 Puchong,Selangor,Malaysia",
                "shipping_method": "Collection Against OPO 260012/EC",
                "shipping_address": "17 Jalan Industri Mas 12,Taman Mas Sepang,47130 Puchong,Selangor,Malaysia",
            }
        ]
    },
    "02__2026-02-09__120363426578757754_g_us__12a4f3a7-d506-4d32-ae06-3f76508c6abd.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "GIIOFINE - P - S",
                        "quantity": 39000.0,
                        "quantity_unit": "kg",
                        "unit_price": 2850.0,
                        "pricing_unit": "usd/mt",
                        "ship_term": "CIF Nhava Sheva",
                        "delivery_terms": "",
                        "shipment_date": "",
                        "shipping_address": "",
                        "packing": "25 kgs in PP bags",
                        "loading": "",
                        "total": 111150.0,
                    }
                ],
                "do_date": "2026-02-29",
                "po_date": "2026-02-09",
                "po_ref_no": "GIIOFINE - P - S-2026-5",
                "vendor_name": "GIIAVA Singapore Pte Ltd",
                "payment_date": "Net 30D",
                "delivery_terms": "CIF Nhava Sheva",
                "billing_address": "GIIAVA India Pvt Ltd, 70/21A Law College Road Pune 411004 India",
                "shipping_method": "",
                "shipping_address": "C3 MIDC Wai Dist Satara 412803 India",
            }
        ]
    },
    "03__2026-01-30__120363403074656566_g_us__8f477a8f-2a60-4e0a-bf0e-8cc3cdf1dc9f.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "BergaPur",
                        "quantity": 6300.0,
                        "quantity_unit": "kg",
                        "unit_price": 3050.0,
                        "pricing_unit": "usd/mt",
                        "ship_term": "EXW",
                        "delivery_terms": "",
                        "shipment_date": "",
                        "shipping_address": "",
                        "packing": "25kg bags in carton",
                        "loading": "10.5MT / 20'",
                        "total": 19215.0,
                    }
                ],
                "do_date": "2026-03-31",
                "po_date": "2026-01-30",
                "po_ref_no": "BergaPur-2026-6",
                "vendor_name": "GIIAVA Singapore Pte Ltd",
                "payment_date": "7D",
                "delivery_terms": "EXW",
                "billing_address": "Berg + Schmidt Asia Pte Ltd, 1 North Buona Vista Link #10-06 Elementum Singapore 139691",
                "shipping_method": "collection",
                "shipping_address": "Unknown",
            }
        ]
    },
    "04__2026-01-29__120363408498669191_g_us__4b9c2faa-94dd-4236-abcc-398807051f21.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "GIIOFINE - P - S",
                        "quantity": 9000.0,
                        "quantity_unit": "KG",
                        "unit_price": 3.25,
                        "pricing_unit": "USD/KG",
                        "ship_term": "CIF Jakarta",
                        "delivery_terms": "",
                        "shipment_date": "",
                        "shipping_address": "",
                        "packing": "25kg bags in carton",
                        "loading": "25kg bags in carton",
                        "total": 29250.0,
                    }
                ],
                "do_date": "2026-02-28",
                "po_date": "2026-01-29",
                "po_ref_no": "GIIOFINE - P - S-2026-4",
                "vendor_name": "GIIAVA Singapore Pte Ltd",
                "payment_date": "CAD",
                "delivery_terms": "CIF Jakarta",
                "billing_address": "PT Bright International, Plaza Niaga 1 Blok B No 50 Sentul City - Bogor Indonesia",
                "shipping_method": "against PO-IMP-BIB-2601-017",
                "shipping_address": "Plaza Niaga 1 Blok B No 50 Sentul City - Bogor Indonesia",
            }
        ]
    },
    "05__2026-01-20__120363407382355715_g_us__12a4f3a7-d506-4d32-ae06-3f76508c6abd.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "GIIOFINE - P - S",
                        "quantity": 26000.0,
                        "quantity_unit": "KG",
                        "unit_price": 2850.0,
                        "pricing_unit": "USD/MT",
                        "ship_term": "CIF NHAVA SHEVA",
                        "delivery_terms": "",
                        "shipment_date": "",
                        "shipping_address": "",
                        "packing": "",
                        "loading": "",
                        "total": 74100.0,
                    }
                ],
                "do_date": "2026-01-31",
                "po_date": "2026-01-20",
                "po_ref_no": "GIIOFINE - P - S-2026-3",
                "vendor_name": "GIIAVA Singapore Pte Ltd",
                "payment_date": "Net 30D",
                "delivery_terms": "CIF NHAVA SHEVA",
                "billing_address": "GIIAVA India Pvt Ltd, 70/21A Law College Road Pune 411004 India",
                "shipping_method": "",
                "shipping_address": "C3 MIDC Wai Dist Satara 412803 India",
            }
        ]
    },
    "06__2026-01-06__120363421131250401_g_us__e05574ec-b110-4554-9fc3-3abb4f9011a8.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "GIIOFINE - P - S",
                        "quantity": 1800.0,
                        "quantity_unit": "kg",
                        "unit_price": 3500.0,
                        "pricing_unit": "usd/mt",
                        "ship_term": "EXW",
                        "delivery_terms": "",
                        "shipment_date": "",
                        "shipping_address": "",
                        "packing": "",
                        "loading": "LCL",
                        "total": 6300.0,
                    }
                ],
                "do_date": "2026-02-28",
                "po_date": "2026-01-06",
                "po_ref_no": "GIIOFINE - P - S-2026-2",
                "vendor_name": "GIIAVA Singapore Pte Ltd",
                "payment_date": "Advanced payment",
                "delivery_terms": "EXW",
                "billing_address": "Epic Chemicals Sdn Bhd, 17 Jalan Industri Mas 12,Taman Mas Sepang,47130 Puchong,Selangor,Malaysia",
                "shipping_method": "",
                "shipping_address": "17 Jalan Industri Mas 12,Taman Mas Sepang,47130 Puchong,Selangor,Malaysia",
            }
        ]
    },
    "07__2025-12-23__120363403074656566_g_us__8f477a8f-2a60-4e0a-bf0e-8cc3cdf1dc9f.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "BergaPur",
                        "quantity": 10500.0,
                        "quantity_unit": "kg",
                        "unit_price": 3100.0,
                        "pricing_unit": "usd/mt",
                        "ship_term": "EXW",
                        "delivery_terms": "",
                        "shipment_date": "",
                        "shipping_address": "",
                        "packing": "standard packaging",
                        "loading": "10.5MT / 20'",
                        "total": 32550.0,
                    }
                ],
                "do_date": "2026-01-31",
                "po_date": "2025-12-23",
                "po_ref_no": "BergaPur-2025-4",
                "vendor_name": "GIIAVA Singapore Pte Ltd",
                "payment_date": "7D",
                "delivery_terms": "EXW",
                "billing_address": "Berg + Schmidt Asia Pte Ltd, 1 North Buona Vista Link #10-06 Elementum Singapore 139691",
                "shipping_method": "",
                "shipping_address": "NA",
            }
        ]
    },
    "08__2025-09-29__120363403592950429_g_us__d586d853-694c-42f9-93be-bc7ba5b2110c.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "TG - BP102",
                        "quantity": 46000.0,
                        "quantity_unit": "kg",
                        "unit_price": 1410.0,
                        "pricing_unit": "usd/mt",
                        "ship_term": "CIF",
                        "delivery_terms": "",
                        "shipment_date": "",
                        "shipping_address": "",
                        "packing": "25kg printed paper bags",
                        "loading": "23 MT / 40' FCL",
                        "total": 64860.0,
                    }
                ],
                "do_date": "2025-11-15",
                "po_date": "2025-09-29",
                "po_ref_no": "TG - BP102-2025-3",
                "vendor_name": "AG Lipids Pte Ltd",
                "payment_date": "Net 14 Days",
                "delivery_terms": "CIF",
                "billing_address": "FeedBEST Company Limited, Factory 354-58 Mojeon-1 Sobuk-gu Republic of Korea",
                "shipping_method": "Unknown",
                "shipping_address": "Factory 354-58 Mojeon-1 Sobuk-gu Republic of Korea",
            }
        ]
    },
    "09__2025-09-29__120363403592950429_g_us__d586d853-694c-42f9-93be-bc7ba5b2110c.json": {
        "data": [
            {
                "items": [
                    {
                        "sr_no": 1,
                        "description": "TG - BP102",
                        "quantity": 23000.0,
                        "quantity_unit": "kg",
                        "unit_price": 1410.0,
                        "pricing_unit": "usd/mt",
                        "ship_term": "CIF",
                        "delivery_terms": "",
                        "shipment_date": "",
                        "shipping_address": "",
                        "packing": "25kg printed paper bag",
                        "loading": "23 MT / 40' FCL",
                        "total": 32430.0,
                    }
                ],
                "do_date": "2025-11-15",
                "po_date": "2025-09-29",
                "po_ref_no": "TG - BP102-2025-1",
                "vendor_name": "AG Lipids Pte Ltd",
                "payment_date": "Net 14 Days",
                "delivery_terms": "CIF",
                "billing_address": "FeedBEST Company Limited, Factory 354-58 Mojeon-1 Sobuk-gu Republic of Korea",
                "shipping_method": "Unknown",
                "shipping_address": "Factory 354-58 Mojeon-1 Sobuk-gu Republic of Korea",
            }
        ]
    },
}


def get_expected_for_chat(chat_filename: str) -> dict | None:
    """Return expected contract data for a chat file, or None if not defined."""
    name = chat_filename if chat_filename.endswith(".json") else f"{chat_filename}.json"
    return EXPECTED_BY_CHAT.get(name)
