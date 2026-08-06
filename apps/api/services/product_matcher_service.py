import json
import logging

from pydantic import BaseModel, Field

from apps.api.db import falkor, mongo, vectors
from core import embeddings
from core.llm_client import call_llm

logger = logging.getLogger(__name__)


class ProductCandidate(BaseModel):
    code: str
    name: str = ""
    score: float = 0.0
    snippet: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)


class MentionList(BaseModel):
    mentions: list[str] = Field(default_factory=list)


class ProductMatch(BaseModel):
    mention: str
    status: str = "no_match"  # confident | ambiguous | no_match
    resolved_code: str | None = None
    canonical_name: str | None = None
    confidence: float = 0.0
    candidates: list[ProductCandidate] = Field(default_factory=list)
    question: str | None = None


class ProductMatchResult(BaseModel):
    matches: list[ProductMatch] = Field(default_factory=list)

    def resolved(self) -> list[ProductMatch]:
        return [m for m in self.matches if m.status == "confident"]

    def unresolved(self) -> list[ProductMatch]:
        return [m for m in self.matches if m.status in ("ambiguous", "no_match")]


_SYSTEM = (
    "You resolve product mentions in a B2B commodity sales chat to catalog "
    "SKUs. You are given the conversation, a candidate pool of SKUs "
    "(code + name), and the codes this customer has ordered before (a "
    "strong prior).\n\n"
    "## Hard rules\n"
    "1. **Empty is a valid answer.** If the chat is not clearly discussing "
    "any product yet, return an empty `matches` list. Never invent a "
    "mention.\n"
    "2. **Only ever use codes from the provided pool.** Never emit a "
    "`resolved_code` that is not present in the candidate pool below. If "
    "nothing in the pool fits, set `status='no_match'` and ask a "
    "clarifying question.\n"
    "3. **Prefer previously-ordered SKUs on ties.** When two candidates "
    "fit equally, break the tie in favor of a code from the "
    "\"Previously ordered\" list. Do not use history to override an "
    "unambiguous chat mention.\n"
    "4. **Status semantics.** Use `status='confident'` with "
    "`resolved_code` + `canonical_name` only when one candidate clearly "
    "wins. Use `status='ambiguous'` with 2+ candidates and a short, "
    "directed `question` when several fit. Use `status='no_match'` with "
    "a `question` when nothing in the pool fits.\n"
    "5. **One match per distinct product.** If the parties discuss two "
    "distinct products in the same window, return two ProductMatch "
    "entries. Do not merge them."
    "\n6. **Candidates come from vector search.** `similarity` is the cosine "
    "similarity between the mention and the product's spec text; `matched` "
    "shows the text that matched. Metadata key/values are authoritative — "
    "use them to apply attribute constraints from the chat (non-GMO, "
    "packing, form, origin) exactly, and cite the differing attribute in "
    "clarifying questions."
)

_MENTION_SYSTEM = (
    "You list distinct product mentions from a B2B commodity sales chat.\n"
    "1. Empty is a valid answer — if no product is being discussed, return "
    "an empty list. Never invent a mention.\n"
    "2. Keep attribute qualifiers attached to the mention (e.g. 'non-GMO "
    "soy lecithin in 25kg bags', not 'soy lecithin').\n"
    "3. One entry per distinct product; do not split one product's "
    "qualifiers into separate mentions.\n"
    "4. Copy the chat's wording; do not normalize or expand abbreviations."
)


def _window_text(window: list[dict]) -> str:
    return "\n".join(f"{m.get('role', '')}: {m.get('body', '') or ''}" for m in window)


def _extract_mentions(text: str, model_key, llm) -> list[str]:
    result = llm(
        "## Conversation\n" + text + "\n\n---\n\n"
        "List the distinct product mentions. Return the MentionList as "
        "valid JSON conforming to the schema. No text before or after "
        "the JSON.",
        MentionList,
        model_key,
        system_prompt=_MENTION_SYSTEM,
    )
    return [m.strip() for m in result.mentions if m and m.strip()]


def _fallback_candidates(mentions: list[str]) -> list[ProductCandidate]:
    """Substring scan over Mongo products; keeps the app working offline."""
    lows = [m.lower() for m in mentions]
    out = []
    for doc in mongo.products().find():
        terms = [doc.get("code") or "", doc.get("name") or ""]
        if any(t and (t.lower() in m or m in t.lower()) for t in terms for m in lows):
            out.append(ProductCandidate(
                code=doc["code"], name=doc.get("name") or "",
                metadata={k: str(v) for k, v in (doc.get("metadata") or {}).items()},
            ))
    return out


def _vector_candidates(mentions: list[str]) -> list[ProductCandidate]:
    if not vectors.is_available():
        return _fallback_candidates(mentions)
    try:
        index = vectors.default_index()
        out = []
        for emb in embeddings.embed(mentions, mode="query"):
            for hit in index.query(emb, top_k=5):
                md = dict(hit.metadata)
                code = md.pop("code", "")
                if not code:
                    continue
                name = md.pop("name", "")
                snippet = md.pop("snippet", "")
                md.pop("kind", None)
                attrs_raw = md.pop("attrs", None)
                try:
                    attrs = json.loads(attrs_raw) if attrs_raw else {}
                except Exception:
                    attrs = {}
                out.append(ProductCandidate(
                    code=code, name=name, score=hit.score, snippet=snippet,
                    metadata={k: str(v) for k, v in attrs.items()},
                ))
        return out
    except Exception:
        logger.warning("vector search failed; using substring fallback", exc_info=True)
        return _fallback_candidates(mentions)


def _history_pool(customer_id: str) -> list[ProductCandidate]:
    if not falkor.is_available():
        return []
    g = falkor.customer_graph(customer_id)
    rows = g.query(
        "MATCH (:Customer {id:$id})-[:HAS_CHAT]->(:Chat)-[:HAS_CONTRACT]->(:Contract)"
        "-[:HAS_LINE]->(li:LineItem) RETURN DISTINCT li.product_code",
        {"id": customer_id},
    ).result_set
    return [ProductCandidate(code=r[0], name=r[0], score=0.0) for r in rows if r[0]]


def _dedup(cands: list[ProductCandidate]) -> list[ProductCandidate]:
    by_code: dict[str, ProductCandidate] = {}
    for c in cands:
        cur = by_code.get(c.code)
        if cur is None:
            by_code[c.code] = c
            continue
        best, other = (c, cur) if c.score > cur.score else (cur, c)
        by_code[c.code] = ProductCandidate(
            code=best.code,
            name=best.name or other.name,
            score=best.score,
            snippet=best.snippet or other.snippet,
            metadata=best.metadata or other.metadata,
        )
    return list(by_code.values())


def _candidate_lines(pool: list[ProductCandidate]) -> str:
    lines = []
    for c in sorted(pool, key=lambda c: -c.score):
        line = f"- {c.code}: {c.name}"
        if c.score:
            line += f" (similarity {c.score:.2f})"
        if c.metadata:
            line += "\n  {" + ", ".join(
                f"{k}: {v}" for k, v in sorted(c.metadata.items())) + "}"
        if c.snippet:
            line += f'\n  matched: "{c.snippet}"'
        lines.append(line)
    return "\n".join(lines)


def _prompt(text: str, pool: list[ProductCandidate], history_codes: list[str]) -> str:
    return (
        "## Candidate SKUs\n"
        + _candidate_lines(pool)
        + "\n\n## Previously ordered by this customer\n"
        + (", ".join(history_codes) if history_codes else "(none)")
        + "\n\n## Conversation\n"
        + text
        + "\n\n---\n\n"
        "Resolve each distinct product mention to a candidate SKU. "
        "Return the ProductMatchResult as valid JSON conforming to the "
        "schema. No text before or after the JSON."
    )


def _guard(result: ProductMatchResult, valid_codes: set[str]) -> ProductMatchResult:
    for m in result.matches:
        if m.status == "confident" and (m.resolved_code not in valid_codes):
            m.status = "no_match"
            m.resolved_code = None
            m.canonical_name = None
            m.question = (
                m.question
                or f"Could not match '{m.mention}' to a catalog product. Which SKU is it?"
            )
    return result


def resolve_products(
    customer_id, window, model_key, *,
    mention_fn=None, candidate_fn=None, history_fn=None, llm=None,
) -> ProductMatchResult:
    llm = llm or call_llm
    mention_fn = mention_fn or (lambda text: _extract_mentions(text, model_key, llm))
    candidate_fn = candidate_fn or _vector_candidates
    history_fn = history_fn or _history_pool
    text = _window_text(window)
    mentions = mention_fn(text)
    if not mentions:
        return ProductMatchResult(matches=[])
    history = history_fn(customer_id)
    pool = _dedup(candidate_fn(mentions) + history)
    if not pool:
        return ProductMatchResult(matches=[
            ProductMatch(
                mention=m, status="no_match",
                question=f'I couldn\'t match "{m}" to the catalog. Which product is it?',
            )
            for m in mentions
        ])
    result = llm(
        _prompt(text, pool, [c.code for c in history]),
        ProductMatchResult,
        model_key,
        system_prompt=_SYSTEM,
    )
    return _guard(result, {c.code for c in pool})
