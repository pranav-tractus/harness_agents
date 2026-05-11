"""Sales-order extraction agent (agent #1).

- input  : a chat JSON file (``raw_data/chats/...``, ``raw_data/customers/<id>/chats/...``, etc.)
- output : ``SOExtractContractList`` JSON
- score  : recursive JSON diff against ``expected_results.EXPECTED_BY_CHAT[chat_filename]``
"""

from agents.so_extraction.agent import SOExtractionAgent  # noqa: F401
