from pathlib import Path

from app.rag.incremental import HashStore, IncrementalIngestService
from app.rag.ingest import build_doc_id
from app.rag.source_models import ReplaceDocumentResult

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\xf8\x0f"
    b"\x00\x01\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeEmbedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]


class FakeCollection:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, object]] = {}
        self.upsert_calls = 0

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, str]],
        embeddings: list[list[float]],
    ) -> None:
        self.upsert_calls += 1
        for item_id, document, metadata, embedding in zip(ids, documents, metadatas, embeddings, strict=True):
            self.records[item_id] = {
                "document": document,
                "metadata": metadata,
                "embedding": embedding,
            }

    def replace_document(
        self,
        *,
        doc_id: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, str]],
        embeddings: list[list[float]],
    ) -> ReplaceDocumentResult:
        existing_ids = [key for key, value in self.records.items() if value["metadata"]["doc_id"] == doc_id]
        stale_ids = [key for key in existing_ids if key not in ids]
        for key in stale_ids:
            del self.records[key]
        if ids:
            self.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
        return ReplaceDocumentResult(upserted=len(ids), deleted=len(stale_ids))

    def delete_doc(self, doc_id: str) -> int:
        keys = [key for key, value in self.records.items() if value["metadata"]["doc_id"] == doc_id]
        for key in keys:
            del self.records[key]
        return len(keys)

    def count_doc(self, doc_id: str) -> int:
        return sum(1 for value in self.records.values() if value["metadata"]["doc_id"] == doc_id)


def build_service(tmp_path: Path, collection: FakeCollection) -> IncrementalIngestService:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    hash_store = HashStore(tmp_path / "data" / "hashes.json")
    return IncrementalIngestService(
        kb_dir=kb_dir,
        debounce_seconds=0.0,
        hash_store=hash_store,
        embedder=FakeEmbedder(),
        collection=collection,
        count_document_chunks_fn=collection.count_doc,
    )


def test_incremental_modify_updates_only_changed_document(tmp_path: Path) -> None:
    collection = FakeCollection()
    service = build_service(tmp_path, collection)
    kb_dir = tmp_path / "knowledge_base"
    doc_path = kb_dir / "notes.md"
    doc_path.write_text("# Storage\nFirst version.\n", encoding="utf-8")

    service.handle_created(doc_path)
    source_path = "notes.md"
    doc_id = build_doc_id(Path(source_path))
    initial_chunk_ids = [key for key in collection.records if key.startswith(doc_id)]
    initial_documents = [collection.records[key]["document"] for key in initial_chunk_ids]

    doc_path.write_text("# Storage\nUpdated version with new content.\n", encoding="utf-8")
    service.handle_modified(doc_path)

    updated_chunk_ids = [key for key in collection.records if key.startswith(doc_id)]
    updated_documents = [collection.records[key]["document"] for key in updated_chunk_ids]

    assert initial_chunk_ids == updated_chunk_ids
    assert initial_documents != updated_documents
    assert updated_documents[0] == "Updated version with new content."
    assert collection.count_doc(doc_id) == len(updated_chunk_ids)


def test_incremental_delete_removes_document_chunks_and_hash(tmp_path: Path) -> None:
    collection = FakeCollection()
    service = build_service(tmp_path, collection)
    kb_dir = tmp_path / "knowledge_base"
    doc_path = kb_dir / "notes.md"
    doc_path.write_text("# Storage\nTo be deleted.\n", encoding="utf-8")

    service.handle_created(doc_path)
    source_path = "notes.md"
    doc_id = build_doc_id(Path(source_path))
    assert collection.count_doc(doc_id) > 0
    assert service._hash_store.get(source_path) is not None

    doc_path.unlink()
    service.handle_deleted(doc_path)

    assert collection.count_doc(doc_id) == 0
    assert service._hash_store.get(source_path) is None


def test_incremental_create_adds_new_document(tmp_path: Path) -> None:
    collection = FakeCollection()
    service = build_service(tmp_path, collection)
    kb_dir = tmp_path / "knowledge_base"
    doc_path = kb_dir / "new_file.md"
    doc_path.write_text("# Intro\nBrand new document.\n", encoding="utf-8")

    service.handle_created(doc_path)

    doc_id = build_doc_id(Path("new_file.md"))
    assert collection.count_doc(doc_id) == 1
    assert collection.upsert_calls == 1


def test_incremental_failed_rebuild_keeps_existing_chunks(tmp_path: Path, monkeypatch) -> None:
    collection = FakeCollection()
    service = build_service(tmp_path, collection)
    kb_dir = tmp_path / "knowledge_base"
    doc_path = kb_dir / "notes.md"
    doc_path.write_text("# Storage\nFirst version.\n", encoding="utf-8")

    service.handle_created(doc_path)
    doc_id = build_doc_id(Path("notes.md"))
    before = dict(collection.records)

    monkeypatch.setattr(
        "app.rag.incremental.build_payload_for_source",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("parse failed")),
    )
    doc_path.write_text("# Storage\nBroken update.\n", encoding="utf-8")
    service.handle_modified(doc_path)

    assert collection.records == before
    assert collection.count_doc(doc_id) == 1


def test_sync_directory_detects_new_file(tmp_path: Path) -> None:
    collection = FakeCollection()
    service = build_service(tmp_path, collection)
    doc_path = tmp_path / "knowledge_base" / "new_file.md"
    doc_path.write_text("# Intro\nBrand new document.\n", encoding="utf-8")

    results = service.sync_directory()

    assert [(result.event_type, result.status) for result in results] == [("created", "updated")]
    doc_id = build_doc_id(Path("new_file.md"))
    assert collection.count_doc(doc_id) == 1
    stored = service._hash_store.get("new_file.md")
    assert stored is not None
    assert stored["status"] == "ready"
    assert stored["error"] is None
    assert stored["last_synced_at"]


def test_sync_directory_detects_png_image_source(tmp_path: Path) -> None:
    collection = FakeCollection()
    service = build_service(tmp_path, collection)
    image_path = tmp_path / "knowledge_base" / "sample.png"
    image_path.write_bytes(PNG_1X1)

    results = service.sync_directory()

    assert [(result.event_type, result.status) for result in results] == [("created", "updated")]
    doc_id = build_doc_id(Path("sample.png"))
    assert collection.count_doc(doc_id) == 1
    record = next(iter(collection.records.values()))
    assert "[Image OCR Text]" in record["document"]
    assert record["metadata"]["source"] == "sample.png"
    assert record["metadata"]["source_media"] == "image"
    assert record["metadata"]["source_kind"] == "image_file"
    assert record["metadata"]["loader_name"] == "image.ocr"
    assert record["metadata"]["retrieval_basis"] == "ocr_text"
    assert record["metadata"]["image_filename"] == "sample.png"


def test_sync_directory_deletes_png_image_source(tmp_path: Path) -> None:
    collection = FakeCollection()
    service = build_service(tmp_path, collection)
    image_path = tmp_path / "knowledge_base" / "sample.png"
    image_path.write_bytes(PNG_1X1)
    service.sync_directory()
    doc_id = build_doc_id(Path("sample.png"))
    assert collection.count_doc(doc_id) == 1

    image_path.unlink()
    results = service.sync_directory()

    assert [(result.event_type, result.status, result.chunks_deleted) for result in results] == [("deleted", "removed", 1)]
    assert collection.count_doc(doc_id) == 0
    assert service._hash_store.get("sample.png") is None


def test_sync_directory_detects_modified_file_without_duplicate_chunks(tmp_path: Path) -> None:
    collection = FakeCollection()
    service = build_service(tmp_path, collection)
    doc_path = tmp_path / "knowledge_base" / "notes.md"
    doc_path.write_text("# Storage\nFirst version.\n", encoding="utf-8")
    service.sync_directory()
    doc_id = build_doc_id(Path("notes.md"))

    doc_path.write_text("# Storage\nUpdated version.\n", encoding="utf-8")
    results = service.sync_directory()

    assert [(result.event_type, result.status) for result in results] == [("modified", "updated")]
    assert collection.count_doc(doc_id) == 1
    assert list(collection.records.values())[0]["document"] == "Updated version."


def test_sync_directory_detects_deleted_file_and_removes_hash_entry(tmp_path: Path) -> None:
    collection = FakeCollection()
    service = build_service(tmp_path, collection)
    doc_path = tmp_path / "knowledge_base" / "notes.md"
    doc_path.write_text("# Storage\nTo be deleted.\n", encoding="utf-8")
    service.sync_directory()
    doc_id = build_doc_id(Path("notes.md"))
    assert collection.count_doc(doc_id) == 1

    doc_path.unlink()
    results = service.sync_directory()

    assert [(result.event_type, result.status, result.chunks_deleted) for result in results] == [("deleted", "removed", 1)]
    assert collection.count_doc(doc_id) == 0
    assert service._hash_store.get("notes.md") is None


def test_sync_directory_skips_unchanged_file(tmp_path: Path) -> None:
    collection = FakeCollection()
    service = build_service(tmp_path, collection)
    doc_path = tmp_path / "knowledge_base" / "notes.md"
    doc_path.write_text("# Storage\nStable version.\n", encoding="utf-8")
    service.sync_directory()

    results = service.sync_directory()

    assert [(result.event_type, result.status, result.detail) for result in results] == [
        ("sync", "skipped", "content hash unchanged")
    ]
    assert collection.upsert_calls == 1


def test_sync_directory_dry_run_does_not_write_chroma_or_hash_store(tmp_path: Path) -> None:
    collection = FakeCollection()
    service = build_service(tmp_path, collection)
    doc_path = tmp_path / "knowledge_base" / "notes.md"
    doc_path.write_text("# Storage\nDry run only.\n", encoding="utf-8")

    results = service.sync_directory(dry_run=True)

    assert [(result.event_type, result.status, result.detail) for result in results] == [
        ("created", "planned", "dry-run: would ingest")
    ]
    assert collection.records == {}
    assert service._hash_store.get("notes.md") is None


def test_hash_store_reads_legacy_entries(tmp_path: Path) -> None:
    store_path = tmp_path / "hashes.json"
    store_path.write_text(
        '{"legacy.md": {"doc_id": "doc-1", "content_hash": "hash-1"}}',
        encoding="utf-8",
    )

    store = HashStore(store_path)

    assert store.get("legacy.md") == {
        "doc_id": "doc-1",
        "content_hash": "hash-1",
        "status": "ready",
        "error": None,
        "last_synced_at": None,
    }


def test_sync_directory_unreadable_file_records_failure(tmp_path: Path, monkeypatch) -> None:
    collection = FakeCollection()
    service = build_service(tmp_path, collection)
    doc_path = tmp_path / "knowledge_base" / "locked.md"
    doc_path.write_text("# Locked\nStill being written.\n", encoding="utf-8")
    original_open = Path.open

    def fake_open(path: Path, *args, **kwargs):
        if path == doc_path:
            raise PermissionError("locked")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fake_open)

    results = service.sync_directory()

    assert len(results) == 1
    assert results[0].status == "failed"
    assert "locked" in (results[0].detail or "")
    stored = service._hash_store.get("locked.md")
    assert stored is not None
    assert stored["status"] == "failed"
    assert "locked" in stored["error"]
    assert collection.records == {}
