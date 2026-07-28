# Product Matcher Embeddings — Design Spec

**Date:** 2026-07-28
**Status:** Approved design, pending implementation plan
**Replaces:** FalkorDB product catalog graph (`product_graph_service`)

## Goal

Replace the product catalog graph with an embedding-based pipeline: product
spec PDFs (`prod_specs/`) are scanned with AWS Textract, distilled by an LLM
into structured product records (source of truth in MongoDB), embedded with
`gemini-embedding-001`, and stored in an Amazon S3 Vectors index. The product
matcher queries that index to resolve chat mentions to SKUs with real
similarity scores, and asks the user clarifying questions — now including
scores and matched snippets — when it is unsure.

## Decisions made during brainstorming

| Question | Decision |
|---|---|
| Role of PDFs vs Mongo catalog | PDFs are the **source of truth** — extraction creates/updates Mongo product records; embeddings are built from those |
| Pipeline trigger | **Offline CLI script** sweeping a folder (`prod_specs/`); re-run when specs change. No upload UI |
| Embedding model | **`gemini-embedding-001`** at 1536 dims (MRL truncation) — top-tier MTEB retrieval, `google-genai` client and key already in the repo |
| Vector store | **Amazon S3 Vectors** (boto3 `s3vectors`, available in `us-east-1`, boto3 1.43.0 already new enough), with an in-memory fallback implementation for tests/offline |
| Graph removal scope | Remove **only the product catalog graph** (service, build endpoints/UI). Customer/chat/profile graphs stay, including the matcher's purchase-history lookup from the customer graph |
| Disambiguation UX | Keep the chat-question flow; questions include **similarity score and matched snippet** per candidate |
| Metadata in matching | Semantic (rendered into vectors) + structured (passed to the resolution LLM). **No hard metadata filters at query time yet** (see Non-goals) |

## Architecture

Two independent flows sharing one vector index:

```
INGESTION (offline CLI)
prod_specs/*.pdf → S3 upload → Textract (async, TABLES) → raw text
    → LLM extraction (ProductSpec: code, name, short/long desc, aliases, metadata)
    → upsert Mongo products → embed (gemini-embedding-001, 1536d, document mode)
    → S3 Vectors index (#main + #spec + #alias vectors; metadata carries snippets)

RUNTIME (agent match)
chat window → LLM mention extraction (attribute qualifiers kept attached)
    → embed each mention (query mode) → S3 Vectors top-k per mention
    → candidates (code, name, score, snippet, structured metadata)
    + purchase-history prior (customer graph, unchanged)
    → existing resolution LLM → confident | ambiguous | no_match
    → ambiguous/no_match ⇒ chat question with scores + matched snippets
```

Division of labor: **vectors get the right ~5 products into the room; the
resolution LLM applies precise constraints** (non-GMO vs GM, numeric specs,
packing) using the structured metadata on each candidate.

## Components

### New

- **`apps/api/db/vectors.py`** — follows the `falkor.py` pattern:
  `is_available()`, plus a small `VectorIndex` interface with two
  implementations:
  - `S3VectorsIndex` — boto3 `s3vectors`: ensure-index-if-missing, `put`,
    `query` (top-k, metadata returned), `delete`.
  - `InMemoryIndex` — numpy cosine over an in-process dict; used by tests and
    offline dev. (~40 lines, not a parallel system.)
- **`core/embeddings.py`** — `embed(texts, *, mode="document"|"query")`
  calling `gemini-embedding-001` via the existing google-genai client,
  `output_dimensionality=1536`, task type set per mode
  (`RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`).
- **`apps/api/services/product_embedding_service.py`** —
  - `build_from_doc(doc)`: render texts → embed → write vectors → save
    `embedded_hash` on the Mongo doc.
  - `status_for_doc(doc)` → `built | stale | not built` via hash compare
    (no S3 call on list endpoints).
  - `remove_product(code)`: delete the product's vectors.
- **`apps/api/services/spec_ingest_service.py`** — per-PDF pipeline:
  S3 upload → Textract (async `StartDocumentAnalysis` with `TABLES`; async is
  required because multi-page PDFs must be read from S3) → LLM extraction into
  a `ProductSpec` model → Mongo upsert → embedding build. Skips files whose
  PDF hash is unchanged unless forced.
- **`scripts/ingest_specs.py`** — CLI wrapper:
  `python -m scripts.ingest_specs prod_specs/ [--dry-run] [--force]`.
  Dry-run prints the extraction table (filename → code, name, alias count)
  and writes nothing.

### Changed

- **`apps/api/services/product_matcher_service.py`** — `_catalog_pool`
  (exact-substring scan over the Falkor graph) is replaced by mention
  extraction + vector search (see Matcher runtime flow). The history pool,
  `_dedup`, `_guard`, the three statuses, and the injectable-fn test seams
  all stay. `ProductCandidate` gains `snippet` and `metadata` fields; `score`
  holds real cosine similarity instead of the current 1.0/2.0 markers.
- **`apps/api/services/agent_service.py`** — `_match_question` renders score
  and snippet per candidate.
- **`apps/api/routers/products.py`** — `/build` and `/build-all` call
  `product_embedding_service`; `build_status` becomes embedding status.
  Manual (non-PDF) products keep working: create/update in Mongo, then
  "build" embeds them.
- **`apps/web` ProductsPage** — button/badge relabeled (e.g. "Build
  embedding"), same mechanics.
- **`apps/api/settings.py`** — adds `specs_s3_bucket`, `vector_bucket`,
  `vector_index`, `aws_region` (env-driven, defaults for `us-east-1`).

### Removed

- `apps/api/services/product_graph_service.py`
- `graph/product_extractor.py`
- All Falkor catalog-graph usage and the associated tests
  (`test_product_graph_service.py`, `test_product_graph_falkor.py`,
  `test_product_extractor.py` — replaced by equivalents for the new services).

Customer/chat/profile graphs are untouched.

## Storage schema

### Vector index

One S3 vector bucket + one index (1536 dims, cosine). Per product:

| Key | Embedded text |
|---|---|
| `{code}#main` | name + short description + long description + metadata rendered as text |
| `{code}#spec` | full spec + metadata block (density, chemical composition, packing, storage, applications) — catches attribute-led queries where the product isn't named |
| `{code}#alias#{n}` | alias + name — catches bare aliases/codes like "PL5" |

Deterministic keys make re-ingest an overwrite and per-product deletion a
key-prefix operation. Query results are deduped by `code`, keeping each
product's best score.

### Vector metadata

- Filterable: `code`, `name`, `kind` (`main`/`spec`/`alias`), plus the
  flattened product metadata dict (future-proofing for query-time filters —
  not used for filtering yet).
- Non-filterable: `snippet` — the embedded text truncated to ~300 chars;
  powers the "why it matched" line in clarifying questions.

### Mongo product doc

Existing fields (`code`, `name`, `short_description`, `long_description`,
`spec`, `metadata`) plus:

- `aliases: [str]` — extracted during ingestion.
- `source_pdf` — S3 key of the source PDF (absent for manual products).
- `source_pdf_hash` — hash of the PDF bytes; lets the CLI skip unchanged
  files (looked up by `source_pdf`, since the product code isn't known until
  extraction runs).
- `embedded_hash` — hash of the embedded content; set only after vectors
  land, so `status` is computed by hash compare and a mid-build crash shows
  as `stale`.

### S3 buckets

- Ordinary bucket/prefix for uploaded PDFs (Textract input).
- Vector bucket + index for embeddings.

## Ingestion pipeline detail

1. **Sweep** the folder; for each PDF compute the hash of its bytes.
2. **Skip check**: if a product with this `source_pdf` exists and its
   `source_pdf_hash` is unchanged (and not `--force`), skip the file before
   any AWS or LLM call.
3. **Upload** the PDF to `specs_s3_bucket`, then **Textract**:
   `StartDocumentAnalysis` with `TABLES` (spec sheets are table-heavy);
   poll until complete; render blocks to text (tables as key/value or grid
   text).
4. **LLM extraction** (existing `call_llm` + instructor pattern) into
   `ProductSpec`: `code`, `name`, `short_description`, `long_description`,
   `aliases`, `metadata` (form, packing, origin, category, storage, …).
   Code comes from the document itself; fallback is a slugified filename,
   flagged in the report.
5. **Upsert** the Mongo product doc by code (PDFs are source of truth).
6. **Embed and store**: build `#main`, `#spec`, `#alias#n` vectors, delete
   any stale vectors for the code, write new ones, then set `embedded_hash`.

`--dry-run` performs steps 1–4 and prints the extraction table. It still
uploads PDFs to S3 and runs Textract (multi-page PDFs can only be read from
S3) but writes nothing to Mongo or the vector index.

## Matcher runtime flow

1. **Mention extraction** — a small structured LLM call over the chat window
   returns a list of mention strings. Instructions require attribute
   qualifiers to stay attached ("non-GMO soy lecithin in 25kg bags", not
   "soy lecithin"). An empty list is valid and short-circuits to an empty
   `ProductMatchResult`, preserving today's "empty is a valid answer" rule.
2. **Vector query** — each mention is embedded (query mode) and queried
   top-5 against the index; results deduped by code with max score.
3. **Resolution** — candidates (code, name, score, snippet, structured
   metadata) plus previously-ordered codes go into the existing resolution
   prompt. Candidate lines look like:

   ```
   - GIIOFINE-L-nGM: GMO-Free Soy Lecithin Liquid (0.86)
     {form: liquid, gmo: non-GM, packing: 200kg drum, origin: India}
   ```

   The LLM still decides `confident | ambiguous | no_match` and writes the
   clarifying question; `_guard` still enforces pool membership. Exact
   attribute reasoning (non-GMO vs GM, numeric specs) happens here, over the
   top-k candidates — not in the vector query.
4. **Disambiguation** — ambiguous/no_match questions render score + snippet,
   and can cite the differing attribute:

   > For "sunflower lecithin": did you mean **Sunflower Lecithin Powder**
   > (GIIOFINE-UP-SF, 0.87 — "de-oiled sunflower lecithin powder,
   > non-GMO…") or **Sunflower Lecithin Liquid** (GIIOFINE_L_SF, 0.84 —
   > "…")?

The purchase-history prior continues to come from the customer graph,
unchanged.

## Error handling & degradation

- **CLI**: per-file failures (Textract job failed, unextractable code) are
  collected and reported at the end; the sweep continues; exit code is
  non-zero if any file failed. Missing code → slugified filename + warning.
- **Runtime**: if the vector index or embedder is unavailable
  (`is_available()` false, or a call raises), the matcher falls back to a
  substring scan over Mongo product docs (code/name/aliases) — the app stays
  functional offline with today's dumber matching. Errors are logged, never
  raised into the chat flow.
- **Consistency**: Mongo upsert happens before vector writes;
  `embedded_hash` is set only after vectors land. A crash mid-build shows as
  `stale`; re-running the build fixes it.

## Testing

- `vectors.py`: unit tests for `InMemoryIndex`; `S3VectorsIndex` against a
  stubbed boto3 client (put/query/delete request shapes).
- Matcher: existing injected-fn style — fake embedder (deterministic
  vectors) + `InMemoryIndex` covering confident, ambiguous (score/snippet
  rendering), no_match, empty-mentions short-circuit, and offline fallback.
- Ingest service: fake Textract/LLM/embedder — upsert correctness,
  hash-skip, `--force`, filename-fallback code, dry-run writes nothing.
- Products API tests updated for the embedding build path.
- Live end-to-end: manual CLI run against real AWS/Gemini on `prod_specs/`
  (27 PDFs; cost is cents).

## Non-goals (deliberate)

- **No product-upload UI** — CLI only, per decision.
- **No chunking** of long descriptions — spec sheets are small; the three
  vector kinds suffice.
- **No query-time metadata filters** — values extracted from heterogeneous
  PDFs aren't normalized ("25kg bag" vs "25 kg bags"), so an `$eq` filter
  would silently drop the right product. The structured metadata is already
  stored filterable; revisit when the catalog reaches thousands of SKUs or
  top-k recall degrades, adding an attribute-normalization pass at ingest
  first.
- **No reranker** — top-5 over a few hundred products doesn't need one.

## Configuration

New settings (env-driven, in `apps/api/settings.py`):

| Setting | Env var | Default |
|---|---|---|
| `specs_s3_bucket` | `SPECS_S3_BUCKET` | — (required for ingestion) |
| `vector_bucket` | `S3_VECTOR_BUCKET` | — (required for S3 Vectors) |
| `vector_index` | `S3_VECTOR_INDEX` | `product-catalog` |
| `aws_region` | `AWS_REGION` | `us-east-1` |

Gemini credentials reuse the existing google-genai setup. AWS credentials
reuse the existing `create_boto3_client` path (`core/utils.py`).
