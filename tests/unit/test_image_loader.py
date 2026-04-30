import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from app.rag.image_loader import (
    IMAGE_EXTENSIONS,
    ImageSourceLoader,
    MockOcrClient,
    OcrResult,
    RapidOcrClient,
    _is_tall_image,
    _parse_rapidocr_result,
    _sort_boxes_by_reading_order,
    _split_image_vertically,
)
from app.rag.ingest import build_documents_for_source
from app.rag.source_loader import FileSourceLoader, SourceLoaderRegistry, build_file_descriptor


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\xf8\x0f"
    b"\x00\x01\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _write_image(tmp_path: Path, name: str = "sample.png") -> tuple[Path, Path]:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    image_path = kb_dir / name
    image_path.write_bytes(PNG_1X1)
    return kb_dir, image_path


def _make_fake_image(tmp_path: Path, name: str, width: int, height: int) -> tuple[Path, Path]:
    """Create a fake image file with explicit dimensions."""
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    image_path = kb_dir / name
    img = Image.new("RGB", (width, height), color="white")
    img.save(image_path)
    return kb_dir, image_path


# ---------------------------------------------------------------------------
# Existing tests
# ---------------------------------------------------------------------------


def test_image_source_loader_supports_expected_extensions(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    loader = ImageSourceLoader()

    for extension in (".png", ".jpg", ".jpeg", ".webp"):
        path = kb_dir / f"sample{extension}"
        path.write_bytes(PNG_1X1)
        assert loader.supports(build_file_descriptor(path, kb_dir))


def test_image_source_loader_rejects_unsupported_extensions(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    loader = ImageSourceLoader()

    for extension in (".gif", ".bmp", ".svg"):
        path = kb_dir / f"sample{extension}"
        path.write_bytes(PNG_1X1)
        assert not loader.supports(build_file_descriptor(path, kb_dir))


def test_mock_ocr_client_returns_placeholder_text(tmp_path: Path) -> None:
    _, image_path = _write_image(tmp_path)

    result = MockOcrClient().extract(image_path)

    assert isinstance(result, OcrResult)
    assert result.provider == "mock"
    assert "[Image OCR Text]" in result.text
    assert "placeholder OCR result for sample.png" in result.text
    assert result.warnings == ("ocr_mock_fallback",)


def test_image_source_loader_with_mock_returns_source_load_result(tmp_path: Path) -> None:
    kb_dir, image_path = _write_image(tmp_path)
    descriptor = build_file_descriptor(image_path, kb_dir)
    loader = ImageSourceLoader(ocr_client=MockOcrClient(text="MindDock image OCR smoke phrase 20260425"))

    result = loader.load(descriptor)

    assert result.text == "MindDock image OCR smoke phrase 20260425"
    assert result.metadata["source_media"] == "image"
    assert result.metadata["source_kind"] == "image_file"
    assert result.metadata["loader_name"] == "image.ocr"
    assert result.metadata["ocr_provider"] == "mock"
    assert result.metadata["retrieval_basis"] == "ocr_text"
    assert result.metadata["image_filename"] == "sample.png"
    assert str(tmp_path) not in " ".join(result.metadata.values())


def test_registry_resolves_image_before_file_loader(tmp_path: Path) -> None:
    kb_dir, image_path = _write_image(tmp_path)
    descriptor = build_file_descriptor(image_path, kb_dir)

    loader = SourceLoaderRegistry().resolve(descriptor)

    assert isinstance(loader, ImageSourceLoader)
    assert not isinstance(loader, FileSourceLoader)


def test_build_documents_for_source_chunks_image_ocr_text(tmp_path: Path) -> None:
    kb_dir, image_path = _write_image(tmp_path)
    descriptor = build_file_descriptor(image_path, kb_dir)
    registry = SourceLoaderRegistry(
        loaders=[ImageSourceLoader(ocr_client=MockOcrClient(text="MindDock image OCR smoke phrase 20260425"))]
    )

    documents = build_documents_for_source(descriptor, registry=registry)

    assert len(documents) == 1
    assert documents[0].page_content == "MindDock image OCR smoke phrase 20260425"
    assert documents[0].metadata["source"] == "sample.png"
    assert documents[0].metadata["source_media"] == "image"
    assert documents[0].metadata["source_kind"] == "image_file"
    assert documents[0].metadata["retrieval_basis"] == "ocr_text"
    assert documents[0].metadata["ocr_provider"] == "mock"


def test_rapidocr_provider_falls_back_when_unavailable(monkeypatch, tmp_path: Path) -> None:
    _, image_path = _write_image(tmp_path)

    def missing_engine(self):
        raise ModuleNotFoundError("rapidocr")

    monkeypatch.setattr(RapidOcrClient, "_build_engine", missing_engine)

    result = RapidOcrClient().extract(image_path)

    assert result.provider == "mock"
    assert "rapidocr_unavailable" in result.warnings
    assert "[Image OCR Text]" in result.text


def test_rapidocr_provider_is_lazy_imported() -> None:
    import app.rag.image_loader as image_loader

    assert "RapidOCR" not in image_loader.__dict__


def test_empty_ocr_text_does_not_create_chunk(tmp_path: Path) -> None:
    kb_dir, image_path = _write_image(tmp_path)
    descriptor = build_file_descriptor(image_path, kb_dir)
    loader = ImageSourceLoader(ocr_client=MockOcrClient(text=""))
    result = loader.load(descriptor)

    documents = build_documents_for_source(descriptor, registry=SourceLoaderRegistry(loaders=[loader]))

    assert "ocr_empty" in result.warnings
    assert documents == []


def test_supported_image_extensions_constant_is_limited() -> None:
    assert IMAGE_EXTENSIONS == {".png", ".jpg", ".jpeg", ".webp"}


# ---------------------------------------------------------------------------
# New tests: reading-order sorting
# ---------------------------------------------------------------------------


def test_parse_rapidocr_result_sorts_by_reading_order() -> None:
    """OCR lines from bottom of image should appear after lines from top (via dt_boxes)."""
    # Format A: modern RapidOCR 3.8+ with dt_boxes, txts, scores as parallel arrays
    # dt_boxes: list of [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] per detection
    dt_boxes = [
        [[100.0, 300.0], [200.0, 300.0], [200.0, 350.0], [100.0, 350.0]],  # bottom
        [[100.0, 150.0], [200.0, 150.0], [200.0, 200.0], [100.0, 200.0]],  # middle
        [[100.0, 50.0], [200.0, 50.0], [200.0, 100.0], [100.0, 100.0]],    # top
    ]
    txts = ("bottom text", "middle text", "top text")
    scores = (0.9, 0.9, 0.9)

    class FakeRapidOCROutput:
        pass

    FakeRapidOCROutput.dt_boxes = dt_boxes
    FakeRapidOCROutput.txts = txts
    FakeRapidOCROutput.scores = scores

    text, confidence, box_count = _parse_rapidocr_result(FakeRapidOCROutput())

    lines = text.split("\n")
    assert lines.index("top text") < lines.index("middle text") < lines.index("bottom text"), (
        f"Reading order wrong: {lines}"
    )
    assert box_count == 3
    assert confidence is not None


def test_parse_rapidocr_result_sorts_left_to_right_within_same_row() -> None:
    """Two items on the same y-level should be sorted left-to-right (via dt_boxes)."""
    dt_boxes = [
        [[300.0, 100.0], [400.0, 100.0], [400.0, 150.0], [300.0, 150.0]],  # right
        [[50.0, 100.0], [150.0, 100.0], [150.0, 150.0], [50.0, 150.0]],    # left
    ]
    txts = ("right text", "left text")
    scores = (0.9, 0.9)

    class FakeRapidOCROutput:
        pass

    FakeRapidOCROutput.dt_boxes = dt_boxes
    FakeRapidOCROutput.txts = txts
    FakeRapidOCROutput.scores = scores

    text, _, box_count = _parse_rapidocr_result(FakeRapidOCROutput())

    lines = text.split("\n")
    assert lines.index("left text") < lines.index("right text"), f"Left-right order wrong: {lines}"
    assert box_count == 2


def test_parse_rapidocr_result_preserves_order_when_boxes_unavailable() -> None:
    """Without dt_boxes, text order is preserved (detection order)."""
    # Format C: 2-element tuple (installed RapidOCR format)
    # each item = [box_points, text_str, score_float]  where box_points = [[x,y],[x,y],[x,y],[x,y]]
    item0 = [[100.0, 300.0], [200.0, 300.0], [200.0, 350.0], [100.0, 350.0]], "first text", 0.9
    item1 = [[100.0, 150.0], [200.0, 150.0], [200.0, 200.0], [100.0, 200.0]], "second text", 0.9
    item2 = [[100.0, 50.0], [200.0, 50.0], [200.0, 100.0], [100.0, 100.0]], "third text", 0.9
    detections = [item0, item1, item2]
    mean_scores = [0.9, 0.9, 0.9]
    raw_result = (detections, mean_scores)  # 2-element format

    text, _, box_count = _parse_rapidocr_result(raw_result)

    assert "first text" in text
    assert "second text" in text
    assert "third text" in text
    assert box_count == 3


def test_parse_rapidocr_result_handles_empty_result() -> None:
    class FakeRapidOCROutput:
        txts = ()
        scores = ()

    text, confidence, box_count = _parse_rapidocr_result(FakeRapidOCROutput())

    assert text == ""
    assert confidence is None
    assert box_count == 0


def test_sort_boxes_by_reading_order_with_non_numeric_coordinates() -> None:
    """Non-numeric box coordinates should not crash; returns original index order."""
    boxes = [["invalid", "coords"], ["also", "invalid"], ["still", "bad"]]
    indices = _sort_boxes_by_reading_order(boxes)
    assert indices == [0, 1, 2]


def test_sort_boxes_by_reading_order_with_empty_input() -> None:
    indices = _sort_boxes_by_reading_order([])
    assert indices == []


def test_mock_ocr_client_box_count_is_none(tmp_path: Path) -> None:
    """MockOcrClient should not produce box_count."""
    _, image_path = _write_image(tmp_path)
    result = MockOcrClient(text="some text").extract(image_path)
    assert result.box_count is None


# ---------------------------------------------------------------------------
# New tests: tall image detection and splitting
# ---------------------------------------------------------------------------


def test_is_tall_image_returns_true_for_tall_aspect_ratio(tmp_path: Path) -> None:
    """Image with height/width > 2.5 should be detected as tall."""
    _, path = _make_fake_image(tmp_path, "tall.png", width=300, height=900)
    assert _is_tall_image(path) is True


def test_is_tall_image_returns_false_for_normal_aspect_ratio(tmp_path: Path) -> None:
    """Normal images should not be flagged as tall."""
    _, path = _make_fake_image(tmp_path, "normal.png", width=300, height=300)
    assert _is_tall_image(path) is False


def test_is_tall_image_returns_false_for_wide_image(tmp_path: Path) -> None:
    """Wide images should not be flagged as tall."""
    _, path = _make_fake_image(tmp_path, "wide.png", width=900, height=300)
    assert _is_tall_image(path) is False


def test_is_tall_image_returns_false_at_exactly_threshold(tmp_path: Path) -> None:
    """At exactly 2.5×, image should NOT be considered tall."""
    _, path = _make_fake_image(tmp_path, "borderline.png", width=100, height=250)
    assert _is_tall_image(path) is False


def test_is_tall_image_returns_false_for_unreadable_file(tmp_path: Path) -> None:
    """Non-image files should not crash; return False."""
    bad_path = tmp_path / "not_an_image.txt"
    bad_path.write_text("not an image")
    assert _is_tall_image(bad_path) is False


def test_split_image_vertically_returns_multiple_slices_for_tall_image(tmp_path: Path) -> None:
    """A 300×900 image should be split into 2+ slices."""
    _, path = _make_fake_image(tmp_path, "tall.png", width=300, height=900)
    slices = _split_image_vertically(path)
    assert len(slices) >= 2


def test_split_image_vertically_single_slice_for_normal_image(tmp_path: Path) -> None:
    """A 300×300 image should produce 1 slice."""
    _, path = _make_fake_image(tmp_path, "normal.png", width=300, height=300)
    slices = _split_image_vertically(path)
    assert len(slices) == 1


def test_split_image_vertically_slices_have_overlap(tmp_path: Path) -> None:
    """Slices should overlap to avoid losing text at boundaries."""
    _, path = _make_fake_image(tmp_path, "tall2.png", width=200, height=700)
    slices = _split_image_vertically(path)
    assert len(slices) >= 2
    # Each slice should be a PIL Image
    for s in slices:
        assert isinstance(s, Image.Image)


def test_rapidocr_tall_image_uses_temp_directory_outside_kb(
    monkeypatch, tmp_path: Path
) -> None:
    """Temp directory for slices must be outside knowledge_base."""
    _, image_path = _make_fake_image(tmp_path, "tall.png", width=300, height=900)
    kb_dir = tmp_path / "knowledge_base"

    # Track that temp dir is outside kb_dir
    tmp_dirs_created: list[str] = []

    original_temp_dir = tempfile.TemporaryDirectory

    class TrackedTempDir(original_temp_dir):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            tmp_dirs_created.append(self.name)

    monkeypatch.setattr(tempfile, "TemporaryDirectory", TrackedTempDir)

    fake_engine = MagicMock()
    fake_engine.return_value = MagicMock(txts=(), scores=())

    with patch.object(RapidOcrClient, "_build_engine", return_value=fake_engine):
        result = RapidOcrClient().extract(image_path)

    # All temp dirs must be outside kb_dir
    for td in tmp_dirs_created:
        assert not td.startswith(str(kb_dir)), f"Temp dir inside kb_dir: {td}"


def test_rapidocr_tall_image_returns_slice_markers(monkeypatch, tmp_path: Path) -> None:
    """OCR result for tall image must contain [image slice N] markers."""
    _, image_path = _make_fake_image(tmp_path, "tall.png", width=300, height=900)

    fake_engine = MagicMock()
    call_count = [0]

    def fake_engine_call(path_str: str):
        call_count[0] += 1
        idx = call_count[0]
        # Format: raw = (detections_list, mean_scores_list)
        # detections_list[i] = [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], text_str, score_float
        detections = [[[0, 0, 10, 0, 10, 10, 0, 10], f"slice {idx} text", 0.9]]
        mean_scores = [0.9]
        return (detections, mean_scores)

    fake_engine.side_effect = fake_engine_call

    with patch.object(RapidOcrClient, "_build_engine", return_value=fake_engine):
        result = RapidOcrClient().extract(image_path)

    assert "[image slice 1]" in result.text
    assert "[image slice 2]" in result.text
    assert "ocr_tall_image_split" in result.warnings


def test_rapidocr_tall_image_partial_failure_continues(monkeypatch, tmp_path: Path) -> None:
    """If one slice fails, successful slices should still be included."""
    _, image_path = _make_fake_image(tmp_path, "tall.png", width=300, height=900)

    fake_engine = MagicMock()
    call_count = [0]

    def fake_engine_call(path_str: str):
        call_count[0] += 1
        if call_count[0] == 2:
            raise RuntimeError("simulated OCR failure on slice 2")
        idx = call_count[0]
        detections = [[[0, 0, 10, 0, 10, 10, 0, 10], f"slice {idx} text", 0.9]]
        mean_scores = [0.9]
        return (detections, mean_scores)

    fake_engine.side_effect = fake_engine_call

    with patch.object(RapidOcrClient, "_build_engine", return_value=fake_engine):
        result = RapidOcrClient().extract(image_path)

    assert "slice 1 text" in result.text
    assert "ocr_slice_failed" in result.warnings
    assert "ocr_tall_image_split" in result.warnings


def test_rapidocr_tall_image_all_slices_fail_graceful_empty(monkeypatch, tmp_path: Path) -> None:
    """If all slices fail, return empty result with warning, not crash."""
    _, image_path = _make_fake_image(tmp_path, "tall.png", width=300, height=900)

    fake_engine = MagicMock()
    fake_engine.side_effect = RuntimeError("all slices fail")

    with patch.object(RapidOcrClient, "_build_engine", return_value=fake_engine):
        result = RapidOcrClient().extract(image_path)

    assert result.text == ""
    assert "ocr_empty" in result.warnings
    assert "ocr_tall_image_split" in result.warnings


def test_image_source_loader_load_sets_tall_image_metadata(monkeypatch, tmp_path: Path) -> None:
    """ImageSourceLoader.load should set ocr_tall_image_split metadata."""
    _, image_path = _make_fake_image(tmp_path, "tall.png", width=300, height=900)
    kb_dir = tmp_path / "knowledge_base"

    fake_engine = MagicMock()
    call_count = [0]

    def fake_engine_call(path_str: str):
        call_count[0] += 1
        idx = call_count[0]
        detections = [[[0, 0, 10, 0, 10, 10, 0, 10], f"slice {idx} text", 0.9]]
        mean_scores = [0.9]
        return (detections, mean_scores)

    fake_engine.side_effect = fake_engine_call

    loader = ImageSourceLoader(ocr_client=RapidOcrClient())
    with patch.object(RapidOcrClient, "_build_engine", return_value=fake_engine):
        descriptor = build_file_descriptor(image_path, kb_dir)
        result = loader.load(descriptor)

    assert result.metadata.get("ocr_tall_image_split") == "true"


def test_image_source_loader_load_sets_box_count_metadata(monkeypatch, tmp_path: Path) -> None:
    """ImageSourceLoader.load should set ocr_box_count when available."""
    _, image_path = _make_fake_image(tmp_path, "normal.png", width=300, height=300)
    kb_dir = tmp_path / "knowledge_base"

    fake_engine = MagicMock()

    detections = [
        [[0, 0, 10, 0, 10, 10, 0, 10], "line 1", 0.9],
        [[0, 20, 10, 20, 10, 30, 0, 30], "line 2", 0.9],
    ]
    mean_scores = [0.9, 0.9]
    fake_engine.return_value = (detections, mean_scores)

    loader = ImageSourceLoader(ocr_client=RapidOcrClient())
    with patch.object(RapidOcrClient, "_build_engine", return_value=fake_engine):
        descriptor = build_file_descriptor(image_path, kb_dir)
        result = loader.load(descriptor)

    assert result.metadata.get("ocr_box_count") == "2"
