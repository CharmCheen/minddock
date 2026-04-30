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
    is_media_sidecar_transcript,
)
from app.rag.ingest import build_documents_for_source
from app.rag.source_loader import FileSourceLoader, SourceLoaderRegistry, build_file_descriptor, iter_file_descriptors


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


def test_video_txt_sidecar_is_used_instead_of_mock(tmp_path: Path) -> None:
    kb_dir, media_path = _write_media(tmp_path, "demo_video.mp4")
    (kb_dir / "demo_video.txt").write_text("Sidecar transcript text", encoding="utf-8")
    descriptor = build_file_descriptor(media_path, kb_dir)
    loader = MediaSourceLoader(transcription_client=MockMediaTranscriptionClient(text="Mock text"))

    result = loader.load(descriptor)

    assert result.text == "Sidecar transcript text"
    assert result.metadata["source_media"] == "video"
    assert result.metadata["loader_name"] == "video.transcribe"
    assert result.metadata["transcript_provider"] == "sidecar"
    assert result.metadata["media_filename"] == "demo_video.mp4"
    assert result.metadata["transcript_sidecar_filename"] == "demo_video.txt"
    assert result.metadata["transcript_sidecar_format"] == "txt"
    assert result.metadata["transcript_segment_count"] == "1"
    assert result.warnings == ()


def test_transcript_md_sidecar_has_priority_over_txt(tmp_path: Path) -> None:
    kb_dir, media_path = _write_media(tmp_path, "demo_video.mp4")
    (kb_dir / "demo_video.txt").write_text("Plain transcript", encoding="utf-8")
    (kb_dir / "demo_video.transcript.md").write_text("# Preferred transcript\n\nMarkdown wins", encoding="utf-8")
    descriptor = build_file_descriptor(media_path, kb_dir)

    result = MediaSourceLoader(transcription_client=MockMediaTranscriptionClient(text="Mock text")).load(descriptor)

    assert "Markdown wins" in result.text
    assert "Plain transcript" not in result.text
    assert result.metadata["transcript_sidecar_filename"] == "demo_video.transcript.md"
    assert result.metadata["transcript_sidecar_format"] == "md"


def test_srt_sidecar_strips_timing_and_index_lines(tmp_path: Path) -> None:
    kb_dir, media_path = _write_media(tmp_path, "demo_video.mp4")
    (kb_dir / "demo_video.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nFirst caption line\n\n2\n00:00:03,000 --> 00:00:04,000\nSecond caption line\n",
        encoding="utf-8",
    )
    descriptor = build_file_descriptor(media_path, kb_dir)

    result = MediaSourceLoader().load(descriptor)

    assert result.text == "First caption line\nSecond caption line"
    assert "00:00" not in result.text
    assert result.metadata["transcript_sidecar_format"] == "srt"
    assert result.metadata["transcript_segment_count"] == "2"


def test_vtt_sidecar_strips_header_timing_and_note_lines(tmp_path: Path) -> None:
    kb_dir, media_path = _write_media(tmp_path, "demo_video.mp4")
    (kb_dir / "demo_video.vtt").write_text(
        "WEBVTT\n\nNOTE generated by test\n00:00:01.000 --> 00:00:02.000\nOpening line\n\n00:00:03.000 --> 00:00:04.000\nClosing line\n",
        encoding="utf-8",
    )
    descriptor = build_file_descriptor(media_path, kb_dir)

    result = MediaSourceLoader().load(descriptor)

    assert result.text == "Opening line\nClosing line"
    assert "WEBVTT" not in result.text
    assert "-->" not in result.text
    assert result.metadata["transcript_sidecar_format"] == "vtt"


def test_empty_sidecar_returns_warning_and_no_absolute_metadata_path(tmp_path: Path) -> None:
    kb_dir, media_path = _write_media(tmp_path, "demo_video.mp4")
    (kb_dir / "demo_video.txt").write_text("   \n", encoding="utf-8")
    descriptor = build_file_descriptor(media_path, kb_dir)

    result = MediaSourceLoader().load(descriptor)

    assert result.text == ""
    assert "transcript_sidecar_empty" in result.warnings
    assert "transcript_empty" in result.warnings
    assert result.metadata["transcript_provider"] == "sidecar"
    assert result.metadata["transcript_sidecar_filename"] == "demo_video.txt"
    for value in result.metadata.values():
        assert str(tmp_path) not in value


def test_sidecar_transcript_files_are_not_indexed_as_standalone_sources(tmp_path: Path) -> None:
    kb_dir, _media_path = _write_media(tmp_path, "demo_video.mp4")
    sidecar = kb_dir / "demo_video.transcript.md"
    sidecar.write_text("Sidecar transcript", encoding="utf-8")
    ordinary_note = kb_dir / "ordinary_note.md"
    ordinary_note.write_text("Standalone note", encoding="utf-8")

    descriptors = iter_file_descriptors(kb_dir)

    sources = {descriptor.source for descriptor in descriptors}
    assert "demo_video.mp4" in sources
    assert "demo_video.transcript.md" not in sources
    assert "ordinary_note.md" in sources
    assert is_media_sidecar_transcript(sidecar)
    assert not is_media_sidecar_transcript(ordinary_note)


def test_plain_txt_sidecar_is_skipped_only_when_matching_media_exists(tmp_path: Path) -> None:
    kb_dir, _media_path = _write_media(tmp_path, "demo_video.mp4")
    (kb_dir / "demo_video.txt").write_text("Video transcript", encoding="utf-8")
    (kb_dir / "research_notes.txt").write_text("Standalone notes", encoding="utf-8")

    sources = {descriptor.source for descriptor in iter_file_descriptors(kb_dir)}

    assert "demo_video.mp4" in sources
    assert "demo_video.txt" not in sources
    assert "research_notes.txt" in sources


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
