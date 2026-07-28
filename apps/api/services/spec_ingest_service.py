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
    aliases: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class IngestReport(BaseModel):
    file: str = ""
    code: str = ""
    name: str = ""
    status: str = ""  # ingested | skipped | dry-run | failed
    aliases: int = 0
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
    "6. `aliases`: alternate names a customer might use in chat (trade "
    "names, abbreviations, line codes). Do not repeat `code` or `name`.\n"
    "7. `metadata`: normalized key/values with lowercase snake_case keys "
    "(form, packing, storage, density, origin, category, application, "
    "shelf_life, ...). Values verbatim from the document.\n"
    "Never invent values not present in the document."
)


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
    if not spec.code.strip():
        spec.code = _slug(filename)
    else:
        spec.code = spec.code.strip()
    return spec


# ---------------------------------------------------------------------------
# Mongo upsert
# ---------------------------------------------------------------------------


def upsert_product(spec: ProductSpec, *, source_pdf: str, pdf_hash: str) -> dict:
    fields = {
        "code": spec.code,
        "name": spec.name or None,
        "short_description": spec.short_description,
        "long_description": spec.long_description or None,
        "spec": spec.spec or None,
        "metadata": spec.metadata,
        "aliases": spec.aliases,
        "source_pdf": source_pdf,
        "source_pdf_hash": pdf_hash,
    }
    mongo.products().update_one({"_id": spec.code}, {"$set": fields}, upsert=True)
    return mongo.products().find_one({"_id": spec.code})


# ---------------------------------------------------------------------------
# PDF ingestion
# ---------------------------------------------------------------------------


def _default_upload(path: Path, bucket: str, key: str) -> None:
    from core.utils import create_boto3_client

    client = create_boto3_client("s3", region=get_settings().aws_region)
    client.put_object(Bucket=bucket, Key=key, Body=path.read_bytes())


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
            return report
        (upload_fn or _default_upload)(path, bucket, key)
        text = (textract_fn or textract_text)(bucket, key)
        spec = extract_spec(text, path.name, model_key, llm=llm)
        report.code, report.name, report.aliases = spec.code, spec.name, len(spec.aliases)
        if dry_run:
            report.status = "dry-run"
            return report
        doc = upsert_product(spec, source_pdf=key, pdf_hash=pdf_hash)
        product_embedding_service.build_from_doc(doc, embed_fn=embed_fn, index=index)
        report.status = "ingested"
        return report
    except Exception as exc:  # per-file isolation: the sweep must continue
        report.status = "failed"
        report.error = str(exc)
        return report


def ingest_folder(folder, **kwargs) -> list[IngestReport]:
    folder = Path(folder)
    if not kwargs.get("dry_run") and kwargs.get("index") is None and vectors.is_available():
        idx = vectors.default_index()
        idx.ensure()
        kwargs["index"] = idx
    return [ingest_pdf(pdf, **kwargs) for pdf in sorted(folder.glob("*.pdf"))]
