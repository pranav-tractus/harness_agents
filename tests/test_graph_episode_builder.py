import json
import pathlib
import pytest
from graph.episode_builder import build_episode, infer_customer_id


RAW_DATA = pathlib.Path(__file__).resolve().parents[1] / "raw_data"


def test_infer_customer_from_customers_dir(tmp_path):
    chat_path = tmp_path / "raw_data" / "customers" / "acme_foods" / "chats" / "test.json"
    chat_path.parent.mkdir(parents=True)
    chat_path.write_text('{"customer_id": "acme_foods", "messages": []}')
    assert infer_customer_id(chat_path) == "acme_foods"


def test_infer_customer_from_downloaded_chats_json(tmp_path):
    chat_path = (
        tmp_path / "raw_data" / "downloaded_chats" /
        "01__2025-07-12__120363400604184610_g_us__c53c0007-bbd6-4474-8348-b011992829f8.json"
    )
    chat_path.parent.mkdir(parents=True)
    chat_path.write_text(json.dumps({"customer_id": "c53c0007-bbd6-4474-8348-b011992829f8", "chats": []}))
    assert infer_customer_id(chat_path) == "c53c0007-bbd6-4474-8348-b011992829f8"


def test_infer_customer_generic_for_chats_dir(tmp_path):
    chat_path = tmp_path / "raw_data" / "chats" / "some_chat.json"
    chat_path.parent.mkdir(parents=True)
    chat_path.write_text("{}")
    assert infer_customer_id(chat_path) == "generic"


def test_build_episode_from_standard_messages(tmp_path):
    chat_path = tmp_path / "raw_data" / "customers" / "acme_foods" / "chats" / "test.json"
    chat_path.parent.mkdir(parents=True)
    chat_path.write_text(json.dumps({
        "customer_id": "acme_foods",
        "messages": [
            {"from_whom": "(TEAM1)", "body": "Price is 25 USD/bag", "timestamp": 1000},
            {"from_whom": "(TEAM2)", "body": "Confirmed", "timestamp": 1001},
        ]
    }))
    raw_data_dir = tmp_path / "raw_data"
    episode = build_episode(chat_path, raw_data_dir)
    assert episode["customer_id"] == "acme_foods"
    assert episode["timestamp"] == 1000
    assert "(TEAM1): Price is 25 USD/bag" in episode["content"]
    assert episode["source_id"] == "customers/acme_foods/chats/test"


def test_build_episode_from_downloaded_chat(tmp_path):
    chat_path = (
        tmp_path / "raw_data" / "downloaded_chats" /
        "01__2025-07-12__120363400604184610_g_us__abc123.json"
    )
    chat_path.parent.mkdir(parents=True)
    chat_path.write_text(json.dumps({
        "customer_id": "abc123",
        "chats": [
            [{"from_me": False, "text": {"body": "raw msg"}, "timestamp": 999, "from_name": "Alice"}],
            [{"from_whom": "(TEAM1)", "body": "Processed msg", "timestamp": 1000}],
        ]
    }))
    raw_data_dir = tmp_path / "raw_data"
    episode = build_episode(chat_path, raw_data_dir)
    assert episode["customer_id"] == "abc123"
    assert "Processed msg" in episode["content"]
    assert episode["timestamp"] == 1000


def test_build_episode_real_acme_file():
    """Integration: builds episode from the real acme_foods fixture."""
    path = RAW_DATA / "customers" / "acme_foods" / "chats" / "fs_acme_simple.json"
    if not path.exists():
        pytest.skip("raw_data not available")
    episode = build_episode(path, RAW_DATA)
    assert episode["customer_id"] == "acme_foods"
    assert len(episode["content"]) > 0
    assert episode["source_id"].startswith("customers/acme_foods")
