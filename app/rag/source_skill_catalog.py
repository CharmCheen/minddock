"""Built-in Source Skill Catalog — read-only descriptive registry for implemented source extraction skills.

This module does NOT execute skills. It provides a stable, typed catalog of source
extraction capabilities so that the system can describe what loaders are available,
what they accept, and what they produce, without introducing arbitrary code execution
or LLM-autonomous dispatch.

Design constraints:
- No executable entrypoints.
- No file-path references to local code.
- No API keys or secrets.
- No runtime skill invocation.
- No community plugin discovery.
- No planned/future skills in the active catalog (future skills belong in docs only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceSkillInfo:
    """Descriptive metadata for one built-in source extraction skill.

    Fields are intentionally restricted to documentation-level metadata.
    There is no ``execute()`` or ``entrypoint`` field — execution remains the
    responsibility of ``SourceLoaderRegistry`` and its concrete loaders.
    """

    id: str
    name: str
    kind: str
    version: str
    input_kinds: tuple[str, ...]
    output_type: str
    source_media: str
    source_kind: str
    loader_name: str
    capabilities: tuple[str, ...]
    providers: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Safe JSON-serializable representation."""

        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "version": self.version,
            "input_kinds": list(self.input_kinds),
            "output_type": self.output_type,
            "source_media": self.source_media,
            "source_kind": self.source_kind,
            "loader_name": self.loader_name,
            "capabilities": list(self.capabilities),
            "providers": list(self.providers),
            "limitations": list(self.limitations),
            "notes": list(self.notes),
        }


# Built-in source skills — ONLY implemented skills, no planned/future entries.
_BUILTIN_SOURCE_SKILLS: tuple[SourceSkillInfo, ...] = (
    SourceSkillInfo(
        id="file.pdf",
        name="PDF Text Extraction",
        kind="source",
        version="1.0.0",
        input_kinds=(".pdf",),
        output_type="SourceLoadResult",
        source_media="text",
        source_kind="pdf_file",
        loader_name="pdf.parse",
        capabilities=(
            "pdf_text_extraction",
            "page_metadata",
            "chunking",
            "citation_page_support",
            "structured_block_parsing",
        ),
        notes=("Legacy file loader behavior represented as a source skill.",),
    ),
    SourceSkillInfo(
        id="file.markdown",
        name="Markdown Text Extraction",
        kind="source",
        version="1.0.0",
        input_kinds=(".md", ".markdown"),
        output_type="SourceLoadResult",
        source_media="text",
        source_kind="markdown_file",
        loader_name="markdown.read",
        capabilities=(
            "markdown_text",
            "heading_structure",
        ),
        notes=("Legacy file loader behavior represented as a source skill.",),
    ),
    SourceSkillInfo(
        id="file.text",
        name="Plain Text Extraction",
        kind="source",
        version="1.0.0",
        input_kinds=(".txt",),
        output_type="SourceLoadResult",
        source_media="text",
        source_kind="text_file",
        loader_name="text.read",
        capabilities=(
            "plain_text",
        ),
        notes=("Legacy file loader behavior represented as a source skill.",),
    ),
    SourceSkillInfo(
        id="url.extract",
        name="URL Static HTML Extraction",
        kind="source",
        version="1.0.0",
        input_kinds=("url",),
        output_type="SourceLoadResult",
        source_media="text",
        source_kind="web_page",
        loader_name="url.extract",
        capabilities=(
            "static_html",
            "title_extraction",
            "main_text_extraction",
            "canonical_url",
            "meta_description",
            "loader_warnings",
        ),
        limitations=(
            "no_js_rendering",
            "no_login",
            "no_crawler",
            "no_antibot_bypass",
        ),
    ),
    SourceSkillInfo(
        id="csv.extract",
        name="CSV Rows as Text",
        kind="source",
        version="1.0.0",
        input_kinds=(".csv",),
        output_type="SourceLoadResult",
        source_media="text",
        source_kind="csv_file",
        loader_name="csv.extract",
        capabilities=(
            "csv_rows_as_text",
            "header_detection",
            "row_limit",
            "loader_warnings",
        ),
        limitations=(
            "no_excel",
            "no_sql",
            "no_table_reasoning_engine",
            "no_chart_generation",
        ),
    ),
    SourceSkillInfo(
        id="image.ocr",
        name="Image OCR Text Extraction",
        kind="source",
        version="1.0.0",
        input_kinds=(".png", ".jpg", ".jpeg", ".webp"),
        output_type="SourceLoadResult",
        source_media="image",
        source_kind="image_file",
        loader_name="image.ocr",
        capabilities=(
            "ocr_text",
            "mock_fallback",
            "optional_rapidocr",
            "citation_to_image_source",
        ),
        providers=("mock", "rapidocr"),
        limitations=(
            "no_image_caption",
            "no_multimodal_embedding",
            "no_pdf_figure_extraction",
            "no_frontend_preview",
            "no_layout_reconstruction",
        ),
    ),
    SourceSkillInfo(
        id="audio.transcribe",
        name="Audio Transcript",
        kind="source",
        version="1.0.0",
        input_kinds=(".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".webm"),
        output_type="SourceLoadResult",
        source_media="audio",
        source_kind="audio_file",
        loader_name="audio.transcribe",
        capabilities=(
            "transcript_text",
            "mock_provider",
            "loader_warnings",
        ),
        providers=("mock", "disabled", "api_stub"),
        limitations=(
            "transcript_only_p0",
            "no_speaker_diarization_p0",
            "no_timestamp_citation_ui",
            "real_asr_future",
        ),
    ),
    SourceSkillInfo(
        id="video.transcribe",
        name="Video Transcript",
        kind="source",
        version="1.0.0",
        input_kinds=(".mp4", ".mov", ".mkv", ".webm"),
        output_type="SourceLoadResult",
        source_media="video",
        source_kind="video_file",
        loader_name="video.transcribe",
        capabilities=(
            "transcript_text",
            "mock_provider",
            "loader_warnings",
        ),
        providers=("mock", "disabled", "api_stub"),
        limitations=(
            "transcript_only_p0",
            "no_frame_understanding",
            "no_multimodal_embedding",
            "no_player_ui",
            "real_asr_future",
        ),
    ),
)


_id_to_skill: dict[str, SourceSkillInfo] = {skill.id: skill for skill in _BUILTIN_SOURCE_SKILLS}


def list_builtin_source_skills() -> tuple[SourceSkillInfo, ...]:
    """Return all implemented built-in source extraction skills."""

    return _BUILTIN_SOURCE_SKILLS


def get_builtin_source_skill(skill_id: str) -> SourceSkillInfo | None:
    """Lookup one built-in source skill by stable id.

    Returns ``None`` if the skill is not in the built-in catalog.
    """

    return _id_to_skill.get(skill_id)
