"""Image OCR source loading with optional RapidOCR support."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings
from app.rag.source_models import SourceDescriptor, SourceLoadResult

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_DEFAULT_MAX_CHARS = 20000


@dataclass(frozen=True)
class OcrResult:
    """Normalized OCR output for image-to-text ingest."""

    text: str
    provider: str
    warnings: tuple[str, ...] = ()
    confidence: float | None = None


class OcrClient(Protocol):
    """Small OCR client contract used by ImageSourceLoader."""

    def extract(self, path: Path) -> OcrResult:
        """Extract OCR text from an image file."""


@dataclass(frozen=True)
class MockOcrClient:
    """Deterministic OCR fallback used when no real OCR provider is available."""

    text: str | None = None

    def extract(self, path: Path) -> OcrResult:
        text = self.text
        if text is None:
            text = (
                "[Image OCR Text]\n"
                f"No OCR provider configured. This is a placeholder OCR result for {path.name}."
            )
        return OcrResult(text=text, provider="mock", warnings=("ocr_mock_fallback",))


@dataclass(frozen=True)
class DisabledOcrClient:
    """OCR client used when image OCR is explicitly disabled."""

    def extract(self, path: Path) -> OcrResult:
        return OcrResult(text="", provider="disabled", warnings=("ocr_disabled", "ocr_empty"))


@dataclass(frozen=True)
class RapidOcrClient:
    """Optional RapidOCR provider with lazy imports and mock fallback."""

    fallback: OcrClient = MockOcrClient()

    def extract(self, path: Path) -> OcrResult:
        try:
            engine = self._build_engine()
        except Exception:
            fallback_result = self.fallback.extract(path)
            return OcrResult(
                text=fallback_result.text,
                provider=fallback_result.provider,
                warnings=_dedupe(("rapidocr_unavailable", *fallback_result.warnings)),
                confidence=fallback_result.confidence,
            )

        try:
            raw_result = engine(str(path))
        except Exception:
            fallback_result = self.fallback.extract(path)
            return OcrResult(
                text=fallback_result.text,
                provider=fallback_result.provider,
                warnings=_dedupe(("rapidocr_failed", *fallback_result.warnings)),
                confidence=fallback_result.confidence,
            )

        text, confidence = _parse_rapidocr_result(raw_result)
        warnings: tuple[str, ...] = ()
        if not text.strip():
            warnings = ("ocr_empty",)
        return OcrResult(text=text, provider="rapidocr", warnings=warnings, confidence=confidence)

    def _build_engine(self):
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ModuleNotFoundError:
            from rapidocr import RapidOCR
        return RapidOCR()


@dataclass(frozen=True)
class ImageSourceLoader:
    """Load image files by extracting OCR text into the normal RAG text path."""

    ocr_client: OcrClient | None = None
    max_chars: int | None = None
    source_type: str = "file"

    def supports(self, descriptor: SourceDescriptor) -> bool:
        return (
            descriptor.source_type == "file"
            and descriptor.local_path is not None
            and descriptor.local_path.suffix.lower() in IMAGE_EXTENSIONS
        )

    def load(self, descriptor: SourceDescriptor) -> SourceLoadResult:
        path = descriptor.local_path
        if path is None:
            raise ValueError("image source requires local_path")
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported image extension: {path.suffix.lower()}")

        client = self.ocr_client or build_ocr_client()
        result = client.extract(path)
        max_chars = self.max_chars if self.max_chars is not None else _settings_max_chars()
        text = result.text.strip()
        warnings = list(result.warnings)
        if max_chars > 0 and len(text) > max_chars:
            text = text[:max_chars].rstrip()
            warnings.append("ocr_text_truncated")
        if not text:
            warnings.append("ocr_empty")

        metadata = {
            "source_media": "image",
            "source_kind": "image_file",
            "loader_name": "image.ocr",
            "ocr_provider": result.provider,
            "retrieval_basis": "ocr_text",
            "image_filename": path.name,
        }
        if result.confidence is not None:
            metadata["ocr_confidence"] = f"{result.confidence:.4f}"

        return SourceLoadResult(
            descriptor=descriptor,
            title=path.stem,
            text=text,
            metadata=metadata,
            warnings=_dedupe(tuple(warnings)),
        )


def build_ocr_client() -> OcrClient:
    settings = get_settings()
    if not getattr(settings, "image_ocr_enabled", True):
        return DisabledOcrClient()
    provider = str(getattr(settings, "image_ocr_provider", "mock") or "mock").strip().lower()
    if provider == "rapidocr":
        return RapidOcrClient()
    return MockOcrClient()


def _settings_max_chars() -> int:
    return int(getattr(get_settings(), "image_ocr_max_chars", _DEFAULT_MAX_CHARS) or _DEFAULT_MAX_CHARS)


def _parse_rapidocr_result(raw_result) -> tuple[str, float | None]:
    # RapidOCR 3.8+ returns a RapidOCROutput object with .txts and .scores
    # Older versions returned a tuple of lists
    txts: tuple[str, ...] | None = None
    scores: tuple[float, ...] | None = None

    if hasattr(raw_result, "txts") and hasattr(raw_result, "scores"):
        # RapidOCR 3.8+ format
        txts = raw_result.txts
        scores = raw_result.scores
    elif isinstance(raw_result, (list, tuple)) and raw_result:
        # Legacy tuple format: (boxes, txts, scores)
        items = raw_result[0] if len(raw_result) > 0 else None
        if items and isinstance(items, (list, tuple)):
            txts = tuple(_extract_text_from_rapidocr_item(item) for item in items)
            scores = tuple(
                _extract_confidence_from_rapidocr_item(item)
                for item in items
            )
        else:
            txts = tuple(raw_result[1]) if len(raw_result) > 1 else ()
            scores = tuple(raw_result[2]) if len(raw_result) > 2 else ()

    if not txts:
        return "", None

    combined_text = "\n".join(t for t in txts if t)
    avg_confidence = sum(s for s in (scores or ()) if s) / len(scores) if scores else None
    return combined_text.strip(), avg_confidence


def _extract_text_from_rapidocr_item(item) -> str:
    for value in item:
        if isinstance(value, str):
            return value.strip()
    return ""


def _extract_confidence_from_rapidocr_item(item) -> float | None:
    for value in item:
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            return float(value)
    return None


def _dedupe(warnings: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(warning for warning in warnings if warning))
