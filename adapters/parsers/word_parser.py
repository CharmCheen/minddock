"""Word (.docx) document parser using zipfile + XML (no python-docx dependency)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _extract_docx_blocks(zf) -> list[dict[str, Any]]:
    """Extract paragraph blocks from a docx zip file."""
    import zipfile
    from xml.etree import ElementTree as ET

    blocks = []
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

    try:
        with zf.open("word/document.xml") as f:
            tree = ET.parse(f)
    except Exception:
        return blocks

    root = tree.getroot()
    body = root.find(f".//{ns}body")
    if body is None:
        return blocks

    for para in body.findall(f".//{ns}p"):
        texts = []
        is_heading = False

        pPr = para.find(f"{ns}pPr")
        if pPr is not None:
            pStyle = pPr.find(f"{ns}pStyle")
            if pStyle is not None:
                style_val = pStyle.get(f"{ns}val", "").lower()
                if style_val in ("heading1", "heading2", "heading3", "heading4", "title", "subtitle"):
                    is_heading = True

        for run in para.findall(f".//{ns}t"):
            if run.text:
                texts.append(run.text)

        text = "".join(texts).strip()
        if text:
            blocks.append({
                "text": text,
                "source": "word",
                "page_num": 0,
                "block_type": "heading" if is_heading else "paragraph",
            })

    return blocks


class WordParser:
    """Parse .docx files into document blocks without external dependencies."""

    def parse(self, file_path: Path) -> list[dict[str, Any]]:
        import zipfile
        blocks = []
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                blocks = _extract_docx_blocks(zf)
        except Exception:
            pass
        return blocks
