"""Deterministic extractive summary/outline generation for media transcripts.

Phase 1 uses purely extractive heuristics (sentence/paragraph extraction)
without any LLM calls.  Derived chunks are additive and never replace raw
split-text chunks.  Failures are swallowed so that ingest never breaks.
"""

from __future__ import annotations

import logging
import re
from app.rag.source_models import Document, SourceLoadResult

logger = logging.getLogger(__name__)

# Heuristic sentence end markers (conservative)
_SENTENCE_END_RE = re.compile(r"[.!?。！？]\s+")
# Paragraph split (blank line or line-start bullet)
_PARA_SPLIT_RE = re.compile(r"\n\s*\n|\n\s*[-•*]\s+")


class MediaTranscriptPostprocessor:
    """Generate deterministic derived chunks from a media transcript."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        min_chars: int = 400,
        max_input_chars: int = 20000,
        summary_max_chars: int = 800,
        outline_max_items: int = 8,
    ) -> None:
        self.enabled = enabled
        self.min_chars = min_chars
        self.max_input_chars = max_input_chars
        self.summary_max_chars = summary_max_chars
        self.outline_max_items = outline_max_items

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def generate_derived_documents(
        self,
        load_result: SourceLoadResult,
        raw_chunks: list[Document],
    ) -> list[Document]:
        """Return additional Document chunks (summary + outline) if eligible.

        The returned documents carry ``is_derived``, ``derived_kind``,
        ``derived_from``, and ``derived_basis`` metadata so downstream
        consumers can distinguish them from raw transcript chunks.
        """
        if not self.enabled:
            return []

        if not raw_chunks:
            return []

        if not self._is_eligible_media(load_result):
            return []

        text = load_result.text
        if not text or len(text) < self.min_chars:
            return []

        # Cap input length to keep heuristics cheap
        if self.max_input_chars > 0 and len(text) > self.max_input_chars:
            text = text[: self.max_input_chars].rstrip()

        try:
            return self._build_derived(load_result, text)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "MediaTranscriptPostprocessor failed for %s: %s",
                load_result.descriptor.source,
                exc,
                exc_info=True,
            )
            return []

    # ------------------------------------------------------------------ #
    # Eligibility
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_eligible_media(load_result: SourceLoadResult) -> bool:
        meta = load_result.metadata
        loader_name = str(meta.get("loader_name") or "").strip()
        if loader_name not in ("audio.transcribe", "video.transcribe"):
            return False

        provider = str(meta.get("transcript_provider") or "").strip().lower()
        # Skip mock / disabled — nothing real to summarise
        if provider in ("mock", "disabled"):
            return False

        return True

    # ------------------------------------------------------------------ #
    # Builders
    # ------------------------------------------------------------------ #

    def _build_derived(
        self,
        load_result: SourceLoadResult,
        text: str,
    ) -> list[Document]:
        documents: list[Document] = []
        descriptor = load_result.descriptor
        doc_id = descriptor.doc_id
        base_meta = dict(load_result.metadata)
        base_meta.pop("_page_blocks", None)

        summary_text = self._extractive_summary(text)
        if summary_text:
            documents.append(
                Document(
                    page_content=summary_text,
                    metadata={
                        **base_meta,
                        "doc_id": doc_id,
                        "source": descriptor.source,
                        "source_path": descriptor.source_path,
                        "source_type": descriptor.source_type,
                        "title": load_result.title.strip() or descriptor.display_name,
                        "chunk_id": f"{doc_id}:derived:summary",
                        "section": "Summary",
                        "location": f"{descriptor.source} > Summary",
                        "ref": f"{load_result.title.strip() or descriptor.display_name} > Summary",
                        "page": "",
                        "anchor": "",
                        "is_derived": "true",
                        "derived_kind": "media_summary",
                        "derived_from": "transcript",
                        "derived_basis": "transcript_text",
                        "evidence_basis": "transcript_text",
                    },
                )
            )

        outline_text = self._extractive_outline(text)
        if outline_text:
            documents.append(
                Document(
                    page_content=outline_text,
                    metadata={
                        **base_meta,
                        "doc_id": doc_id,
                        "source": descriptor.source,
                        "source_path": descriptor.source_path,
                        "source_type": descriptor.source_type,
                        "title": load_result.title.strip() or descriptor.display_name,
                        "chunk_id": f"{doc_id}:derived:outline",
                        "section": "Outline",
                        "location": f"{descriptor.source} > Outline",
                        "ref": f"{load_result.title.strip() or descriptor.display_name} > Outline",
                        "page": "",
                        "anchor": "",
                        "is_derived": "true",
                        "derived_kind": "media_outline",
                        "derived_from": "transcript",
                        "derived_basis": "transcript_text",
                        "evidence_basis": "transcript_text",
                    },
                )
            )

        return documents

    # ------------------------------------------------------------------ #
    # Extractive summary — sentence selection by position + length heuristic
    # ------------------------------------------------------------------ #

    def _extractive_summary(self, text: str) -> str:
        sentences = _split_sentences(text)
        if not sentences:
            return ""

        # Score: prefer early sentences and moderately long ones
        indexed_scores: list[tuple[int, float]] = []
        for idx, sent in enumerate(sentences):
            length_score = min(len(sent) / 80.0, 3.0)  # 0..3
            position_score = max(3.0 - idx * 0.3, 0.0)  # early sentences win
            indexed_scores.append((idx, length_score + position_score))

        # Sort descending by score
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        # Greedily build summary within char budget, tracking by index
        selected_indices: set[int] = set()
        budget = self.summary_max_chars
        for idx, _ in indexed_scores:
            sent = sentences[idx]
            if len(sent) > budget:
                continue
            selected_indices.add(idx)
            budget -= len(sent) + 1  # +1 for space
            if budget <= 0:
                break

        if not selected_indices:
            # Fallback: just take the first sentence
            first = sentences[0]
            if len(first) <= self.summary_max_chars:
                selected_indices.add(0)
            else:
                sentences[0] = first[: self.summary_max_chars].rstrip()
                selected_indices.add(0)

        # Reconstruct in original order
        ordered = [sentences[i] for i in sorted(selected_indices)]
        return " ".join(ordered)

    # ------------------------------------------------------------------ #
    # Extractive outline — paragraph first-sentence bullets
    # ------------------------------------------------------------------ #

    def _extractive_outline(self, text: str) -> str:
        paragraphs = _split_paragraphs(text)
        if not paragraphs:
            return ""

        bullets: list[str] = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            # Take first sentence of paragraph as bullet
            first_sent = _first_sentence(para)
            if not first_sent:
                continue
            # Deduplicate near-identical bullets
            if any(_normalize_for_dedup(first_sent) == _normalize_for_dedup(b) for b in bullets):
                continue
            bullets.append(first_sent)
            if len(bullets) >= self.outline_max_items:
                break

        if not bullets:
            return ""

        return "\n".join(f"- {b}" for b in bullets)


# ---------------------------------------------------------------------- #
# Text utilities
# ---------------------------------------------------------------------- #

def _split_sentences(text: str) -> list[str]:
    """Naïve sentence splitter; good enough for transcript text."""
    # Preserve the delimiters by using a capturing split
    parts = _SENTENCE_END_RE.split(text)
    if not parts:
        return []

    sentences: list[str] = []
    i = 0
    while i < len(parts):
        sent = parts[i].strip()
        i += 1
        # Append delimiter back if it was consumed by the split
        # (split drops the match; we reconstruct by looking ahead)
        # Actually re.split without capturing drops the match entirely.
        # Simpler: use finditer.
        if sent:
            sentences.append(sent)

    # Alternative robust approach using finditer
    if not sentences:
        return [text.strip()]

    # Reconstruct properly with delimiters
    sentences = []
    last_end = 0
    for m in _SENTENCE_END_RE.finditer(text):
        end = m.end()
        sent = text[last_end:end].strip()
        if sent:
            sentences.append(sent)
        last_end = end
    trailing = text[last_end:].strip()
    if trailing:
        sentences.append(trailing)

    # Clean up stray newlines inside sentences
    return [s.replace("\n", " ") for s in sentences if s]


def _first_sentence(text: str) -> str:
    """Return the first sentence of *text*, capped reasonably."""
    m = _SENTENCE_END_RE.search(text)
    if m:
        return text[: m.end()].strip()
    return text.strip()


def _split_paragraphs(text: str) -> list[str]:
    """Split into paragraphs by blank lines or bullet markers."""
    # Normalise bullets to paragraph boundaries first
    text = text.replace("\n- ", "\n\n- ")
    text = text.replace("\n• ", "\n\n• ")
    text = text.replace("\n* ", "\n\n* ")
    parts = _PARA_SPLIT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def _normalize_for_dedup(text: str) -> str:
    """Lowercase, drop punctuation, collapse spaces for deduplication."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
