"""Deterministic evidence-sufficiency badge computation (PRD FR-1).

The badge is a deterministic mapping over existing retrieval-quality and
grounding signals only:

- ``support_status`` / ``insufficient_evidence`` / ``refusal_reason``
- pipeline quality fields merged into ``workflow_trace`` (``quality_ok``,
  ``low_confidence``, ``quality_reasons``, ``retry_count``)
- trace warnings (``no_citations``, ``fallback_hit_only``, ...)
- mock/fallback generation flags

No numeric thresholds are introduced before the 50-case evaluation set is
calibrated (PRD NFR-4). The mapping is intentionally one-to-one with the
existing signal enums so every badge decision can be explained.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

BADGE_VERSION = "evidence_badge_v1"

_LEVELS = ("green", "yellow", "red", "unknown")

# Reasons that indicate an empty retrieval pool. These map to RED because the
# answer has no evidence base at all (PRD FR-1: 红 = insufficient_evidence 或
# 检索空).
_RETRIEVAL_EMPTY_REASONS = frozenset(
    {
        "no_hits",
        "No hits retrieved",
        "no_compressed_hits",
        "No compressed hits",
    }
)

_INSUFFICIENT_STATUSES = frozenset({"insufficient_evidence", "conflicting_evidence"})


def compute_evidence_badge(
    *,
    task_type: str,
    support_status: str | None = None,
    insufficient_evidence: bool = False,
    refusal_reason: str | None = None,
    warnings: Sequence[str] = (),
    workflow_trace: Mapping[str, object] | None = None,
    mock_used: bool = False,
    fallback_used: bool = False,
    quality_signals_available: bool | None = None,
) -> dict[str, object]:
    """Compute the deterministic evidence badge for one grounded output.

    Returns a serializable dict: ``{version, level, reasons, signals}``.
    Levels: green / yellow / red / unknown.
    """

    trace = dict(workflow_trace or {})
    quality_reasons = _string_list(trace.get("quality_reasons"))
    trace_warnings = _string_list(trace.get("trace_warnings"))
    low_confidence = trace.get("low_confidence") is True

    if quality_signals_available is None:
        quality_signals_available = any(
            key in trace for key in ("quality_ok", "low_confidence", "quality_reasons", "retry_count")
        )

    signals: dict[str, object] = {
        "task_type": task_type,
        "support_status": support_status,
        "insufficient_evidence": insufficient_evidence,
        "refusal_reason": refusal_reason,
        "low_confidence": low_confidence,
        "quality_ok": trace.get("quality_ok"),
        "retry_count": trace.get("retry_count"),
        "quality_reasons": quality_reasons,
        "trace_warnings": trace_warnings,
        "mock_used": mock_used,
        "fallback_used": fallback_used,
        "quality_signals_available": quality_signals_available,
    }

    retrieval_empty = any(reason in _RETRIEVAL_EMPTY_REASONS for reason in (*quality_reasons, *trace_warnings))
    soft_flags = [
        reason
        for reason in (*quality_reasons, *trace_warnings)
        if reason not in _RETRIEVAL_EMPTY_REASONS
    ]

    reasons: list[str] = []
    level: str

    if (
        insufficient_evidence
        or refusal_reason is not None
        or (support_status is not None and support_status in _INSUFFICIENT_STATUSES)
        or retrieval_empty
    ):
        level = "red"
        if insufficient_evidence:
            reasons.append("insufficient_evidence_flag")
        if refusal_reason is not None:
            reasons.append(f"refusal:{refusal_reason}")
        if support_status in _INSUFFICIENT_STATUSES:
            reasons.append(f"support_status:{support_status}")
        if retrieval_empty:
            reasons.append("retrieval_empty")
    elif (
        support_status == "partially_supported"
        or low_confidence
        or soft_flags
        or warnings
        or mock_used
        or fallback_used
    ):
        level = "yellow"
        if support_status == "partially_supported":
            reasons.append("partially_supported")
        if low_confidence:
            reasons.append("low_confidence_retrieval")
        for flag in soft_flags[:3]:
            reasons.append(f"signal:{flag}")
        if warnings:
            reasons.append("generation_warnings_present")
        if mock_used:
            reasons.append("mock_generation_path")
        if fallback_used:
            reasons.append("fallback_generation_path")
    elif support_status == "supported":
        level = "green"
        reasons.append("supported_with_clean_quality_signals")
    else:
        level = "unknown"
        reasons.append("no_grounding_signals_available")

    # Compare runs before FR-6 carry no unified-pipeline quality fields. A bare
    # "supported" verdict alone must not render as a confident green badge;
    # degrade to unknown until compare quality signals are wired (PRD FR-1).
    if task_type == "compare" and not quality_signals_available and level == "green":
        level = "unknown"
        reasons.append("compare_quality_pipeline_pending")

    return {
        "version": BADGE_VERSION,
        "level": level,
        "reasons": reasons,
        "signals": signals,
    }


def badge_level(value: object) -> str | None:
    """Return the normalized badge level for arbitrary input, if valid."""

    normalized = str(value or "").strip().lower()
    return normalized if normalized in _LEVELS else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if isinstance(item, str)]
