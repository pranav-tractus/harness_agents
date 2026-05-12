"""Thin shim — delegates to the unified runner.

The single-chat CLI moved to ``harness.runner``. This file is kept so existing
docs and scripts that say ``python main.py`` keep working.

Examples:

    python main.py --agent so_extraction --chat raw_data/chats/foo.json
    python main.py --pipeline so_then_retrieval --chat raw_data/chats/foo.json
    python main.py --agent so_extraction --datasets acme_foods --few-shot-sweep 0 3 10

Run ``python -m harness.runner --help`` for the full option list.
"""

from harness.runner import main

if __name__ == "__main__":
    main()
