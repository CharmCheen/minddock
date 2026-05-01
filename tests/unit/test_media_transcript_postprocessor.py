"""Unit tests for MediaTranscriptPostprocessor (deterministic, no LLM)."""

from pathlib import Path

import pytest

from app.rag.media_transcript_postprocessor import (
    MediaTranscriptPostprocessor,
    _first_sentence,
    _normalize_for_dedup,
    _split_paragraphs,
    _split_sentences,
)
from app.rag.source_models import Document, SourceDescriptor, SourceLoadResult


def _make_descriptor(source: str = "demo.mp4") -> SourceDescriptor:
    return SourceDescriptor(source=source, source_type="file", local_path=Path(source))


def _make_load_result(
    text: str,
    *,
    loader_name: str = "video.transcribe",
    provider: str = "sidecar",
    title: str = "Demo",
) -> SourceLoadResult:
    descriptor = _make_descriptor()
    return SourceLoadResult(
        descriptor=descriptor,
        title=title,
        text=text,
        metadata={
            "loader_name": loader_name,
            "transcript_provider": provider,
            "retrieval_basis": "transcript_text",
            "source_media": "video",
            "media_filename": "demo.mp4",
        },
    )


def _make_raw_chunk(text: str = "raw") -> Document:
    return Document(page_content=text, metadata={"chunk_id": "abc:0"})


# ------------------------------------------------------------------ #
# Basic eligibility
# ------------------------------------------------------------------ #


def test_disabled_returns_empty() -> None:
    pp = MediaTranscriptPostprocessor(enabled=False)
    result = _make_load_result("a" * 500)
    assert pp.generate_derived_documents(result, [_make_raw_chunk()]) == []


def test_empty_raw_chunks_returns_empty() -> None:
    pp = MediaTranscriptPostprocessor(enabled=True)
    result = _make_load_result("a" * 500)
    assert pp.generate_derived_documents(result, []) == []


def test_non_media_loader_returns_empty() -> None:
    pp = MediaTranscriptPostprocessor(enabled=True)
    result = _make_load_result("a" * 500, loader_name="file.markdown")
    assert pp.generate_derived_documents(result, [_make_raw_chunk()]) == []


def test_mock_provider_skipped() -> None:
    pp = MediaTranscriptPostprocessor(enabled=True)
    result = _make_load_result("a" * 500, provider="mock")
    assert pp.generate_derived_documents(result, [_make_raw_chunk()]) == []


def test_disabled_provider_skipped() -> None:
    pp = MediaTranscriptPostprocessor(enabled=True)
    result = _make_load_result("a" * 500, provider="disabled")
    assert pp.generate_derived_documents(result, [_make_raw_chunk()]) == []


def test_short_text_skipped() -> None:
    pp = MediaTranscriptPostprocessor(enabled=True, min_chars=100)
    result = _make_load_result("short")
    assert pp.generate_derived_documents(result, [_make_raw_chunk()]) == []


def test_audio_loader_is_eligible() -> None:
    pp = MediaTranscriptPostprocessor(enabled=True)
    result = _make_load_result("a" * 500, loader_name="audio.transcribe", provider="api")
    docs = pp.generate_derived_documents(result, [_make_raw_chunk()])
    assert len(docs) == 2


# ------------------------------------------------------------------ #
# Derived document content
# ------------------------------------------------------------------ #


def test_sidecar_provider_generates_summary_and_outline() -> None:
    text = (
        "First we discuss the architecture of the system. "
        "Then we look at the data layer and how it handles persistence. "
        "Finally we cover the API surface and authentication flow. "
        "This is a long enough transcript to pass the minimum threshold."
    )
    pp = MediaTranscriptPostprocessor(enabled=True, min_chars=50)
    result = _make_load_result(text, provider="sidecar")
    docs = pp.generate_derived_documents(result, [_make_raw_chunk()])

    assert len(docs) == 2
    kinds = {d.metadata["derived_kind"] for d in docs}
    assert kinds == {"media_summary", "media_outline"}


def test_summary_respects_max_chars() -> None:
    text = "Sentence one. " * 50
    pp = MediaTranscriptPostprocessor(enabled=True, min_chars=10, summary_max_chars=80)
    result = _make_load_result(text, provider="sidecar")
    docs = pp.generate_derived_documents(result, [_make_raw_chunk()])
    summary_doc = next(d for d in docs if d.metadata["derived_kind"] == "media_summary")
    assert len(summary_doc.page_content) <= 80


def test_outline_respects_max_items() -> None:
    # 10 paragraphs → outline should be capped
    paragraphs = [f"Paragraph {i} starts here. It continues with more words." for i in range(10)]
    text = "\n\n".join(paragraphs)
    pp = MediaTranscriptPostprocessor(enabled=True, min_chars=10, outline_max_items=3)
    result = _make_load_result(text, provider="sidecar")
    docs = pp.generate_derived_documents(result, [_make_raw_chunk()])
    outline_doc = next(d for d in docs if d.metadata["derived_kind"] == "media_outline")
    bullet_count = outline_doc.page_content.count("\n-") + (1 if outline_doc.page_content.startswith("-") else 0)
    # If all bullets fit on one line without newline, count differently
    if "\n" not in outline_doc.page_content:
        bullet_count = 1 if outline_doc.page_content.startswith("-") else 0
    assert bullet_count <= 3


def test_max_input_chars_truncates_text() -> None:
    text = "Word. " * 2000  # well over 200 chars
    pp = MediaTranscriptPostprocessor(
        enabled=True, min_chars=10, max_input_chars=200, summary_max_chars=100
    )
    result = _make_load_result(text, provider="sidecar")
    docs = pp.generate_derived_documents(result, [_make_raw_chunk()])
    assert len(docs) == 2


# ------------------------------------------------------------------ #
# Metadata correctness
# ------------------------------------------------------------------ #


def test_derived_metadata_includes_flags() -> None:
    text = (
        "Introduction to the topic at hand. "
        "We then move on to implementation details. "
        "Finally we evaluate the results with benchmarks."
    )
    pp = MediaTranscriptPostprocessor(enabled=True, min_chars=10)
    result = _make_load_result(text, provider="sidecar", title="My Demo")
    docs = pp.generate_derived_documents(result, [_make_raw_chunk()])

    for doc in docs:
        assert doc.metadata["is_derived"] == "true"
        assert doc.metadata["derived_kind"] in ("media_summary", "media_outline")
        assert doc.metadata["derived_from"] == "transcript"
        assert doc.metadata["derived_basis"] == "transcript_text"
        assert doc.metadata["evidence_basis"] == "transcript_text"
        assert doc.metadata["loader_name"] == "video.transcribe"
        assert doc.metadata["transcript_provider"] == "sidecar"
        assert doc.metadata["retrieval_basis"] == "transcript_text"
        assert doc.metadata["source_media"] == "video"
        assert doc.metadata["media_filename"] == "demo.mp4"
        assert doc.metadata["doc_id"] == result.descriptor.doc_id
        assert doc.metadata["chunk_id"].startswith(result.descriptor.doc_id)


def test_derived_chunk_ids_are_distinct() -> None:
    text = "One. Two. Three. Four. Five."
    pp = MediaTranscriptPostprocessor(enabled=True, min_chars=10)
    result = _make_load_result(text, provider="sidecar")
    docs = pp.generate_derived_documents(result, [_make_raw_chunk()])
    ids = [d.metadata["chunk_id"] for d in docs]
    assert len(ids) == len(set(ids))


# ------------------------------------------------------------------ #
# Exception safety
# ------------------------------------------------------------------ #


def test_exception_safety_returns_empty(monkeypatch) -> None:
    pp = MediaTranscriptPostprocessor(enabled=True, min_chars=10)
    result = _make_load_result("Some text here to summarise.", provider="sidecar")

    # Force an exception inside _build_derived via broken summary function
    monkeypatch.setattr(
        pp,
        "_extractive_summary",
        lambda _text: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert pp.generate_derived_documents(result, [_make_raw_chunk()]) == []


# ------------------------------------------------------------------ #
# Text utilities
# ------------------------------------------------------------------ #


def test_split_sentences_basic() -> None:
    assert _split_sentences("Hello world. This is a test.") == [
        "Hello world.",
        "This is a test.",
    ]


def test_split_sentences_no_period_returns_single() -> None:
    assert _split_sentences("No punctuation here") == ["No punctuation here"]


def test_first_sentence_finds_first() -> None:
    assert _first_sentence("First. Second.") == "First."


def test_first_sentence_no_period_returns_all() -> None:
    assert _first_sentence("No period") == "No period"


def test_split_paragraphs_by_blank_line() -> None:
    text = "Para one.\n\nPara two.\n\nPara three."
    paras = _split_paragraphs(text)
    assert len(paras) == 3
    assert paras[0] == "Para one."


def test_normalize_for_dedup() -> None:
    assert _normalize_for_dedup("Hello, World!") == "hello world"


# ------------------------------------------------------------------ #
# Ingest integration — derived chunks appended without touching raw IDs
# ------------------------------------------------------------------ #


def test_ingest_appends_derived_chunks_for_media(tmp_path: Path, monkeypatch) -> None:
    """When enabled, media transcript sources get raw + derived chunks."""
    from app.rag.ingest import build_documents_for_source
    from app.rag.media_loader import MediaSourceLoader, MockMediaTranscriptionClient
    from app.rag.source_loader import SourceLoaderRegistry, build_file_descriptor

    # Enable derived docs
    monkeypatch.setattr(
        "app.rag.ingest.get_settings",
        lambda: type(
            "S",
            (),
            {
                "media_transcript_derived_enabled": True,
                "media_transcript_derived_min_chars": 10,
                "media_transcript_derived_max_input_chars": 20000,
                "media_transcript_derived_summary_max_chars": 200,
                "media_transcript_derived_outline_max_items": 4,
            },
        )(),
    )

    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    media_path = kb_dir / "sample.mp4"
    media_path.write_text("fake", encoding="utf-8")

    # Use a sidecar so provider != mock
    (kb_dir / "sample.txt").write_text(
        "First sentence about topic. Second sentence about details. "
        "Third sentence about results. Fourth sentence about future work.\n\n"
        "Paragraph two starts here. It talks about methodology.\n\n"
        "Paragraph three covers evaluation. It uses benchmarks.\n\n"
        "Paragraph four is about conclusions. It wraps up everything.",
        encoding="utf-8",
    )

    descriptor = build_file_descriptor(media_path, kb_dir)
    registry = SourceLoaderRegistry(loaders=[MediaSourceLoader()])
    documents = build_documents_for_source(descriptor, registry=registry)

    # Should have raw chunk(s) + summary + outline
    assert len(documents) >= 3

    raw_chunks = [d for d in documents if d.metadata.get("is_derived") != "true"]
    derived = [d for d in documents if d.metadata.get("is_derived") == "true"]

    assert len(raw_chunks) >= 1
    assert len(derived) == 2

    summary = next(d for d in derived if d.metadata["derived_kind"] == "media_summary")
    outline = next(d for d in derived if d.metadata["derived_kind"] == "media_outline")

    assert summary.page_content
    assert outline.page_content.startswith("-")
    assert summary.metadata["derived_from"] == "transcript"
    assert outline.metadata["derived_from"] == "transcript"

    # Raw chunk IDs must remain unchanged (no derived suffix)
    for rc in raw_chunks:
        assert ":derived:" not in str(rc.metadata.get("chunk_id", ""))


def test_ingest_skips_derived_when_disabled(tmp_path: Path, monkeypatch) -> None:
    """When disabled, only raw chunks are produced."""
    from app.rag.ingest import build_documents_for_source
    from app.rag.media_loader import MediaSourceLoader
    from app.rag.source_loader import SourceLoaderRegistry, build_file_descriptor

    monkeypatch.setattr(
        "app.rag.ingest.get_settings",
        lambda: type(
            "S",
            (),
            {
                "media_transcript_derived_enabled": False,
                "media_transcript_derived_min_chars": 10,
                "media_transcript_derived_max_input_chars": 20000,
                "media_transcript_derived_summary_max_chars": 200,
                "media_transcript_derived_outline_max_items": 4,
            },
        )(),
    )

    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    media_path = kb_dir / "sample.mp4"
    media_path.write_text("fake", encoding="utf-8")
    (kb_dir / "sample.txt").write_text(
        "First sentence. Second sentence. Third sentence. Fourth sentence.\n\n"
        "Para two. More words here.\n\nPara three. Even more words.",
        encoding="utf-8",
    )

    descriptor = build_file_descriptor(media_path, kb_dir)
    registry = SourceLoaderRegistry(loaders=[MediaSourceLoader()])
    documents = build_documents_for_source(descriptor, registry=registry)

    derived = [d for d in documents if d.metadata.get("is_derived") == "true"]
    assert derived == []
