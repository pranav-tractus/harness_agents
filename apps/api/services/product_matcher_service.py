from pydantic import BaseModel, Field

from apps.api.db import falkor
from core.llm_client import call_llm


class ProductCandidate(BaseModel):
    code: str
    name: str = ""
    score: float = 0.0


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
)


def _window_text(window: list[dict]) -> str:
    return "\n".join(f"{m.get('role', '')}: {m.get('body', '') or ''}" for m in window)


def _catalog_pool(text: str) -> list[ProductCandidate]:
    if not falkor.is_available():
        return []
    g = falkor.catalog_graph()
    rows = g.query(
        "MATCH (p:Product) OPTIONAL MATCH (p)-[:HAS_ALIAS]->(a:Alias) "
        "RETURN p.code, p.name, collect(a.name)"
    ).result_set
    low = text.lower()
    pool: list[ProductCandidate] = []
    for code, name, aliases in rows:
        terms = [code] + ([name] if name else []) + [a for a in (aliases or []) if a]
        if any(t and t.lower() in low for t in terms):
            pool.append(ProductCandidate(code=code, name=name or "", score=1.0))
    return pool


def _history_pool(customer_id: str) -> list[ProductCandidate]:
    if not falkor.is_available():
        return []
    g = falkor.customer_graph(customer_id)
    rows = g.query(
        "MATCH (:Customer {id:$id})-[:HAS_CHAT]->(:Chat)-[:HAS_CONTRACT]->(:Contract)"
        "-[:HAS_LINE]->(li:LineItem) RETURN DISTINCT li.product_code",
        {"id": customer_id},
    ).result_set
    return [ProductCandidate(code=r[0], name=r[0], score=2.0) for r in rows if r[0]]


def _dedup(cands: list[ProductCandidate]) -> list[ProductCandidate]:
    by_code: dict[str, ProductCandidate] = {}
    for c in cands:
        if c.code not in by_code:
            by_code[c.code] = c
        else:
            existing = by_code[c.code]
            by_code[c.code] = ProductCandidate(
                code=c.code,
                name=existing.name if len(existing.name) >= len(c.name) else c.name,
                score=max(existing.score, c.score),
            )
    return list(by_code.values())


def _prompt(text: str, pool: list[ProductCandidate], history_codes: list[str]) -> str:
    lines = [f"- {c.code}: {c.name}" for c in pool]
    return (
        "## Candidate SKUs\n"
        + "\n".join(lines)
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
    customer_id, window, model_key, *, catalog_pool_fn=None, history_fn=None, llm=None
) -> ProductMatchResult:
    catalog_pool_fn = catalog_pool_fn or _catalog_pool
    history_fn = history_fn or _history_pool
    llm = llm or call_llm
    text = _window_text(window)
    history = history_fn(customer_id)
    pool = _dedup(catalog_pool_fn(text) + history)
    if not pool:
        return ProductMatchResult(matches=[])
    result = llm(
        _prompt(text, pool, [c.code for c in history]),
        ProductMatchResult,
        model_key,
        system_prompt=_SYSTEM,
    )
    return _guard(result, {c.code for c in pool})
