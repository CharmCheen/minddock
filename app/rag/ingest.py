"""Source-to-document builders and CLI helpers for ingestion."""

from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path
import hashlib

from app.core.config import get_settings
from app.rag.source_loader import (
    SUPPORTED_EXTENSIONS,
    SourceLoaderRegistry,
    build_file_descriptor,
    build_url_descriptor,
    iter_file_descriptors,
)
from app.rag.source_models import Document, DocumentPayload, SourceDescriptor, SourceLoadResult
from app.rag.source_models import utc_now_iso
from app.rag.splitter import _chunk_by_tokens, split_text
from app.rag.vectorstore import clear_vectorstore_cache, get_vectorstore
from app.rag.structured_chunker import structured_pdf_chunks, ChunkMeta

logger = logging.getLogger(__name__)


def build_doc_id(path: Path) -> str:
    """Compatibility helper for callers/tests that expect file doc ids."""

    return SourceDescriptor(source=path.as_posix(), source_type="file").doc_id


def build_url_doc_id(url: str) -> str:
    """Compatibility helper for callers/tests that expect URL doc ids."""

    return build_url_descriptor(url).doc_id


def iter_docs(kb_dir: Path):
    """Compatibility iterator returning local file paths only."""

    for descriptor in iter_file_descriptors(kb_dir):
        if descriptor.local_path is not None:
            yield descriptor.local_path


def _build_page_mode_chunks(
    *, load_result: SourceLoadResult,
) -> list[Document]:
    """Legacy fallback: page-mode token chunking without structured parsing."""
    documents: list[Document] = []
    normalized_text = load_result.text.strip()
    descriptor = load_result.descriptor
    extra = {k: v for k, v in load_result.metadata.items() if k != "_page_blocks"}
    content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    last_ingested_at = utc_now_iso()
    title = load_result.title.strip() or descriptor.display_name

    chunk_index = 0
    for page_block in normalized_text.split("\n\n[page "):
        block = page_block.strip()
        if not block:
            continue
        if block.startswith("[page "):
            header, _, page_text = block.partition("]\n")
        else:
            header, _, page_text = block.partition("]\n")
        if not page_text.strip():
            continue
        page_number = header.replace("[page ", "").strip()
        for chunk_text in _chunk_by_tokens(page_text.strip(), chunk_size=600, overlap=80):
            chunk_text = chunk_text.strip()
            if not chunk_text:
                continue
            chunk_id = f"{descriptor.doc_id}:{chunk_index}"
            location = f"page {page_number}"
            ref = f"{title} > page {page_number}"
            metadata = {
                "doc_id": descriptor.doc_id,
                "source": descriptor.source,
                "source_path": descriptor.source_path,
                "source_type": descriptor.source_type,
                "title": title,
                "chunk_id": chunk_id,
                "section": "",
                "location": location,
                "ref": ref,
                "page": str(page_number),
                "anchor": "",
                "source_version": content_hash,
                "content_hash": content_hash,
                "last_ingested_at": last_ingested_at,
                "ingest_status": "ready",
                **extra,
            }
            documents.append(Document(page_content=chunk_text, metadata=metadata))
            chunk_index += 1
    return documents


def _build_structured_chunks(
    *, load_result: SourceLoadResult, page_blocks: list,
) -> list[Document]:
    """Structured block-level PDF chunking with rich metadata."""
    documents: list[Document] = []
    descriptor = load_result.descriptor
    extra = {k: v for k, v in load_result.metadata.items() if k != "_page_blocks"}
    content_hash = hashlib.sha256(load_result.text.encode("utf-8")).hexdigest()
    last_ingested_at = utc_now_iso()
    title = load_result.title.strip() or descriptor.display_name

    # Convert page_blocks dicts → structured_chunker expected format
    pages_input = [
        {"page": pb["page"], "blocks": pb["blocks"]}
        for pb in page_blocks
    ]

    for chunk_text, meta in structured_pdf_chunks(
        pages_input,
        doc_id=descriptor.doc_id,
        source=descriptor.source,
        source_path=descriptor.source_path,
        source_type=descriptor.source_type,
        title=title,
        source_version=content_hash,
        content_hash=content_hash,
        last_ingested_at=last_ingested_at,
    ):
        # Build Chroma-compatible metadata (flat str dict)
        metadata: dict[str, str] = {
            "doc_id": meta.doc_id,
            "source": meta.source,
            "source_path": meta.source_path,
            "source_type": meta.source_type,
            "title": meta.title,
            "chunk_id": meta.chunk_id,
            "section": meta.section_title,
            "location": meta.location,
            "ref": meta.ref,
            "page": str(meta.page_start) if meta.page_start == meta.page_end
                    else f"{meta.page_start}-{meta.page_end}",
            "anchor": meta.table_id or "",
            # Existing structured fields
            "block_type": meta.block_type,
            "table_id": meta.table_id or "",
            "section_title": meta.section_title,
            "order_in_doc": str(meta.order_in_doc),
            "char_count": str(meta.char_count),
            "token_estimate": str(meta.token_estimate),
            "page_start": str(meta.page_start),
            "page_end": str(meta.page_end),
            "source_version": meta.source_version,
            "content_hash": meta.content_hash,
            "last_ingested_at": meta.last_ingested_at,
            "ingest_status": meta.ingest_status,
            # Fine-grained citation support fields
            # block_ids: comma-separated block IDs composing this chunk
            "block_ids": ",".join(meta.block_ids) if meta.block_ids else "",
            # section_path: hierarchical path like "1.2.3" for section hierarchy
            "section_path": meta.section_path or "",
            # semantic_type: derived semantic type (e.g., "abstract", "introduction")
            "semantic_type": meta.semantic_type or "",
            # parent_block_id: parent block ID for hierarchical relationships
            "parent_block_id": meta.parent_block_id or "",
            # child_block_ids: comma-separated child block IDs
            "child_block_ids": ",".join(meta.child_block_ids) if meta.child_block_ids else "",
            **extra,
        }
        documents.append(Document(page_content=chunk_text, metadata=metadata))

    return documents


def _build_chunk_documents(
    *,
    load_result: SourceLoadResult,
    page_mode: bool = False,
) -> list[Document]:
    documents: list[Document] = []
    normalized_text = load_result.text.strip()
    if not normalized_text:
        return documents

    descriptor = load_result.descriptor
    extra = dict(load_result.metadata)
    content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    last_ingested_at = utc_now_iso()
    title = load_result.title.strip() or descriptor.display_name

    if page_mode:
        # Try structured PDF chunking when block data is available
        page_blocks = load_result.metadata.get("_page_blocks")
        if page_blocks:
            return _build_structured_chunks(
                load_result=load_result,
                page_blocks=page_blocks,
            )
        # Fallback to legacy page-mode token chunking
        return _build_page_mode_chunks(load_result=load_result)

    for index, chunk in enumerate(split_text(normalized_text)):
        chunk_text = (chunk.get("text") or "").strip()
        if not chunk_text:
            continue

        section = str(chunk.get("section") or "").strip()
        location = section or descriptor.source
        ref = title if not section else f"{title} > {section}"
        chunk_id = f"{descriptor.doc_id}:{index}"
        metadata = {
            "doc_id": descriptor.doc_id,
            "source": descriptor.source,
            "source_path": descriptor.source_path,
            "source_type": descriptor.source_type,
            "title": title,
            "chunk_id": chunk_id,
            "section": section,
            "location": location,
            "ref": ref,
            "page": "",
            "anchor": "",
            "source_version": content_hash,
            "content_hash": content_hash,
            "last_ingested_at": last_ingested_at,
            "ingest_status": "ready",
            # Fine-grained citation support fields (text files use simple splitting, so these are mostly empty)
            "block_ids": "",
            "section_path": section or "",
            "semantic_type": "",
            "parent_block_id": "",
            "child_block_ids": "",
            **extra,
        }
        documents.append(Document(page_content=chunk_text, metadata=metadata))

    return documents


def build_documents_for_source(
    descriptor: SourceDescriptor,
    registry: SourceLoaderRegistry | None = None,
) -> list[Document]:
    """Build LangChain documents for one source descriptor."""

    source_registry = registry or SourceLoaderRegistry()
    load_result = source_registry.load(descriptor)
    is_pdf = descriptor.source_type == "file" and descriptor.local_path is not None and descriptor.local_path.suffix.lower() == ".pdf"
    return _build_chunk_documents(load_result=load_result, page_mode=is_pdf)


def build_payload_for_source(
    descriptor: SourceDescriptor,
    registry: SourceLoaderRegistry | None = None,
) -> DocumentPayload:
    """Build a normalized payload for one source descriptor."""

    documents = build_documents_for_source(descriptor=descriptor, registry=registry)
    if not documents:
        return DocumentPayload.empty(descriptor)
    actual_descriptor = SourceDescriptor(
        source=str(documents[0].metadata.get("source", descriptor.source)),
        source_type=str(documents[0].metadata.get("source_type", descriptor.source_type)),
        local_path=descriptor.local_path,
        requested_source=descriptor.requested_source,
    )
    return DocumentPayload.from_documents(actual_descriptor, documents)


def build_langchain_documents(path: Path, kb_dir: Path) -> list[Document]:
    """Compatibility helper for file-based callers/tests."""

    descriptor = build_file_descriptor(path, kb_dir)
    return build_documents_for_source(descriptor)


def build_document_payload(path: Path, kb_dir: Path) -> dict[str, object]:
    """Compatibility helper returning the legacy dict shape for file sources."""

    descriptor = build_file_descriptor(path, kb_dir)
    return build_payload_for_source(descriptor).to_legacy_dict()


def build_url_documents(url: str) -> list[Document]:
    """Compatibility helper for URL-based callers/tests."""

    return build_documents_for_source(build_url_descriptor(url))


def build_url_document_payload(url: str) -> dict[str, object]:
    """Compatibility helper returning the legacy dict shape for URL sources."""

    return build_payload_for_source(build_url_descriptor(url)).to_legacy_dict()


def ingest(rebuild: bool = False) -> None:
    settings = get_settings()
    kb_dir = Path(settings.kb_dir)
    chroma_dir = Path(settings.chroma_dir)

    if rebuild and chroma_dir.exists():
        shutil.rmtree(chroma_dir)
        clear_vectorstore_cache()

    collection = get_vectorstore()
    descriptors = iter_file_descriptors(kb_dir) if kb_dir.exists() else []

    langchain_documents: list[Document] = []
    for descriptor in descriptors:
        langchain_documents.extend(build_documents_for_source(descriptor))

    total_chunks = len(langchain_documents)
    if total_chunks:
        collection.upsert_documents(langchain_documents)

    print(f"Loaded {len(descriptors)} documents")
    print(f"Created {total_chunks} chunks")
    print("Stored to Chroma")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest local markdown/text/PDF files into Chroma")
    parser.add_argument("--rebuild", action="store_true", help="Delete existing Chroma data before ingest")
    args = parser.parse_args()
    ingest(rebuild=args.rebuild)


if __name__ == "__main__":
    main()
