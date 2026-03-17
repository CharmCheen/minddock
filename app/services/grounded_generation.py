"""Shared helpers for grounded generation services."""

from __future__ import annotations

from ports.llm import EvidenceItem

SNIPPET_LIMIT = 120
MAX_EVIDENCE_DISTANCE = 1.5


def select_grounded_hits(hits: list[dict[str, object]]) -> list[dict[str, object]]:
    """Filter retrieved hits down to evidence strong enough for generation."""

    grounded_hits: list[dict[str, object]] = []
    for hit in hits:
        distance = hit.get("distance")
        if distance is None or float(distance) < MAX_EVIDENCE_DISTANCE:
            grounded_hits.append(hit)
    return grounded_hits


def build_context(hits: list[dict[str, object]]) -> list[EvidenceItem]:
    """Normalize retrieved hits into the provider evidence shape."""

    context: list[EvidenceItem] = []
    for hit in hits:
        context.append(
            {
                "chunk_id": hit["chunk_id"],
                "source": hit["source"],
                "title": hit.get("title", ""),
                "section": hit.get("section", ""),
                "location": hit.get("location", ""),
                "ref": hit.get("ref", ""),
                "text": hit["text"],
            }
        )
    return context


def build_citation(hit: dict[str, object]) -> dict[str, str | None]:
    """Build a traceable citation from a retrieved hit."""

    text = str(hit["text"]).strip().replace("\n", " ")
    source = str(hit.get("source", ""))
    title = str(hit.get("title", "")).strip()
    section = str(hit.get("section", "")).strip()
    location = str(hit.get("location", "")).strip()
    ref = str(hit.get("ref", "")).strip()
    return {
        "doc_id": str(hit["doc_id"]),
        "chunk_id": str(hit["chunk_id"]),
        "source": source,
        "snippet": text[:SNIPPET_LIMIT],
        "title": title or None,
        "section": section or None,
        "location": location or None,
        "ref": ref or title or source or None,
    }
