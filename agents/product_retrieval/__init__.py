"""Product specification retrieval agent (agent #2, scaffold only).

- input  : an SO summary (``SOExtractContractList`` JSON dict) produced by the
           ``so_extraction`` agent
- output : ranked product spec docs (``list[{doc_id, score, snippet}]``)
- score  : :func:`harness.scoring.retrieval_metrics` (precision@K, recall@K, MRR)

The implementation of :meth:`ProductRetrievalAgent.run_one` is intentionally
left as ``NotImplementedError`` — this commit only proves the pipeline
abstraction works end-to-end. Plug in the actual retrieval method (vector
store, BM25, LLM rerank, ...) when ready.
"""

from agents.product_retrieval.agent import ProductRetrievalAgent  # noqa: F401
