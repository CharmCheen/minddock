"""Citation self-check: verify that citations actually support the answer (PRD FR-2).

Two-layer verification:

- **Rule layer** (synchronous, deterministic, zero-cost): citation structural
  validity plus lexical alignment between answer sentences and each cited
  snippet. Reuses the dangling-citation idea from the offline evaluation
  metrics but runs inline on production answers.
- **LLM layer** (bounded): one batched NLI-style call over at most a handful
  of citations producing per-citation three-state verdicts. Requires an
  optional runtime; failures degrade gracefully back to rule-layer results.

Failures never break the parent run (PRD NFR-5).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

STATUS_SUPPORTED = "supported"
STATUS_PARTIAL = "partial"
STATUS_UNSUPPORTED = "unsupported"

_OVERALL_PASS = "pass"
_OVERALL_PARTIAL = "partial"
_OVERALL_FAIL = "fail"

_LAYER_COMPLETED = "completed"
_LAYER_SKIPPED_NO_RUNTIME = "skipped_no_runtime"
_LAYER_SKIPPED_DISABLED = "skipped_disabled"
_LAYER_FAILED = "failed"

_VALID_VERDICTS = {STATUS_SUPPORTED, STATUS_PARTIAL, STATUS_UNSUPPORTED}
_MAX_LLM_CITATIONS = 8
_MAX_SNIPPET_CHARS = 600
_MAX_ANSWER_CHARS = 2400

# Alignment thresholds. These gate only the RULE layer's lexical fallback and
# are intentionally conservative; the LLM layer provides semantic judgment.
_WEAK_ALIGNMENT_SCORE = 0.05
_PARTIAL_ALIGNMENT_SCORE = 0.18

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")
_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fa5]")
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.S)


@dataclass(frozen=True)
class CitationCheckItem:
    """Verification verdict for one citation."""

    index: int
    ref: str | None
    chunk_id: str
    doc_id: str
    status: str
    score: float | None = None
    reasons: tuple[str, ...] = ()

    def to_api_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "ref": self.ref,
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "status": self.status,
            "score": self.score,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class CitationSelfCheckReport:
    """Complete self-check report for one grounded output."""

    overall: str
    items: tuple[CitationCheckItem, ...]
    layers: dict[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def counts(self) -> dict[str, int]:
        return {
            "total": len(self.items),
            "supported": sum(1 for item in self.items if item.status == STATUS_SUPPORTED),
            "partial": sum(1 for item in self.items if item.status == STATUS_PARTIAL),
            "unsupported": sum(1 for item in self.items if item.status == STATUS_UNSUPPORTED),
        }

    def to_api_dict(self) -> dict[str, object]:
        return {
            "version": "citation_self_check_v1",
            "overall": self.overall,
            "counts": self.counts(),
            "layers": dict(self.layers),
            "notes": list(self.notes),
            "items": [item.to_api_dict() for item in self.items],
        }


def run_rule_based_self_check(
    *,
    answer_text: str,
    citations: Sequence[object],
) -> CitationSelfCheckReport:
    """Deterministic structural + lexical verification of every citation."""

    sentences = [
        _tokenize(sentence)
        for sentence in _SENTENCE_SPLIT_RE.split(answer_text or "")
        if sentence.strip()
    ]
    items: list[CitationCheckItem] = []

    for index, citation in enumerate(citations):
        chunk_id = str(_field(citation, "chunk_id") or "").strip()
        doc_id = str(_field(citation, "doc_id") or "").strip()
        ref = _optional_text(_field(citation, "ref")) or f"[{index + 1}]"
        snippet = str(
            _field(citation, "snippet")
            or _field(citation, "evidence_preview")
            or ""
        ).strip()
        reasons: list[str] = []
        status = STATUS_SUPPORTED

        if not chunk_id:
            status = STATUS_UNSUPPORTED
            reasons.append("missing_chunk_id")
        if not snippet:
            status = STATUS_UNSUPPORTED
            reasons.append("empty_snippet")

        score: float | None = None
        if status == STATUS_SUPPORTED:
            snippet_tokens = set(_tokenize(snippet))
            best_overlap = 0.0
            for sentence_tokens in sentences:
                if not sentence_tokens:
                    continue
                overlap = len(sentence_tokens & snippet_tokens) / min(
                    len(sentence_tokens), len(snippet_tokens)
                )
                best_overlap = max(best_overlap, overlap)
            score = round(min(best_overlap, 1.0), 4)
            if best_overlap < _WEAK_ALIGNMENT_SCORE:
                status = STATUS_UNSUPPORTED
                reasons.append("weak_lexical_alignment")
            elif best_overlap < _PARTIAL_ALIGNMENT_SCORE:
                status = STATUS_PARTIAL
                reasons.append("partial_lexical_alignment")
            else:
                reasons.append("lexical_alignment_ok")

        if bool(_field(citation, "is_hit_only_fallback")) and status == STATUS_SUPPORTED:
            status = STATUS_PARTIAL
            reasons.append("downgraded_hit_only_fallback")

        items.append(
            CitationCheckItem(
                index=index,
                ref=ref,
                chunk_id=chunk_id,
                doc_id=doc_id,
                status=status,
                score=score,
                reasons=tuple(reasons),
            )
        )

    return CitationSelfCheckReport(
        overall=_overall_for(items),
        items=tuple(items),
        layers={"rule": _LAYER_COMPLETED},
        notes=("rule_layer_only",) if items else ("no_citations_to_check",),
    )


def run_citation_self_check(
    *,
    answer_text: str,
    citations: Sequence[object],
    runtime=None,
    llm_enabled: bool = True,
) -> CitationSelfCheckReport:
    """Run the full two-layer self-check.

    The LLM layer requires a runtime; when absent or when the call fails the
    rule-layer report is returned unchanged with an explanatory layer status.
    """

    report = run_rule_based_self_check(answer_text=answer_text, citations=citations)
    if not report.items:
        return report

    if runtime is None:
        return _with_layer_status(report, "llm", _LAYER_SKIPPED_NO_RUNTIME)
    if not llm_enabled:
        return _with_layer_status(report, "llm", _LAYER_SKIPPED_DISABLED)

    try:
        llm_verdicts = _llm_verdicts(runtime, answer_text=answer_text, citations=citations)
    except Exception as exc:  # pragma: no cover - defensive boundary
        logger.warning("Citation self-check LLM layer failed: %s", exc)
        return _with_layer_status(report, "llm", f"{_LAYER_FAILED}:{exc.__class__.__name__}")

    merged_items: list[CitationCheckItem] = []
    for item in report.items:
        verdict = llm_verdicts.get(item.index)
        if verdict is None:
            merged_items.append(item)
            continue
        status, reason = verdict
        merged_items.append(
            CitationCheckItem(
                index=item.index,
                ref=item.ref,
                chunk_id=item.chunk_id,
                doc_id=item.doc_id,
                # Never upgrade an unsupported rule verdict via the LLM layer.
                status=_merge_statuses(item.status, status),
                score=item.score,
                reasons=item.reasons + (f"llm:{status}" + (f":{reason}" if reason else ""),),
            )
        )

    merged = CitationSelfCheckReport(
        overall=_overall_for(merged_items),
        items=tuple(merged_items),
        layers={"rule": _LAYER_COMPLETED, "llm": _LAYER_COMPLETED},
        notes=(),
    )
    return merged


def _llm_verdicts(runtime, *, answer_text: str, citations: Sequence[object]) -> dict[int, tuple[str, str]]:
    limited = list(citations)[:_MAX_LLM_CITATIONS]
    listing_lines: list[str] = []
    for index, citation in enumerate(limited):
        snippet = str(_field(citation, "snippet") or _field(citation, "evidence_preview") or "")[:_MAX_SNIPPET_CHARS]
        listing_lines.append(f"[{index + 1}] {_field(citation, 'title') or _field(citation, 'source') or 'source'}: {snippet}")

    prompt = (
        "You are verifying whether cited evidence supports an answer.\n"
        "For EACH numbered citation decide one verdict:\n"
        '- "supported": the evidence clearly supports the answer claims it is attached to\n'
        '- "partial": the evidence partially supports or is related but incomplete\n'
        '- "unsupported": the evidence does not support the claim\n\n'
        f"Answer:\n{answer_text[:_MAX_ANSWER_CHARS]}\n\n"
        "Citations:\n" + "\n".join(listing_lines) + "\n\n"
        'Reply ONLY with a JSON array like: [{"index": 1, "verdict": "supported", "reason": "..."}]'
    )
    raw = runtime.invoke(
        prompt=prompt,
        inputs={"task": "citation_verification"},
        fallback_query="Verify citations",
        fallback_evidence=[],
    )
    parsed = _parse_verdict_json(raw)
    verdicts: dict[int, tuple[str, str]] = {}
    for entry in parsed:
        if not isinstance(entry, Mapping):
            continue
        try:
            index = int(entry.get("index"))
        except (TypeError, ValueError):
            continue
        if index < 1 or index > len(limited):
            continue
        verdict = str(entry.get("verdict") or "").strip().lower()
        if verdict not in _VALID_VERDICTS:
            continue
        reason = str(entry.get("reason") or "").strip()[:200]
        verdicts[index - 1] = (verdict, reason)
    return verdicts


def _parse_verdict_json(raw: str) -> list[object]:
    text = str(raw or "").strip()
    fenced = _CODE_FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    match = _JSON_ARRAY_RE.search(text)
    if not match:
        raise ValueError("self-check llm response contained no JSON array")
    payload = json.loads(match.group(0))
    if not isinstance(payload, list):
        raise ValueError("self-check llm response was not a JSON list")
    return payload


def _merge_statuses(rule_status: str, llm_status: str) -> str:
    """Merge rule-layer and LLM-layer verdicts.

    Policy: the semantic LLM verdict wins except for one conservative guard —
    an ``unsupported`` rule verdict (structural failure: missing chunk id,
    empty snippet) can never be upgraded straight to ``supported``; the best
    it can reach is ``partial``.
    """

    if rule_status == STATUS_UNSUPPORTED and llm_status == STATUS_SUPPORTED:
        return STATUS_PARTIAL
    return llm_status


def _overall_for(items: Sequence[CitationCheckItem]) -> str:
    if not items:
        return _OVERALL_PARTIAL
    statuses = {item.status for item in items}
    if statuses == {STATUS_SUPPORTED}:
        return _OVERALL_PASS
    if STATUS_UNSUPPORTED in statuses:
        return _OVERALL_FAIL
    return _OVERALL_PARTIAL


def _with_layer_status(report: CitationSelfCheckReport, layer: str, status: str) -> CitationSelfCheckReport:
    layers = dict(report.layers)
    layers[layer] = status
    notes = report.notes + ((f"{layer}:{status}",) if status != _LAYER_COMPLETED else ())
    return CitationSelfCheckReport(
        overall=report.overall,
        items=report.items,
        layers=layers,
        notes=notes,
    )


def _field(record: object, name: str):
    if isinstance(record, Mapping):
        return record.get(name)
    return getattr(record, name, None)


def _optional_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(str(text or "").lower()))
