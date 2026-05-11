"""Core building blocks for the agent harness.

Houses the LLM-agnostic primitives that every agent needs:

- ``models``: pydantic schemas (e.g. ``SOExtractContractList``)
- ``llm_client``: provider-aware ``call_llm``
- ``prompt_builder``: jinja prompt rendering + few-shot merging
- ``extractor``: the ``ExtractionEngine`` pipeline
- ``chat_loader``: normalize chat JSON files into prompt-ready text
- ``db``: SQLite persistence for saved summaries / few-shot history
- ``utils``: model catalog, AWS clients, logging helpers
"""
