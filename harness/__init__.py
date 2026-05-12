"""Unified runner, scoring, and artifact pipeline.

- ``runner``: single + bulk + pipeline runs over an Agent or Pipeline
- ``scoring``: per-agent comparators (JSON diff, retrieval metrics)
- ``artifacts``: one folder per run (jsonl + aggregate.json + report.html + config.json)
- ``seed_expected``: helper to draft new entries into an agent's ``expected_results.py``
"""
