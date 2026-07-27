import re

AGENT_TAG = re.compile(r"^@agent\b", re.IGNORECASE)
CONFIRM_WORDS = frozenset({"confirm", "finalize", "approve"})


def parse(body: str) -> str | None:
    """Return "ask" | "approve" for an @agent-tagged message, None otherwise.

    Ported verbatim from the browser's lib/agentTag.ts so the trigger rule has
    exactly one definition, and it lives server-side. The keyword check is
    deliberately deterministic: finalizing writes the contract to the graph and
    closes the chat, so that step must never be model-decided.
    """
    trimmed = (body or "").strip()
    if not AGENT_TAG.match(trimmed):
        return None
    words = AGENT_TAG.sub("", trimmed, count=1).split()
    first = words[0].lower() if words else ""
    return "approve" if first in CONFIRM_WORDS else "ask"
