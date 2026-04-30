"""Image OCR source loading with optional RapidOCR support."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings
from app.rag.source_models import SourceDescriptor, SourceLoadResult

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_DEFAULT_MAX_CHARS = 20000

# Tall image detection: images with height/width > this ratio are split vertically
_TALL_IMAGE_THRESHOLD = 2.5
# Overlap between vertical slices as a fraction of slice height
_SLICE_OVERLAP_RATIO = 0.15


@dataclass(frozen=True)
class OcrResult:
    """Normalized OCR output for image-to-text ingest."""

    text: str
    provider: str
    warnings: tuple[str, ...] = ()
    confidence: float | None = None
    box_count: int | None = None


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

        if _is_tall_image(path):
            return self._extract_tall_image(path, engine)

        return self._extract_single_image(path, engine)

    def _extract_single_image(self, path: Path, engine) -> OcrResult:
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

        text, confidence, box_count = _parse_rapidocr_result(raw_result)
        warnings: tuple[str, ...] = ()
        if not text.strip():
            warnings = ("ocr_empty",)
        return OcrResult(
            text=text,
            provider="rapidocr",
            warnings=warnings,
            confidence=confidence,
            box_count=box_count,
        )

    def _extract_tall_image(self, path: Path, engine) -> OcrResult:
        slices = _split_image_vertically(path)
        parts: list[str] = []
        confidences: list[float] = []
        slice_warnings: list[str] = []
        ocr_tall_image_split = True

        with tempfile.TemporaryDirectory() as tmp_dir:
            for idx, slice_img in enumerate(slices):
                tmp_path = Path(tmp_dir) / f"slice_{idx}{path.suffix}"
                try:
                    slice_img.save(tmp_path)
                    raw = engine(str(tmp_path))
                except Exception:
                    slice_warnings.append("ocr_slice_failed")
                    continue
                text, confidence, _ = _parse_rapidocr_result(raw)
                if text.strip():
                    parts.append(f"[image slice {idx + 1}]\n{text}")
                    if confidence is not None:
                        confidences.append(confidence)

        if not parts:
            return OcrResult(
                text="",
                provider="rapidocr",
                warnings=_dedupe(("ocr_tall_image_split", *slice_warnings, "ocr_empty")),
                confidence=None,
                box_count=0,
            )

        avg_confidence = sum(confidences) / len(confidences) if confidences else None
        return OcrResult(
            text="\n".join(parts),
            provider="rapidocr",
            warnings=_dedupe(("ocr_tall_image_split", *slice_warnings)),
            confidence=avg_confidence,
            box_count=None,
        )

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
        if result.box_count is not None:
            metadata["ocr_box_count"] = str(result.box_count)
        if "ocr_tall_image_split" in result.warnings:
            metadata["ocr_tall_image_split"] = "true"
            slice_count = result.text.count("[image slice ")
            if slice_count > 0:
                metadata["ocr_slices"] = str(slice_count)

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


def _parse_rapidocr_result(raw_result) -> tuple[str, float | None, int | None]:
    # RapidOCR can return three shapes:
    # A. Modern 3.8+: object with .dt_boxes (coords), .txts (str list), .scores (float list)
    # B. Legacy 3-element tuple: ([box_item, ...], [txt_str, ...], [score_float, ...])
    #    where each box_item = [x1,y1,x2,y2,...,text_str,score_float]
    # C. 2-element tuple: ([box_item, ...], [mean_score_float, ...])
    #    where each box_item = [[[x1,y1],[x2,y2],[x3,y3],[x4,y4]], text_str, score_float]

    boxes: list | None = None
    txts: list | None = None
    scores: list | None = None

    if hasattr(raw_result, "dt_boxes") and hasattr(raw_result, "txts") and hasattr(raw_result, "scores"):
        # Format A: modern RapidOCR 3.8+
        boxes = raw_result.dt_boxes
        txts = list(raw_result.txts) if raw_result.txts else []
        scores = list(raw_result.scores) if raw_result.scores else []
    elif isinstance(raw_result, (list, tuple)) and raw_result:
        first = raw_result[0]
        if isinstance(first, (list, tuple)) and first and isinstance(first[0], (list, tuple)):
            # Could be format B or C: list of [box_points, text, score] items
            items = list(first)
            if len(raw_result) == 3:
                # Format B: 3-element (items, txts_strlist, scores_floatlist)
                txts = list(raw_result[1]) if raw_result[1] else []
                scores = list(raw_result[2]) if raw_result[2] else []
                # boxes are embedded in items, need to extract
            elif len(raw_result) == 2:
                # Format C: 2-element (items, mean_scores_floatlist)
                # txts and scores are embedded in items
                txts = []
                scores = []
            for item in items:
                # item = [box_points_list, text_str, score_float]
                if len(item) >= 2:
                    txts.append(item[1] if isinstance(item[1], str) else "")
                if len(item) >= 3:
                    try:
                        scores.append(float(item[2]))
                    except (ValueError, TypeError):
                        pass
            boxes = items
        else:
            # Fallback: flat parallel arrays
            txts = list(raw_result[1]) if len(raw_result) > 1 and raw_result[1] else []
            scores = list(raw_result[2]) if len(raw_result) > 2 and raw_result[2] else []

    if not txts:
        return "", None, 0

    # Sort by reading order: top-to-bottom, left-to-right using coordinates
    if boxes:
        sorted_indices = _sort_boxes_by_reading_order(boxes)
        sorted_txts = [txts[i] for i in sorted_indices] if all(isinstance(i, int) and 0 <= i < len(txts) for i in sorted_indices) else txts
        sorted_scores = [scores[i] for i in sorted_indices] if (scores and all(isinstance(i, int) and 0 <= i < len(scores) for i in sorted_indices)) else (scores or [])
    else:
        sorted_txts = txts
        sorted_scores = scores

    combined_text = "\n".join(t.strip() for t in sorted_txts if isinstance(t, str) and t.strip())
    avg_confidence = sum(s for s in sorted_scores if isinstance(s, (int, float))) / len(sorted_scores) if sorted_scores else None
    return combined_text.strip(), avg_confidence, len(sorted_txts)


def _sort_boxes_by_reading_order(boxes: list) -> list[int]:
    """Return sorted indices of boxes by reading order (top-to-bottom, left-to-right).

    Each box is expected to be a list of [x,y] coordinate pairs.
    The first y-coordinate (top of box) is used for primary sort,
    the first x-coordinate (left of box) for secondary sort.
    Returns a list of original indices, sorted.
    """
    if not boxes:
        return []

    def sort_key(item_with_idx):
        idx, box = item_with_idx
        if isinstance(box, (list, tuple)) and len(box) >= 1:
            first_point = box[0]
            # first_point is [x1, y1] — the top-left corner
            if isinstance(first_point, (list, tuple)) and len(first_point) >= 2:
                try:
                    y = float(first_point[1])
                    x = float(first_point[0])
                    return (y, x)
                except (ValueError, TypeError):
                    pass
        return (float("inf"), float("inf"))

    items_with_idx = list(enumerate(boxes))
    try:
        sorted_items = sorted(items_with_idx, key=sort_key)
        return [idx for idx, _ in sorted_items]
    except Exception:
        return list(range(len(boxes)))




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


def _is_tall_image(path: Path) -> bool:
    try:
        from PIL import Image
    except Exception:
        return False
    try:
        with Image.open(path) as img:
            w, h = img.size
            if w <= 0 or h <= 0:
                return False
            return (h / w) > _TALL_IMAGE_THRESHOLD
    except Exception:
        return False


def _split_image_vertically(path: Path) -> list:
    from PIL import Image

    with Image.open(path) as img:
        w, h = img.size
        slice_h = int(w * _TALL_IMAGE_THRESHOLD)
        overlap = int(slice_h * _SLICE_OVERLAP_RATIO)
        slices: list = []
        offset_y = 0
        idx = 0
        while offset_y < h:
            bottom = min(offset_y + slice_h + overlap, h)
            slice_img = img.crop((0, offset_y, w, bottom))
            slices.append(slice_img)
            idx += 1
            if offset_y + slice_h >= h:
                break
            offset_y += slice_h
        return slices
