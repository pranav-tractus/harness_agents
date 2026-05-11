# Product Retrieval Agent (scaffold)

This agent consumes the upstream sales-order summary produced by
[`agents/so_extraction`](../so_extraction/agent.py) and is intended to query a
**separate** product spec document database to return the most relevant spec
docs per line item.

## Status

Skeleton only. `ProductRetrievalAgent.run_one` returns a `not_implemented`
failure so the pipeline plumbing can be exercised end-to-end while the real
retrieval backend is implemented in a follow-up.

## Inputs / outputs

- Input  : `SOExtractContractList` dict (from `so_extraction`)
- Output : `list[{doc_id, score, snippet}]`
- Scoring: `harness.scoring.retrieval_metrics` (precision@K, recall@K, MRR)

## Data layout

- `raw_data/product_specs/` — source documents (PDF, Markdown, ...)
- `product_specs.db`        — index (vector store / BM25 / SQLite-FTS)
- `agents/product_retrieval/expected_results.py` — `{chat_filename: [expected_doc_ids]}`

## Plug-in checklist

1. Decide the retrieval method (e.g. `instructor` + Bedrock embeddings into
   a local `sqlite-vec` store, or `rank_bm25`, or LLM rerank).
2. Build the index over `raw_data/product_specs/` (offline indexer script
   under `agents/product_retrieval/data_gen/`).
3. Implement `ProductRetrievalAgent.run_one` to query the index using line
   items from the upstream summary.
4. Curate `expected_results.py` by running
   `python -m harness.seed_expected --agent product_retrieval --source <chat>`.
5. Run the pipeline:
   ```bash
   python -m harness.runner --pipeline so_then_retrieval --chat raw_data/chats/foo.json
   ```
