"""Assign a product to an organization: deterministic rules, LLM on a miss.

Matching is two passes across ALL rules — every rule's category set first,
then every rule's keyword pattern. That ordering is load-bearing: several
products mention another org's keywords in passing, and a single-pass
first-hit-wins loop misfiles them.
"""
import logging
import re
from typing import NamedTuple

from pydantic import BaseModel

from apps.api.orgs import CATCHALL_ID
from apps.api.services import org_service
from core.llm_client import call_llm
from core.utils import DEFAULT_MODEL_KEY

logger = logging.getLogger(__name__)


class OrgChoice(BaseModel):
    org_id: str
    reason: str = ""


class Classification(NamedTuple):
    org_id: str
    via: str  # "rule" | "llm" | "catchall"


# (org_id, metadata.category values, keyword pattern)
_RULES: list[tuple[str, set[str], str]] = [
    (
        "roxxon",
        {"Dairy nutrition"},
        r"lecithin|phosphatid|choline|fat powder|lipid|\boil\b|tallow|glycerid",
    ),
    (
        "pym",
        {"Amino acids", "Enzymes", "Probiotics"},
        r"lysine|methionine|threonine|tryptophan|valine|phytase|xylanase"
        r"|glucanase|protease|yeast|probiotic|enzyme|bacillus",
    ),
    (
        "alchemax",
        {"Vitamins", "Minerals", "Organic acids"},
        r"vitamin|tocopherol|betaine|calcite|calcium carbonate|formic|propionic"
        r"|acidifier|preservative|mineral|toxin binder|selenium|zinc",
    ),
]

_SYSTEM = (
    "You assign a B2B animal-feed product to the organization that sells it. "
    "Choose exactly one org_id from the list you are given. Never invent an "
    "org_id. If nothing fits well, choose the catch-all org."
)


def _keyword_text(doc: dict) -> str:
    """Code, name and short description only.

    Long descriptions routinely name competing products ('partially replaces
    DL-methionine and choline chloride'), which would misfile the product.
    """
    parts = [doc.get("code") or "", doc.get("name") or "",
             doc.get("short_description") or doc.get("description") or ""]
    return " ".join(parts).lower()


def _by_rule(doc: dict) -> str | None:
    category = (doc.get("metadata") or {}).get("category")
    if category:
        for org_id, categories, _ in _RULES:
            if category in categories:
                return org_id
    text = _keyword_text(doc)
    for org_id, _, pattern in _RULES:
        if re.search(pattern, text):
            return org_id
    return None


def _prompt(doc: dict) -> str:
    roster = "\n".join(
        f"- {o['_id']}: {o['name']} — {o.get('tagline') or ''}"
        for o in org_service.list_orgs()
    )
    return (
        "## Organizations\n" + roster
        + "\n\n## Product\n"
        + f"code: {doc.get('code') or ''}\n"
        + f"name: {doc.get('name') or ''}\n"
        + f"short_description: {doc.get('short_description') or ''}\n"
        + f"long_description: {doc.get('long_description') or ''}\n"
        + f"spec: {doc.get('spec') or ''}\n"
        + f"metadata: {doc.get('metadata') or {}}\n"
        + "\n---\n\nReturn the OrgChoice as valid JSON conforming to the "
        "schema. No text before or after the JSON."
    )


def classify(doc: dict, *, llm=None, model_key: str = DEFAULT_MODEL_KEY) -> Classification:
    by_rule = _by_rule(doc)
    if by_rule:
        return Classification(by_rule, "rule")
    llm = llm or call_llm
    try:
        choice = llm(_prompt(doc), OrgChoice, model_key, system_prompt=_SYSTEM)
    except Exception:
        logger.warning("org classification failed for %s", doc.get("code"), exc_info=True)
        return Classification(CATCHALL_ID, "catchall")
    if org_service.exists(choice.org_id):
        return Classification(choice.org_id, "llm")
    logger.warning("classifier returned unknown org %r for %s", choice.org_id, doc.get("code"))
    return Classification(CATCHALL_ID, "catchall")
