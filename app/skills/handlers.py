"""Trusted source-skill handler contracts.

Local manifests may bind only to these built-in handler identifiers. The
contract is descriptive metadata only: it does not contain Python callables,
module paths, entrypoints, or user-controlled code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


HandlerConfigType = Literal["str", "int", "float", "bool", "enum"]


@dataclass(frozen=True)
class HandlerConfigField:
    name: str
    type: HandlerConfigType
    required: bool = False
    default: Any | None = None
    choices: tuple[str, ...] = ()
    min_value: int | float | None = None
    max_value: int | float | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "default": self.default,
            "choices": list(self.choices),
            "min_value": self.min_value,
            "max_value": self.max_value,
            "description": self.description,
        }


@dataclass(frozen=True)
class TrustedSourceHandler:
    id: str
    name: str
    input_kinds: tuple[str, ...]
    output_type: str
    source_media: str
    source_kind: str
    loader_name: str
    permissions: tuple[str, ...]
    capabilities: tuple[str, ...]
    limitations: tuple[str, ...]
    config_schema: tuple[HandlerConfigField, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "input_kinds": list(self.input_kinds),
            "output_type": self.output_type,
            "source_media": self.source_media,
            "source_kind": self.source_kind,
            "loader_name": self.loader_name,
            "permissions": list(self.permissions),
            "capabilities": list(self.capabilities),
            "limitations": list(self.limitations),
            "config_schema": [field.to_dict() for field in self.config_schema],
        }

ALLOWED_SOURCE_SKILL_PERMISSIONS: frozenset[str] = frozenset(
    {
        "read_file",
        "read_url",
        "use_ocr",
        "use_llm_api",
        "write_index",
    }
)

FORBIDDEN_SOURCE_SKILL_PERMISSIONS: frozenset[str] = frozenset(
    {
        "subprocess",
        "read_env",
        "write_file",
        "delete_file",
        "network_any",
        "execute_code",
    }
)

DANGEROUS_MANIFEST_FIELDS: frozenset[str] = frozenset(
    {
        "entrypoint",
        "module_path",
        "script_path",
        "python_path",
        "execute",
        "run",
        "subprocess",
        "env",
        "api_key",
        "secret",
        "token",
    }
)

DANGEROUS_HANDLER_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "token",
        "secret",
        "env",
        "command",
        "script",
        "subprocess",
        "path",
    }
)


_TRUSTED_SOURCE_HANDLERS_BY_ID: dict[str, TrustedSourceHandler] = {
    "file.pdf": TrustedSourceHandler(
        id="file.pdf",
        name="PDF Parser",
        input_kinds=(".pdf",),
        output_type="SourceLoadResult",
        source_media="text",
        source_kind="pdf_file",
        loader_name="pdf.parse",
        permissions=("read_file", "write_index"),
        capabilities=("pdf_text", "page_metadata"),
        limitations=("no_scanned_pdf_ocr", "no_pdf_figure_extraction"),
    ),
    "file.markdown": TrustedSourceHandler(
        id="file.markdown",
        name="Markdown Loader",
        input_kinds=(".md", ".markdown"),
        output_type="SourceLoadResult",
        source_media="text",
        source_kind="markdown_file",
        loader_name="markdown.read",
        permissions=("read_file", "write_index"),
        capabilities=("markdown_text",),
        limitations=("no_markdown_execution",),
    ),
    "file.text": TrustedSourceHandler(
        id="file.text",
        name="Text Loader",
        input_kinds=(".txt",),
        output_type="SourceLoadResult",
        source_media="text",
        source_kind="text_file",
        loader_name="text.read",
        permissions=("read_file", "write_index"),
        capabilities=("plain_text",),
        limitations=("no_binary_text_detection",),
    ),
    "url.extract": TrustedSourceHandler(
        id="url.extract",
        name="Static URL Extraction",
        input_kinds=("url",),
        output_type="SourceLoadResult",
        source_media="text",
        source_kind="web_page",
        loader_name="url.extract",
        permissions=("read_url", "write_index"),
        capabilities=("static_html_text", "metadata_extraction"),
        limitations=("no_js_rendering", "no_crawler", "no_login"),
        config_schema=(
            HandlerConfigField(
                name="timeout_seconds",
                type="int",
                default=15,
                min_value=1,
                max_value=60,
                description="Static HTML fetch timeout used by future handler integrations.",
            ),
        ),
    ),
    "image.ocr": TrustedSourceHandler(
        id="image.ocr",
        name="Image OCR",
        input_kinds=(".png", ".jpg", ".jpeg", ".webp"),
        output_type="SourceLoadResult",
        source_media="image",
        source_kind="image_file",
        loader_name="image.ocr",
        permissions=("read_file", "use_ocr", "write_index"),
        capabilities=("ocr_text",),
        limitations=("no_image_caption", "no_multimodal_embedding", "no_frontend_preview"),
        config_schema=(
            HandlerConfigField(
                name="max_chars",
                type="int",
                default=20000,
                min_value=100,
                max_value=200000,
                description="Maximum OCR text characters retained by future handler integrations.",
            ),
        ),
    ),
    "csv.extract": TrustedSourceHandler(
        id="csv.extract",
        name="CSV Extraction",
        input_kinds=(".csv",),
        output_type="SourceLoadResult",
        source_media="text",
        source_kind="csv_file",
        loader_name="csv.extract",
        permissions=("read_file", "write_index"),
        capabilities=("csv_rows_as_text", "header_detection"),
        limitations=("no_excel", "no_sql", "no_formula_execution"),
        config_schema=(
            HandlerConfigField(
                name="max_rows",
                type="int",
                default=200,
                min_value=1,
                max_value=5000,
                description="Maximum CSV rows used by future handler integrations.",
            ),
            HandlerConfigField(
                name="max_chars",
                type="int",
                default=20000,
                min_value=100,
                max_value=200000,
                description="Maximum extracted CSV text characters used by future handler integrations.",
            ),
            HandlerConfigField(
                name="include_header",
                type="bool",
                default=True,
                description="Whether CSV header names are included in row text.",
            ),
        ),
    ),
    "audio.transcribe": TrustedSourceHandler(
        id="audio.transcribe",
        name="Audio Transcription",
        input_kinds=(".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".webm"),
        output_type="SourceLoadResult",
        source_media="audio",
        source_kind="audio_file",
        loader_name="audio.transcribe",
        permissions=("read_file", "use_llm_api", "write_index"),
        capabilities=("transcript_text",),
        limitations=("transcript_only_p0", "no_speaker_diarization_p0", "no_timestamp_citation_ui"),
        config_schema=(
            HandlerConfigField(
                name="provider",
                type="enum",
                default="mock",
                choices=("mock", "disabled", "api"),
                description="Transcription provider. mock = placeholder text; disabled = skip; api = real provider (requires backend config).",
            ),
            HandlerConfigField(
                name="language",
                type="str",
                required=False,
                description="Optional language hint for transcription.",
            ),
            HandlerConfigField(
                name="max_chars",
                type="int",
                default=30000,
                min_value=100,
                max_value=300000,
                description="Maximum transcript characters retained.",
            ),
            HandlerConfigField(
                name="include_timestamps",
                type="bool",
                default=False,
                description="Whether to include segment timestamps in transcript text.",
            ),
        ),
    ),
    "video.transcribe": TrustedSourceHandler(
        id="video.transcribe",
        name="Video Transcription",
        input_kinds=(".mp4", ".mov", ".mkv", ".webm"),
        output_type="SourceLoadResult",
        source_media="video",
        source_kind="video_file",
        loader_name="video.transcribe",
        permissions=("read_file", "use_llm_api", "write_index"),
        capabilities=("transcript_text",),
        limitations=("transcript_only_p0", "no_frame_understanding", "no_multimodal_embedding", "no_player_ui"),
        config_schema=(
            HandlerConfigField(
                name="provider",
                type="enum",
                default="mock",
                choices=("mock", "disabled", "api"),
                description="Transcription provider. mock = placeholder text; disabled = skip; api = real provider (requires backend config).",
            ),
            HandlerConfigField(
                name="language",
                type="str",
                required=False,
                description="Optional language hint for transcription.",
            ),
            HandlerConfigField(
                name="max_chars",
                type="int",
                default=30000,
                min_value=100,
                max_value=300000,
                description="Maximum transcript characters retained.",
            ),
            HandlerConfigField(
                name="include_timestamps",
                type="bool",
                default=False,
                description="Whether to include segment timestamps in transcript text.",
            ),
        ),
    ),
}

TRUSTED_SOURCE_HANDLERS: frozenset[str] = frozenset(_TRUSTED_SOURCE_HANDLERS_BY_ID)


def list_trusted_source_handlers() -> tuple[TrustedSourceHandler, ...]:
    return tuple(_TRUSTED_SOURCE_HANDLERS_BY_ID[key] for key in sorted(_TRUSTED_SOURCE_HANDLERS_BY_ID))


def get_trusted_source_handler(handler_id: str) -> TrustedSourceHandler | None:
    return _TRUSTED_SOURCE_HANDLERS_BY_ID.get(handler_id)


def is_trusted_source_handler(handler_id: str) -> bool:
    return handler_id in _TRUSTED_SOURCE_HANDLERS_BY_ID


def validate_handler_config(handler_id: str, config: dict[str, Any] | None) -> tuple[str, ...]:
    handler = get_trusted_source_handler(handler_id)
    if handler is None:
        return (f"Handler '{handler_id}' is not a trusted built-in source handler.",)
    if config is None:
        config = {}
    if not isinstance(config, dict):
        return ("Handler config must be an object.",)

    errors: list[str] = []
    lower_keys = {str(key).lower() for key in config}
    dangerous = sorted(lower_keys & DANGEROUS_HANDLER_CONFIG_KEYS)
    if dangerous:
        errors.append(f"Forbidden handler config keys: {', '.join(dangerous)}")

    schema_by_name = {field.name: field for field in handler.config_schema}
    if config and not schema_by_name:
        errors.append(f"Handler '{handler_id}' does not accept manifest config.")
        return tuple(errors)

    unknown = sorted(set(config) - set(schema_by_name))
    if unknown:
        errors.append(f"Unsupported handler config keys for {handler_id}: {', '.join(unknown)}")

    for field in handler.config_schema:
        if field.required and field.name not in config:
            errors.append(f"Missing required handler config key: {field.name}")
        if field.name in config:
            errors.extend(_validate_config_value(field, config[field.name]))

    return tuple(errors)


def _validate_config_value(field: HandlerConfigField, value: Any) -> list[str]:
    errors: list[str] = []
    if field.type == "bool":
        if not isinstance(value, bool):
            errors.append(f"Handler config '{field.name}' must be a bool.")
        return errors
    if field.type == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(f"Handler config '{field.name}' must be an int.")
            return errors
        _validate_range(field, value, errors)
        return errors
    if field.type == "float":
        if isinstance(value, bool) or not isinstance(value, int | float):
            errors.append(f"Handler config '{field.name}' must be a float.")
            return errors
        _validate_range(field, float(value), errors)
        return errors
    if field.type == "str":
        if not isinstance(value, str):
            errors.append(f"Handler config '{field.name}' must be a str.")
        return errors
    if field.type == "enum":
        if not isinstance(value, str):
            errors.append(f"Handler config '{field.name}' must be an enum string.")
        elif value not in field.choices:
            errors.append(f"Handler config '{field.name}' must be one of: {', '.join(field.choices)}")
        return errors
    errors.append(f"Handler config '{field.name}' has unsupported schema type.")
    return errors


def _validate_range(field: HandlerConfigField, value: int | float, errors: list[str]) -> None:
    if field.min_value is not None and value < field.min_value:
        errors.append(f"Handler config '{field.name}' must be >= {field.min_value}.")
    if field.max_value is not None and value > field.max_value:
        errors.append(f"Handler config '{field.name}' must be <= {field.max_value}.")
