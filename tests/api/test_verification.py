import pytest
from pydantic import ValidationError

from apps.api.verification import Violation, has_blocking, verify
from tests.api._factories import make_extract, make_item


def test_clean_contract_has_no_violations():
    contract = make_extract(items=[make_item(description="TG-BPPC", ship_term="CIF")])
    slots = [{"slot": "ship_term", "value": "CIF", "source": "chat", "source_seqs": [1]}]
    assert verify(contract, slots, resolved_codes={"TG-BPPC"}, window_seqs={1}) == []


def test_unknown_product_code_blocks():
    contract = make_extract(items=[make_item(description="GHOST-1")])
    v = verify(contract, [], resolved_codes={"TG-BPPC"}, window_seqs=set())
    assert has_blocking(v)
    assert any(x.code == "unknown_product_code" for x in v)


def test_resolved_codes_none_skips_product_check():
    contract = make_extract(items=[make_item(description="GHOST-1")])
    v = verify(contract, [], resolved_codes=None, window_seqs=set())
    assert not any(x.code == "unknown_product_code" for x in v)


def test_bad_ship_term_blocks():
    contract = make_extract(items=[make_item(description="TG-BPPC", ship_term="CIFF")])
    v = verify(contract, [], resolved_codes={"TG-BPPC"}, window_seqs=set())
    assert any(x.code == "bad_ship_term" and x.severity == "block" for x in v)


def test_empty_ship_term_blocks():
    contract = make_extract(items=[make_item(description="TG-BPPC", ship_term="")])
    v = verify(contract, [], resolved_codes={"TG-BPPC"}, window_seqs=set())
    assert any(x.code == "missing_ship_term" and x.severity == "block" for x in v)
    assert has_blocking(v)


def test_violation_severity_rejects_unknown_value():
    with pytest.raises(ValidationError):
        Violation(code="x", message="y", severity="bogus")


def test_total_mismatch_warns_but_does_not_block():
    contract = make_extract(items=[make_item(
        description="TG-BPPC", ship_term="CIF",
        quantity=10.0, unit_price=100.0, total=999.0)])
    v = verify(contract, [], resolved_codes={"TG-BPPC"}, window_seqs=set())
    assert any(x.code == "total_mismatch" and x.severity == "warn" for x in v)
    assert not has_blocking(v)


def test_non_chat_critical_source_blocks():
    contract = make_extract(items=[make_item(description="TG-BPPC", ship_term="CIF")])
    slots = [{"slot": "quantity", "value": "10", "source": "last_order", "source_seqs": []}]
    v = verify(contract, slots, resolved_codes={"TG-BPPC"}, window_seqs=set())
    assert any(x.code == "critical_not_chat_sourced" and x.severity == "block" for x in v)


def test_ship_term_case_insensitive():
    contract = make_extract(items=[make_item(description="TG-BPPC", ship_term="cif")])
    v = verify(contract, [], resolved_codes={"TG-BPPC"}, window_seqs=set())
    assert not any(x.code in ("bad_ship_term", "missing_ship_term") for x in v)


def test_critical_slot_unknown_source_blocks():
    contract = make_extract(items=[make_item(description="TG-BPPC")])
    slots = [{"slot": "quantity", "value": "10", "source": "unknown", "source_seqs": []}]
    v = verify(contract, slots, resolved_codes={"TG-BPPC"}, window_seqs=set())
    assert any(x.code == "critical_unknown_source" and x.severity == "block" for x in v)


def test_chat_slot_without_citation_blocks():
    contract = make_extract(items=[make_item(description="TG-BPPC")])
    slots = [{"slot": "unit_price", "value": "100", "source": "chat", "source_seqs": []}]
    v = verify(contract, slots, resolved_codes={"TG-BPPC"}, window_seqs={1})
    assert any(x.code == "missing_provenance" and x.severity == "block" for x in v)
    assert has_blocking(v)


def test_stale_citation_warns():
    contract = make_extract(items=[make_item(description="TG-BPPC", ship_term="CIF")])
    slots = [{"slot": "ship_term", "value": "CIF", "source": "chat", "source_seqs": [99]}]
    v = verify(contract, slots, resolved_codes={"TG-BPPC"}, window_seqs={1, 2})
    assert any(x.code == "stale_citation" and x.severity == "warn" for x in v)
