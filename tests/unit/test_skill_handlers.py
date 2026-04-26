from __future__ import annotations

from app.skills.handlers import (
    get_trusted_source_handler,
    is_trusted_source_handler,
    list_trusted_source_handlers,
    validate_handler_config,
)


def test_trusted_handler_registry_contains_csv_extract() -> None:
    handlers = list_trusted_source_handlers()
    ids = {handler.id for handler in handlers}

    assert "csv.extract" in ids
    assert get_trusted_source_handler("csv.extract") is not None
    assert is_trusted_source_handler("csv.extract") is True


def test_trusted_handler_registry_contains_audio_transcribe() -> None:
    handlers = list_trusted_source_handlers()
    ids = {handler.id for handler in handlers}

    assert "audio.transcribe" in ids
    assert get_trusted_source_handler("audio.transcribe") is not None
    assert is_trusted_source_handler("audio.transcribe") is True


def test_trusted_handler_registry_contains_video_transcribe() -> None:
    handlers = list_trusted_source_handlers()
    ids = {handler.id for handler in handlers}

    assert "video.transcribe" in ids
    assert get_trusted_source_handler("video.transcribe") is not None
    assert is_trusted_source_handler("video.transcribe") is True


def test_audio_transcribe_config_schema() -> None:
    handler = get_trusted_source_handler("audio.transcribe")
    assert handler is not None
    names = {field.name for field in handler.config_schema}
    assert "provider" in names
    assert "language" in names
    assert "max_chars" in names
    assert "include_timestamps" in names


def test_video_transcribe_config_schema() -> None:
    handler = get_trusted_source_handler("video.transcribe")
    assert handler is not None
    names = {field.name for field in handler.config_schema}
    assert "provider" in names
    assert "language" in names
    assert "max_chars" in names
    assert "include_timestamps" in names


def test_unknown_handler_returns_none_and_false() -> None:
    assert get_trusted_source_handler("custom.handler") is None
    assert is_trusted_source_handler("custom.handler") is False


def test_csv_extract_config_schema_contains_max_rows() -> None:
    handler = get_trusted_source_handler("csv.extract")
    assert handler is not None

    names = {field.name for field in handler.config_schema}
    assert "max_rows" in names


def test_valid_handler_config_passes() -> None:
    errors = validate_handler_config("csv.extract", {"max_rows": 500, "max_chars": 1000, "include_header": True})

    assert errors == ()


def test_unknown_config_key_is_rejected() -> None:
    errors = validate_handler_config("csv.extract", {"unknown": 1})

    assert any("Unsupported handler config keys" in error for error in errors)


def test_wrong_config_type_is_rejected() -> None:
    errors = validate_handler_config("csv.extract", {"max_rows": "many"})

    assert "Handler config 'max_rows' must be an int." in errors


def test_out_of_range_config_is_rejected() -> None:
    errors = validate_handler_config("csv.extract", {"max_rows": 10000})

    assert "Handler config 'max_rows' must be <= 5000." in errors


def test_dangerous_config_key_is_rejected() -> None:
    errors = validate_handler_config("csv.extract", {"api_key": "secret"})

    assert any("Forbidden handler config keys" in error for error in errors)
