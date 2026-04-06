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
