"""Unit tests for the scoring helpers in test_memory_extraction.py."""
from __future__ import annotations

import pytest

from graph.extractor import ExtractedFacts, ExtractedProduct
from tests.test_memory_extraction import _score_facts, _score_product, _find_best_product_match


def test_score_facts_perfect_match():
    expected = {
        "products": [{"name": "KISAN Coffee", "quantity": 10.0, "unit": "bags",
                      "price": 25.0, "price_unit": "USD/bag", "incoterm": "FOB", "port": "Singapore"}],
        "ports": ["Singapore"],
        "payment_terms": "Net 15",
        "packing": "",
        "loading": "",
    }
    actual = ExtractedFacts(
        products=[ExtractedProduct(name="KISAN Coffee", quantity=10.0, unit="bags",
                                   price=25.0, price_unit="USD/bag", incoterm="FOB", port="Singapore")],
        ports=["Singapore"],
        payment_terms="Net 15",
        packing="",
        loading="",
    )
    assert _score_facts(expected, actual) == 1.0


def test_score_facts_missing_price():
    expected = {
        "products": [{"name": "GIIOFEED PL-5", "quantity": 2.0, "unit": "MT",
                      "price": 1420.0, "price_unit": "USD/MT", "incoterm": "CIF", "port": "Busan"}],
        "ports": ["Busan"],
        "payment_terms": "",
        "packing": "",
        "loading": "",
    }
    actual = ExtractedFacts(
        products=[ExtractedProduct(name="GIIOFEED PL-5", quantity=2.0, unit="MT",
                                   price=None, price_unit=None, incoterm="CIF", port="Busan")],
        ports=["Busan"],
        payment_terms="",
        packing="",
        loading="",
    )
    score = _score_facts(expected, actual)
    # 7 product fields (name, qty, unit, price, price_unit, incoterm, port)
    # + 1 port = 8 total; price and price_unit missing → 6/8 = 0.75
    assert score == pytest.approx(6 / 8)


def test_score_facts_no_product_found():
    expected = {
        "products": [{"name": "BP102", "quantity": 23.0, "unit": "MT",
                      "price": 1425.0, "price_unit": "USD/MT", "incoterm": "CIF", "port": "Busan"}],
        "ports": ["Busan"],
        "payment_terms": "",
        "packing": "",
        "loading": "",
    }
    actual = ExtractedFacts(products=[], ports=[], payment_terms="", packing="", loading="")
    score = _score_facts(expected, actual)
    assert score == 0.0


def test_find_best_product_match_case_insensitive():
    products = [ExtractedProduct(name="giiofeed pl-5")]
    result = _find_best_product_match({"name": "GIIOFEED PL-5"}, products)
    assert result is not None
    assert result.name == "giiofeed pl-5"
