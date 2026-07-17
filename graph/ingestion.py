import logging
from pathlib import Path

from graph.backend import AbstractGraphBackend
from graph.episode_builder import build_episode
from graph.extractor import ExtractedFacts, extract_entities

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"
_SKIP_DIRS = {".git", "__pycache__"}


def ingest_all(
    raw_data_dir: Path,
    backend: AbstractGraphBackend,
    model_key: str = _DEFAULT_MODEL,
) -> int:
    raw_data_dir = Path(raw_data_dir)
    ingested = 0

    for path in sorted(raw_data_dir.rglob("*.json")):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue

        try:
            episode = build_episode(path, raw_data_dir)
        except Exception:
            logger.warning("Failed to build episode from %s", path, exc_info=True)
            continue

        if not episode["content"].strip():
            logger.debug("Skipping empty episode: %s", episode["source_id"])
            continue

        try:
            facts: ExtractedFacts = extract_entities(episode["content"], model_key=model_key)
        except Exception:
            logger.warning("Extraction failed for %s", episode["source_id"], exc_info=True)
            continue

        episode["entities"] = {
            "products": [p.model_dump() for p in facts.products],
            "ports": facts.ports,
            "payment_terms": facts.payment_terms,
            "packing": facts.packing,
            "loading": facts.loading,
        }

        try:
            written = backend.write_episode(episode)
            if written:
                ingested += 1
                logger.info("Ingested: %s (customer=%s)", episode["source_id"], episode["customer_id"])
            else:
                logger.debug("Skipped (already exists): %s", episode["source_id"])
        except Exception:
            logger.warning("Failed to write episode %s", episode["source_id"], exc_info=True)

    return ingested
