"""Unit tests for demo serialization helpers."""

from pathlib import Path

from app.demo import (
    _metadata_to_dict,
    _serialize_catalog_result,
    _serialize_compare_result,
    _serialize_delete_source_result,
    _serialize_chat_result,
    _serialize_ingest_result,
    _serialize_reingest_source_result,
    _serialize_search_result,
    _serialize_source_detail_result,
    _serialize_source_inspect_result,
    _serialize_summarize_result,
    main,
)
from app.evaluation.models import EvaluationReport, EvaluationRunArtifacts, EvaluationSummary
from app.rag.retrieval_models import (
    CitationRecord,
    ComparedPoint,
    EvidenceObject,
    GroundedCompareResult,
    RetrievedChunk,
    SearchHitRecord,
    SearchResult,
    SupportStatus,
)
from app.rag.source_models import DeleteSourceResult, FailedSourceInfo, IngestBatchResult, IngestSourceResult, SourceCatalogEntry, SourceChunkPage, SourceChunkPreview, SourceDescriptor, SourceDetail, SourceInspectResult
from app.services.service_models import (
    CatalogServiceResult,
    ChatServiceResult,
    CompareServiceResult,
    DeleteSourceServiceResult,
    IngestServiceResult,
    ReingestSourceServiceResult,
    SearchServiceResult,
    ServiceIssue,
    SourceStats,
    SourceDetailServiceResult,
    SourceInspectServiceResult,
    SummarizeServiceResult,
    UseCaseMetadata,
    UseCaseTiming,
)


def test_metadata_to_dict_includes_controlled_fields() -> None:
    payload = _metadata_to_dict(
        UseCaseMetadata(
            retrieved_count=1,
            warnings=("warning",),
            issues=(ServiceIssue(code="empty_result", message="no hits", severity="info"),),
            timing=UseCaseTiming(total_ms=12.5, retrieval_ms=4.0),
            filter_applied=True,
            source_stats=SourceStats(requested_sources=2, succeeded_sources=1, failed_sources=1),
        )
    )

    assert payload["warnings"] == ["warning"]
    assert payload["issues"][0]["code"] == "empty_result"
    assert payload["timing"]["total_ms"] == 12.5
    assert payload["source_stats"]["failed_sources"] == 1


def test_demo_serializers_consume_service_results() -> None:
    chunk = RetrievedChunk(text="text", doc_id="d1", chunk_id="c1", source="kb/doc.md")
    citation = CitationRecord(doc_id="d1", chunk_id="c1", source="kb/doc.md", snippet="text")

    search_payload = _serialize_search_result(
        SearchServiceResult(
            search_result=SearchResult(
                query="q",
                top_k=1,
                hits=[SearchHitRecord(chunk=chunk, citation=citation)],
            ),
            metadata=UseCaseMetadata(retrieved_count=1),
        )
    )
    chat_payload = _serialize_chat_result(
        ChatServiceResult(
            answer="answer",
            citations=[citation],
            metadata=UseCaseMetadata(retrieved_count=1, mode="grounded"),
        )
    )
    summarize_payload = _serialize_summarize_result(
        SummarizeServiceResult(
            summary="summary",
            citations=[citation],
            metadata=UseCaseMetadata(retrieved_count=1, mode="basic", output_format="text"),
        )
    )
    ingest_payload = _serialize_ingest_result(
        IngestServiceResult(
            batch=IngestBatchResult(
                source_results=[
                    IngestSourceResult(
                        descriptor=SourceDescriptor(source="doc.md", source_type="file"),
                        ok=True,
                        chunks_upserted=1,
                    ),
                    IngestSourceResult(
                        descriptor=SourceDescriptor(source="https://example.com", source_type="url"),
                        ok=False,
                        failure=FailedSourceInfo(
                            source="https://example.com",
                            source_type="url",
                            reason="network failed",
                        ),
                    ),
                ]
            ),
            metadata=UseCaseMetadata(partial_failure=True),
        )
    )

    assert search_payload["hits"][0]["source"] == "kb/doc.md"
    assert chat_payload["mode"] == "grounded"
    assert summarize_payload["retrieved_count"] == 1
    assert ingest_payload["partial_failure"] is True


def test_demo_catalog_serializers() -> None:
    catalog_payload = _serialize_catalog_result(
        CatalogServiceResult(
            entries=[
                SourceCatalogEntry(
                    doc_id="d1",
                    source="notes.md",
                    source_type="file",
                    title="notes",
                    chunk_count=2,
                )
            ]
        )
    )
    detail_payload = _serialize_source_detail_result(
        SourceDetailServiceResult(
            found=True,
            detail=SourceDetail(
                entry=SourceCatalogEntry(
                    doc_id="d1",
                    source="notes.md",
                    source_type="file",
                    title="notes",
                    chunk_count=2,
                ),
                representative_metadata={"title": "notes"},
            ),
        )
    )
    delete_payload = _serialize_delete_source_result(
        DeleteSourceServiceResult(result=DeleteSourceResult(found=True, doc_id="d1", source="notes.md", source_type="file", deleted_chunks=2))
    )
    reingest_payload = _serialize_reingest_source_result(
        ReingestSourceServiceResult(
            found=True,
            source_result=IngestSourceResult(
                descriptor=SourceDescriptor(source="notes.md", source_type="file"),
                ok=True,
                chunks_upserted=2,
                chunks_deleted=1,
            ),
        )
    )
    inspect_payload = _serialize_source_inspect_result(
        SourceInspectServiceResult(
            found=True,
            inspect=SourceInspectResult(
                detail=SourceDetail(
                    entry=SourceCatalogEntry(
                        doc_id="d1",
                        source="notes.md",
                        source_type="file",
                        title="notes",
                        chunk_count=2,
                    ),
                    representative_metadata={"title": "notes"},
                ),
                chunk_page=SourceChunkPage(
                    total_chunks=2,
                    returned_chunks=1,
                    limit=1,
                    offset=0,
                    chunks=[
                        SourceChunkPreview(
                            chunk_id="d1:0",
                            chunk_index=0,
                            preview_text="chunk preview",
                            title="notes",
                            section="Storage",
                            location="Storage",
                            ref="notes > Storage",
                            admin_metadata={"doc_id": "d1"},
                        )
                    ],
                ),
                include_admin_metadata=True,
                admin_metadata={"doc_id": "d1"},
            ),
        )
    )

    assert catalog_payload["total"] == 1
    assert detail_payload["item"]["source"] == "notes.md"
    assert delete_payload["deleted_chunks"] == 2
    assert reingest_payload["ok"] is True
    assert inspect_payload["chunks"][0]["chunk_id"] == "d1:0"
    assert inspect_payload["admin_metadata"]["doc_id"] == "d1"


def test_demo_compare_serializer_produces_correct_contract() -> None:
    """Verify _serialize_compare_result produces the expected demo output contract."""
    result = CompareServiceResult(
        compare_result=GroundedCompareResult(
            query="Compare storage",
            common_points=(
                ComparedPoint(
                    statement="Both discuss storage.",
                    left_evidence=(EvidenceObject(doc_id="d1", chunk_id="c1", source="a.md", snippet="Chroma"),),
                    right_evidence=(EvidenceObject(doc_id="d2", chunk_id="c2", source="b.md", snippet="Postgres"),),
                ),
            ),
            differences=(),
            conflicts=(),
            support_status=SupportStatus.SUPPORTED,
            refusal_reason=None,
        ),
        citations=[
            CitationRecord(doc_id="d1", chunk_id="c1", source="a.md", snippet="Chroma"),
            CitationRecord(doc_id="d2", chunk_id="c2", source="b.md", snippet="Postgres"),
        ],
        metadata=UseCaseMetadata(
            retrieved_count=2,
            mode="grounded_compare",
            support_status="supported",
            insufficient_evidence=False,
            timing=UseCaseTiming(total_ms=100.0),
            filter_applied=True,
        ),
    )
    payload = _serialize_compare_result(result)
    assert payload["query"] == "Compare storage"
    assert payload["support_status"] == "supported"
    assert len(payload["common_points"]) == 1
    assert payload["common_points"][0]["left_evidence"][0]["source"] == "a.md"
    assert len(payload["citations"]) == 2
    assert payload["metadata"]["filter_applied"] is True


def test_demo_compare_api_payload_filters_as_list() -> None:
    """Verify --via-api mode passes filters as a list of source strings."""
    # Simulate the payload construction logic from cmd_compare for --via-api
    filters_input = "a.md,b.md,c.md"
    source_list = [s.strip() for s in filters_input.split(",") if s.strip()]
    payload = {
        "task_type": "compare",
        "user_input": "Compare docs",
        "top_k": 5,
        "output_mode": "structured",
    }
    if source_list:
        payload["filters"] = {"source": source_list}

    assert payload["filters"]["source"] == ["a.md", "b.md", "c.md"]
    assert isinstance(payload["filters"]["source"], list)
    # Verify each source is a separate string, not a comma-joined string
    for src in payload["filters"]["source"]:
        assert "," not in src


def test_cmd_compare_via_api_sends_correct_request(monkeypatch) -> None:
    """cmd_compare --via-api sends task_type=compare, output_mode=structured, and source list to /frontend/execute."""
    import json
    from app.demo import main

    captured: dict = {}

    class _FakeHTTPResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps({}).encode()

    def _fake_urlopen(req):
        captured["url"] = req.full_url
        captured["method"] = req.method
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeHTTPResponse()

    monkeypatch.setattr("app.demo.request.urlopen", _fake_urlopen)

    main([
        "compare",
        "--via-api",
        "--question", "Compare the storage approaches",
        "--top-k", "5",
        "--filters", "a.md,b.md,c.md",
    ])

    assert captured["url"] == "http://127.0.0.1:8000/frontend/execute"
    assert captured["method"] == "POST"
    assert captured["body"]["task_type"] == "compare"
    assert captured["body"]["output_mode"] == "structured"
    assert captured["body"]["user_input"] == "Compare the storage approaches"
    # --filters a.md,b.md,c.md must be sent as a source list, not a comma-joined string
    assert captured["body"]["filters"]["source"] == ["a.md", "b.md", "c.md"]
    for src in captured["body"]["filters"]["source"]:
        assert "," not in src


def test_demo_evaluate_command_prints_summary(monkeypatch, capsys) -> None:
    fake_run = EvaluationRunArtifacts(
        report=EvaluationReport(
            dataset_path="eval/benchmark/sample_eval_set.jsonl",
            generated_at="2026-04-07T00:00:00+00:00",
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
                    "by_task_type": {"search": {"avg_ms": 10.0, "p50_ms": 10.0, "p95_ms": 10.0, "max_ms": 10.0, "sample_count": 1}},
                },
                failed_case_count=0,
            ),
        ),
        json_path=str(Path("data/eval/report.json")),
        markdown_path=str(Path("data/eval/report.md")),
    )
    monkeypatch.setattr("app.demo.run_evaluation_from_dataset", lambda **kwargs: fake_run)

    main(["evaluate", "--dataset", "eval/benchmark/sample_eval_set.jsonl"])

    output = capsys.readouterr().out
    assert "Evaluation dataset" in output
    assert "JSON report" in output
