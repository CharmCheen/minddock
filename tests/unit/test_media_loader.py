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
    from app.runtime.media_transcript_active_config import ActiveMediaTranscriptConfig

    monkeypatch.setattr(
        "app.runtime.media_transcript_active_config.get_active_media_transcript_config",
        lambda: ActiveMediaTranscriptConfig(enabled=False),
    )
    client = build_media_transcription_client()
    assert isinstance(client, MockMediaTranscriptionClient)


def test_build_media_transcription_client_disabled_when_setting_false(monkeypatch) -> None:
    from app.runtime.media_transcript_active_config import ActiveMediaTranscriptConfig
    monkeypatch.setattr(
        "app.rag.media_loader.get_settings",
        lambda: Settings(media_transcript_enabled=False),
    )
    monkeypatch.setattr(
        "app.runtime.media_transcript_active_config.get_active_media_transcript_config",
        lambda: ActiveMediaTranscriptConfig(enabled=False),
    )
    client = build_media_transcription_client()
    assert isinstance(client, DisabledMediaTranscriptionClient)


def test_build_media_transcription_client_api_when_setting_api(monkeypatch) -> None:
    from app.runtime.media_transcript_active_config import ActiveMediaTranscriptConfig
    monkeypatch.setattr(
        "app.rag.media_loader.get_settings",
        lambda: Settings(media_transcript_provider="api"),
    )
    monkeypatch.setattr(
        "app.runtime.media_transcript_active_config.get_active_media_transcript_config",
        lambda: ActiveMediaTranscriptConfig(enabled=False),
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


# ── _build_transcription_endpoint ──────────────────────────────


def test_build_endpoint_appends_path() -> None:
    from app.rag.media_loader import _build_transcription_endpoint

    assert _build_transcription_endpoint("https://api.openai.com/v1") == "https://api.openai.com/v1/audio/transcriptions"


def test_build_endpoint_strips_trailing_slash() -> None:
    from app.rag.media_loader import _build_transcription_endpoint

    assert _build_transcription_endpoint("https://api.openai.com/v1/") == "https://api.openai.com/v1/audio/transcriptions"


def test_build_endpoint_no_double_append() -> None:
    from app.rag.media_loader import _build_transcription_endpoint

    url = "https://api.openai.com/v1/audio/transcriptions"
    assert _build_transcription_endpoint(url) == url


# ── API provider success ───────────────────────────────────────


def _fake_httpx_post_success(url, headers=None, data=None, files=None, timeout=None, **kwargs):
    class FakeResponse:
        status_code = 200
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "Hello world from ASR"}

    r = FakeResponse()
    r._call_url = url
    r._call_headers = headers or {}
    r._call_data = data or {}
    r._call_files = files or {}
    r._call_timeout = timeout
    return r


def test_api_client_success_calls_correct_endpoint(monkeypatch, tmp_path: Path) -> None:
    from app.rag.media_loader import OptionalApiMediaTranscriptionClient

    calls: dict = {}

    def _fake_post(url, headers=None, data=None, files=None, timeout=None, **kwargs):
        calls["url"] = url
        calls["headers"] = headers or {}
        calls["data"] = data or {}
        calls["files"] = files or {}
        calls["timeout"] = timeout
        return _fake_httpx_post_success(url, headers, data, files, timeout)

    monkeypatch.setattr("httpx.post", _fake_post)

    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    client = OptionalApiMediaTranscriptionClient(
        api_key="sk-test-fake-key",
        api_base_url="https://api.example.com/v1",
        model="whisper-1",
        timeout_seconds=30.0,
    )
    result = client.transcribe(media_path, "audio")

    assert result.provider == "api"
    assert result.text == "Hello world from ASR"
    assert calls["url"] == "https://api.example.com/v1/audio/transcriptions"
    assert calls["headers"]["Authorization"] == "Bearer sk-test-fake-key"
    assert calls["data"]["model"] == "whisper-1"
    assert calls["timeout"] == 30.0


def test_api_client_success_no_double_endpoint(monkeypatch, tmp_path: Path) -> None:
    from app.rag.media_loader import OptionalApiMediaTranscriptionClient

    call_url: str | None = None

    def _fake_post(url, headers=None, data=None, files=None, timeout=None, **kwargs):
        nonlocal call_url
        call_url = url
        return _fake_httpx_post_success(url, headers, data, files, timeout)

    monkeypatch.setattr("httpx.post", _fake_post)

    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    client = OptionalApiMediaTranscriptionClient(
        api_key="sk-test-fake-key",
        api_base_url="https://api.example.com/v1/audio/transcriptions",
    )
    client.transcribe(media_path, "audio")
    assert call_url == "https://api.example.com/v1/audio/transcriptions"


# ── API provider fallback scenarios ────────────────────────────


def test_api_client_missing_config_fallback(monkeypatch, tmp_path: Path) -> None:
    from app.rag.media_loader import OptionalApiMediaTranscriptionClient

    httpx_called = False

    def _fake_post(*args, **kwargs):
        nonlocal httpx_called
        httpx_called = True
        return _fake_httpx_post_success(*args, **kwargs)

    monkeypatch.setattr("httpx.post", _fake_post)

    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    client = OptionalApiMediaTranscriptionClient()
    result = client.transcribe(media_path, "audio")

    assert result.provider == "mock"
    assert "transcript_api_unconfigured" in result.warnings
    assert "transcript_mock_fallback" in result.warnings
    assert not httpx_called


def test_api_client_missing_key_only_fallback(monkeypatch, tmp_path: Path) -> None:
    from app.rag.media_loader import OptionalApiMediaTranscriptionClient

    httpx_called = False

    def _fake_post(*args, **kwargs):
        nonlocal httpx_called
        httpx_called = True
        return _fake_httpx_post_success(*args, **kwargs)

    monkeypatch.setattr("httpx.post", _fake_post)

    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    result = OptionalApiMediaTranscriptionClient(
        api_base_url="https://api.example.com/v1",
    ).transcribe(media_path, "audio")

    assert result.provider == "mock"
    assert "transcript_api_unconfigured" in result.warnings
    assert not httpx_called


def test_api_client_missing_base_url_only_fallback(monkeypatch, tmp_path: Path) -> None:
    from app.rag.media_loader import OptionalApiMediaTranscriptionClient

    httpx_called = False

    def _fake_post(*args, **kwargs):
        nonlocal httpx_called
        httpx_called = True
        return _fake_httpx_post_success(*args, **kwargs)

    monkeypatch.setattr("httpx.post", _fake_post)

    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    result = OptionalApiMediaTranscriptionClient(
        api_key="sk-test-fake-key",
    ).transcribe(media_path, "audio")

    assert result.provider == "mock"
    assert "transcript_api_unconfigured" in result.warnings
    assert not httpx_called


def test_api_client_http_4xx_fallback(monkeypatch, tmp_path: Path) -> None:
    from app.rag.media_loader import OptionalApiMediaTranscriptionClient
    import httpx

    def _fake_post(*args, **kwargs):
        raise httpx.HTTPStatusError(
            "401 Unauthorized",
            request=object(),
            response=object(),
        )

    monkeypatch.setattr("httpx.post", _fake_post)

    kb_dir, media_path = _write_media(tmp_path, "sample.mp4")
    result = OptionalApiMediaTranscriptionClient(
        api_key="sk-test-fake-key",
        api_base_url="https://api.example.com/v1",
    ).transcribe(media_path, "video")

    assert result.provider == "mock"
    assert "transcript_api_http_error" in result.warnings
    assert "transcript_mock_fallback" in result.warnings


def test_api_client_timeout_fallback(monkeypatch, tmp_path: Path) -> None:
    from app.rag.media_loader import OptionalApiMediaTranscriptionClient
    import httpx

    def _fake_post(*args, **kwargs):
        raise httpx.TimeoutException("Request timed out")

    monkeypatch.setattr("httpx.post", _fake_post)

    kb_dir, media_path = _write_media(tmp_path, "sample.mp4")
    result = OptionalApiMediaTranscriptionClient(
        api_key="sk-test-fake-key",
        api_base_url="https://api.example.com/v1",
    ).transcribe(media_path, "video")

    assert result.provider == "mock"
    assert "transcript_api_timeout" in result.warnings


def test_api_client_network_error_fallback(monkeypatch, tmp_path: Path) -> None:
    from app.rag.media_loader import OptionalApiMediaTranscriptionClient
    import httpx

    def _fake_post(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr("httpx.post", _fake_post)

    kb_dir, media_path = _write_media(tmp_path, "sample.mp4")
    result = OptionalApiMediaTranscriptionClient(
        api_key="sk-test-fake-key",
        api_base_url="https://api.example.com/v1",
    ).transcribe(media_path, "video")

    assert result.provider == "mock"
    assert "transcript_api_network_error" in result.warnings


def test_api_client_empty_text_fallback(monkeypatch, tmp_path: Path) -> None:
    from app.rag.media_loader import OptionalApiMediaTranscriptionClient

    def _fake_post(*args, **kwargs):
        class FakeResponse:
            status_code = 200
            text = ""

            def raise_for_status(self):
                return None

            def json(self):
                return {"text": "   "}

        return FakeResponse()

    monkeypatch.setattr("httpx.post", _fake_post)

    kb_dir, media_path = _write_media(tmp_path, "sample.mp4")
    result = OptionalApiMediaTranscriptionClient(
        api_key="sk-test-fake-key",
        api_base_url="https://api.example.com/v1",
    ).transcribe(media_path, "video")

    assert result.provider == "mock"
    assert "transcript_api_empty" in result.warnings
    assert "transcript_mock_fallback" in result.warnings


# ── Sidecar priority over API ──────────────────────────────────


def test_sidecar_priority_over_api_provider(monkeypatch, tmp_path: Path) -> None:
    httpx_called = False

    def _fake_post(*args, **kwargs):
        nonlocal httpx_called
        httpx_called = True
        return _fake_httpx_post_success(*args, **kwargs)

    monkeypatch.setattr("httpx.post", _fake_post)

    kb_dir, media_path = _write_media(tmp_path, "demo_video.mp4")
    (kb_dir / "demo_video.txt").write_text("Sidecar beats API", encoding="utf-8")
    descriptor = build_file_descriptor(media_path, kb_dir)

    client = OptionalApiMediaTranscriptionClient(
        api_key="sk-test-fake-key",
        api_base_url="https://api.example.com/v1",
    )
    result = MediaSourceLoader(transcription_client=client).load(descriptor)

    assert result.text == "Sidecar beats API"
    assert result.metadata["transcript_provider"] == "sidecar"
    assert not httpx_called


# ── API key not leaked ─────────────────────────────────────────


def test_api_key_not_in_metadata_when_api_success(monkeypatch, tmp_path: Path) -> None:
    from app.rag.media_loader import OptionalApiMediaTranscriptionClient

    monkeypatch.setattr("httpx.post", _fake_httpx_post_success)

    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    descriptor = build_file_descriptor(media_path, kb_dir)
    loader = MediaSourceLoader(transcription_client=OptionalApiMediaTranscriptionClient(
        api_key="sk-secret-do-not-leak",
        api_base_url="https://api.example.com/v1",
    ))
    result = loader.load(descriptor)

    raw = " ".join(result.metadata.values())
    assert "sk-secret-do-not-leak" not in raw
    assert "sk-secret" not in raw
    assert "Bearer" not in raw.lower()


def test_api_key_not_in_warnings_when_api_success(monkeypatch, tmp_path: Path) -> None:
    from app.rag.media_loader import OptionalApiMediaTranscriptionClient

    monkeypatch.setattr("httpx.post", _fake_httpx_post_success)

    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    result = OptionalApiMediaTranscriptionClient(
        api_key="sk-secret-do-not-leak",
        api_base_url="https://api.example.com/v1",
    ).transcribe(media_path, "audio")

    for warning in result.warnings:
        assert "sk-secret" not in warning
        assert "Bearer" not in warning


def test_api_key_not_in_warnings_when_api_fallback(monkeypatch, tmp_path: Path) -> None:
    from app.rag.media_loader import OptionalApiMediaTranscriptionClient

    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    result = OptionalApiMediaTranscriptionClient(
        api_key="sk-secret-do-not-leak",
    ).transcribe(media_path, "audio")

    for warning in result.warnings:
        assert "sk-secret" not in warning


def test_api_client_fallback_uses_correct_warning_code(monkeypatch, tmp_path: Path) -> None:
    from app.rag.media_loader import OptionalApiMediaTranscriptionClient

    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    result = OptionalApiMediaTranscriptionClient(
        api_key="sk-test-fake-key",
    ).transcribe(media_path, "audio")

    assert result.provider == "mock"
    assert "transcript_api_unconfigured" in result.warnings
    assert "transcript_mock_fallback" in result.warnings


# ── Mock / disabled original behavior preserved ────────────────


def test_mock_provider_still_works_with_new_settings(monkeypatch, tmp_path: Path) -> None:
    from app.runtime.media_transcript_active_config import ActiveMediaTranscriptConfig

    monkeypatch.setattr(
        "app.rag.media_loader.get_settings",
        lambda: Settings(
            media_transcript_provider="mock",
            media_transcript_api_key="sk-test-fake-key",
            media_transcript_api_base_url="https://api.example.com/v1",
        ),
    )
    monkeypatch.setattr(
        "app.runtime.media_transcript_active_config.get_active_media_transcript_config",
        lambda: ActiveMediaTranscriptConfig(enabled=False),
    )

    client = build_media_transcription_client()
    assert isinstance(client, MockMediaTranscriptionClient)

    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    result = client.transcribe(media_path, "audio")
    assert result.provider == "mock"
    assert "[Audio Transcript - Mock Provider]" in result.text


def test_disabled_provider_still_works_with_new_settings(monkeypatch, tmp_path: Path) -> None:
    from app.runtime.media_transcript_active_config import ActiveMediaTranscriptConfig

    monkeypatch.setattr(
        "app.rag.media_loader.get_settings",
        lambda: Settings(
            media_transcript_provider="disabled",
            media_transcript_api_key="sk-test-fake-key",
            media_transcript_api_base_url="https://api.example.com/v1",
        ),
    )
    monkeypatch.setattr(
        "app.runtime.media_transcript_active_config.get_active_media_transcript_config",
        lambda: ActiveMediaTranscriptConfig(enabled=False),
    )

    client = build_media_transcription_client()
    assert isinstance(client, DisabledMediaTranscriptionClient)

    kb_dir, media_path = _write_media(tmp_path, "sample.mp3")
    result = client.transcribe(media_path, "audio")
    assert result.text == ""
    assert result.provider == "disabled"
    assert "transcript_disabled" in result.warnings


def test_api_client_json_parse_error_fallback(monkeypatch, tmp_path: Path) -> None:
    from app.rag.media_loader import OptionalApiMediaTranscriptionClient

    def _fake_post(*args, **kwargs):
        class FakeResponse:
            status_code = 200
            text = ""

            def raise_for_status(self):
                return None

            def json(self):
                return "not a dict"

        return FakeResponse()

    monkeypatch.setattr("httpx.post", _fake_post)

    kb_dir, media_path = _write_media(tmp_path, "sample.mp4")
    result = OptionalApiMediaTranscriptionClient(
        api_key="sk-test-fake-key",
        api_base_url="https://api.example.com/v1",
    ).transcribe(media_path, "video")

    assert result.provider == "mock"
    assert "transcript_api_parse_error" in result.warnings


# ---------------------------------------------------------------------------
# Phase 3: UI override tests
# ---------------------------------------------------------------------------


def test_ui_override_active_config_enabled_api_uses_override_values(monkeypatch) -> None:
    """When active config has enabled=True and provider=api,
    build_media_transcription_client() uses UI override provider/base_url/model/timeout."""
    from app.runtime.media_transcript_active_config import ActiveMediaTranscriptConfig

    monkeypatch.setattr(
        "app.runtime.media_transcript_active_config.get_active_media_transcript_config",
        lambda: ActiveMediaTranscriptConfig(
            enabled=True,
            provider="api",
            base_url="https://ui-override.example.com/v1",
            model="ui-model",
            timeout_seconds=120.0,
            api_key_source="env",
        ),
    )
    # Settings should be ignored when active config is enabled
    monkeypatch.setattr(
        "app.rag.media_loader.get_settings",
        lambda: Settings(
            media_transcript_provider="mock",
            media_transcript_api_base_url="https://settings.example.com/v1",
            media_transcript_model="settings-model",
            media_transcript_timeout_seconds=30.0,
        ),
    )
    monkeypatch.setenv("MEDIA_TRANSCRIPT_API_KEY", "sk-ui-override-key")

    client = build_media_transcription_client()
    assert isinstance(client, OptionalApiMediaTranscriptionClient)
    assert client.api_base_url == "https://ui-override.example.com/v1"
    assert client.model == "ui-model"
    assert client.timeout_seconds == 120.0
    assert client.api_key == "sk-ui-override-key"


def test_ui_override_base_url_model_timeout_priority_over_settings(monkeypatch) -> None:
    """UI override base_url/model/timeout take priority over env Settings."""
    from app.rag.media_loader import _resolve_media_transcript_runtime_config
    from app.runtime.media_transcript_active_config import ActiveMediaTranscriptConfig

    monkeypatch.setattr(
        "app.runtime.media_transcript_active_config.get_active_media_transcript_config",
        lambda: ActiveMediaTranscriptConfig(
            enabled=True,
            provider="api",
            base_url="https://priority.example.com/v1",
            model="priority-model",
            timeout_seconds=99.0,
            api_key_source="env",
        ),
    )
    monkeypatch.setattr(
        "app.rag.media_loader.get_settings",
        lambda: Settings(
            media_transcript_provider="mock",
            media_transcript_api_base_url="https://lower-priority.example.com/v1",
            media_transcript_model="lower-model",
            media_transcript_timeout_seconds=10.0,
        ),
    )
    monkeypatch.setenv("MEDIA_TRANSCRIPT_API_KEY", "sk-priority-key")

    resolved = _resolve_media_transcript_runtime_config()
    assert resolved.base_url == "https://priority.example.com/v1"
    assert resolved.model == "priority-model"
    assert resolved.timeout_seconds == 99.0
    assert resolved.provider == "api"
    assert resolved.config_source == "ui_override"


def test_ui_override_api_key_from_environ(monkeypatch) -> None:
    """api_key is always read from os.environ when active config api_key_source='env'."""
    from app.rag.media_loader import _resolve_media_transcript_runtime_config
    from app.runtime.media_transcript_active_config import ActiveMediaTranscriptConfig

    monkeypatch.setattr(
        "app.runtime.media_transcript_active_config.get_active_media_transcript_config",
        lambda: ActiveMediaTranscriptConfig(
            enabled=True,
            provider="api",
            base_url="https://api.example.com/v1",
            model="whisper-1",
            timeout_seconds=60.0,
            api_key_source="env",
        ),
    )
    monkeypatch.setattr(
        "app.rag.media_loader.get_settings",
        lambda: Settings(media_transcript_api_key=""),
    )
    monkeypatch.setenv("MEDIA_TRANSCRIPT_API_KEY", "sk-from-env-var")

    resolved = _resolve_media_transcript_runtime_config()
    assert resolved.api_key == "sk-from-env-var"


def test_ui_override_api_key_empty_when_no_env(monkeypatch) -> None:
    """api_key is empty when api_key_source='env' but env var is not set."""
    from app.rag.media_loader import _resolve_media_transcript_runtime_config
    from app.runtime.media_transcript_active_config import ActiveMediaTranscriptConfig

    monkeypatch.setattr(
        "app.runtime.media_transcript_active_config.get_active_media_transcript_config",
        lambda: ActiveMediaTranscriptConfig(
            enabled=True,
            provider="api",
            base_url="https://api.example.com/v1",
            model="whisper-1",
            timeout_seconds=60.0,
            api_key_source="env",
        ),
    )
    monkeypatch.setattr(
        "app.rag.media_loader.get_settings",
        lambda: Settings(media_transcript_api_key=""),
    )
    monkeypatch.delenv("MEDIA_TRANSCRIPT_API_KEY", raising=False)

    resolved = _resolve_media_transcript_runtime_config()
    assert resolved.api_key == ""


def test_ui_override_active_config_enabled_local_uses_local_fields(monkeypatch) -> None:
    """When active config has enabled=True and provider=local,
    build_media_transcription_client() resolves local base_url via bootstrap."""
    from app.runtime.media_transcript_active_config import ActiveMediaTranscriptConfig
    from app.runtime.local_asr_bootstrap import LocalAsrBootstrapResult

    monkeypatch.setattr(
        "app.runtime.media_transcript_active_config.get_active_media_transcript_config",
        lambda: ActiveMediaTranscriptConfig(
            enabled=True,
            provider="local",
            base_url="",
            model="small",
            timeout_seconds=120.0,
            api_key_source="none",
            local_asr_server_path="/local/asr",
            local_asr_host="127.0.0.1",
            local_asr_port=9001,
            local_asr_model="small",
            local_asr_device="auto",
            local_asr_compute_type="int8",
            local_asr_auto_start=True,
            local_asr_timeout_seconds=120.0,
        ),
    )
    monkeypatch.setattr(
        "app.rag.media_loader.get_settings",
        lambda: Settings(),
    )

    # Mock bootstrap to return already_running
    def _fake_ensure(**kwargs):
        return LocalAsrBootstrapResult(
            status="already_running",
            message="ok",
            base_url="http://127.0.0.1:9001/v1",
        )

    monkeypatch.setattr(
        "app.runtime.local_asr_bootstrap.ensure_local_asr_if_enabled",
        _fake_ensure,
    )

    client = build_media_transcription_client()
    assert isinstance(client, OptionalApiMediaTranscriptionClient)
    assert client.api_base_url == "http://127.0.0.1:9001/v1"
    assert client.api_key == "local-dev-key"
    assert client.model == "small"


def test_local_provider_fallback_to_mock_on_bootstrap_failure(monkeypatch) -> None:
    """Local ASR bootstrap failure should fall back to mock."""
    from app.runtime.media_transcript_active_config import ActiveMediaTranscriptConfig
    from app.runtime.local_asr_bootstrap import LocalAsrBootstrapResult

    monkeypatch.setattr(
        "app.runtime.media_transcript_active_config.get_active_media_transcript_config",
        lambda: ActiveMediaTranscriptConfig(
            enabled=True,
            provider="local",
            model="small",
            api_key_source="none",
            local_asr_server_path="/missing",
            local_asr_host="127.0.0.1",
            local_asr_port=9001,
            local_asr_auto_start=True,
            local_asr_timeout_seconds=120.0,
        ),
    )
    monkeypatch.setattr(
        "app.rag.media_loader.get_settings",
        lambda: Settings(),
    )

    def _fake_ensure(**kwargs):
        return LocalAsrBootstrapResult(
            status="failed",
            message="server path missing",
            base_url="http://127.0.0.1:9001/v1",
        )

    monkeypatch.setattr(
        "app.runtime.local_asr_bootstrap.ensure_local_asr_if_enabled",
        _fake_ensure,
    )

    client = build_media_transcription_client()
    assert isinstance(client, MockMediaTranscriptionClient)


def test_local_provider_resolved_config_has_local_fields(monkeypatch) -> None:
    """_resolve_media_transcript_runtime_config should include local ASR fields."""
    from app.rag.media_loader import _resolve_media_transcript_runtime_config
    from app.runtime.media_transcript_active_config import ActiveMediaTranscriptConfig

    monkeypatch.setattr(
        "app.runtime.media_transcript_active_config.get_active_media_transcript_config",
        lambda: ActiveMediaTranscriptConfig(
            enabled=True,
            provider="local",
            model="small",
            api_key_source="none",
            local_asr_server_path="/local/asr",
            local_asr_host="127.0.0.1",
            local_asr_port=9001,
            local_asr_model="base",
            local_asr_device="cuda",
            local_asr_compute_type="int8",
            local_asr_auto_start=False,
            local_asr_timeout_seconds=90.0,
        ),
    )
    monkeypatch.setattr(
        "app.rag.media_loader.get_settings",
        lambda: Settings(),
    )

    resolved = _resolve_media_transcript_runtime_config()
    assert resolved.provider == "local"
    assert resolved.local_asr_server_path == "/local/asr"
    assert resolved.local_asr_model == "base"
    assert resolved.local_asr_auto_start is False
    assert resolved.local_asr_timeout_seconds == 90.0


def test_sidecar_still_takes_priority_over_local_provider(monkeypatch, tmp_path: Path) -> None:
    """Even with provider=local, sidecar transcript wins."""
    from app.runtime.media_transcript_active_config import ActiveMediaTranscriptConfig

    monkeypatch.setattr(
        "app.runtime.media_transcript_active_config.get_active_media_transcript_config",
        lambda: ActiveMediaTranscriptConfig(
            enabled=True,
            provider="local",
            model="small",
            api_key_source="none",
            local_asr_server_path="/local/asr",
            local_asr_auto_start=False,
            local_asr_timeout_seconds=120.0,
        ),
    )
    monkeypatch.setattr(
        "app.rag.media_loader.get_settings",
        lambda: Settings(),
    )

    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    media_path = kb_dir / "video.mp4"
    media_path.write_text("fake-video", encoding="utf-8")
    sidecar = kb_dir / "video.transcript.md"
    sidecar.write_text("Sidecar transcript text.", encoding="utf-8")

    loader = MediaSourceLoader()
    descriptor = build_file_descriptor(media_path, kb_dir)
    result = loader.load(descriptor)
    assert result.metadata["transcript_provider"] == "sidecar"
    assert "Sidecar transcript text." in result.text


def test_local_provider_uses_local_asr_model_not_generic_model(monkeypatch) -> None:
    """Provider=local must use local_asr_model, not the generic model field."""
    from app.runtime.media_transcript_active_config import ActiveMediaTranscriptConfig
    from app.runtime.local_asr_bootstrap import LocalAsrBootstrapResult

    monkeypatch.setattr(
        "app.runtime.media_transcript_active_config.get_active_media_transcript_config",
        lambda: ActiveMediaTranscriptConfig(
            enabled=True,
            provider="local",
            base_url="",
            model="whisper-1",  # generic model should be ignored
            timeout_seconds=120.0,
            api_key_source="none",
            local_asr_server_path="/local/asr",
            local_asr_host="127.0.0.1",
            local_asr_port=9001,
            local_asr_model="small",  # this must be used
            local_asr_device="auto",
            local_asr_compute_type="int8",
            local_asr_auto_start=True,
            local_asr_timeout_seconds=120.0,
        ),
    )
    monkeypatch.setattr(
        "app.rag.media_loader.get_settings",
        lambda: Settings(),
    )

    # Capture what OptionalApiMediaTranscriptionClient receives
    captured = {}

    original_init = OptionalApiMediaTranscriptionClient.__init__

    def _capturing_init(self, *, fallback=None, api_key="", api_base_url="", model="", timeout_seconds=0.0):
        captured["model"] = model
        captured["api_key"] = api_key
        captured["api_base_url"] = api_base_url
        return original_init(self, fallback=fallback, api_key=api_key, api_base_url=api_base_url, model=model, timeout_seconds=timeout_seconds)

    monkeypatch.setattr(OptionalApiMediaTranscriptionClient, "__init__", _capturing_init)

    def _fake_ensure(**kwargs):
        return LocalAsrBootstrapResult(
            status="already_running",
            message="ok",
            base_url="http://127.0.0.1:9001/v1",
        )

    monkeypatch.setattr(
        "app.runtime.local_asr_bootstrap.ensure_local_asr_if_enabled",
        _fake_ensure,
    )

    client = build_media_transcription_client()
    assert isinstance(client, OptionalApiMediaTranscriptionClient)
    assert captured["model"] == "small"
    assert captured["model"] != "whisper-1"
    assert captured["api_key"] == "local-dev-key"
