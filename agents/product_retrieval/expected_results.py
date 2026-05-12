"""Expected product-spec retrievals per chat file.

Each entry maps a chat filename to the list of doc ids that the retrieval
agent should surface in its top-K results. Add entries by hand (or via
``python -m harness.seed_expected --agent product_retrieval ...`` once the
retrieval backend is implemented).
"""

EXPECTED_BY_CHAT: dict[str, list[str]] = {
    # "single_product_single_shipment_simple.json": ["coffee/knm_coffee_spec.pdf"],
}


def get_expected_doc_ids(chat_filename: str) -> list[str] | None:
    name = chat_filename if chat_filename.endswith(".json") else f"{chat_filename}.json"
    return EXPECTED_BY_CHAT.get(name)
