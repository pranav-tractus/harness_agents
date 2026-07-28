import time

from apps.api.settings import get_settings


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
