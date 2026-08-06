import re

import mongomock
import pytest

from apps.api.db import mongo
from apps.api.db.vectors import InMemoryIndex
from apps.api.services import spec_ingest_service as si
from apps.api.services.spec_ingest_service import ProductSpec


@pytest.fixture(autouse=True)
def _fake_mongo(monkeypatch):
    monkeypatch.setattr(mongo, "_client", mongomock.MongoClient())
    monkeypatch.setenv("SPECS_S3_BUCKET", "spec-bucket")
    from apps.api import settings as settings_mod
    settings_mod.get_settings.cache_clear()
    yield
    settings_mod.get_settings.cache_clear()
    mongo.reset_client()


_SPEC = ProductSpec(
    code="GIIOFEED-PL5", name="Feed Lecithin PL5",
    short_description="Soy lecithin for animal feed",
    long_description="Liquid soy lecithin for feed mills.",
    spec="AI >= 60%", metadata={"form": "liquid"})


def _fake_llm(spec=_SPEC):
    return lambda prompt, schema, model_key, system_prompt=None: spec


def _fake_embed(texts, *, mode="document"):
    return [[1.0, 0.0] for _ in texts]


def _deps(tmp_path, **over):
    pdf = tmp_path / "GIIOFEED PL5.pdf"
    pdf.write_bytes(b"%PDF fake")
    deps = dict(
        upload_fn=lambda path, bucket, key: None,
        textract_fn=lambda bucket, key: "GIIOFEED PL5 spec text",
        llm=_fake_llm(),
        embed_fn=_fake_embed,
        index=InMemoryIndex(),
    )
    deps.update(over)
    return pdf, deps


def test_extract_spec_falls_back_to_filename_slug():
    spec = si.extract_spec("text", "GIIOFINE_L_SF .pdf", llm=_fake_llm(
        ProductSpec(name="Sunflower Lecithin Liquid", short_description="x")))
    assert spec.code == "GIIOFINE-L-SF"


@pytest.mark.parametrize("raw,expected", [
    ("15100105", "15100105"),
    ("  15100105  ", "15100105"),
    ("1510010515022, 15100105", "15100105"),
    ("1510011525700, 1510011590600, 15100115", "15100115"),
    ("100087401; 100087402", "100087401"),
    ("110028323 ; 110034824", "110028323"),
    ("A-1,,A-22", "A-1"),
])
def test_canonical_code_reduces_to_one_code(raw, expected):
    assert si._canonical_code(raw) == expected


def test_canonical_code_of_blank_is_blank():
    assert si._canonical_code("   ") == ""
    assert si._canonical_code(",  ;") == ""


def test_extract_spec_canonicalizes_a_multi_code_sheet():
    spec = si.extract_spec("text", "Krystar450.pdf", llm=_fake_llm(
        ProductSpec(code="1510010515022, 15100105", name="KRYSTAR 450",
                    short_description="x")))
    assert spec.code == "15100105"


def test_extract_spec_falls_back_to_slug_when_codes_are_all_blank():
    spec = si.extract_spec("text", "GIIOFINE_L_SF .pdf", llm=_fake_llm(
        ProductSpec(code=" , ; ", name="Sunflower Lecithin Liquid",
                    short_description="x")))
    assert spec.code == "GIIOFINE-L-SF"


def test_ingest_writes_product_and_vectors(tmp_path):
    pdf, deps = _deps(tmp_path)
    report = si.ingest_pdf(pdf, **deps)
    assert report.status == "ingested"
    assert report.code == "GIIOFEED-PL5"
    doc = mongo.products().find_one({"_id": "GIIOFEED-PL5"})
    assert doc["name"] == "Feed Lecithin PL5"
    assert doc["source_pdf"] == "specs/GIIOFEED PL5.pdf"
    assert doc["source_pdf_hash"]
    assert doc["embedded_hash"]
    assert doc["source_label"] == "OG Files"
    assert not any("#alias" in k for k in deps["index"]._store)


def test_ingest_skips_unchanged_pdf(tmp_path):
    pdf, deps = _deps(tmp_path)
    si.ingest_pdf(pdf, **deps)
    called = {"n": 0}

    def _counting_textract(bucket, key):
        called["n"] += 1
        return "text"

    report = si.ingest_pdf(pdf, **{**deps, "textract_fn": _counting_textract})
    assert report.status == "skipped"
    assert called["n"] == 0


def test_force_reingests_unchanged_pdf(tmp_path):
    pdf, deps = _deps(tmp_path)
    si.ingest_pdf(pdf, **deps)
    report = si.ingest_pdf(pdf, force=True, **deps)
    assert report.status == "ingested"


def test_dry_run_extracts_but_writes_nothing(tmp_path):
    pdf, deps = _deps(tmp_path)
    report = si.ingest_pdf(pdf, dry_run=True, **deps)
    assert report.status == "dry-run"
    assert report.code == "GIIOFEED-PL5"
    assert mongo.products().count_documents({}) == 0
    assert deps["index"]._store == {}


def test_failure_is_reported_not_raised(tmp_path):
    def _boom(bucket, key):
        raise RuntimeError("textract exploded")

    pdf, deps = _deps(tmp_path, textract_fn=_boom)
    report = si.ingest_pdf(pdf, **deps)
    assert report.status == "failed"
    assert "textract exploded" in report.error


def test_ingest_folder_sweeps_and_continues(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"%PDF a")
    (tmp_path / "b.pdf").write_bytes(b"%PDF b")
    calls = []

    def _llm_by_file(prompt, schema, model_key, system_prompt=None):
        calls.append(1)
        n = len(calls)
        return ProductSpec(code=f"P-{n}", name=f"Prod {n}", short_description="s")

    reports = si.ingest_folder(
        tmp_path,
        upload_fn=lambda path, bucket, key: None,
        textract_fn=lambda bucket, key: "text",
        llm=_llm_by_file, embed_fn=_fake_embed, index=InMemoryIndex())
    assert [r.status for r in reports] == ["ingested", "ingested"]
    assert mongo.products().count_documents({}) == 2


def test_upsert_preserves_embedding_bookkeeping():
    mongo.products().insert_one({
        "_id": "GIIOFEED-PL5", "code": "GIIOFEED-PL5",
        "short_description": "old", "embedded_hash": "h", "vector_keys": ["k"]})
    si.upsert_product(_SPEC, source_pdf="specs/x.pdf", pdf_hash="ph")
    doc = mongo.products().find_one({"_id": "GIIOFEED-PL5"})
    assert doc["short_description"] == "Soy lecithin for animal feed"
    assert doc["embedded_hash"] == "h" and doc["vector_keys"] == ["k"]


def test_upsert_defaults_source_label_to_og_files():
    si.upsert_product(_SPEC, source_pdf="specs/x.pdf", pdf_hash="ph")
    doc = mongo.products().find_one({"_id": "GIIOFEED-PL5"})
    assert doc["source_label"] == "OG Files"


def test_upsert_accepts_explicit_source_label():
    si.upsert_product(_SPEC, source_pdf="s3://ext-bucket/x.pdf", pdf_hash="ph", source_label="Test Files")
    doc = mongo.products().find_one({"_id": "GIIOFEED-PL5"})
    assert doc["source_label"] == "Test Files"


def _fake_s3_deps(**over):
    deps = dict(
        get_bytes_fn=lambda bucket, key: b"%PDF fake",
        textract_fn=lambda bucket, key: "GIIOFEED PL5 spec text",
        llm=_fake_llm(),
        embed_fn=_fake_embed,
        index=InMemoryIndex(),
    )
    deps.update(over)
    return deps


def test_ingest_pdf_from_s3_writes_product_with_test_files_label():
    deps = _fake_s3_deps()
    report = si.ingest_pdf_from_s3("ext-bucket", "incoming/GIIOFEED PL5.pdf", **deps)
    assert report.status == "ingested"
    assert report.code == "GIIOFEED-PL5"
    doc = mongo.products().find_one({"_id": "GIIOFEED-PL5"})
    assert doc["source_pdf"] == "s3://ext-bucket/incoming/GIIOFEED PL5.pdf"
    assert doc["source_label"] == "Test Files"
    assert doc["embedded_hash"]


def test_ingest_pdf_from_s3_skips_unchanged():
    deps = _fake_s3_deps()
    si.ingest_pdf_from_s3("ext-bucket", "incoming/x.pdf", **deps)
    called = {"n": 0}

    def _counting_textract(bucket, key):
        called["n"] += 1
        return "text"

    report = si.ingest_pdf_from_s3("ext-bucket", "incoming/x.pdf", **{**deps, "textract_fn": _counting_textract})
    assert report.status == "skipped"
    assert called["n"] == 0


def test_ingest_folder_sweeps_s3_uri():
    calls = []

    def _list_s3(bucket, prefix):
        calls.append((bucket, prefix))
        return ["incoming/a.pdf", "incoming/b.pdf"]

    def _llm_by_file(prompt, schema, model_key, system_prompt=None):
        # extract_spec builds the prompt as "## Document: <filename>\n\n...",
        # so recover the filename to give each of the two PDFs a distinct code.
        filename = re.search(r"## Document: (.+)", prompt).group(1)
        stem = filename.rsplit(".", 1)[0]
        return ProductSpec(code=f"EXT-{stem}", name=stem, short_description="s")

    reports = si.ingest_folder(
        "s3://ext-bucket/incoming/",
        list_s3_fn=_list_s3,
        get_bytes_fn=lambda bucket, key: b"%PDF fake",
        textract_fn=lambda bucket, key: "text",
        llm=_llm_by_file, embed_fn=_fake_embed, index=InMemoryIndex())
    assert calls == [("ext-bucket", "incoming/")]
    assert [r.status for r in reports] == ["ingested", "ingested"]
    assert mongo.products().count_documents({}) == 2
    assert {d["source_label"] for d in mongo.products().find()} == {"Test Files"}
