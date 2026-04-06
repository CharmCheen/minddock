"""Application service for grounded summaries."""

from __future__ import annotations

from collections import defaultdict
import logging
import time
from dataclasses import dataclass, field

from app.core.exceptions import SummarizeError
from app.llm.factory import get_generation_runtime
from app.llm.mock import INSUFFICIENT_EVIDENCE
from app.rag.retrieval_models import ContextBlock, GroundedAnswer, RetrievalFilters, RetrievedChunk
from app.rag.postprocess import Compressor, Reranker, get_compressor, get_reranker
from app.runtime import GenerationRuntime, RuntimeRequest
from app.services.grounded_generation import assess_grounding, build_citation, build_context, build_evidence, format_evidence_block
from app.services.search_service import SearchService
from app.services.service_models import (
    DocumentEvidenceGroup,
    RetrievalStats,
    ServiceIssue,
    SummarizeServiceResult,
    UseCaseMetadata,
    UseCaseTiming,
)
from app.services.structured_output_service import StructuredOutputService
from app.workflows.langgraph_pipeline import run_retrieval_workflow
from ports.llm import LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class SummarizeService:
    """Build grounded summarize pipelines including map-reduce and structured output."""

    search_service: SearchService = field(default_factory=SearchService)
    reranker: Reranker = field(default_factory=get_reranker)
    compressor: Compressor = field(default_factory=get_compressor)
    runtime: GenerationRuntime = field(default_factory=get_generation_runtime)
    structured_output_service: StructuredOutputService = field(default_factory=StructuredOutputService)
    llm: LLMProvider | None = None

    def summarize(
        self,
        topic: str,
        top_k: int,
        filters: RetrievalFilters | None = None,
        mode: str = "basic",
        output_format: str = "text",
    ) -> SummarizeServiceResult:
        try:
            started = time.perf_counter()
            logger.info(
                "Summarize started: topic_preview=%s top_k=%d mode=%s output_format=%s",
                topic[:60],
                top_k,
                mode,
                output_format,
            )

            retrieval_started = time.perf_counter()
            workflow_state = run_retrieval_workflow(
                query=topic,
                top_k=top_k,
                filters=filters,
                search_service=self.search_service,
            )
            retrieval_ms = round((time.perf_counter() - retrieval_started) * 1000, 2)
            grounded_hits = workflow_state.grounded_hits
            if not grounded_hits:
                grounding = assess_grounding(retrieved_hits=workflow_state.hits, evidence=[])
                logger.info("Summarize returning insufficient evidence: topic_preview=%s", topic[:60])
                return SummarizeServiceResult(
                    summary=INSUFFICIENT_EVIDENCE,
                    citations=[],
                    grounded_answer=GroundedAnswer(
                        answer=INSUFFICIENT_EVIDENCE,
                        evidence=(),
                        support_status=grounding.support_status,
                        refusal_reason=grounding.refusal_reason,
                    ),
                    metadata=UseCaseMetadata(
                        retrieved_count=0,
                        mode=mode,
                        output_format=output_format,
                        insufficient_evidence=True,
                        support_status=grounding.support_status.value,
                        refusal_reason=None if grounding.refusal_reason is None else grounding.refusal_reason.value,
                        empty_result=not workflow_state.hits,
                        warnings=("Insufficient grounded evidence for summarize response.",),
                        issues=(
                            ServiceIssue(
                                code="insufficient_evidence",
                                message="Insufficient grounded evidence for summarize response.",
                                severity="info",
                            ),
                        ),
                        timing=UseCaseTiming(
                            total_ms=round((time.perf_counter() - started) * 1000, 2),
                            retrieval_ms=retrieval_ms,
                        ),
                        runtime_mode=getattr(self.runtime, "runtime_name", type(self.runtime).__name__),
                        provider_mode=type(self.llm).__name__ if self.llm is not None else getattr(self.runtime, "provider_name", None),
                        filter_applied=filters is not None,
                        retrieval_stats=RetrievalStats(
                            retrieved_hits=len(workflow_state.hits),
                            grounded_hits=0,
                            returned_hits=0,
                        ),
                    ),
                    structured_output=None,
                    context=workflow_state.context,
                )

            rerank_started = time.perf_counter()
            reranked_hits = self.reranker.rerank(query=topic, hits=grounded_hits)
            rerank_ms = round((time.perf_counter() - rerank_started) * 1000, 2)
            compress_started = time.perf_counter()
            compressed_hits = self.compressor.compress(query=topic, hits=reranked_hits)
            compress_ms = round((time.perf_counter() - compress_started) * 1000, 2)
            context = build_context(compressed_hits)
            citations = [build_citation(hit) for hit in compressed_hits]
            evidence = [build_evidence(hit) for hit in compressed_hits]
            grounding = assess_grounding(retrieved_hits=workflow_state.hits, evidence=evidence)
            grouped_hits = self._group_hits_by_doc(compressed_hits)

            generation_started = time.perf_counter()
            if mode == "map_reduce":
                summary = self._summarize_map_reduce(
                    topic=topic,
                    grouped_hits=grouped_hits,
                    fallback_hits=compressed_hits,
                )
            else:
                summary = self._summarize_basic(topic=topic, context=context)
            generation_ms = round((time.perf_counter() - generation_started) * 1000, 2)

            structured_output = None
            if output_format == "mermaid":
                structured_output = self.structured_output_service.render_mermaid(
                    topic=topic,
                    evidence=context.to_evidence_items(),
                )

            logger.info(
                "Summarize completed: topic_preview=%s grounded=%d reranked=%d compressed=%d mode=%s output_format=%s",
                topic[:60], len(grounded_hits), len(reranked_hits), len(compressed_hits), mode, output_format,
            )
            return SummarizeServiceResult(
                summary=summary,
                citations=citations,
                grounded_answer=GroundedAnswer(
                    answer=summary,
                    evidence=tuple(evidence),
                    support_status=grounding.support_status,
                    refusal_reason=grounding.refusal_reason,
                ),
                metadata=UseCaseMetadata(
                    retrieved_count=len(compressed_hits),
                    mode=mode,
                    output_format=output_format,
                    support_status=grounding.support_status.value,
                    refusal_reason=None if grounding.refusal_reason is None else grounding.refusal_reason.value,
                    timing=UseCaseTiming(
                        total_ms=round((time.perf_counter() - started) * 1000, 2),
                        retrieval_ms=retrieval_ms,
                        rerank_ms=rerank_ms,
                        compress_ms=compress_ms,
                        generation_ms=generation_ms,
                    ),
                    runtime_mode=getattr(self.runtime, "runtime_name", type(self.runtime).__name__),
                    provider_mode=type(self.llm).__name__ if self.llm is not None else getattr(self.runtime, "provider_name", None),
                    filter_applied=filters is not None,
                    retrieval_stats=RetrievalStats(
                        retrieved_hits=len(workflow_state.hits),
                        grounded_hits=len(grounded_hits),
                        reranked_hits=len(reranked_hits),
                        returned_hits=len(compressed_hits),
                    ),
                ),
                structured_output=structured_output,
                context=context,
            )
        except Exception as exc:
            logger.exception("Summarize failed: topic_preview=%s", topic[:60])
            raise SummarizeError(detail=f"Summarization failed: {exc}") from exc

    def _group_hits_by_doc(self, hits: list[RetrievedChunk]) -> list[DocumentEvidenceGroup]:
        grouped: dict[str, list[RetrievedChunk]] = defaultdict(list)
        for hit in hits:
            grouped[hit.doc_id].append(hit)

        return [
            DocumentEvidenceGroup(
                doc_id=doc_id,
                hits=doc_hits,
                citation=build_citation(doc_hits[0]),
                context=build_context(doc_hits),
            )
            for doc_id, doc_hits in grouped.items()
            if doc_hits
        ]

    def _summarize_basic(self, topic: str, context: ContextBlock) -> str:
        summary_query = (
            "Summarize the topic using only the provided evidence. "
            "Keep it concise, grounded, and synthesis-oriented.\n"
            f"Topic: {topic}"
        )
        return self.runtime.generate(
            RuntimeRequest(
                prompt=self._build_basic_prompt(),
                inputs={"topic": topic, "evidence_block": format_evidence_block(context)},
                fallback_query=summary_query,
                fallback_evidence=context.to_evidence_items(),
                llm_override=self.llm,
            )
        ).text

    def _summarize_map_reduce(
        self,
        *,
        topic: str,
        grouped_hits: list[DocumentEvidenceGroup],
        fallback_hits: list[RetrievedChunk],
    ) -> str:
        partial_summaries: list[str] = []
        for group in grouped_hits:
            group_context: ContextBlock = group.context
            if not group_context.chunks:
                continue
            partial = self.runtime.generate(
                RuntimeRequest(
                    prompt=self._build_map_prompt(),
                    inputs={
                        "topic": topic,
                        "document_ref": str(group.citation.ref or group.doc_id or "document"),
                        "evidence_block": format_evidence_block(group_context),
                    },
                    fallback_query=f"Summarize document evidence for topic: {topic}",
                    fallback_evidence=group_context.to_evidence_items(),
                    llm_override=self.llm,
                )
            ).text
            partial_summaries.append(partial)

        if not partial_summaries:
            partial_summaries = [self._summarize_basic(topic=topic, context=build_context(fallback_hits))]

        reduce_evidence = [
            {
                "chunk_id": f"map:{index}",
                "source": "map_reduce",
                "title": f"Partial summary {index}",
                "section": "",
                "location": "",
                "ref": f"Partial summary {index}",
                "text": summary,
            }
            for index, summary in enumerate(partial_summaries, start=1)
        ]
        return self.runtime.generate(
            RuntimeRequest(
                prompt=self._build_reduce_prompt(),
                inputs={
                    "topic": topic,
                    "partial_summaries": "\n".join(f"- {summary}" for summary in partial_summaries),
                },
                fallback_query=f"Summarize the topic using map-reduce.\nTopic: {topic}",
                fallback_evidence=reduce_evidence,
                llm_override=self.llm,
            )
        ).text

    def _build_basic_prompt(self):
        try:
            from langchain_core.prompts import ChatPromptTemplate
        except ModuleNotFoundError:
            return "minddock-grounded-summary-prompt"

        return ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "You are MindDock's grounded summarization assistant. "
                        "Summarize only from the provided evidence. "
                        "If the evidence is insufficient, say so explicitly. "
                        "Produce a short synthesis rather than a verbatim extract."
                    ),
                ),
                ("human", "Topic:\n{topic}\n\nEvidence:\n{evidence_block}"),
            ]
        )

    def _build_map_prompt(self):
        try:
            from langchain_core.prompts import ChatPromptTemplate
        except ModuleNotFoundError:
            return "minddock-grounded-summary-map-prompt"

        return ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Summarize the provided document evidence only. Keep the summary local to that document.",
                ),
                (
                    "human",
                    "Topic:\n{topic}\n\nDocument:\n{document_ref}\n\nEvidence:\n{evidence_block}",
                ),
            ]
        )

    def _build_reduce_prompt(self):
        try:
            from langchain_core.prompts import ChatPromptTemplate
        except ModuleNotFoundError:
            return "minddock-grounded-summary-reduce-prompt"

        return ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "Combine the partial summaries into one grounded synthesis. "
                        "Highlight agreements, distinctions, and the overall takeaway."
                    ),
                ),
                ("human", "Topic:\n{topic}\n\nPartial summaries:\n{partial_summaries}"),
            ]
        )
