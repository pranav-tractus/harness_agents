import mongomock
import pytest
from fastapi.testclient import TestClient

from apps.api import seed
from apps.api.db import mongo
from apps.api.services import product_embedding_service


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    seed.seed_all()
    calls = []
    monkeypatch.setattr(product_embedding_service, "build_from_doc",
                        lambda doc, **k: calls.append(doc["code"]))
    monkeypatch.setattr(product_embedding_service, "status_for_doc",
                        lambda doc: "not built")
    from apps.api.main import create_app
    with TestClient(create_app()) as c:
        c.calls = calls
        yield c


def test_build_single(client):
    r = client.post("/api/products/TG-BPPC/build")
    assert r.status_code == 200
    assert "TG-BPPC" in client.calls


def test_create_does_not_autosync(client):
    client.post("/api/products", json={"code": "NEW-1", "short_description": "x", "spec": None})
    assert "NEW-1" not in client.calls   # build only happens on explicit request
