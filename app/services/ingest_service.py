"""Application service for document ingestion into the vector store."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.core.config import get_settings
from app.core.exceptions import IngestError
from app.rag.embeddings import get_embedding_backend
from app.rag.ingest import build_document_payload, iter_docs
from app.rag.vectorstore import get_vectorstore

logger = logging.getLogger(__name__)


class IngestService:
    """Thin service wrapper around the batch ingest pipeline.

    Encapsulates the full flow: scan files → split → embed → upsert,
    returning a structured result instead of printing to stdout.
    """

    def ingest(self, rebuild: bool = False) -> dict[str, int]:
        """Run a full batch ingest of the knowledge base directory.

        Args:
            rebuild: If True, delete existing Chroma data before re-ingesting.

        Returns:
            Dict with ``documents`` (source files processed) and
            ``chunks`` (total chunks written).

        Raises:
            IngestError: If anything goes wrong during ingestion.
        """
        settings = get_settings()
        kb_dir = Path(settings.kb_dir)
        chroma_dir = Path(settings.chroma_dir)

        logger.info(
            "Ingest started: kb_dir=%s chroma_dir=%s rebuild=%s",
            kb_dir, chroma_dir, rebuild,
        )

        try:
            if rebuild and chroma_dir.exists():
                shutil.rmtree(chroma_dir)
                logger.info("Existing Chroma data deleted for rebuild")

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

            logger.info(
                "Ingest completed: documents=%d chunks=%d",
                loaded_documents, total_chunks,
            )
            return {"documents": loaded_documents, "chunks": total_chunks}

        except Exception as exc:
            logger.exception("Ingest failed")
            raise IngestError(detail=f"Ingestion failed: {exc}") from exc
