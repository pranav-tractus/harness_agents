import pytest

from apps.api.services import spec_ingest_service as si


def _line(text):
    return {"Id": f"line-{text}", "BlockType": "LINE", "Text": text}


def _word(wid, text):
    return {"Id": wid, "BlockType": "WORD", "Text": text}


def _cell(cid, row, col, word_ids):
    return {"Id": cid, "BlockType": "CELL", "RowIndex": row, "ColumnIndex": col,
            "Relationships": [{"Type": "CHILD", "Ids": word_ids}]}


def _table(cell_ids):
    return {"Id": "t1", "BlockType": "TABLE",
            "Relationships": [{"Type": "CHILD", "Ids": cell_ids}]}


def test_render_blocks_lines_and_table_grid():
    blocks = [
        _line("Sunflower Lecithin Powder"),
        _line("Product Data Sheet"),
        _table(["c1", "c2", "c3", "c4"]),
        _cell("c1", 1, 1, ["w1"]), _cell("c2", 1, 2, ["w2"]),
        _cell("c3", 2, 1, ["w3"]), _cell("c4", 2, 2, ["w4", "w5"]),
        _word("w1", "Moisture"), _word("w2", "≤2%"),
        _word("w3", "Acetone"), _word("w4", "insoluble"), _word("w5", "≥95%"),
    ]
    text = si.render_blocks(blocks)
    assert "Sunflower Lecithin Powder\nProduct Data Sheet" in text
    assert "## Tables" in text
    assert "Moisture | ≤2%" in text
    assert "Acetone | insoluble ≥95%" in text


def test_render_blocks_without_tables_has_no_tables_header():
    assert "## Tables" not in si.render_blocks([_line("hello")])


class FakeTextract:
    def __init__(self):
        self.pages = [
            {"JobStatus": "IN_PROGRESS"},
            {"JobStatus": "SUCCEEDED", "Blocks": [_line("page one")], "NextToken": "tok"},
            {"JobStatus": "SUCCEEDED", "Blocks": [_line("page two")]},
        ]
        self.start_kwargs = None
        self.get_calls = []

    def start_document_analysis(self, **kw):
        self.start_kwargs = kw
        return {"JobId": "job-1"}

    def get_document_analysis(self, **kw):
        self.get_calls.append(kw)
        return self.pages.pop(0)


def test_textract_text_polls_and_paginates():
    client = FakeTextract()
    text = si.textract_text("bkt", "specs/x.pdf", client=client, poll_interval=0)
    assert "page one" in text and "page two" in text
    assert client.start_kwargs == {
        "DocumentLocation": {"S3Object": {"Bucket": "bkt", "Name": "specs/x.pdf"}},
        "FeatureTypes": ["TABLES"],
    }
    assert client.get_calls[-1]["NextToken"] == "tok"


def test_textract_text_raises_on_failed_job():
    class FailTextract(FakeTextract):
        def __init__(self):
            self.pages = [{"JobStatus": "FAILED", "StatusMessage": "bad pdf"}]
            self.get_calls = []

    with pytest.raises(RuntimeError, match="bad pdf"):
        si.textract_text("bkt", "specs/x.pdf", client=FailTextract(), poll_interval=0)
