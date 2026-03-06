"""CLI for ingesting local documents into Chroma."""

from __future__ import annotations

import argparse
import hashlib
import shutil
from collections.abc import Iterator
from pathlib import Path

from app.core.config import get_settings
from app.rag.embeddings import get_embedding_backend
from app.rag.splitter import split_text
from app.rag.vectorstore import get_vectorstore

SUPPORTED_EXTENSIONS = {".md", ".txt"}


def _build_doc_id(path: Path) -> str:
    return hashlib.sha1(path.as_posix().encode("utf-8")).hexdigest()


def _iter_docs(kb_dir: Path) -> Iterator[Path]:
    for path in kb_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def ingest(rebuild: bool = False) -> None:
    settings = get_settings()
    kb_dir = Path(settings.kb_dir)
    chroma_dir = Path(settings.chroma_dir)

    if rebuild and chroma_dir.exists():
        shutil.rmtree(chroma_dir)

    collection = get_vectorstore()
    embedder = get_embedding_backend(settings.embedding_model)

    doc_paths = sorted(_iter_docs(kb_dir)) if kb_dir.exists() else []
    loaded_documents = len(doc_paths)

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, str]] = []

    for path in doc_paths:
        relative = path.relative_to(kb_dir)
        source_path = relative.as_posix()
        doc_id = _build_doc_id(relative)

        text = path.read_text(encoding="utf-8", errors="ignore")
        for index, chunk in enumerate(split_text(text)):
            chunk_text = (chunk.get("text") or "").strip()
            if not chunk_text:
                continue

            chunk_id = f"{doc_id}:{index}"
            metadata = {
                "doc_id": doc_id,
                "source_path": source_path,
                "chunk_id": chunk_id,
                "section": str(chunk.get("section") or ""),
            }

            ids.append(chunk_id)
            documents.append(chunk_text)
            metadatas.append(metadata)

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
    parser = argparse.ArgumentParser(description="Ingest local markdown/text files into Chroma")
    parser.add_argument("--rebuild", action="store_true", help="Delete existing Chroma data before ingest")
    args = parser.parse_args()
    ingest(rebuild=args.rebuild)


if __name__ == "__main__":
    main()
