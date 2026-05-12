"""Back-compat shim. Expected SO-extraction results now live in
``agents/so_extraction/expected_results.py``. Importers should switch.
"""

from agents.so_extraction.expected_results import (  # noqa: F401
    EXPECTED_BY_CHAT,
    get_expected_for_chat,
)
