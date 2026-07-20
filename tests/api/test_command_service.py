import mongomock
import pytest

from apps.api.db import mongo
from apps.api.services import chat_service, command_service
from tests.api._factories import make_extract, make_item, make_update


def _seed_data() -> None:
    for cid in ("dummy-01", "dummy-02", "dummy-03"):
        mongo.customers().insert_one(
            {"_id": cid, "name": cid, "profile": {}, "last_contract_seq": 0, "updated_at": "now"}
        )
    mongo.products().insert_one(
        {"_id": "TG-BPPC", "code": "TG-BPPC", "description": "Rumen bypass", "spec": None}
    )


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    _seed_data()
    yield
    mongo.reset_client()


def _fake_summary(*a, **k):
    return make_extract(items=[make_item(description="TG-BPPC", quantity=10, quantity_unit="MT")])


def _fake_revision(*a, **k):
    return make_update(items=[make_item(description="TG-BPPC", quantity=20, quantity_unit="MT")])


def _ctx(*a, **k):
    return {"profile_block": "PROFILE", "history_block": "HISTORY", "product_block": "CATALOG"}


def _record_graph(order):
    def _fn(customer_id, chat_id, chat_title, contract, slots, source_seqs, to_seq):
        order.append(("graph", to_seq))
        return "contract-id"
    return _fn


def _chat(customer_id="dummy-01"):
    return chat_service.ensure_default_chat(customer_id)


def test_create_posts_pending_without_graph_write():
    ch = _chat()
    order = []
    chat_service.add_message("dummy-01", ch, "me", "need 10MT TG-BPPC")   # seq 1
    chat_service.add_message("dummy-01", ch, "customer", "ok")            # seq 2

    def _gen(*a, **k):
        order.append(("summary", None))
        return _fake_summary()

    out = command_service.dispatch("dummy-01", "create-sales-order", None, "sonnet-4-6",
                                   graph_fn=_record_graph(order), summary_gen=_gen, context_fn=_ctx)

    assert [step[0] for step in order] == ["summary"]  # no graph write on create
    assert out["summary"]["status"] == "pending"
    assert out["summary"]["chat_id"] == ch
    assert mongo.summaries().count_documents({"status": "pending"}) == 1
    # the raw model response (JSON) is shared alongside the rendered card
    card = out["messages"][-1]
    assert card["kind"] == "summary"
    assert card["summary_json"] and '"data"' in card["summary_json"]


def test_create_blocked_when_pending_exists():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "me", "x")
    command_service.dispatch("dummy-01", "create-sales-order", None, "sonnet-4-6",
                             summary_gen=_fake_summary, context_fn=_ctx)
    out = command_service.dispatch("dummy-01", "create-sales-order", None, "sonnet-4-6",
                                   summary_gen=_fake_summary, context_fn=_ctx)
    assert out["summary"] is None
    assert "pending" in out["messages"][-1]["body"].lower()


def test_approve_advances_checkpoint_and_persists():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "me", "x")   # seq 1
    command_service.dispatch("dummy-01", "create-sales-order", None, "sonnet-4-6",
                             summary_gen=_fake_summary, context_fn=_ctx)
    command_service.dispatch("dummy-01", "approve", None, "sonnet-4-6",
                             graph_fn=_record_graph([]))
    assert chat_service.get_last_contract_seq(ch) == 1
    assert mongo.summaries().count_documents({"status": "approved"}) == 1
    assert mongo.summaries().count_documents({"status": "pending"}) == 0


def test_edit_requires_pending_and_bumps_revision():
    ch = _chat()
    chat_service.add_message("dummy-01", ch, "me", "x")
    command_service.dispatch("dummy-01", "create-sales-order", None, "sonnet-4-6",
                             summary_gen=_fake_summary, context_fn=_ctx)
    command_service.dispatch("dummy-01", "edit", "qty 20", "sonnet-4-6",
                             summary_revise=_fake_revision, context_fn=_ctx)
    pending = mongo.summaries().find_one({"status": "pending"})
    assert pending["revision"] == 1
    assert pending["content"]["data"][0]["items"][0]["quantity"] == 20


def test_create_forwards_context_blocks_to_summary_gen():
    ch = _chat()
    captured = {}
    chat_service.add_message("dummy-01", ch, "me", "need 10MT TG-BPPC")

    def _gen(name, window, product_block, model_key, *, profile_block=None, history_block=None, **k):
        captured.update(product_block=product_block, profile_block=profile_block,
                        history_block=history_block)
        return _fake_summary()

    command_service.dispatch("dummy-01", "create-sales-order", None, "sonnet-4-6",
                             summary_gen=_gen, context_fn=_ctx)
    assert captured == {"product_block": "CATALOG", "profile_block": "PROFILE",
                        "history_block": "HISTORY"}


def test_edit_forwards_context_blocks_to_summary_revise():
    ch = _chat()
    captured = {}
    chat_service.add_message("dummy-01", ch, "me", "x")
    command_service.dispatch("dummy-01", "create-sales-order", None, "sonnet-4-6",
                             summary_gen=_fake_summary, context_fn=_ctx)

    def _rev(name, previous, instructions, window, model_key, *, product_block=None,
             profile_block=None, history_block=None, **k):
        captured.update(product_block=product_block, profile_block=profile_block,
                        history_block=history_block)
        return _fake_revision()

    command_service.dispatch("dummy-01", "edit", "qty 20", "sonnet-4-6",
                             summary_revise=_rev, context_fn=_ctx)
    assert captured == {"product_block": "CATALOG", "profile_block": "PROFILE",
                        "history_block": "HISTORY"}
