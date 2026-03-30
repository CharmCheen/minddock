"""CLI for ingesting local documents into Chroma."""

from __future__ import annotations

import argparse
import hashlib
import logging
import shutil
from collections.abc import Iterator
from pathlib import Path

from app.core.config import get_settings
from app.rag.embeddings import get_embedding_backend
from app.rag.splitter import split_text, _chunk_by_tokens
from app.rag.vectorstore import get_vectorstore

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf"}
_TEXT_EXTENSIONS = {".md", ".txt"}
_PDF_EXTENSIONS = {".pdf"}


def build_doc_id(path: Path) -> str:
    return hashlib.sha1(path.as_posix().encode("utf-8")).hexdigest()


def iter_docs(kb_dir: Path) -> Iterator[Path]:
    for path in kb_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


# ---------------------------------------------------------------------------
# Text document (md / txt) payload builder
# ---------------------------------------------------------------------------

def _build_text_document_payload(path: Path, kb_dir: Path) -> dict[str, object]:
    """Build Chroma payload for a plain-text document (md/txt)."""

    relative = path.relative_to(kb_dir)
    source_path = relative.as_posix()
    doc_id = build_doc_id(relative)
    title = path.stem

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, str]] = []

    text = path.read_text(encoding="utf-8", errors="ignore")
    for index, chunk in enumerate(split_text(text)):
        chunk_text = (chunk.get("text") or "").strip()
        if not chunk_text:
            continue

        chunk_id = f"{doc_id}:{index}"
        section = str(chunk.get("section") or "").strip()
        location = section or source_path
        ref = title if not section else f"{title} > {section}"
        metadata = {
            "doc_id": doc_id,
            "source": source_path,
            "source_path": source_path,
            "title": title,
            "chunk_id": chunk_id,
            "section": section,
            "location": location,
            "ref": ref,
            "page": "",
            "anchor": "",
        }

        ids.append(chunk_id)
        documents.append(chunk_text)
        metadatas.append(metadata)

    return {
        "doc_id": doc_id,
        "source_path": source_path,
        "ids": ids,
        "documents": documents,
        "metadatas": metadatas,
    }


# ---------------------------------------------------------------------------
# PDF document payload builder
# ---------------------------------------------------------------------------

def _build_pdf_document_payload(path: Path, kb_dir: Path) -> dict[str, object]:
    """Build Chroma payload for a PDF document with real page numbers.

    Flow:
        1. Extract text per page via pdf_parser.extract_pages()
        2. For each page, chunk the text using _chunk_by_tokens
        3. Each chunk carries ``page`` = real 1-based page number (as str
           for Chroma metadata compatibility)
    """
    from app.rag.pdf_parser import extract_pages

    relative = path.relative_to(kb_dir)
    source_path = relative.as_posix()
    doc_id = build_doc_id(relative)
    title = path.stem

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, str]] = []

    pages = extract_pages(path)

    if not pages:
        logger.warning("PDF yielded no extractable text: path=%s", path)
        return {
            "doc_id": doc_id,
            "source_path": source_path,
            "ids": [],
            "documents": [],
            "metadatas": [],
        }

    chunk_index = 0
    for page_data in pages:
        page_text = page_data.text.strip()
        if not page_text:
            continue

        # Chunk the page text using the existing token-based chunker
        for chunk_text in _chunk_by_tokens(page_text, chunk_size=600, overlap=80):
            chunk_text = chunk_text.strip()
            if not chunk_text:
                continue

            chunk_id = f"{doc_id}:{chunk_index}"
            location = f"page {page_data.page}"
            ref = f"{title} > page {page_data.page}"
            metadata = {
                "doc_id": doc_id,
                "source": source_path,
                "source_path": source_path,
                "title": title,
                "chunk_id": chunk_id,
                "section": "",
                "location": location,
                "ref": ref,
                "page": str(page_data.page),   # real page number as string
                "anchor": "",
            }

            ids.append(chunk_id)
            documents.append(chunk_text)
            metadatas.append(metadata)
            chunk_index += 1

    logger.info(
        "PDF payload built: path=%s pages=%d chunks=%d",
        path, len(pages), len(documents),
    )

    return {
        "doc_id": doc_id,
        "source_path": source_path,
        "ids": ids,
        "documents": documents,
        "metadatas": metadatas,
    }


# ---------------------------------------------------------------------------
# Unified dispatcher
# ---------------------------------------------------------------------------

def build_document_payload(path: Path, kb_dir: Path) -> dict[str, object]:
    """Build Chroma payload for any supported document type.

    Dispatches to the appropriate builder based on file extension.
    """
    suffix = path.suffix.lower()

    if suffix in _PDF_EXTENSIONS:
        return _build_pdf_document_payload(path, kb_dir)
    elif suffix in _TEXT_EXTENSIONS:
        return _build_text_document_payload(path, kb_dir)
    else:
        raise ValueError(f"Unsupported file extension: {suffix}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def ingest(rebuild: bool = False) -> None:
    settings = get_settings()
    kb_dir = Path(settings.kb_dir)
    chroma_dir = Path(settings.chroma_dir)

    if rebuild and chroma_dir.exists():
        shutil.rmtree(chroma_dir)

    collection = get_vectorstore()
    embedder = get_embedding_backend(settings.embedding_model)

    doc_paths = sorted(iter_docs(kb_dir)) if kb_dir.exists() else []
    loaded_documents = len(doc_paths)

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, str]] = []

    for path in doc_paths:
        payload = build_document_payload(path=path, kb_dir=kb_dir)
        ids.extend(payload["ids"])
        documents.extend(payload["documents"])
        metadatas.extend(payload["metadatas"])

    total_chunks = len(documents)
    if total_chunks:
        embeddings = embedder.embed_texts(documents)
        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    print(f"Loaded {loaded_documents} documents")
    print(f"Created {total_chunks} chunks")
    print("Stored to Chroma")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest local markdown/text/PDF files into Chroma")
    parser.add_argument("--rebuild", action="store_true", help="Delete existing Chroma data before ingest")
    args = parser.parse_args()
    ingest(rebuild=args.rebuild)


if __name__ == "__main__":
    main()
