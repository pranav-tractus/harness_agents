import numpy as np

MODEL = "gemini-embedding-001"
DIMENSION = 1536

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai  # reads GEMINI_API_KEY / GOOGLE_API_KEY

        _client = genai.Client()
    return _client


def _normalize(values: list[float]) -> list[float]:
    arr = np.asarray(values, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    return (arr / norm).tolist() if norm else arr.tolist()


def embed(texts: list[str], *, mode: str = "document") -> list[list[float]]:
    """Embed texts with gemini-embedding-001 at 1536 dims, L2-normalized.

    Gemini only returns unit-norm vectors at 3072 dims; at 1536 we must
    normalize ourselves for cosine distance to be meaningful.
    """
    from google.genai import types

    task = "RETRIEVAL_DOCUMENT" if mode == "document" else "RETRIEVAL_QUERY"
    resp = _get_client().models.embed_content(
        model=MODEL,
        contents=list(texts),
        config=types.EmbedContentConfig(
            task_type=task, output_dimensionality=DIMENSION
        ),
    )
    return [_normalize(e.values) for e in resp.embeddings]
