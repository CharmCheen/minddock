"""Persistent run-trace archive (PRD FR-2 acceptance).

RunRegistry keeps runs in memory with a TTL, so self-check reports and
workflow traces vanish on restart. This module archives one JSON file per
completed run under ``data/run_traces/`` so verification reports survive
backend restarts. Persistence is best-effort: failures are swallowed by the
caller and never break execution.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_TRACE_DIR = Path("data") / "run_traces"
_RUN_ID_RE = re.compile(r"[^A-Za-z0-9_\-]")


def persist_run_trace(
    *,
    run_id: str,
    task_type: str,
    request_summary: object | None = None,
    final_response: object | None = None,
    trace_dir: Path | None = None,
) -> Path | None:
    """Write one run trace JSON file. Returns the written path or None."""

    directory = Path(trace_dir) if trace_dir is not None else DEFAULT_TRACE_DIR
    safe_id = _RUN_ID_RE.sub("_", str(run_id))[:120]
    if not safe_id:
        return None

    payload = _build_trace_payload(
        run_id=run_id,
        task_type=task_type,
        request_summary=request_summary,
        final_response=final_response,
    )
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{safe_id}.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
        return target
    except Exception as exc:
        logger.debug("Run trace persistence failed for %s: %s", run_id, exc)
        return None


def load_run_trace(run_id: str, *, trace_dir: Path | None = None) -> dict | None:
    """Load one archived run trace, or None when missing/corrupt."""

    safe_id = _RUN_ID_RE.sub("_", str(run_id))[:120]
    directory = Path(trace_dir) if trace_dir is not None else DEFAULT_TRACE_DIR
    target = directory / f"{safe_id}.json"
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_run_traces(*, limit: int = 50, trace_dir: Path | None = None) -> list[dict]:
    """List archived traces, newest first."""

    directory = Path(trace_dir) if trace_dir is not None else DEFAULT_TRACE_DIR
    entries: list[dict] = []
    try:
        files = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
    for path in files[: max(0, int(limit))]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        entries.append(
            {
                "run_id": data.get("run_id") or path.stem,
                "task_type": data.get("task_type"),
                "archived_at": data.get("archived_at"),
                "self_check_overall": (data.get("citation_self_check") or {}).get("overall")
                if isinstance(data.get("citation_self_check"), dict)
                else None,
            }
        )
    return entries


def _build_trace_payload(
    *,
    run_id: str,
    task_type: str,
    request_summary: object | None,
    final_response: object | None,
) -> dict:
    metadata = getattr(final_response, "metadata", None)
    workflow_trace = getattr(metadata, "workflow_trace", None) if metadata is not None else None

    badges: list[dict] = []
    self_check: dict | None = None
    artifacts = getattr(final_response, "artifacts", ()) or ()
    for artifact in artifacts:
        artifact_metadata = getattr(artifact, "metadata", None) or {}
        badge = artifact_metadata.get("evidence_badge")
        if isinstance(badge, dict):
            badges.append({"artifact_id": getattr(artifact, "artifact_id", None), "badge": badge})
        check = artifact_metadata.get("citation_self_check")
        if isinstance(check, dict) and self_check is None:
            self_check = check

    summary = request_summary.__dict__ if hasattr(request_summary, "__dict__") else request_summary

    return {
        "version": "run_trace_archive_v1",
        "run_id": run_id,
        "task_type": task_type,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "request_summary": _jsonable(summary),
        "workflow_trace": _jsonable(workflow_trace),
        "evidence_badges": badges,
        "citation_self_check": self_check,
        "warnings": list(getattr(metadata, "warnings", ()) or ()) if metadata is not None else [],
    }


def _jsonable(value: object) -> object:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return str(value)
