MODEL = "text-embedding-3-large"
DIMENSION = 3072

_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        from core.utils import OPENAI_API_KEY

        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def embed(texts: list[str], *, mode: str = "document") -> list[list[float]]:
    """Embed texts with text-embedding-3-large at 3072 dims.

    text-embedding-3 models return unit-norm vectors natively, so no
    manual normalization is needed (unlike the previous Gemini client).
    `mode` is kept for interface compatibility with callers — OpenAI has
    no document/query task-type distinction, so it has no effect here.
    """
    resp = _get_client().embeddings.create(
        model=MODEL, input=list(texts), dimensions=DIMENSION
    )
    return [d.embedding for d in resp.data]
