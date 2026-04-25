from pathlib import Path

from app.rag.image_loader import (
    IMAGE_EXTENSIONS,
    ImageSourceLoader,
    MockOcrClient,
    OcrResult,
    RapidOcrClient,
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
