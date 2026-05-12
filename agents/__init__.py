"""Agent registry.

Each agent owns:

- its own dataset (chat / doc / row globs)
- its own few-shot pool
- its own expected_results.py
- its own ``run_one`` and ``score`` implementations

Agents can be chained into a :class:`agents.base.Pipeline` so that the output of
one agent feeds the input of the next (e.g. ``so_extraction`` -> ``product_retrieval``).
"""
