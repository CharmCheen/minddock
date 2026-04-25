"""CSV source skill — converts CSV rows into normalized text for RAG ingestion.

Uses only the Python standard library ``csv`` module. No pandas.
Design constraints:
- UTF-8 default, handles UTF-8 BOM
- Header-aware; falls back to Column 1, Column 2, ...
- Row limit to avoid oversized prompts
- Friendly warnings for empty / truncated CSV
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from app.rag.source_models import SourceDescriptor, SourceLoadResult

logger = logging.getLogger(__name__)

CSV_EXTENSIONS = {".csv"}
_DEFAULT_MAX_ROWS = 500


class CsvSourceLoader:
    """Load CSV files by converting rows into readable text."""

    source_type: str = "file"

    def __init__(self, max_rows: int | None = None) -> None:
        self.max_rows = max_rows if max_rows is not None else _DEFAULT_MAX_ROWS

    def supports(self, descriptor: SourceDescriptor) -> bool:
        return (
            descriptor.source_type == "file"
            and descriptor.local_path is not None
            and descriptor.local_path.suffix.lower() in CSV_EXTENSIONS
        )

    def load(self, descriptor: SourceDescriptor) -> SourceLoadResult:
        path = descriptor.local_path
        if path is None:
            raise ValueError("csv source requires local_path")

        try:
            text, metadata, warnings = self._load_csv(path)
        except Exception as exc:
            logger.warning("CSV load failed: path=%s error=%s", path, exc)
            raise RuntimeError(f"Failed to parse CSV `{path.name}`: {exc}") from exc

        return SourceLoadResult(
            descriptor=descriptor,
            title=path.stem,
            text=text,
            metadata=metadata,
            warnings=_dedupe(tuple(warnings)),
        )

    def _load_csv(self, path: Path) -> tuple[str, dict[str, str], list[str]]:
        raw_bytes = path.read_bytes()
        if not raw_bytes:
            return "", self._build_metadata(path, []), ["csv_empty"]

        # Handle UTF-8 BOM
        encoding = "utf-8-sig" if raw_bytes.startswith(b"\xef\xbb\xbf") else "utf-8"
        text_content = raw_bytes.decode(encoding, errors="ignore")

        reader = csv.reader(text_content.splitlines())
        rows = list(reader)

        if not rows:
            return "", self._build_metadata(path, []), ["csv_empty"]

        # Detect header: first row looks like header (all strings, no pure numbers)
        header = rows[0]
        data_rows = rows[1:]

        if not data_rows:
            return "", self._build_metadata(path, header), ["csv_empty"]

        # If header looks like data (all values are numeric), treat it as data too
        if _looks_like_data_row(header):
            data_rows = rows
            header = [f"Column {i + 1}" for i in range(len(data_rows[0]))]

        warnings: list[str] = []
        total_rows = len(data_rows)
        truncated = False
        if self.max_rows > 0 and total_rows > self.max_rows:
            data_rows = data_rows[: self.max_rows]
            truncated = True
            warnings.append("csv_truncated")

        if not data_rows:
            return "", self._build_metadata(path, header), ["csv_empty"]

        output_lines: list[str] = ["[CSV Table]", f"Columns: {', '.join(header)}", ""]
        for idx, row in enumerate(data_rows, start=1):
            output_lines.append(f"Row {idx}:")
            for col_name, value in zip(header, row, strict=False):
                output_lines.append(f"{col_name}: {value}")
            output_lines.append("")

        metadata = self._build_metadata(
            path,
            header,
            row_count=total_rows,
            rows_indexed=len(data_rows),
            truncated=truncated,
        )
        return "\n".join(output_lines).strip(), metadata, warnings

    def _build_metadata(
        self,
        path: Path,
        header: list[str],
        *,
        row_count: int = 0,
        rows_indexed: int = 0,
        truncated: bool = False,
    ) -> dict[str, str]:
        metadata: dict[str, str] = {
            "source_media": "text",
            "source_kind": "csv_file",
            "loader_name": "csv.extract",
            "retrieval_basis": "csv_rows_as_text",
            "csv_filename": path.name,
            "csv_columns": ",".join(header) if header else "",
            "csv_row_count": str(row_count),
            "csv_rows_indexed": str(rows_indexed),
        }
        if truncated:
            metadata["csv_truncated"] = "true"
        return metadata


def _looks_like_data_row(row: list[str]) -> bool:
    """Heuristic: if every cell looks numeric, treat the row as data, not header."""

    if not row:
        return False
    numeric_count = 0
    for cell in row:
        stripped = cell.strip()
        if not stripped:
            continue
        try:
            float(stripped.replace(",", "").replace("%", ""))
            numeric_count += 1
        except ValueError:
            pass
    return numeric_count == len([c for c in row if c.strip()])


def _dedupe(warnings: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(w for w in warnings if w))
