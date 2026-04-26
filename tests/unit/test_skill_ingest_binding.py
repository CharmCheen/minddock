from __future__ import annotations

from pathlib import Path

from app.rag.ingest import build_documents_for_source
from app.rag.source_loader import build_file_descriptor
from app.skills.local_store import LocalSkillStore
from app.skills.source_binding import resolve_source_skill_binding, resolve_source_skill_binding_with_reason
from app.skills.source_registry import SourceSkillRegistry


def _manifest(skill_id: str = "local.project_csv", *, enabled: bool = True, handler: str = "csv.extract", input_kinds: list[str] | None = None) -> dict:
    return {
        "id": skill_id,
        "name": "Project CSV Skill",
        "kind": "source",
        "version": "0.1.0",
        "description": "Parse project CSV files into searchable rows.",
        "handler": handler,
        "input_kinds": input_kinds or [".csv"],
        "output_type": "SourceLoadResult",
        "source_media": "text",
        "source_kind": "csv_file",
        "loader_name": handler,
        "permissions": ["read_file", "write_index"],
        "config": {"max_rows": 500} if handler == "csv.extract" else {},
        "enabled": enabled,
    }


def _registry(tmp_path: Path, monkeypatch) -> SourceSkillRegistry:
    root = tmp_path / "skills"
    monkeypatch.setenv("MINDDOCK_SKILLS_DIR", str(root))
    return SourceSkillRegistry(local_store=LocalSkillStore(root))


def test_enabled_local_csv_skill_matches_csv_source(tmp_path: Path, monkeypatch) -> None:
    registry = _registry(tmp_path, monkeypatch)
    assert registry.register_manifest(_manifest()).ok is True

    binding = resolve_source_skill_binding("data.csv", registry=registry)

    assert binding is not None
    assert binding.skill_id == "local.project_csv"
    assert binding.handler == "csv.extract"
    assert binding.config == {"max_rows": 500}


def test_disabled_local_skill_does_not_match(tmp_path: Path, monkeypatch) -> None:
    registry = _registry(tmp_path, monkeypatch)
    assert registry.register_manifest(_manifest(enabled=False)).ok is True

    binding = resolve_source_skill_binding("data.csv", registry=registry)

    assert binding is None


def test_non_local_builtin_skill_is_not_a_local_binding(tmp_path: Path, monkeypatch) -> None:
    registry = _registry(tmp_path, monkeypatch)

    binding = resolve_source_skill_binding("data.csv", registry=registry)

    assert binding is None


def test_multiple_matching_local_skills_are_ambiguous(tmp_path: Path, monkeypatch) -> None:
    registry = _registry(tmp_path, monkeypatch)
    assert registry.register_manifest(_manifest("local.project_csv")).ok is True
    assert registry.register_manifest(_manifest("local.project_csv_alt")).ok is True

    result = resolve_source_skill_binding_with_reason("data.csv", registry=registry)

    assert result.binding is None
    assert result.warning == "ambiguous_local_skill_binding"
    assert set(result.matches) == {"local.project_csv", "local.project_csv_alt"}


def test_url_and_image_handlers_match_input_kinds(tmp_path: Path, monkeypatch) -> None:
    registry = _registry(tmp_path, monkeypatch)
    url_manifest = _manifest("local.web_page", handler="url.extract", input_kinds=["url"])
    url_manifest["permissions"] = ["read_url", "write_index"]
    url_manifest["config"] = {"timeout_seconds": 10}
    image_manifest = _manifest("local.image_ocr", handler="image.ocr", input_kinds=[".png", ".jpg", ".webp"])
    image_manifest["permissions"] = ["read_file", "use_ocr", "write_index"]
    image_manifest["config"] = {"max_chars": 1000}
    assert registry.register_manifest(url_manifest).ok is True
    assert registry.register_manifest(image_manifest).ok is True

    url_binding = resolve_source_skill_binding("https://example.com", loader_name="url.extract", registry=registry)
    image_binding = resolve_source_skill_binding("image.png", loader_name="image.ocr", registry=registry)

    assert url_binding is not None
    assert url_binding.skill_id == "local.web_page"
    assert image_binding is not None
    assert image_binding.skill_id == "local.image_ocr"


def test_ingest_csv_chunk_metadata_includes_enabled_local_skill(tmp_path: Path, monkeypatch) -> None:
    registry = _registry(tmp_path, monkeypatch)
    assert registry.register_manifest(_manifest()).ok is True
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    csv_path = kb_dir / "data.csv"
    csv_path.write_text("name,value\nMindDock,1\n", encoding="utf-8")

    documents = build_documents_for_source(build_file_descriptor(csv_path, kb_dir))

    assert documents
    metadata = documents[0].metadata
    assert metadata["skill_id"] == "local.project_csv"
    assert metadata["skill_name"] == "Project CSV Skill"
    assert metadata["skill_handler"] == "csv.extract"
    assert metadata["skill_origin"] == "local"
    assert metadata["skill_version"] == "0.1.0"
    assert metadata["skill_config_keys"] == "max_rows"
    assert "[CSV Table]" in documents[0].page_content
    assert "local.project_csv" not in documents[0].page_content


def test_disabled_local_skill_does_not_write_ingest_metadata(tmp_path: Path, monkeypatch) -> None:
    registry = _registry(tmp_path, monkeypatch)
    assert registry.register_manifest(_manifest(enabled=False)).ok is True
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    csv_path = kb_dir / "data.csv"
    csv_path.write_text("name,value\nMindDock,1\n", encoding="utf-8")

    documents = build_documents_for_source(build_file_descriptor(csv_path, kb_dir))

    assert documents
    assert "skill_id" not in documents[0].metadata


def test_ambiguous_local_skills_do_not_write_skill_identity(tmp_path: Path, monkeypatch) -> None:
    registry = _registry(tmp_path, monkeypatch)
    assert registry.register_manifest(_manifest("local.project_csv")).ok is True
    assert registry.register_manifest(_manifest("local.project_csv_alt")).ok is True
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    csv_path = kb_dir / "data.csv"
    csv_path.write_text("name,value\nMindDock,1\n", encoding="utf-8")

    documents = build_documents_for_source(build_file_descriptor(csv_path, kb_dir))

    assert documents
    assert "skill_id" not in documents[0].metadata
    assert documents[0].metadata["skill_binding_warning"] == "ambiguous_local_skill_binding"


def test_enabled_local_audio_skill_matches_audio_source(tmp_path: Path, monkeypatch) -> None:
    from app.rag.media_loader import MockMediaTranscriptionClient, MediaSourceLoader
    from app.rag.source_loader import SourceLoaderRegistry
    registry = _registry(tmp_path, monkeypatch)
    manifest = {
        "id": "local.audio_notes",
        "name": "Audio Notes Skill",
        "kind": "source",
        "version": "0.1.0",
        "description": "Transcribe audio files.",
        "handler": "audio.transcribe",
        "input_kinds": [".mp3", ".wav", ".m4a"],
        "output_type": "SourceLoadResult",
        "source_media": "audio",
        "source_kind": "audio_file",
        "loader_name": "audio.transcribe",
        "permissions": ["read_file", "use_llm_api", "write_index"],
        "enabled": True,
    }
    assert registry.register_manifest(manifest).ok is True
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    audio_path = kb_dir / "lecture.mp3"
    audio_path.write_text("fake-audio", encoding="utf-8")

    documents = build_documents_for_source(
        build_file_descriptor(audio_path, kb_dir),
        registry=SourceLoaderRegistry(loaders=[MediaSourceLoader(transcription_client=MockMediaTranscriptionClient(text="Audio transcript"))]),
    )

    assert documents
    assert documents[0].metadata["skill_id"] == "local.audio_notes"
    assert documents[0].metadata["skill_handler"] == "audio.transcribe"
    assert documents[0].metadata["skill_origin"] == "local"


def test_enabled_local_video_skill_matches_video_source(tmp_path: Path, monkeypatch) -> None:
    from app.rag.media_loader import MockMediaTranscriptionClient, MediaSourceLoader
    from app.rag.source_loader import SourceLoaderRegistry
    registry = _registry(tmp_path, monkeypatch)
    manifest = {
        "id": "local.video_notes",
        "name": "Video Notes Skill",
        "kind": "source",
        "version": "0.1.0",
        "description": "Transcribe video files.",
        "handler": "video.transcribe",
        "input_kinds": [".mp4", ".mov", ".mkv"],
        "output_type": "SourceLoadResult",
        "source_media": "video",
        "source_kind": "video_file",
        "loader_name": "video.transcribe",
        "permissions": ["read_file", "use_llm_api", "write_index"],
        "enabled": True,
    }
    assert registry.register_manifest(manifest).ok is True
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    video_path = kb_dir / "lecture.mp4"
    video_path.write_text("fake-video", encoding="utf-8")

    documents = build_documents_for_source(
        build_file_descriptor(video_path, kb_dir),
        registry=SourceLoaderRegistry(loaders=[MediaSourceLoader(transcription_client=MockMediaTranscriptionClient(text="Video transcript"))]),
    )

    assert documents
    assert documents[0].metadata["skill_id"] == "local.video_notes"
    assert documents[0].metadata["skill_handler"] == "video.transcribe"
    assert documents[0].metadata["skill_origin"] == "local"


def test_disabled_local_audio_skill_does_not_match(tmp_path: Path, monkeypatch) -> None:
    registry = _registry(tmp_path, monkeypatch)
    manifest = {
        "id": "local.audio_notes",
        "name": "Audio Notes Skill",
        "kind": "source",
        "version": "0.1.0",
        "handler": "audio.transcribe",
        "input_kinds": [".mp3"],
        "permissions": ["read_file", "use_llm_api", "write_index"],
        "enabled": False,
    }
    assert registry.register_manifest(manifest).ok is True
    binding = resolve_source_skill_binding("lecture.mp3", registry=registry)
    assert binding is None
