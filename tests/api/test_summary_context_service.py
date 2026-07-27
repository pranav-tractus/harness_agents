from apps.api.services import summary_context_service as scs


def test_assemble_composes_three_blocks_from_injected_readers():
    out = scs.assemble(
        "dummy-01",
        profile_reader=lambda cid: f"profile:{cid}",
        history_reader=lambda cid: f"history:{cid}",
        product_reader=lambda: "products",
    )
    assert out == {
        "profile_block": "profile:dummy-01",
        "history_block": "history:dummy-01",
        "product_block": "products",
    }


def test_assemble_passes_through_none_blocks():
    out = scs.assemble(
        "dummy-01",
        profile_reader=lambda cid: None,
        history_reader=lambda cid: None,
        product_reader=lambda: None,
    )
    assert out == {"profile_block": None, "history_block": None, "product_block": None}


def test_assemble_defaults_product_block_to_none():
    out = scs.assemble(
        "dummy-01",
        profile_reader=lambda cid: None,
        history_reader=lambda cid: None,
    )
    assert out["product_block"] is None
