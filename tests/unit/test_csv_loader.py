"""Tests for the CSV source skill."""

from __future__ import annotations

from pathlib import Path

from app.rag.ingest import build_documents_for_source
from app.rag.source_loader import FileSourceLoader, SourceLoaderRegistry, build_file_descriptor
from app.rag.source_skills.csv_skill import CSV_EXTENSIONS, CsvSourceLoader


# ---------------------------------------------------------------------------
# Support and rejection
# ---------------------------------------------------------------------------


def test_csv_source_loader_supports_csv(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    csv_path = kb_dir / "data.csv"
    csv_path.write_text("name,value\nfoo,1\n", encoding="utf-8")

    loader = CsvSourceLoader()
    assert loader.supports(build_file_descriptor(csv_path, kb_dir))


def test_csv_source_loader_rejects_xlsx(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    xlsx_path = kb_dir / "data.xlsx"
    xlsx_path.write_text("fake", encoding="utf-8")

    loader = CsvSourceLoader()
    assert not loader.supports(build_file_descriptor(xlsx_path, kb_dir))


def test_csv_extensions_constant() -> None:
    assert CSV_EXTENSIONS == {".csv"}


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------


def test_simple_csv_with_header(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    csv_path = kb_dir / "simple.csv"
    csv_path.write_text("name,category,note\nMindDock,project,validates contract\n", encoding="utf-8")

    loader = CsvSourceLoader()
    result = loader.load(build_file_descriptor(csv_path, kb_dir))

    assert "[CSV Table]" in result.text
    assert "Columns: name, category, note" in result.text
    assert "name: MindDock" in result.text
    assert "category: project" in result.text
    assert "note: validates contract" in result.text


def test_csv_with_utf8_bom(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    csv_path = kb_dir / "bom.csv"
    csv_path.write_bytes(b"\xef\xbb\xbfname,value\n" + "\u6d4b\u8bd5,1\n".encode("utf-8"))

    loader = CsvSourceLoader()
    result = loader.load(build_file_descriptor(csv_path, kb_dir))

    assert "\u6d4b\u8bd5" in result.text
    assert result.metadata["source_media"] == "text"


def test_csv_without_header_uses_column_names(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    csv_path = kb_dir / "no_header.csv"
    # First row is all-numeric, so heuristic treats it as data and generates Column N names
    csv_path.write_text("1,30\nBob,25\n", encoding="utf-8")

    loader = CsvSourceLoader()
    result = loader.load(build_file_descriptor(csv_path, kb_dir))

    assert "Column 1: 1" in result.text
    assert "Column 2: 30" in result.text
    assert "Column 1: Bob" in result.text


def test_empty_csv_warning(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    csv_path = kb_dir / "empty.csv"
    csv_path.write_text("", encoding="utf-8")

    loader = CsvSourceLoader()
    result = loader.load(build_file_descriptor(csv_path, kb_dir))

    assert "csv_empty" in result.warnings
    assert result.text == ""


def test_csv_header_only_warning(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    csv_path = kb_dir / "header_only.csv"
    csv_path.write_text("name,value\n", encoding="utf-8")

    loader = CsvSourceLoader()
    result = loader.load(build_file_descriptor(csv_path, kb_dir))

    assert "csv_empty" in result.warnings


def test_large_csv_truncated(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    csv_path = kb_dir / "large.csv"
    lines = ["id,name"] + [f"{i},row{i}" for i in range(1, 12)]
    csv_path.write_text("\n".join(lines), encoding="utf-8")

    loader = CsvSourceLoader(max_rows=5)
    result = loader.load(build_file_descriptor(csv_path, kb_dir))

    assert "csv_truncated" in result.warnings
    assert result.metadata["csv_row_count"] == "11"
    assert result.metadata["csv_rows_indexed"] == "5"
    assert result.metadata["csv_truncated"] == "true"


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def test_csv_metadata_fields(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    csv_path = kb_dir / "meta.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")

    loader = CsvSourceLoader()
    result = loader.load(build_file_descriptor(csv_path, kb_dir))

    assert result.metadata["source_media"] == "text"
    assert result.metadata["source_kind"] == "csv_file"
    assert result.metadata["loader_name"] == "csv.extract"
    assert result.metadata["retrieval_basis"] == "csv_rows_as_text"
    assert result.metadata["csv_filename"] == "meta.csv"
    assert result.metadata["csv_columns"] == "a,b"
    assert result.metadata["csv_row_count"] == "1"
    assert result.metadata["csv_rows_indexed"] == "1"


def test_csv_metadata_does_not_contain_absolute_path(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    csv_path = kb_dir / "path_test.csv"
    csv_path.write_text("x\n1\n", encoding="utf-8")

    loader = CsvSourceLoader()
    result = loader.load(build_file_descriptor(csv_path, kb_dir))

    text = " ".join(result.metadata.values())
    assert str(tmp_path) not in text


# ---------------------------------------------------------------------------
# Registry and chunking
# ---------------------------------------------------------------------------


def test_registry_resolves_csv_before_generic_file_loader(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    csv_path = kb_dir / "data.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")
    descriptor = build_file_descriptor(csv_path, kb_dir)

    loader = SourceLoaderRegistry().resolve(descriptor)

    assert isinstance(loader, CsvSourceLoader)
    assert not isinstance(loader, FileSourceLoader)


def test_build_documents_for_source_chunks_csv_text(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    csv_path = kb_dir / "chunk.csv"
    csv_path.write_text("name,value\nFoo,1\nBar,2\n", encoding="utf-8")
    descriptor = build_file_descriptor(csv_path, kb_dir)

    documents = build_documents_for_source(descriptor)

    assert len(documents) >= 1
    assert "[CSV Table]" in documents[0].page_content
    assert documents[0].metadata["source"] == "chunk.csv"
    assert documents[0].metadata["source_media"] == "text"
    assert documents[0].metadata["source_kind"] == "csv_file"
    assert documents[0].metadata["loader_name"] == "csv.extract"


def test_csv_chunk_metadata_preserves_loader_warnings(tmp_path: Path) -> None:
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()
    csv_path = kb_dir / "warn.csv"
    lines = ["id,name"] + [f"{i},row{i}" for i in range(1, 12)]
    csv_path.write_text("\n".join(lines), encoding="utf-8")
    descriptor = build_file_descriptor(csv_path, kb_dir)

    documents = build_documents_for_source(descriptor, registry=SourceLoaderRegistry(loaders=[CsvSourceLoader(max_rows=5)]))

    assert len(documents) >= 1
    assert "csv_truncated" in documents[0].metadata["loader_warnings"]
