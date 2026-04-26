from pathlib import Path

from app.rag.ingest import build_payload_for_source
from app.rag.source_loader import SourceLoaderRegistry, build_file_descriptor, build_url_descriptor
from app.rag.source_models import IngestBatchResult, IngestSourceResult, SourceDescriptor
from app.rag.source_models import SourceLoadResult


class StubLoader:
    source_type = "note"

    def supports(self, descriptor: SourceDescriptor) -> bool:
        return descriptor.source_type == "note"

    def load(self, descriptor: SourceDescriptor):
        from app.rag.source_models import SourceLoadResult

        return SourceLoadResult(descriptor=descriptor, title="Stub Note", text="hello world")


def test_ingest_batch_result_to_api_dict() -> None:
    from app.rag.source_models import FailedSourceInfo

    result = IngestBatchResult(
        source_results=[
            IngestSourceResult(descriptor=SourceDescriptor(source="a.md", source_type="file"), ok=True, chunks_upserted=2),
            IngestSourceResult(
                descriptor=SourceDescriptor(source="http://example.com", source_type="url"),
                ok=False,
                failure=FailedSourceInfo(source="http://example.com", source_type="url", reason="boom"),
            ),
        ]
    )

    body = result.to_api_dict()
    assert body["documents"] == 1
    assert body["chunks"] == 2
    assert body["ingested_sources"] == ["a.md"]
    assert body["failed_sources"][0]["source_type"] == "url"


def test_source_loader_registry_allows_extension(tmp_path: Path) -> None:
    registry = SourceLoaderRegistry(loaders=[StubLoader()])
    descriptor = SourceDescriptor(source="note://1", source_type="note")

    payload = build_payload_for_source(descriptor=descriptor, registry=registry)

    assert payload.doc_id == descriptor.doc_id
    assert payload.documents == ["hello world"]
    assert payload.metadatas[0]["source_type"] == "note"


def test_source_load_result_warnings_default_to_empty_tuple() -> None:
    result = SourceLoadResult(
        descriptor=SourceDescriptor(source="note://1", source_type="note"),
        title="Note",
        text="hello world",
    )

    assert result.warnings == ()


def test_source_load_result_warnings_flow_to_chunk_metadata() -> None:
    class WarningLoader:
        source_type = "note"

        def supports(self, descriptor: SourceDescriptor) -> bool:
            return descriptor.source_type == "note"

        def load(self, descriptor: SourceDescriptor):
            return SourceLoadResult(
                descriptor=descriptor,
                title="Warn Note",
                text="hello warning world",
                warnings=("empty_main_text", "canonical_missing"),
            )

    registry = SourceLoaderRegistry(loaders=[WarningLoader()])
    descriptor = SourceDescriptor(source="note://warn", source_type="note")

    payload = build_payload_for_source(descriptor=descriptor, registry=registry)

    assert payload.documents == ["hello warning world"]
    assert payload.metadatas[0]["loader_warnings"] == "empty_main_text,canonical_missing"


def test_file_and_url_descriptor_doc_ids_are_stable(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    file_path = kb_dir / "notes.md"
    file_path.write_text("hello", encoding="utf-8")

    file_descriptor = build_file_descriptor(file_path, kb_dir)
    same_file_descriptor = build_file_descriptor(file_path, kb_dir)
    url_descriptor = build_url_descriptor("https://example.com")

    assert file_descriptor.source == "notes.md"
    assert file_descriptor.doc_id == same_file_descriptor.doc_id
    assert url_descriptor.doc_id == build_url_descriptor("https://example.com").doc_id


def test_source_loader_registry_resolves_media_before_file(tmp_path: Path) -> None:
    from app.rag.media_loader import MediaSourceLoader
    from app.rag.source_loader import SourceLoaderRegistry
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    audio_path = kb_dir / "lecture.mp3"
    audio_path.write_text("fake", encoding="utf-8")
    descriptor = build_file_descriptor(audio_path, kb_dir)

    loader = SourceLoaderRegistry().resolve(descriptor)

    assert isinstance(loader, MediaSourceLoader)
