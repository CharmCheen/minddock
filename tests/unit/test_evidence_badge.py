"""Unit tests for the deterministic evidence badge (PRD FR-1)."""

from __future__ import annotations

from app.application.artifacts import ArtifactBuilder
from app.application.evidence_badge import BADGE_VERSION, badge_level, compute_evidence_badge
from app.rag.retrieval_models import (
    CitationRecord,
    ComparedPoint,
    EvidenceObject,
    GroundedCompareResult,
)
from app.services.service_models import (
    ChatServiceResult,
    CompareServiceResult,
    SummarizeServiceResult,
    UseCaseMetadata,
)


class TestComputeEvidenceBadge:
    def test_supported_with_clean_signals_is_green(self):
        badge = compute_evidence_badge(
            task_type="chat",
            support_status="supported",
            workflow_trace={"quality_ok": True, "low_confidence": False, "retry_count": 0},
        )
        assert badge["level"] == "green"
        assert "supported_with_clean_quality_signals" in badge["reasons"]

    def test_insufficient_evidence_is_red(self):
        badge = compute_evidence_badge(
            task_type="chat",
            support_status="insufficient_evidence",
            insufficient_evidence=True,
        )
        assert badge["level"] == "red"
        assert "insufficient_evidence_flag" in badge["reasons"]

    def test_conflicting_evidence_is_red(self):
        badge = compute_evidence_badge(
            task_type="chat",
            support_status="conflicting_evidence",
        )
        assert badge["level"] == "red"

    def test_refusal_reason_is_red(self):
        badge = compute_evidence_badge(
            task_type="chat",
            support_status="supported",
            refusal_reason="no_relevant_evidence",
        )
        assert badge["level"] == "red"
        assert any(reason.startswith("refusal:") for reason in badge["reasons"])

    def test_empty_retrieval_reason_is_red(self):
        badge = compute_evidence_badge(
            task_type="chat",
            support_status="supported",
            workflow_trace={"quality_ok": False, "quality_reasons": ["No hits retrieved"], "low_confidence": False},
        )
        assert badge["level"] == "red"
        assert "retrieval_empty" in badge["reasons"]

    def test_low_confidence_is_yellow(self):
        badge = compute_evidence_badge(
            task_type="chat",
            support_status="supported",
            workflow_trace={"quality_ok": True, "low_confidence": True, "retry_count": 1},
        )
        assert badge["level"] == "yellow"
        assert "low_confidence_retrieval" in badge["reasons"]

    def test_partially_supported_is_yellow(self):
        badge = compute_evidence_badge(task_type="chat", support_status="partially_supported")
        assert badge["level"] == "yellow"

    def test_no_citations_warning_is_yellow(self):
        badge = compute_evidence_badge(
            task_type="chat",
            support_status="supported",
            workflow_trace={"trace_warnings": ["no_citations"]},
        )
        assert badge["level"] == "yellow"
        assert "signal:no_citations" in badge["reasons"]

    def test_mock_generation_path_is_yellow(self):
        badge = compute_evidence_badge(
            task_type="chat",
            support_status="supported",
            mock_used=True,
        )
        assert badge["level"] == "yellow"
        assert "mock_generation_path" in badge["reasons"]

    def test_no_signals_at_all_is_unknown(self):
        badge = compute_evidence_badge(task_type="search")
        assert badge["level"] == "unknown"

    def test_compare_green_degrades_to_unknown_without_quality_pipeline(self):
        badge = compute_evidence_badge(
            task_type="compare",
            support_status="supported",
            quality_signals_available=False,
        )
        assert badge["level"] == "unknown"
        assert "compare_quality_pipeline_pending" in badge["reasons"]

    def test_compare_keeps_full_mapping_when_quality_pipeline_present(self):
        badge = compute_evidence_badge(
            task_type="compare",
            support_status="insufficient_evidence",
            quality_signals_available=True,
        )
        assert badge["level"] == "red"

    def test_badge_carries_version_and_signals(self):
        badge = compute_evidence_badge(task_type="chat", support_status="supported")
        assert badge["version"] == BADGE_VERSION
        assert badge["signals"]["support_status"] == "supported"
        assert isinstance(badge["signals"], dict)

    def test_non_string_quality_reasons_are_ignored(self):
        badge = compute_evidence_badge(
            task_type="chat",
            support_status="supported",
            workflow_trace={"quality_reasons": [123, None], "low_confidence": "yes"},
        )
        # low_confidence must be strictly boolean True; non-list items ignored.
        assert badge["level"] == "green"


class TestBadgeLevelHelper:
    def test_valid_levels(self):
        assert badge_level("GREEN") == "green"
        assert badge_level("red") == "red"
        assert badge_level(None) is None
        assert badge_level("purple") is None


def _citation(chunk_id: str) -> CitationRecord:
    return CitationRecord(
        doc_id=f"doc-{chunk_id}",
        chunk_id=chunk_id,
        source="notes.md",
        snippet="Retrieval augmented generation grounds answers.",
    )


class TestArtifactBuilderBadgeIntegration:
    def test_chat_artifact_metadata_contains_badge(self):
        result = ChatServiceResult(
            answer="Grounded answer.",
            citations=[_citation("c1")],
            metadata=UseCaseMetadata(support_status="supported"),
        )
        artifacts = ArtifactBuilder().build_chat_artifacts(result)
        badge = artifacts[0].metadata.get("evidence_badge")
        assert isinstance(badge, dict)
        assert badge["level"] == "green"
        assert badge["signals"]["task_type"] == "chat"

    def test_summarize_artifact_metadata_contains_badge(self):
        result = SummarizeServiceResult(
            summary="Summary text.",
            citations=[_citation("c1")],
            metadata=UseCaseMetadata(support_status="partially_supported"),
        )
        artifacts = ArtifactBuilder().build_summarize_artifacts(result, output_mode="text")
        badge = artifacts[0].metadata.get("evidence_badge")
        assert badge["level"] == "yellow"

    def test_compare_artifact_metadata_contains_gated_badge(self):
        point = ComparedPoint(
            statement="Both use vectors.",
            left_evidence=(EvidenceObject(doc_id="a", chunk_id="a1", source="a.md", snippet="text"),),
            right_evidence=(EvidenceObject(doc_id="b", chunk_id="b1", source="b.md", snippet="text"),),
        )
        compare_result = GroundedCompareResult(query="q", common_points=(point,))
        result = CompareServiceResult(
            compare_result=compare_result,
            citations=[],
            metadata=UseCaseMetadata(support_status="supported"),
        )
        artifacts = ArtifactBuilder().build_compare_artifacts(result)
        badge = artifacts[0].metadata.get("evidence_badge")
        # No unified-pipeline quality signals for compare yet (pre FR-6).
        assert badge["level"] == "unknown"
