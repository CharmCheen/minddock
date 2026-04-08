"""Unit tests for the evaluation module."""

from pathlib import Path

from app.application.artifacts import ArtifactKind, SearchResultItemArtifact, SearchResultsArtifact
from app.application.models import TaskType, UnifiedExecutionResponse
from app.evaluation.datasets import load_benchmark_dataset
from app.evaluation.metrics import (
    evaluate_citation_consistency,
    evaluate_retrieval,
    extract_retrieval_references,
    summarize_latencies,
)
from app.evaluation.models import BenchmarkCase
from app.evaluation.runner import run_evaluation_from_dataset
from app.rag.retrieval_models import CitationRecord, ComparedPoint, EvidenceObject, GroundedAnswer, GroundedCompareResult
from app.services.service_models import UseCaseMetadata, UseCaseTiming


def test_load_benchmark_dataset_parses_jsonl(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        "\n".join(
            [
                '{"id":"case-1","task_type":"search","query":"storage","expected_doc_ids":["d1"]}',
                '{"id":"case-2","task_type":"chat","query":"citations","expected_chunk_ids":["d2:1"],"top_k":3}',
            ]
        ),
        encoding="utf-8",
    )

    cases = load_benchmark_dataset(dataset)

    assert [case.id for case in cases] == ["case-1", "case-2"]
    assert cases[0].expected_doc_ids == ("d1",)
    assert cases[1].expected_chunk_ids == ("d2:1",)
    assert cases[1].top_k == 3


def test_evaluate_retrieval_prefers_chunk_match_then_doc_match() -> None:
    chunk_case = BenchmarkCase(
        id="chunk-case",
        task_type="search",
        query="storage",
        expected_doc_ids=("d1",),
        expected_chunk_ids=("d1:2",),
    )
    doc_case = BenchmarkCase(
        id="doc-case",
        task_type="search",
        query="storage",
        expected_doc_ids=("d1",),
    )
    references = [
        type("Ref", (), {"doc_id": "d1", "chunk_id": "d1:9", "source": "doc.md", "rank": 1})(),
        type("Ref", (), {"doc_id": "d1", "chunk_id": "d1:2", "source": "doc.md", "rank": 2})(),
    ]

    chunk_result = evaluate_retrieval(chunk_case, references)
    doc_result = evaluate_retrieval(doc_case, references)

    assert chunk_result.match_basis == "chunk"
    assert chunk_result.hit_at_1 is False
    assert chunk_result.hit_at_3 is True
    assert doc_result.match_basis == "doc"
    assert doc_result.hit_at_1 is True


def test_evaluate_citation_consistency_detects_dangling_and_expected_source() -> None:
    case = BenchmarkCase(
        id="chat-case",
        task_type="chat",
        query="citations",
        expected_doc_ids=("d1",),
        expected_citation_doc_ids=("d1",),
    )
    response = UnifiedExecutionResponse(
        task_type=TaskType.CHAT,
        artifacts=(),
        citations=(
            CitationRecord(doc_id="d1", chunk_id="c1", source="doc.md", snippet="ok"),
            CitationRecord(doc_id="d2", chunk_id="c9", source="other.md", snippet="dangling"),
        ),
        grounded_answer=GroundedAnswer(
            answer="answer",
            evidence=(EvidenceObject(doc_id="d1", chunk_id="c1", source="doc.md", snippet="ok", score=0.1),),
        ),
    )
    references = extract_retrieval_references(response)

    result = evaluate_citation_consistency(case, response, references)

    assert result.structure_consistent is False
    assert result.expected_source_consistent is True
    assert result.overall_consistent is False
    assert result.dangling_citation_keys == ("d2:c9",)


def test_summarize_latencies_returns_expected_percentiles() -> None:
    summary = summarize_latencies([10.0, 20.0, 30.0, 40.0])

    assert summary.avg_ms == 25.0
    assert summary.p50_ms == 25.0
    assert summary.p95_ms == 38.5
    assert summary.max_ms == 40.0


class FakeFacade:
    def execute(self, request):
        if request.task_type == TaskType.SEARCH:
            return UnifiedExecutionResponse(
                task_type=TaskType.SEARCH,
                artifacts=(
                    SearchResultsArtifact(
                        artifact_id="search-1",
                        kind=ArtifactKind.SEARCH_RESULTS,
                        items=(
                            SearchResultItemArtifact(
                                chunk_id="d-search:0",
                                doc_id="d-search",
                                source="search.md",
                                source_type="file",
                                snippet="storage",
                            ),
                        ),
                        total=1,
                        offset=0,
                        limit=1,
                    ),
                ),
                citations=(CitationRecord(doc_id="d-search", chunk_id="d-search:0", source="search.md", snippet="storage"),),
                metadata=UseCaseMetadata(timing=UseCaseTiming(total_ms=12.0)),
            )
        if request.task_type == TaskType.CHAT:
            return UnifiedExecutionResponse(
                task_type=TaskType.CHAT,
                artifacts=(),
                citations=(CitationRecord(doc_id="d-chat", chunk_id="d-chat:1", source="chat.md", snippet="citations"),),
                grounded_answer=GroundedAnswer(
                    answer="chat answer",
                    evidence=(EvidenceObject(doc_id="d-chat", chunk_id="d-chat:1", source="chat.md", snippet="citations", score=0.1),),
                ),
                metadata=UseCaseMetadata(timing=UseCaseTiming(total_ms=20.0)),
            )
        return UnifiedExecutionResponse(
            task_type=TaskType.COMPARE,
            artifacts=(),
            citations=(
                CitationRecord(doc_id="d-left", chunk_id="d-left:0", source="left.md", snippet="left"),
                CitationRecord(doc_id="d-right", chunk_id="d-right:0", source="right.md", snippet="right"),
            ),
            compare_result=GroundedCompareResult(
                query=request.user_input,
                common_points=(
                    ComparedPoint(
                        statement="common",
                        left_evidence=(EvidenceObject(doc_id="d-left", chunk_id="d-left:0", source="left.md", snippet="left", score=0.1),),
                        right_evidence=(EvidenceObject(doc_id="d-right", chunk_id="d-right:0", source="right.md", snippet="right", score=0.1),),
                    ),
                ),
            ),
            metadata=UseCaseMetadata(timing=UseCaseTiming(total_ms=30.0)),
        )


def test_run_evaluation_from_dataset_happy_path(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        "\n".join(
            [
                '{"id":"search-case","task_type":"search","query":"storage","expected_doc_ids":["d-search"],"expected_chunk_ids":["d-search:0"],"expected_citation_doc_ids":["d-search"]}',
                '{"id":"chat-case","task_type":"chat","query":"citations","expected_doc_ids":["d-chat"],"expected_chunk_ids":["d-chat:1"],"expected_citation_doc_ids":["d-chat"]}',
                '{"id":"compare-case","task_type":"compare","query":"compare docs","expected_doc_ids":["d-left","d-right"],"expected_citation_doc_ids":["d-left","d-right"]}',
            ]
        ),
        encoding="utf-8",
    )

    result = run_evaluation_from_dataset(
        dataset_path=dataset,
        output_dir=tmp_path / "reports",
        facade=FakeFacade(),
    )

    assert result.report.summary.dataset_size == 3
    assert result.report.summary.retrieval["hit_at_5"] == 1.0
    assert result.report.summary.citation["overall_consistency_rate"] == 1.0
    assert Path(result.json_path).exists()
    assert Path(result.markdown_path).exists()
    assert "compare-case" in Path(result.markdown_path).read_text(encoding="utf-8")
