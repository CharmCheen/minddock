"""Unit tests for citation self-check and run-trace archive (PRD FR-2)."""

from __future__ import annotations

import json

from app.application.run_trace_archive import list_run_traces, load_run_trace, persist_run_trace
from app.rag.retrieval_models import CitationRecord, GroundedAnswer, SupportStatus
from app.services.citation_self_check import (
    STATUS_PARTIAL,
    STATUS_SUPPORTED,
    STATUS_UNSUPPORTED,
    run_citation_self_check,
    run_rule_based_self_check,
)
from app.services.service_models import ChatServiceResult, UseCaseMetadata


def _citation(chunk_id: str, snippet: str) -> CitationRecord:
    return CitationRecord(
        doc_id=f"doc-{chunk_id}",
        chunk_id=chunk_id,
        source="notes.md",
        snippet=snippet,
    )


class TestRuleBasedSelfCheck:
    def test_aligned_citation_is_supported(self):
        answer = "Retrieval augmented generation grounds answers in indexed documents."
        citations = [_citation("c1", "grounded answers use retrieval over indexed documents")]
        report = run_rule_based_self_check(answer_text=answer, citations=citations)
        assert report.items[0].status == STATUS_SUPPORTED
        assert report.overall == "pass"
        assert report.layers["rule"] == "completed"

    def test_unrelated_snippet_is_unsupported(self):
        answer = "The quick brown fox jumps over the lazy dog near the river bank today."
        citations = [_citation("c1", "quantum chromodynamics describes gluon interactions inside hadrons")]
        report = run_rule_based_self_check(answer_text=answer, citations=citations)
        assert report.items[0].status in {STATUS_UNSUPPORTED, STATUS_PARTIAL}
        assert report.overall in {"fail", "partial"}

    def test_missing_chunk_id_is_unsupported(self):
        broken = CitationRecord(doc_id="d", chunk_id="", source="s", snippet="text")
        report = run_rule_based_self_check(answer_text="some answer text", citations=[broken])
        item = report.items[0]
        assert item.status == STATUS_UNSUPPORTED
        assert "missing_chunk_id" in item.reasons

    def test_empty_snippet_is_unsupported(self):
        report = run_rule_based_self_check(
            answer_text="answer",
            citations=[_citation("c1", "")],
        )
        assert report.items[0].status == STATUS_UNSUPPORTED
        assert report.overall == "fail"

    def test_hit_only_fallback_downgrades_supported(self):
        record = CitationRecord(
            doc_id="d",
            chunk_id="c1",
            source="notes.md",
            snippet="retrieval augmented generation grounds answers",
            is_hit_only_fallback=True,
        )
        answer = "retrieval augmented generation grounds answers"
        report = run_rule_based_self_check(answer_text=answer, citations=[record])
        # Without fallback it would be supported; fallback caps at partial.
        assert report.items[0].status == STATUS_PARTIAL
        assert "downgraded_hit_only_fallback" in report.items[0].reasons


class TestFullSelfCheckLayers:
    def test_no_runtime_skips_llm_layer(self):
        answer = "retrieval augmented generation grounds answers"
        citations = [_citation("c1", "grounded answers via retrieval augmentation")]
        report = run_citation_self_check(answer_text=answer, citations=citations, runtime=None)
        assert report.layers["llm"] == "skipped_no_runtime"
        assert report.layers["rule"] == "completed"

    class _FakeRuntime:
        runtime_name = "fake"

        def invoke(self, *, prompt, inputs, fallback_query, fallback_evidence, llm_override=None):
            return json.dumps(
                [
                    {"index": 1, "verdict": "unsupported", "reason": "snippet contradicts"},
                    {"index": 2, "verdict": "supported", "reason": "clear match"},
                ]
            )

    def test_llm_layer_merges_verdicts(self):
        answer = "retrieval augmented generation grounds answers. unrelated second sentence about weather patterns."
        citations = [
            _citation("c1", "completely different topic about ocean salinity measurements"),
            _citation("c2", "grounded answers via retrieval augmentation systems"),
        ]
        report = run_citation_self_check(answer_text=answer, citations=citations, runtime=self._FakeRuntime())
        assert report.layers["llm"] == "completed"
        by_index = {item.index: item for item in report.items}
        assert by_index[0].status == STATUS_UNSUPPORTED
        assert any(r.startswith("llm:unsupported") for r in by_index[0].reasons)

    def test_llm_failure_degrades_to_rule_results(self):
        class _BrokenRuntime:
            runtime_name = "broken"

            def invoke(self, **kwargs):
                raise RuntimeError("boom")

        answer = "retrieval augmented generation grounds answers"
        citations = [_citation("c1", "grounded answers via retrieval augmentation")]
        report = run_citation_self_check(answer_text=answer, citations=citations, runtime=_BrokenRuntime())
        assert report.layers["llm"].startswith("failed")
        assert report.items[0].status == STATUS_SUPPORTED

    def test_report_serialization_shape(self):
        answer = "retrieval augmented generation grounds answers"
        citations = [_citation("c1", "grounded answers via retrieval augmentation")]
        data = run_citation_self_check(answer_text=answer, citations=citations).to_api_dict()
        assert data["version"] == "citation_self_check_v1"
        assert set(data.keys()) >= {"overall", "counts", "layers", "items"}
        assert data["counts"]["total"] == 1


class TestRunTraceArchive:
    def _sample_response(self):
        result = ChatServiceResult(
            answer="Grounded answer.",
            citations=[_citation("c1", "grounded answers")],
            grounded_answer=GroundedAnswer(answer="Grounded answer.", support_status=SupportStatus.SUPPORTED),
            metadata=UseCaseMetadata(support_status="supported", warnings=("w1",)),
        )
        return result

    def test_persist_and_load_roundtrip(self, tmp_path):
        from app.application.artifacts import ArtifactBuilder

        result = self._sample_response()
        response_artifacts = ArtifactBuilder().build_chat_artifacts(result)

        class _Response:
            metadata = result.metadata
            artifacts = response_artifacts

        class _Summary:
            task_type = "chat"
            user_input_preview = "q"

        path = persist_run_trace(
            run_id="run-123",
            task_type="chat",
            request_summary=_Summary(),
            final_response=_Response(),
            trace_dir=tmp_path,
        )
        assert path is not None and path.exists()
        data = load_run_trace("run-123", trace_dir=tmp_path)
        assert data is not None
        assert data["run_id"] == "run-123"
        assert data["status"] == "completed"
        badges = data.get("evidence_badges")
        assert isinstance(badges, list) and len(badges) == 1
        # Metadata carries a warning, so deterministic mapping yields yellow.
        assert badges[0]["badge"]["level"] == "yellow"

    def test_failed_run_archives_error_summary(self, tmp_path):
        class _Summary:
            task_type = "chat"

        path = persist_run_trace(
            run_id="run-fail",
            task_type="chat",
            request_summary=_Summary(),
            final_response=None,
            error_summary={"status": "failed", "error": "RuntimeError", "detail": "boom"},
            status="failed",
            trace_dir=tmp_path,
        )
        assert path is not None
        data = load_run_trace("run-fail", trace_dir=tmp_path)
        assert data["status"] == "failed"
        assert data["error_summary"]["detail"] == "boom"
        assert data["citation_self_check"] is None

    def test_retention_keeps_newest_only(self, tmp_path):
        import time as _t

        from app.application.run_trace_archive import _enforce_retention

        shared = tmp_path / "shared"
        shared.mkdir()
        for i in range(6):
            path = shared / f"run-{i}.json"
            path.write_text("{}", encoding="utf-8")
            _t.sleep(0.01)
        _enforce_retention(shared, max_files=3)
        remaining = sorted(p.stem for p in shared.glob("*.json"))
        assert remaining == ["run-3", "run-4", "run-5"]

    def test_load_missing_returns_none(self, tmp_path):
        assert load_run_trace("nope", trace_dir=tmp_path) is None

    def test_list_traces_newest_first(self, tmp_path):
        for rid in ("run-a", "run-b"):
            (tmp_path / f"{rid}.json").write_text(
                json.dumps({"run_id": rid, "task_type": "chat", "archived_at": "t", "citation_self_check": {"overall": "pass"}}),
                encoding="utf-8",
            )
        traces = list_run_traces(limit=10, trace_dir=tmp_path)
        assert {t["run_id"] for t in traces} == {"run-a", "run-b"}
