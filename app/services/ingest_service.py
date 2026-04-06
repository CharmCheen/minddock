"""Application service for robust source ingestion into the vector store."""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from app.core.config import get_settings
from app.core.exceptions import IngestError
from app.core.logging import TRACE_LEVEL_NUM
from app.rag.embeddings import EmbeddingBackend, get_embedding_backend
from app.rag.ingest import build_payload_for_source
from app.rag.source_loader import SourceLoaderRegistry, build_url_descriptor, iter_file_descriptors
from app.rag.source_models import (
    FailedSourceInfo,
    IngestBatchResult,
    IngestSourceResult,
    SourceDescriptor,
)
from app.services.service_models import IngestServiceResult, UseCaseMetadata
from app.services.service_models import ServiceIssue, SourceStats, UseCaseTiming
from app.rag.vectorstore import clear_vectorstore_cache, get_vectorstore

logger = logging.getLogger(__name__)


class IngestService:
    """Batch ingest local files and optional URLs with partial-failure handling."""

    def __init__(
        self,
        *,
        settings=None,
        loader_registry: SourceLoaderRegistry | None = None,
        embedder: EmbeddingBackend | None = None,
        collection=None,
    ) -> None:
        runtime_settings = settings or get_settings()
        self._settings = runtime_settings
        self._loader_registry = loader_registry or SourceLoaderRegistry()
        self._embedder = embedder or get_embedding_backend(runtime_settings.embedding_model)
        self._collection = collection

    def ingest(self, rebuild: bool = False, urls: list[str] | None = None) -> IngestServiceResult:
        """Run a full batch ingest of the knowledge base plus optional URLs."""

        started = time.perf_counter()
        kb_dir = Path(self._settings.kb_dir)
        chroma_dir = Path(self._settings.chroma_dir)
        source_descriptors = self._build_source_descriptors(kb_dir=kb_dir, urls=urls)

        logger.info(
            "Ingest started: kb_dir=%s chroma_dir=%s rebuild=%s source_count=%d",
            kb_dir,
            chroma_dir,
            rebuild,
            len(source_descriptors),
        )

        try:
            if rebuild:
                self._rebuild_vectorstore(chroma_dir)

            collection = self._collection or get_vectorstore()
        except Exception as exc:
            logger.exception("Ingest setup failed")
            raise IngestError(detail=f"Ingestion setup failed: {exc}") from exc

        source_results = [
            self._ingest_source(collection=collection, descriptor=descriptor)
            for descriptor in source_descriptors
        ]
        batch_result = IngestBatchResult(source_results=source_results)

        if batch_result.all_failed():
            detail = "; ".join(f"{item.source}: {item.reason}" for item in batch_result.failed_sources[:3])
            raise IngestError(detail=f"Ingestion failed for all requested sources. {detail}")

        logger.info(
            "Ingest completed: completed_sources=%d failed_sources=%d chunks=%d",
            batch_result.documents,
            len(batch_result.failed_sources),
            batch_result.chunks,
        )
        warnings = ()
        issues: tuple[ServiceIssue, ...] = ()
        if batch_result.failed_sources:
            warnings = (f"{len(batch_result.failed_sources)} sources failed during ingest.",)
            issues = tuple(
                ServiceIssue(
                    code="source_ingest_failed",
                    message=item.reason,
                    severity="warning",
                    source=item.source,
                )
                for item in batch_result.failed_sources
            )
        return IngestServiceResult(
            batch=batch_result,
            metadata=UseCaseMetadata(
                partial_failure=bool(batch_result.failed_sources),
                warnings=warnings,
                issues=issues,
                timing=UseCaseTiming(total_ms=round((time.perf_counter() - started) * 1000, 2)),
                source_stats=SourceStats(
                    requested_sources=len(source_descriptors),
                    succeeded_sources=batch_result.documents,
                    failed_sources=len(batch_result.failed_sources),
                ),
            ),
        )

    def ingest_descriptor(self, descriptor: SourceDescriptor) -> IngestSourceResult:
        """Public single-source ingest entrypoint reused by lifecycle management."""

        collection = self._collection or get_vectorstore()
        return self._ingest_source(collection=collection, descriptor=descriptor)

    def _ingest_source(self, *, collection, descriptor: SourceDescriptor) -> IngestSourceResult:
        try:
            payload = build_payload_for_source(descriptor=descriptor, registry=self._loader_registry)
            embeddings = self._embedder.embed_texts(payload.documents) if payload.documents else []
            replaced = collection.replace_document(
                doc_id=payload.doc_id,
                ids=payload.ids,
                documents=payload.documents,
                metadatas=payload.metadatas,
                embeddings=embeddings,
            )
            logger.log(
                TRACE_LEVEL_NUM,
                "Source ingested: source=%s source_type=%s doc_id=%s upserted=%d deleted=%d",
                payload.descriptor.source,
                payload.descriptor.source_type,
                payload.doc_id,
                replaced.upserted,
                replaced.deleted,
            )
            return IngestSourceResult(
                descriptor=payload.descriptor,
                ok=True,
                chunks_upserted=replaced.upserted,
                chunks_deleted=replaced.deleted,
            )
        except Exception as exc:
            logger.exception("Source ingest failed: source=%s source_type=%s", descriptor.source, descriptor.source_type)
            return IngestSourceResult(
                descriptor=descriptor,
                ok=False,
                failure=FailedSourceInfo(
                    source=descriptor.source,
                    source_type=descriptor.source_type,
                    reason=str(exc),
                ),
            )

    def _build_source_descriptors(self, *, kb_dir: Path, urls: list[str] | None) -> list[SourceDescriptor]:
        file_sources = iter_file_descriptors(kb_dir) if kb_dir.exists() else []
        url_sources = [build_url_descriptor(url) for url in self._normalize_urls(urls)]
        return [*sorted(file_sources, key=lambda item: item.source), *url_sources]

    def _rebuild_vectorstore(self, chroma_dir: Path) -> None:
        clear_vectorstore_cache()
        if not chroma_dir.exists():
            return

        last_error: Exception | None = None
        for attempt in range(1, self._settings.rebuild_max_retries + 1):
            try:
                shutil.rmtree(chroma_dir)
                logger.info("Existing Chroma data deleted for rebuild on attempt %d", attempt)
                return
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Failed to delete Chroma directory during rebuild: attempt=%d path=%s error=%s",
                    attempt,
                    chroma_dir,
                    exc,
                )
                time.sleep(self._settings.rebuild_retry_seconds)
                clear_vectorstore_cache()

        raise RuntimeError(f"Unable to rebuild vector store at `{chroma_dir}`: {last_error}")

    def _normalize_urls(self, urls: list[str] | None) -> list[str]:
        normalized: list[str] = []
        for url in urls or []:
            candidate = str(url).strip()
            if not candidate:
                continue
            normalized.append(candidate)
        return normalized
