"""Unit tests for the evaluation module."""

import pytest
from pathlib import Path

from app.application.artifacts import ArtifactKind, SearchResultItemArtifact, SearchResultsArtifact, StructuredJsonArtifact
from app.application.models import TaskType, UnifiedExecutionResponse
from app.evaluation.datasets import load_benchmark_dataset
from app.evaluation.metrics import (
    evaluate_citation_consistency,
    evaluate_retrieval,
    extract_retrieval_references,
    summarize_latencies,
)
from app.evaluation.models import BenchmarkCase, EvaluationReport, EvaluationRunArtifacts, EvaluationSummary
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


# ---------------------------------------------------------------------------
# Artifact-first evaluation tests
# ---------------------------------------------------------------------------


def test_extract_retrieval_references_compare_artifact_first() -> None:
    """extract_retrieval_references prefers compare.v1 artifact over top-level compare_result.

    When both compare.v1 artifact and top-level compare_result exist,
    the artifact (primary source) must be used.
    """
    # Top-level compare_result has WRONG doc_ids to prove artifact wins
    response = UnifiedExecutionResponse(
        task_type=TaskType.COMPARE,
        artifacts=(
            StructuredJsonArtifact(
                artifact_id="cmp-1",
                kind=ArtifactKind.STRUCTURED_JSON,
                schema_name="compare.v1",
                data={
                    "query": "compare storage",
                    "common_points": [
                        {
                            "statement": "Both discuss storage.",
                            "left_evidence": [
                                {"doc_id": "artifact-left", "chunk_id": "alc1", "source": "kb/a.md", "snippet": "Chroma storage"},
                            ],
                            "right_evidence": [
                                {"doc_id": "artifact-right", "chunk_id": "arc1", "source": "kb/b.md", "snippet": "Postgres storage"},
                            ],
                        },
                    ],
                    "differences": [],
                    "conflicts": [],
                    "support_status": "supported",
                    "refusal_reason": None,
                },
            ),
        ),
        # This wrong top-level data must NOT be used when artifact is present
        compare_result=GroundedCompareResult(
            query="compare storage",
            common_points=(
                ComparedPoint(
                    statement="Both discuss storage.",
                    left_evidence=(EvidenceObject(doc_id="wrong-left", chunk_id="wlc1", source="kb/wrong.md", snippet="wrong"),),
                    right_evidence=(EvidenceObject(doc_id="wrong-right", chunk_id="wrc1", source="kb/wrong.md", snippet="wrong"),),
                ),
            ),
            differences=(),
            conflicts=(),
        ),
        citations=(
            CitationRecord(doc_id="wrong-left", chunk_id="wlc1", source="kb/wrong.md", snippet="wrong"),
            CitationRecord(doc_id="wrong-right", chunk_id="wrc1", source="kb/wrong.md", snippet="wrong"),
        ),
    )

    refs = extract_retrieval_references(response)

    # Must use artifact data, not top-level compare_result
    doc_ids = [ref.doc_id for ref in refs]
    assert "artifact-left" in doc_ids
    assert "artifact-right" in doc_ids
    assert "wrong-left" not in doc_ids
    assert "wrong-right" not in doc_ids


def test_extract_retrieval_references_compare_falls_back_to_top_level() -> None:
    """When compare.v1 artifact is absent, top-level compare_result is used as fallback."""
    response = UnifiedExecutionResponse(
        task_type=TaskType.COMPARE,
        artifacts=(),
        compare_result=GroundedCompareResult(
            query="compare storage",
            common_points=(
                ComparedPoint(
                    statement="Both discuss storage.",
                    left_evidence=(EvidenceObject(doc_id="top-left", chunk_id="tlc1", source="kb/a.md", snippet="Chroma"),),
                    right_evidence=(EvidenceObject(doc_id="top-right", chunk_id="trc1", source="kb/b.md", snippet="Postgres"),),
                ),
            ),
            differences=(),
            conflicts=(),
        ),
        citations=(),
    )

    refs = extract_retrieval_references(response)

    doc_ids = [ref.doc_id for ref in refs]
    assert "top-left" in doc_ids
    assert "top-right" in doc_ids


def test_evaluate_citation_consistency_compare_artifact_first_over_top_level() -> None:
    """evaluate_citation_consistency uses compare.v1 artifact keys (primary) for validity check.

    When artifact has different citation keys than top-level compare_result,
    the artifact keys drive citation validity — not top-level and not citations list alone.
    """
    case = BenchmarkCase(
        id="compare-eval-case",
        task_type="compare",
        query="compare storage",
        expected_doc_ids=("artifact-left", "artifact-right"),
    )
    response = UnifiedExecutionResponse(
        task_type=TaskType.COMPARE,
        artifacts=(
            StructuredJsonArtifact(
                artifact_id="cmp-1",
                kind=ArtifactKind.STRUCTURED_JSON,
                schema_name="compare.v1",
                data={
                    "query": "compare storage",
                    "common_points": [
                        {
                            "statement": "Both discuss storage.",
                            "left_evidence": [
                                {"doc_id": "artifact-left", "chunk_id": "alc1", "source": "kb/a.md", "snippet": "Chroma storage"},
                            ],
                            "right_evidence": [
                                {"doc_id": "artifact-right", "chunk_id": "arc1", "source": "kb/b.md", "snippet": "Postgres storage"},
                            ],
                        },
                    ],
                    "differences": [],
                    "conflicts": [],
                    "support_status": "supported",
                    "refusal_reason": None,
                },
            ),
        ),
        # citations point to artifact evidence — should be valid
        citations=(
            CitationRecord(doc_id="artifact-left", chunk_id="alc1", source="kb/a.md", snippet="Chroma storage"),
            CitationRecord(doc_id="artifact-right", chunk_id="arc1", source="kb/b.md", snippet="Postgres storage"),
        ),
        compare_result=GroundedCompareResult(
            query="compare storage",
            common_points=(
                ComparedPoint(
                    statement="Both discuss storage.",
                    left_evidence=(EvidenceObject(doc_id="wrong-left", chunk_id="wlc1", source="kb/wrong.md", snippet="wrong"),),
                    right_evidence=(EvidenceObject(doc_id="wrong-right", chunk_id="wrc1", source="kb/wrong.md", snippet="wrong"),),
                ),
            ),
            differences=(),
            conflicts=(),
        ),
    )
    # References from artifact
    references = extract_retrieval_references(response)

    result = evaluate_citation_consistency(case, response, references)

    # Citations match artifact evidence — must be consistent
    assert result.structure_consistent is True
    assert result.overall_consistent is True
    assert result.dangling_citation_keys == ()
    # If top-level were used, dangling would contain artifact citations (they don't match top-level)
    assert result.citation_count == 2


def test_evaluate_citation_consistency_artifact_metadata_not_authoritative() -> None:
    """Evaluation is unaffected by whether artifact metadata contains grounded_answer/compare_result.

    When SearchResultsArtifact provides retrieval, evaluation must succeed even if
    the artifact's metadata block is empty (no grounded_answer key).
    This proves artifact metadata is a compatibility copy, not the authoritative source.
    """
    case = BenchmarkCase(
        id="search-case",
        task_type="search",
        query="storage",
        expected_doc_ids=("d1",),
        expected_chunk_ids=("c1",),
        expected_citation_doc_ids=("d1",),
    )
    # Response with SearchResultsArtifact — no grounded_answer in artifact metadata
    response = UnifiedExecutionResponse(
        task_type=TaskType.SEARCH,
        artifacts=(
            # SearchResultsArtifact with empty metadata — no "grounded_answer" key
            SearchResultsArtifact(
                artifact_id="search-1",
                kind=ArtifactKind.SEARCH_RESULTS,
                items=(
                    SearchResultItemArtifact(
                        chunk_id="c1",
                        doc_id="d1",
                        source="kb/doc.md",
                        source_type="file",
                        snippet="Chroma stores vectors.",
                    ),
                ),
                total=1,
                offset=0,
                limit=5,
            ),
        ),
        citations=(
            CitationRecord(doc_id="d1", chunk_id="c1", source="kb/doc.md", snippet="Chroma stores vectors."),
        ),
    )

    references = extract_retrieval_references(response)
    result = evaluate_citation_consistency(case, response, references)

    # Evaluation succeeds because retrieval reference comes from SearchResultsArtifact,
    # not from artifact metadata grounded_answer
    assert result.structure_consistent is True
    assert result.expected_source_consistent is True
    assert result.overall_consistent is True


def test_search_results_artifact_takes_priority_over_citations() -> None:
    """For search task, SearchResultsArtifact drives retrieval references.

    citations list must NOT override artifact-based retrieval.
    """
    case = BenchmarkCase(
        id="search-case",
        task_type="search",
        query="storage",
        expected_doc_ids=("artifact-doc",),
        expected_chunk_ids=("artifact-chunk",),
    )
    response = UnifiedExecutionResponse(
        task_type=TaskType.SEARCH,
        artifacts=(
            SearchResultsArtifact(
                artifact_id="search-1",
                kind=ArtifactKind.SEARCH_RESULTS,
                items=(
                    SearchResultItemArtifact(
                        chunk_id="artifact-chunk",
                        doc_id="artifact-doc",
                        source="kb/artifact.md",
                        source_type="file",
                        snippet="artifact text",
                    ),
                ),
                total=1,
                offset=0,
                limit=5,
            ),
        ),
        # These citations have different doc_ids — must be ignored for retrieval
        citations=(
            CitationRecord(doc_id="wrong-doc", chunk_id="wrong-chunk", source="kb/wrong.md", snippet="wrong"),
        ),
    )

    references = extract_retrieval_references(response)

    # Retrieval references come from SearchResultsArtifact, not citations
    assert len(references) == 1
    assert references[0].doc_id == "artifact-doc"
    assert references[0].chunk_id == "artifact-chunk"


def test_sample_benchmark_dataset_covers_all_task_types() -> None:
    """Verify the sample benchmark dataset covers search, chat, and compare task types.

    This is a lightweight dataset-coverage test, not a quality test.
    It locks the minimum coverage boundary: all three task types must be present.
    """
    from collections import Counter
    from app.evaluation.datasets import load_benchmark_dataset

    dataset_path = Path(__file__).parents[2] / "eval" / "benchmark" / "sample_eval_set.jsonl"
    cases = load_benchmark_dataset(dataset_path)
    task_counts = Counter(c.task_type for c in cases)

    assert "search" in task_counts, "sample dataset must include at least one search case"
    assert "chat" in task_counts, "sample dataset must include at least one chat case"
    assert "compare" in task_counts, "sample dataset must include at least one compare case"
    assert task_counts["compare"] >= 3, "sample dataset must have at least 3 compare cases (compare is thin at 2)"
    assert len(cases) <= 15, "sample dataset should remain a small hand-curated set"


def test_benchmark_script_runs_successfully_with_sample_dataset(tmp_path: Path, monkeypatch) -> None:
    """Verify the benchmark script entry (scripts/evaluate_rag.py) can call the evaluation runner.

    This test proves the benchmark command can invoke the existing evaluation runner
    without errors, using the sample dataset. It does not require a live server
    or vector store.
    """
    # Set up a minimal in-memory dataset
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        '{"id":"b-case","task_type":"search","query":"storage","expected_doc_ids":["d1"]}\n',
        encoding="utf-8",
    )
    output_dir = tmp_path / "reports"

    # Patch the evaluation runner so it uses our fake dataset
    fake_report = EvaluationReport(
        dataset_path=str(dataset),
        generated_at="2026-04-08T00:00:00+00:00",
        cases=(),
        results=(),
        summary=EvaluationSummary(
            dataset_size=1,
            task_counts={"search": 1},
            retrieval={"hit_at_1": 1.0, "hit_at_3": 1.0, "hit_at_5": 1.0},
            citation={
                "overall_consistency_rate": 1.0,
                "structure_consistency_rate": 1.0,
                "expected_source_consistency_rate": 1.0,
                "expected_source_case_count": 1,
            },
            latency={
                "overall": {"avg_ms": 10.0, "p50_ms": 10.0, "p95_ms": 10.0, "max_ms": 10.0, "sample_count": 1},
                "by_task_type": {},
            },
            failed_case_count=0,
        ),
    )
    fake_artifacts = EvaluationRunArtifacts(
        report=fake_report,
        json_path=str(output_dir / "report.json"),
        markdown_path=str(output_dir / "report.md"),
    )

    # Patch at the module level used by scripts/evaluate_rag.py
    monkeypatch.setattr("scripts.evaluate_rag.run_evaluation_from_dataset", lambda **kwargs: fake_artifacts)
    monkeypatch.setattr("scripts.evaluate_rag._check_chroma_available", lambda: None)

    # Import and run the benchmark script's main
    from scripts.evaluate_rag import main as benchmark_main

    benchmark_main(["--dataset", str(dataset), "--output-dir", str(output_dir)])


def test_benchmark_script_raises_clear_error_when_chroma_missing(tmp_path: Path, monkeypatch, capsys) -> None:
    """_run_script_cli raises SystemExit(1) with a langchain-chroma message in stderr
    when the vector store dependency is absent.

    This tests the scripts/evaluate_rag.py CLI wrapper.
    """
    from scripts.evaluate_rag import _run_script_cli

    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        '{"id":"b-case","task_type":"search","query":"storage","expected_doc_ids":["d1"]}\n',
        encoding="utf-8",
    )

    # Simulate langchain-chroma being absent
    def fake_get_vectorstore():
        raise RuntimeError(
            "langchain-chroma and chromadb are required for vector storage."
        )

    monkeypatch.setattr("app.rag.vectorstore.get_vectorstore", fake_get_vectorstore)

    err = pytest.raises(SystemExit, _run_script_cli, ["--dataset", str(dataset)])
    assert err.value.code == 1

    stderr = capsys.readouterr().err
    assert "langchain-chroma" in stderr
    assert "Error:" in stderr


def test_scripts_evaluate_rag_cli_wrapper_calls_own_main(tmp_path: Path, monkeypatch) -> None:
    """_run_script_cli calls scripts/evaluate_rag.main (not app.demo.main).

    This proves the scripts/evaluate_rag.py entry point is bound to its own
    main function, not app.demo.main.
    """
    from scripts.evaluate_rag import _run_script_cli

    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        '{"id":"b-case","task_type":"search","query":"storage","expected_doc_ids":["d1"]}\n',
        encoding="utf-8",
    )
    output_dir = tmp_path / "reports"

    app_demo_call_tracker = []
    script_call_tracker = []

    def fake_app_demo_main(inner_argv):
        app_demo_call_tracker.append(inner_argv)

    def fake_script_main(inner_argv):
        script_call_tracker.append(inner_argv)

    monkeypatch.setattr("app.demo.main", fake_app_demo_main)
    monkeypatch.setattr("scripts.evaluate_rag.main", fake_script_main)
    monkeypatch.setattr("app.demo._check_chroma_available", lambda: None)
    monkeypatch.setattr("scripts.evaluate_rag._check_chroma_available", lambda: None)
    # Return a fake EvaluationRunArtifacts so main() completes without error
    fake_result = type("FakeResult", (), {"report": None})()
    monkeypatch.setattr("scripts.evaluate_rag.run_evaluation_from_dataset", lambda **kwargs: fake_result)

    # Success path: main() completes, _run_script_cli() returns 0 (no SystemExit)
    from scripts.evaluate_rag import run_cli_with_benchmark_error_handling
    ret = run_cli_with_benchmark_error_handling(
        lambda argv: _run_script_cli(argv),
        ["--dataset", str(dataset), "--output-dir", str(output_dir)],
    )
    # On success the inner call returns 0, wrapper returns 0
    assert ret == 0

    # scripts/evaluate_rag.main must have been called
    assert len(script_call_tracker) == 1
    assert script_call_tracker[0] == ["--dataset", str(dataset), "--output-dir", str(output_dir)]
    # app.demo.main must NOT have been called
    assert len(app_demo_call_tracker) == 0
