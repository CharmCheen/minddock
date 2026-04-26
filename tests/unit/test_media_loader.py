from pathlib import Path

from app.core.config import Settings, get_settings
from app.rag.media_loader import (
    AUDIO_EXTENSIONS,
    DisabledMediaTranscriptionClient,
    MEDIA_EXTENSIONS,
    MockMediaTranscriptionClient,
    OptionalApiMediaTranscriptionClient,
    MediaSourceLoader,
    VIDEO_EXTENSIONS,
    build_media_transcription_client,
)
from app.rag.ingest import build_documents_for_source
from app.rag.source_loader import FileSourceLoader, SourceLoaderRegistry, build_file_descriptor


def _write_media(tmp_path: Path, name: str = "sample.mp3") -> tuple[Path, Path]:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    media_path = kb_dir / name
    media_path.write_text("fake-media-content", encoding="utf-8")
    return kb_dir, media_path


def test_audio_extensions_set() -> None:
    assert ".mp3" in AUDIO_EXTENSIONS
    assert ".wav" in AUDIO_EXTENSIONS
    assert ".m4a" in AUDIO_EXTENSIONS
    assert ".aac" in AUDIO_EXTENSIONS
    assert ".flac" in AUDIO_EXTENSIONS
    assert ".ogg" in AUDIO_EXTENSIONS
    assert ".webm" in AUDIO_EXTENSIONS


def test_video_extensions_set() -> None:
    assert ".mp4" in VIDEO_EXTENSIONS
    assert ".mov" in VIDEO_EXTENSIONS
    assert ".mkv" in VIDEO_EXTENSIONS
    assert ".webm" in VIDEO_EXTENSIONS


def test_media_extensions_union() -> None:
    assert AUDIO_EXTENSIONS | VIDEO_EXTENSIONS == MEDIA_EXTENSIONS


def test_media_source_loader_supports_audio_extensions(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    loader = MediaSourceLoader()
    for ext in (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".webm"):
        path = kb_dir / f"sample{ext}"
        path.write_text("fake", encoding="utf-8")
        assert loader.supports(build_file_descriptor(path, kb_dir))


def test_media_source_loader_supports_video_extensions(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    loader = MediaSourceLoader()
    for ext in (".mp4", ".mov", ".mkv", ".webm"):
        path = kb_dir / f"sample{ext}"
        path.write_text("fake", encoding="utf-8")
        assert loader.supports(build_file_descriptor(path, kb_dir))


def test_media_source_loader_rejects_unsupported_extensions(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    loader = MediaSourceLoader()
    for ext in (".gif", ".bmp", ".svg", ".pdf", ".txt"):
        path = kb_dir / f"sample{ext}"
        path.write_text("fake", encoding="utf-8")
        assert not loader.supports(build_file_descriptor(path, kb_dir))


def test_mock_audio_client_returns_placeholder_text(tmp_path: Path) -> None:
    _, media_path = _write_media(tmp_path, "sample.mp3")
    result = MockMediaTranscriptionClient().transcribe(media_path, "audio")
    assert result.provider == "mock"
    assert "[Audio Transcript - Mock Provider]" in result.text
    assert "No real audio understanding was performed" in result.text
    assert "transcript_mock_fallback" in result.warnings


def test_mock_video_client_returns_placeholder_text(tmp_path: Path) -> None:
    _, media_path = _write_media(tmp_path, "sample.mp4")
    result = MockMediaTranscriptionClient().transcribe(media_path, "video")
    assert result.provider == "mock"
    assert "[Video Transcript - Mock Provider]" in result.text
    assert "No real video or frame understanding was performed" in result.text
    assert "transcript_mock_fallback" in result.warnings


def test_mock_client_with_custom_text(tmp_path: Path) -> None:
    _, media_path = _write_media(tmp_path, "sample.mp3")
    result = MockMediaTranscriptionClient(text="Custom mock transcript").transcribe(media_path, "audio")
    assert result.text == "Custom mock transcript"
    assert result.provider == "mock"


def test_disabled_client_returns_empty_with_warning(tmp_path: Path) -> None:
    _, media_path = _write_media(tmp_path, "sample.mp3")
    result = DisabledMediaTranscriptionClient().transcribe(media_path, "audio")
    assert result.text == ""
    assert result.provider == "disabled"
    assert "transcript_disabled" in result.warnings
    assert "transcript_empty" in result.warnings


def test_api_client_falls_back_when_unconfigured(tmp_path: Path) -> None:
    _, media_path = _write_media(tmp_path, "sample.mp3")
    result = OptionalApiMediaTranscriptionClient().transcribe(media_path, "audio")
    assert result.provider == "mock"
    assert "transcript_api_unconfigured" in result.warnings
    assert "[Audio Transcript - Mock Provider]" in result.text


def test_media_source_loader_audio_metadata(tmp_path: Path) -> None:
    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    descriptor = build_file_descriptor(media_path, kb_dir)
    loader = MediaSourceLoader(transcription_client=MockMediaTranscriptionClient(text="Audio smoke phrase"))
    result = loader.load(descriptor)
    assert result.text == "Audio smoke phrase"
    assert result.metadata["source_media"] == "audio"
    assert result.metadata["source_kind"] == "audio_file"
    assert result.metadata["loader_name"] == "audio.transcribe"
    assert result.metadata["transcript_provider"] == "mock"
    assert result.metadata["retrieval_basis"] == "transcript_text"
    assert result.metadata["media_filename"] == "sample.mp3"
    assert str(tmp_path) not in " ".join(result.metadata.values())


def test_media_source_loader_video_metadata(tmp_path: Path) -> None:
    kb_dir, media_path = _write_media(tmp_path, "sample.mp4")
    descriptor = build_file_descriptor(media_path, kb_dir)
    loader = MediaSourceLoader(transcription_client=MockMediaTranscriptionClient(text="Video smoke phrase"))
    result = loader.load(descriptor)
    assert result.text == "Video smoke phrase"
    assert result.metadata["source_media"] == "video"
    assert result.metadata["source_kind"] == "video_file"
    assert result.metadata["loader_name"] == "video.transcribe"
    assert result.metadata["transcript_provider"] == "mock"
    assert result.metadata["retrieval_basis"] == "transcript_text"


def test_media_source_loader_webm_assumed_video_with_warning(tmp_path: Path) -> None:
    kb_dir, media_path = _write_media(tmp_path, "sample.webm")
    descriptor = build_file_descriptor(media_path, kb_dir)
    loader = MediaSourceLoader(transcription_client=MockMediaTranscriptionClient())
    result = loader.load(descriptor)
    assert result.metadata["source_media"] == "video"
    assert "webm_media_type_assumed_video" in result.warnings


def test_registry_resolves_media_before_file_loader(tmp_path: Path) -> None:
    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    descriptor = build_file_descriptor(media_path, kb_dir)
    loader = SourceLoaderRegistry().resolve(descriptor)
    assert isinstance(loader, MediaSourceLoader)
    assert not isinstance(loader, FileSourceLoader)


def test_registry_resolves_image_before_media_loader(tmp_path: Path) -> None:
    from app.rag.image_loader import ImageSourceLoader
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    image_path = kb_dir / "sample.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    descriptor = build_file_descriptor(image_path, kb_dir)
    loader = SourceLoaderRegistry().resolve(descriptor)
    assert isinstance(loader, ImageSourceLoader)


def test_build_documents_for_source_chunks_media_transcript_text(tmp_path: Path) -> None:
    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    descriptor = build_file_descriptor(media_path, kb_dir)
    registry = SourceLoaderRegistry(
        loaders=[MediaSourceLoader(transcription_client=MockMediaTranscriptionClient(text="MindDock audio smoke phrase 20260426"))]
    )
    documents = build_documents_for_source(descriptor, registry=registry)
    assert len(documents) == 1
    assert documents[0].page_content == "MindDock audio smoke phrase 20260426"
    assert documents[0].metadata["source"] == "sample.mp3"
    assert documents[0].metadata["source_media"] == "audio"
    assert documents[0].metadata["source_kind"] == "audio_file"
    assert documents[0].metadata["retrieval_basis"] == "transcript_text"
    assert documents[0].metadata["transcript_provider"] == "mock"


def test_empty_transcript_does_not_create_chunk(tmp_path: Path) -> None:
    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    descriptor = build_file_descriptor(media_path, kb_dir)
    loader = MediaSourceLoader(transcription_client=MockMediaTranscriptionClient(text=""))
    result = loader.load(descriptor)
    documents = build_documents_for_source(descriptor, registry=SourceLoaderRegistry(loaders=[loader]))
    assert "transcript_empty" in result.warnings
    assert documents == []


def test_disabled_provider_empty_transcript_no_chunk(tmp_path: Path) -> None:
    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    descriptor = build_file_descriptor(media_path, kb_dir)
    loader = MediaSourceLoader(transcription_client=DisabledMediaTranscriptionClient())
    result = loader.load(descriptor)
    documents = build_documents_for_source(descriptor, registry=SourceLoaderRegistry(loaders=[loader]))
    assert "transcript_empty" in result.warnings
    assert documents == []


def test_media_source_loader_truncates_long_text(tmp_path: Path) -> None:
    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    descriptor = build_file_descriptor(media_path, kb_dir)
    long_text = "a" * 5000
    loader = MediaSourceLoader(
        transcription_client=MockMediaTranscriptionClient(text=long_text),
        max_chars=100,
    )
    result = loader.load(descriptor)
    assert len(result.text) == 100
    assert "transcript_text_truncated" in result.warnings


def test_build_media_transcription_client_mock_by_default(monkeypatch) -> None:
    client = build_media_transcription_client()
    assert isinstance(client, MockMediaTranscriptionClient)


def test_build_media_transcription_client_disabled_when_setting_false(monkeypatch) -> None:
    original = get_settings()
    monkeypatch.setattr(
        "app.rag.media_loader.get_settings",
        lambda: Settings(media_transcript_enabled=False),
    )
    client = build_media_transcription_client()
    assert isinstance(client, DisabledMediaTranscriptionClient)


def test_build_media_transcription_client_api_when_setting_api(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.rag.media_loader.get_settings",
        lambda: Settings(media_transcript_provider="api"),
    )
    client = build_media_transcription_client()
    assert isinstance(client, OptionalApiMediaTranscriptionClient)


def test_no_absolute_path_in_metadata(tmp_path: Path) -> None:
    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    descriptor = build_file_descriptor(media_path, kb_dir)
    loader = MediaSourceLoader(transcription_client=MockMediaTranscriptionClient(text="text"))
    result = loader.load(descriptor)
    for value in result.metadata.values():
        assert str(tmp_path) not in value


def test_no_api_key_in_metadata(tmp_path: Path) -> None:
    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    descriptor = build_file_descriptor(media_path, kb_dir)
    loader = MediaSourceLoader(transcription_client=MockMediaTranscriptionClient(text="text"))
    result = loader.load(descriptor)
    raw = " ".join(result.metadata.values())
    assert "api_key" not in raw.lower()
    assert "secret" not in raw.lower()
    assert "token" not in raw.lower()
