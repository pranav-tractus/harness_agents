import logging
from graph.backend import AbstractGraphBackend
from graph.retrieval import get_memory_block

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"

_QA_PROMPT = """\
You are a helpful assistant answering questions about a customer's trading history.
Use only the facts provided below. Include source references in your answer.
If you cannot answer from the facts, say so clearly.

Customer history:
{memory_block}

Question: {question}
"""


def call_llm_text(prompt: str, model_key: str = _DEFAULT_MODEL) -> str:
    from pydantic import BaseModel
    from core.llm_client import call_llm

    class TextResponse(BaseModel):
        answer: str

    result = call_llm(prompt, TextResponse, model_key)
    return result.answer


def answer_question(
    customer_id: str,
    question: str,
    backend: AbstractGraphBackend,
    model_key: str = _DEFAULT_MODEL,
) -> str:
    if not customer_id:
        raise ValueError("customer_id is required — cross-customer queries are not allowed")

    memory_block = get_memory_block(customer_id, backend)
    if not memory_block:
        return f"No history found for customer '{customer_id}'."

    prompt = _QA_PROMPT.format(memory_block=memory_block, question=question)
    return call_llm_text(prompt, model_key=model_key)
