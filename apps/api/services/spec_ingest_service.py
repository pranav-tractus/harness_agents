import hashlib
import re
import time
from pathlib import Path

from pydantic import BaseModel, Field

from apps.api.db import mongo, vectors
from apps.api.services import product_embedding_service
from apps.api.settings import get_settings
from core.llm_client import call_llm


def render_blocks(blocks: list[dict]) -> str:
    """Textract blocks → plain text: LINEs in order, then tables as grids."""
    by_id = {b["Id"]: b for b in blocks}
    lines = [b["Text"] for b in blocks if b["BlockType"] == "LINE" and b.get("Text")]
    tables = []
    for table in (b for b in blocks if b["BlockType"] == "TABLE"):
        cells: dict[tuple[int, int], str] = {}
        for rel in table.get("Relationships", []):
            if rel["Type"] != "CHILD":
                continue
            for cid in rel["Ids"]:
                cell = by_id.get(cid)
                if not cell or cell["BlockType"] != "CELL":
                    continue
                words = []
                for crel in cell.get("Relationships", []):
                    if crel["Type"] != "CHILD":
                        continue
                    for wid in crel["Ids"]:
                        w = by_id.get(wid)
                        if w and w["BlockType"] == "WORD":
                            words.append(w["Text"])
                        elif w and w["BlockType"] == "SELECTION_ELEMENT":
                            words.append(
                                "[x]" if w.get("SelectionStatus") == "SELECTED" else "[ ]"
                            )
                cells[(cell["RowIndex"], cell["ColumnIndex"])] = " ".join(words)
        if not cells:
            continue
        n_rows = max(r for r, _ in cells)
        n_cols = max(c for _, c in cells)
        tables.append("\n".join(
            " | ".join(cells.get((r, c), "") for c in range(1, n_cols + 1)).rstrip()
            for r in range(1, n_rows + 1)
        ))
    out = "\n".join(lines)
    if tables:
        out += "\n\n## Tables\n" + "\n\n".join(tables)
    return out


def textract_text(
    bucket: str, key: str, *, client=None, poll_interval: float = 2.0, timeout: float = 300
) -> str:
    if client is None:
        from core.utils import create_boto3_client

        client = create_boto3_client("textract", region=get_settings().aws_region)
    job_id = client.start_document_analysis(
        DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}},
        FeatureTypes=["TABLES"],
    )["JobId"]
    deadline = time.time() + timeout
    while True:
        resp = client.get_document_analysis(JobId=job_id, MaxResults=1000)
        status = resp["JobStatus"]
        if status == "SUCCEEDED":
            break
        if status == "FAILED":
            raise RuntimeError(
                f"Textract job failed for {key}: {resp.get('StatusMessage', '')}"
            )
        if time.time() > deadline:
            raise TimeoutError(f"Textract job timed out for {key}")
        time.sleep(poll_interval)
    blocks = list(resp.get("Blocks", []))
    while resp.get("NextToken"):
        resp = client.get_document_analysis(
            JobId=job_id, MaxResults=1000, NextToken=resp["NextToken"]
        )
        blocks.extend(resp.get("Blocks", []))
    return render_blocks(blocks)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ProductSpec(BaseModel):
    code: str = ""
    name: str = ""
    short_description: str = ""
    long_description: str = ""
    spec: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)


class IngestReport(BaseModel):
    file: str = ""
    code: str = ""
    name: str = ""
    status: str = ""  # ingested | skipped | dry-run | failed
    error: str = ""


# ---------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = (
    "You read raw text extracted from a product specification PDF for a B2B "
    "commodity catalog and return a ProductSpec.\n"
    "1. `code`: the manufacturer product code / SKU exactly as printed in "
    "the document. If no code is printed, return an empty string.\n"
    "2. `name`: the commercial product name.\n"
    "3. `short_description`: one sentence, what the product is.\n"
    "4. `long_description`: 2-4 sentences covering composition, key "
    "properties, and applications.\n"
    "5. `spec`: a condensed one-line spec string of the key technical "
    "attributes (e.g. 'AI >= 95%, moisture <= 2%').\n"
    "6. `metadata`: normalized key/values with lowercase snake_case keys "
    "(form, packing, storage, density, origin, category, application, "
    "shelf_life, ...). Values verbatim from the document.\n"
    "Never invent values not present in the document."
)


def _canonical_code(raw: str) -> str:
    """One SKU code from a possibly multi-code string.

    Spec sheets often print a pack-size table, and the extractor returns
    every code at once ("1510010515022, 15100105"). The shortest code is
    the base SKU — the longer siblings are pack-suffixed extensions of it —
    so that one wins, ties going to the first printed.
    """
    parts = [p.strip() for p in re.split(r"[;,]", raw or "")]
    codes = [p for p in parts if p]
    if not codes:
        return ""
    return min(codes, key=lambda c: (len(c), codes.index(c)))


def _slug(filename: str) -> str:
    stem = Path(filename).stem
    return re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9]+", "-", stem)).strip("-").upper()


def extract_spec(text: str, filename: str, model_key: str = "openai:5.5", llm=None) -> ProductSpec:
    llm = llm or call_llm
    spec = llm(
        f"## Document: {filename}\n\n{text}\n\n---\n\n"
        "Return the ProductSpec as valid JSON conforming to the schema. "
        "No text before or after the JSON.",
        ProductSpec,
        model_key,
        system_prompt=_EXTRACT_SYSTEM,
    )
    spec.code = _canonical_code(spec.code) or _slug(filename)
    return spec


# ---------------------------------------------------------------------------
# Mongo upsert
# ---------------------------------------------------------------------------


def upsert_product(
    spec: ProductSpec, *, source_pdf: str, pdf_hash: str, source_label: str = "OG Files"
) -> dict:
    fields = {
        "code": spec.code,
        "name": spec.name or None,
        "short_description": spec.short_description,
        "long_description": spec.long_description or None,
        "spec": spec.spec or None,
        "metadata": spec.metadata,
        "source_pdf": source_pdf,
        "source_pdf_hash": pdf_hash,
        "source_label": source_label,
    }
    mongo.products().update_one({"_id": spec.code}, {"$set": fields}, upsert=True)
    return mongo.products().find_one({"_id": spec.code})


# ---------------------------------------------------------------------------
# PDF ingestion
# ---------------------------------------------------------------------------


import logging
import threading

logger = logging.getLogger(__name__)

_print_lock = threading.Lock()


def _log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def _default_upload(path: Path, bucket: str, key: str) -> None:
    from core.utils import create_boto3_client

    client = create_boto3_client("s3", region=get_settings().aws_region)
    client.put_object(Bucket=bucket, Key=key, Body=path.read_bytes())


def _finish_ingest(
    report: IngestReport, source_pdf: str, pdf_hash: str, *, model_key: str, dry_run: bool,
    source_label: str, textract_bucket: str, textract_key: str,
    textract_fn=None, llm=None, embed_fn=None, index=None,
) -> None:
    """Textract -> LLM extract -> (dry-run stop | upsert + embed). Mutates `report` in place."""
    filename = report.file
    _log(f"  [ocr]    {filename} — waiting for Textract…")
    text = (textract_fn or textract_text)(textract_bucket, textract_key)
    _log(f"  [llm]    {filename} — extracting spec…")
    spec = extract_spec(text, filename, model_key, llm=llm)
    report.code, report.name = spec.code, spec.name
    if dry_run:
        report.status = "dry-run"
        _log(f"  [dry]    {filename} → {spec.code}  \"{spec.name}\"")
        return
    doc = upsert_product(spec, source_pdf=source_pdf, pdf_hash=pdf_hash, source_label=source_label)
    _log(f"  [embed]  {filename} → {spec.code}  \"{spec.name}\"")
    product_embedding_service.build_from_doc(doc, embed_fn=embed_fn, index=index)
    report.status = "ingested"
    _log(f"  [done]   {filename} → {spec.code}  \"{spec.name}\"")


def ingest_pdf(
    path, *, model_key: str = "openai:5.5", force: bool = False,
    dry_run: bool = False, upload_fn=None, textract_fn=None, llm=None,
    embed_fn=None, index=None,
) -> IngestReport:
    path = Path(path)
    report = IngestReport(file=path.name)
    try:
        pdf_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        bucket = get_settings().specs_s3_bucket
        key = f"specs/{path.name}"
        existing = mongo.products().find_one({"source_pdf": key})
        if existing and existing.get("source_pdf_hash") == pdf_hash and not force:
            report.code = existing["code"]
            report.name = existing.get("name") or ""
            report.status = "skipped"
            _log(f"  [skip]   {path.name} — unchanged")
            return report
        _log(f"  [upload] {path.name} → s3://{bucket}/{key}")
        (upload_fn or _default_upload)(path, bucket, key)
        _finish_ingest(
            report, key, pdf_hash, model_key=model_key, dry_run=dry_run,
            source_label="OG Files", textract_bucket=bucket, textract_key=key,
            textract_fn=textract_fn, llm=llm, embed_fn=embed_fn, index=index,
        )
        return report
    except Exception as exc:  # per-file isolation: the sweep must continue
        report.status = "failed"
        report.error = str(exc)
        _log(f"  [fail]   {path.name} — {exc}")
        logger.debug("ingest_pdf error for %s", path.name, exc_info=True)
        return report


def _default_get_bytes(bucket: str, key: str) -> bytes:
    from core.utils import create_boto3_client

    client = create_boto3_client("s3", region=get_settings().aws_region)
    return client.get_object(Bucket=bucket, Key=key)["Body"].read()


def ingest_pdf_from_s3(
    bucket: str, key: str, *, model_key: str = "openai:5.5", force: bool = False,
    dry_run: bool = False, get_bytes_fn=None, textract_fn=None, llm=None,
    embed_fn=None, index=None,
) -> IngestReport:
    """Ingest a PDF already sitting in an external S3 bucket, in place.

    Unlike `ingest_pdf`, this never uploads/copies anything into
    SPECS_S3_BUCKET — Textract reads directly from `bucket`/`key`, and the
    dedup hash is computed from the object bytes (not a local file).
    """
    filename = key.rsplit("/", 1)[-1]
    report = IngestReport(file=filename)
    source_pdf = f"s3://{bucket}/{key}"
    try:
        pdf_bytes = (get_bytes_fn or _default_get_bytes)(bucket, key)
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()[:16]
        existing = mongo.products().find_one({"source_pdf": source_pdf})
        if existing and existing.get("source_pdf_hash") == pdf_hash and not force:
            report.code = existing["code"]
            report.name = existing.get("name") or ""
            report.status = "skipped"
            _log(f"  [skip]   {filename} — unchanged")
            return report
        _finish_ingest(
            report, source_pdf, pdf_hash, model_key=model_key, dry_run=dry_run,
            source_label="Test Files", textract_bucket=bucket, textract_key=key,
            textract_fn=textract_fn, llm=llm, embed_fn=embed_fn, index=index,
        )
        return report
    except Exception as exc:  # per-file isolation: the sweep must continue
        report.status = "failed"
        report.error = str(exc)
        _log(f"  [fail]   {filename} — {exc}")
        logger.debug("ingest_pdf_from_s3 error for %s", filename, exc_info=True)
        return report


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    rest = uri[len("s3://"):]
    bucket, _, prefix = rest.partition("/")
    return bucket, prefix


def _default_list_s3_keys(bucket: str, prefix: str) -> list[str]:
    from core.utils import create_boto3_client

    client = create_boto3_client("s3", region=get_settings().aws_region)
    keys = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].lower().endswith(".pdf"):
                keys.append(obj["Key"])
    return sorted(keys)


def _ingest_folder_local(folder: Path, *, workers: int, kwargs: dict) -> list[IngestReport]:
    import concurrent.futures

    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        _log(f"No PDFs found in {folder}")
        return []

    _log(f"Ingesting {len(pdfs)} PDFs with {workers} workers…\n")

    results: dict[Path, IngestReport] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(ingest_pdf, pdf, **kwargs): pdf for pdf in pdfs}
        for fut in concurrent.futures.as_completed(futures):
            pdf = futures[fut]
            try:
                results[pdf] = fut.result()
            except Exception as exc:
                results[pdf] = IngestReport(file=pdf.name, status="failed", error=str(exc))

    return [results[pdf] for pdf in pdfs]


def _ingest_folder_s3(uri: str, *, workers: int, list_s3_fn, kwargs: dict) -> list[IngestReport]:
    import concurrent.futures

    bucket, prefix = _parse_s3_uri(uri)
    keys = (list_s3_fn or _default_list_s3_keys)(bucket, prefix)
    if not keys:
        _log(f"No PDFs found in {uri}")
        return []

    _log(f"Ingesting {len(keys)} PDFs from {uri} with {workers} workers…\n")

    results: dict[str, IngestReport] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(ingest_pdf_from_s3, bucket, key, **kwargs): key for key in keys}
        for fut in concurrent.futures.as_completed(futures):
            key = futures[fut]
            try:
                results[key] = fut.result()
            except Exception as exc:
                results[key] = IngestReport(file=key.rsplit("/", 1)[-1], status="failed", error=str(exc))

    return [results[key] for key in keys]


def ingest_folder(folder, *, workers: int = 15, list_s3_fn=None, **kwargs) -> list[IngestReport]:
    mongo.ensure_indexes()
    if not kwargs.get("dry_run") and kwargs.get("index") is None and vectors.is_available():
        idx = vectors.default_index()
        idx.ensure()
        kwargs["index"] = idx

    folder_str = str(folder)
    if folder_str.startswith("s3://"):
        return _ingest_folder_s3(folder_str, workers=workers, list_s3_fn=list_s3_fn, kwargs=kwargs)
    return _ingest_folder_local(Path(folder), workers=workers, kwargs=kwargs)
