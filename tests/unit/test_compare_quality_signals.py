"""Unit tests for compare quality-signal derivation (PRD FR-6)."""

from __future__ import annotations

from app.application.artifacts import ArtifactBuilder
from app.rag.retrieval_models import (
    ComparedPoint,
    EvidenceObject,
    GroundedCompareResult,
    SupportStatus,
)
from app.services.service_models import CompareServiceResult, UseCaseMetadata
from app.services.workflow_trace import build_compare_quality_trace


def _point(left=1, right=1) -> ComparedPoint:
    def evidence(doc: str, chunk: str) -> tuple:
        return (EvidenceObject(doc_id=doc, chunk_id=chunk, source=f"{doc}.md", snippet="text"),)

    return ComparedPoint(
        statement="point",
        left_evidence=evidence("a", f"a{left}") if left else (),
        right_evidence=evidence("b", f"b{right}") if right else (),
    )


class TestBuildCompareQualityTrace:
    def test_zero_evidence_is_low_confidence(self):
        compare = GroundedCompareResult(query="q")
        trace = build_compare_quality_trace(compare, citations=[])
        assert trace["quality_ok"] is False
        assert trace["low_confidence"] is True
        assert "No compressed hits" in trace["quality_reasons"]

    def test_insufficient_evidence_status_is_low_confidence(self):
        compare = GroundedCompareResult(query="q", common_points=(_point(),), support_status=SupportStatus.INSUFFICIENT_EVIDENCE)
        trace = build_compare_quality_trace(compare, citations=["c"])
        assert trace["low_confidence"] is True
        assert "insufficient_evidence" in trace["quality_reasons"]

    def test_healthy_compare_passes(self):
        compare = GroundedCompareResult(query="q", common_points=(_point(),), differences=(_point(),))
        trace = build_compare_quality_trace(compare, citations=["c1", "c2"])
        assert trace["quality_ok"] is True
        assert trace["low_confidence"] is False
        assert trace["quality_reasons"] == []
        assert trace["compare_evidence_count"] == 4


class TestCompareBadgeUpgrade:
    def test_badge_is_green_when_quality_signals_present(self):
        compare = GroundedCompareResult(query="q", common_points=(_point(),))
        result = CompareServiceResult(
            compare_result=compare,
            citations=[],
            metadata=UseCaseMetadata(
                support_status="supported",
                workflow_trace={
                    "quality_ok": True,
                    "low_confidence": False,
                    "quality_reasons": [],
                    "retry_count": 0,
                },
            ),
        )
        artifacts = ArtifactBuilder().build_compare_artifacts(result)
        badge = artifacts[0].metadata.get("evidence_badge")
        # Pre-FR-6 this degraded to unknown; with pipeline-style signals the
        # full deterministic mapping applies.
        assert badge["level"] == "green"
        assert badge["signals"]["quality_signals_available"] is True

    def test_badge_is_red_on_insufficient_evidence_compare(self):
        compare = GroundedCompareResult(query="q", support_status=SupportStatus.INSUFFICIENT_EVIDENCE)
        result = CompareServiceResult(
            compare_result=compare,
            citations=[],
            metadata=UseCaseMetadata(
                support_status="insufficient_evidence",
                insufficient_evidence=True,
                workflow_trace={
                    "quality_ok": False,
                    "low_confidence": True,
                    "quality_reasons": ["insufficient_evidence"],
                    "retry_count": 0,
                },
            ),
        )
        artifacts = ArtifactBuilder().build_compare_artifacts(result)
        badge = artifacts[0].metadata.get("evidence_badge")
        assert badge["level"] == "red"
