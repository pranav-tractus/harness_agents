import json
import pathlib
import pytest
from unittest.mock import patch
from graph.extractor import ExtractedFacts, ExtractedProduct
from graph.kuzu_backend import KuzuBackend
from graph.ingestion import ingest_all


@pytest.fixture
def fake_raw_data(tmp_path):
    for cid, product in [("acme_foods", "KNM Coffee"), ("nova_exports", "Palm Oil")]:
        chat_dir = tmp_path / "raw_data" / "customers" / cid / "chats"
        chat_dir.mkdir(parents=True)
        (chat_dir / "ep001.json").write_text(json.dumps({
            "customer_id": cid,
            "messages": [
                {"from_whom": "(TEAM1)", "body": f"100 MT {product} @ USD 300/MT CIF Singapore", "timestamp": 1000},
                {"from_whom": "(TEAM2)", "body": "Confirmed. Net 30.", "timestamp": 1001},
            ]
        }))
    return tmp_path / "raw_data"


def _fake_extract(chat_text, model_key="claude-sonnet-4-6"):
    product_name = "KNM Coffee" if "KNM Coffee" in chat_text else "Palm Oil"
    return ExtractedFacts(
        products=[ExtractedProduct(name=product_name, quantity=100.0, unit="MT",
                                   price=300.0, price_unit="USD/MT",
                                   incoterm="CIF", port="Singapore")],
        ports=["Singapore"],
        payment_terms="Net 30",
        packing="",
        loading="",
    )


def test_ingest_all_writes_to_backend(fake_raw_data, tmp_path):
    backend = KuzuBackend(db_path=tmp_path / "test.db")
    with patch("graph.ingestion.extract_entities", side_effect=_fake_extract):
        count = ingest_all(fake_raw_data, backend, model_key="claude-sonnet-4-6")
    assert count == 2
    acme = backend.query_customer("acme_foods")
    assert any(r.get("product_name") == "KNM Coffee" for r in acme)
    backend.close()


def test_ingest_all_idempotent(fake_raw_data, tmp_path):
    backend = KuzuBackend(db_path=tmp_path / "test.db")
    with patch("graph.ingestion.extract_entities", side_effect=_fake_extract):
        first = ingest_all(fake_raw_data, backend, model_key="claude-sonnet-4-6")
        second = ingest_all(fake_raw_data, backend, model_key="claude-sonnet-4-6")
    assert first == 2
    assert second == 0  # all already ingested
    backend.close()


def test_ingest_all_skips_empty_content(tmp_path):
    raw = tmp_path / "raw_data" / "chats"
    raw.mkdir(parents=True)
    (raw / "empty.json").write_text(json.dumps({"messages": []}))
    backend = KuzuBackend(db_path=tmp_path / "test.db")
    with patch("graph.ingestion.extract_entities", return_value=ExtractedFacts()):
        count = ingest_all(tmp_path / "raw_data", backend)
    backend.close()
    assert count == 0  # skipped because content is empty
