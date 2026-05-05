"""Prompt registry and service integration tests."""

from app.prompts import (
    EVIDENCE_FIRST_CHAT_PROFILE_ID,
    GROUNDED_COMPARE_JSON_PROFILE_ID,
    GROUNDED_SUMMARY_PROFILE_ID,
    get_prompt_profile,
)
from app.rag.retrieval_models import RetrievedChunk
from app.services.chat_service import ChatService
from app.services.grounded_generation import build_context
from app.services.service_models import RetrievalPreparationResult
from app.services.summarize_service import SummarizeService
from app.services.compare_service import CompareService
from app.runtime import RuntimeRequest, RuntimeResponse


class FakeSearchService:
    def __init__(self, hits: list[RetrievedChunk]) -> None:
        self._hits = hits

    def retrieve(self, query: str, top_k: int, filters=None) -> list[RetrievedChunk]:
        return self._hits[:top_k]

    def retrieve_structured_reference_candidates(self, query: str, top_k: int, filters=None) -> list[RetrievedChunk]:
        return []


class PassthroughReranker:
    def rerank(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return hits


class PassthroughCompressor:
    def compress(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return hits


class RecordingRuntime:
    runtime_name = "recording-runtime"
    provider_name = "recording-provider"

    def __init__(self, text: str = "ok") -> None:
        self.text = text
        self.last_prompt = None
        self.last_inputs = None

    def generate(self, request: RuntimeRequest) -> RuntimeResponse:
        self.last_prompt = request.prompt
        self.last_inputs = request.inputs
        return RuntimeResponse(
            text=self.text,
            runtime_name=self.runtime_name,
            provider_name=self.provider_name,
        )


def _chunk(
    *,
    text: str = "MindDock stores chunks in Chroma for grounded retrieval.",
    doc_id: str = "d1",
    chunk_id: str = "c1",
    source: str = "kb/doc.md",
    distance: float = 0.2,
) -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        doc_id=doc_id,
        chunk_id=chunk_id,
        source=source,
        title=source,
        section="Storage",
        ref=f"{source} > Storage",
        distance=distance,
    )


def test_prompt_registry_gets_profiles_by_id() -> None:
    chat = get_prompt_profile(EVIDENCE_FIRST_CHAT_PROFILE_ID)
    summary = get_prompt_profile(GROUNDED_SUMMARY_PROFILE_ID)
    compare = get_prompt_profile(GROUNDED_COMPARE_JSON_PROFILE_ID)

    assert chat.id == "evidence_first_chat_v1"
    assert chat.task_type == "chat"
    assert summary.id == "grounded_summary_v1"
    assert summary.task_type == "summarize"
    assert compare.id == "grounded_compare_json_v1"
    assert compare.task_type == "compare"


def test_chat_prompt_uses_evidence_first_profile_and_metadata() -> None:
    runtime = RecordingRuntime(text="grounded answer")
    service = ChatService(
        search_service=FakeSearchService([_chunk()]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=runtime,
    )

    result = service.chat(query="Where does MindDock store chunks?", top_k=1)

    formatted = service._format_prompt_for_debug(
        runtime.last_prompt,
        {"query": "Where does MindDock store chunks?", "evidence_block": "evidence"},
    )
    assert "Answer only from the provided evidence" in formatted
    trace = result.metadata.workflow_trace or {}
    assert trace["prompt_profile_id"] == EVIDENCE_FIRST_CHAT_PROFILE_ID
    assert trace["prompt_profile_version"] == "1.0.0"
    assert trace["prompt_policy"]["evidence_policy"].startswith("answer_only_from_provided_evidence")


def test_summary_prompt_uses_grounded_summary_profile_and_metadata(monkeypatch) -> None:
    hit = _chunk()
    monkeypatch.setattr(
        "app.services.summarize_service.run_retrieval_workflow",
        lambda **kwargs: RetrievalPreparationResult(
            hits=[hit],
            grounded_hits=[hit],
            context=build_context([hit]),
            citations=[],
        ),
    )
    runtime = RecordingRuntime(text="grounded summary")
    service = SummarizeService(
        search_service=FakeSearchService([]),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=runtime,
    )

    result = service.summarize(topic="MindDock storage", top_k=1)

    assert "Summarize only from the provided evidence" in service._build_basic_prompt().format(
        topic="MindDock storage",
        evidence_block="evidence",
    )
    trace = result.metadata.workflow_trace or {}
    assert trace["prompt_profile_id"] == GROUNDED_SUMMARY_PROFILE_ID
    assert trace["prompt_profile_version"] == "1.0.0"
    assert trace["prompt_policy"]["output_policy"].startswith("short_synthesis")


def test_compare_prompt_uses_grounded_compare_json_profile_and_metadata() -> None:
    runtime = RecordingRuntime(
        text=(
            '{"common_points":[{"statement":"Both mention vector storage.",'
            '"left_evidence_ids":["L1"],"right_evidence_ids":["R1"]}],'
            '"differences":[],"conflicts":[]}'
        )
    )
    service = CompareService(
        search_service=FakeSearchService(
            [
                _chunk(text="Project A uses Chroma vector storage.", doc_id="d1", chunk_id="c1", source="a.md"),
                _chunk(text="Project B uses Postgres vector storage.", doc_id="d2", chunk_id="c2", source="b.md"),
            ]
        ),
        reranker=PassthroughReranker(),
        compressor=PassthroughCompressor(),
        runtime=runtime,
    )

    result = service.compare(question="Compare vector storage", top_k=2)

    assert "Return strictly valid JSON" in str(runtime.last_prompt)
    assert "Evidence ids MUST come from the L1..Ln" in str(runtime.last_prompt)
    trace = result.metadata.workflow_trace or {}
    assert trace["prompt_profile_id"] == GROUNDED_COMPARE_JSON_PROFILE_ID
    assert trace["prompt_profile_version"] == "1.0.0"
    assert trace["prompt_policy"]["citation_policy"].startswith("compare_points_reference")
