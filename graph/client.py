import logging
import os
from pathlib import Path

from graph.backend import AbstractGraphBackend
from graph.kuzu_backend import KuzuBackend
from graph.retrieval import get_memory_block
from graph.qa import answer_question

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path("graph.db")
_DEFAULT_MODEL = "claude-sonnet-4-6"


class GraphitiMemoryClient:
    def __init__(
        self,
        backend: AbstractGraphBackend | None = None,
        model_key: str = _DEFAULT_MODEL,
    ) -> None:
        if backend is None:
            db_path = Path(os.environ.get("KUZU_DB_PATH", str(_DEFAULT_DB_PATH)))
            backend = KuzuBackend(db_path=db_path)
        self._backend = backend
        self._model_key = model_key

    def get_memory_block(self, customer_id: str) -> str | None:
        if not customer_id:
            return None
        return get_memory_block(customer_id, self._backend)

    def answer_question(self, customer_id: str, question: str) -> str:
        return answer_question(customer_id, question, self._backend, model_key=self._model_key)

    def close(self) -> None:
        self._backend.close()
