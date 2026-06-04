import pytest
from unittest.mock import patch
from graph.kuzu_backend import KuzuBackend
from graph.qa import answer_question

_EP = {
    "source_id": "customers/acme_foods/chats/ep1",
    "customer_id": "acme_foods",
    "timestamp": 1000,
    "entities": {
        "products": [{"name": "KNM Coffee", "quantity": 10.0, "unit": "bags",
                      "price": 25.0, "price_unit": "USD/bag", "incoterm": "FOB", "port": "Singapore"}],
        "ports": ["Singapore"],
        "payment_terms": "Net 30",
        "packing": "25kg PP bags",
        "loading": "1x20 FCL",
    },
}


@pytest.fixture
def backend(tmp_path):
    b = KuzuBackend(db_path=tmp_path / "qa.db")
    b.write_episode(_EP)
    yield b
    b.close()


def test_answer_question_refuses_empty_customer(backend):
    with pytest.raises(ValueError, match="customer_id"):
        answer_question("", "What products?", backend)


def test_answer_question_returns_no_history_for_unknown(backend):
    result = answer_question("unknown_customer", "What products?", backend)
    assert "no history" in result.lower() or "no data" in result.lower()


def test_answer_question_calls_llm(backend, monkeypatch):
    monkeypatch.setattr(
        "graph.qa.call_llm_text",
        lambda prompt, model_key: "Based on history, acme_foods buys KNM Coffee."
    )
    result = answer_question("acme_foods", "What products does this customer buy?", backend)
    assert "KNM Coffee" in result or "acme_foods" in result
