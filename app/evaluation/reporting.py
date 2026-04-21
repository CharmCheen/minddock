"""Console and Markdown rendering for evaluation reports."""

from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.models import EvaluationReport


def render_console_summary(report: EvaluationReport, *, json_path: str | None = None, markdown_path: str | None = None) -> str:
    """Render a concise console summary for one evaluation run."""

    lines = [
        f"Evaluation dataset: {report.dataset_path}",
        f"Cases: {report.summary.dataset_size} | Failed cases: {report.summary.failed_case_count}",
        f"Task counts: {_format_task_counts(report.summary.task_counts)}",
        (
            "Retrieval: "
            f"hit@1={report.summary.retrieval['hit_at_1']:.2%} "
            f"hit@3={report.summary.retrieval['hit_at_3']:.2%} "
            f"hit@5={report.summary.retrieval['hit_at_5']:.2%}"
        ),
        (
            "Citation: "
            f"overall={report.summary.citation['overall_consistency_rate']:.2%} "
            f"structure={report.summary.citation['structure_consistency_rate']:.2%} "
            f"expected_source={_format_optional_rate(report.summary.citation['expected_source_consistency_rate'])}"
        ),
        (
            "Latency: "
            f"avg={report.summary.latency['overall']['avg_ms']:.2f}ms "
            f"p50={report.summary.latency['overall']['p50_ms']:.2f}ms "
            f"p95={report.summary.latency['overall']['p95_ms']:.2f}ms "
            f"max={report.summary.latency['overall']['max_ms']:.2f}ms"
        ),
    ]
    if json_path:
        lines.append(f"JSON report: {json_path}")
    if markdown_path:
        lines.append(f"Markdown report: {markdown_path}")
    return "\n".join(lines)


def render_markdown_report(report: EvaluationReport) -> str:
    """Render a thesis-friendly Markdown report."""

    lines = [
        "# MindDock Evaluation Report",
        "",
        f"- Dataset: `{report.dataset_path}`",
        f"- Generated at: `{report.generated_at}`",
        f"- Dataset size: **{report.summary.dataset_size}**",
        f"- Task counts: {_format_task_counts(report.summary.task_counts)}",
        "",
        "## Retrieval Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| hit@1 | {report.summary.retrieval['hit_at_1']:.2%} |",
        f"| hit@3 | {report.summary.retrieval['hit_at_3']:.2%} |",
        f"| hit@5 | {report.summary.retrieval['hit_at_5']:.2%} |",
        "",
        "## Citation Consistency",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Overall consistency rate | {report.summary.citation['overall_consistency_rate']:.2%} |",
        f"| Structure consistency rate | {report.summary.citation['structure_consistency_rate']:.2%} |",
        f"| Expected-source consistency rate | {_format_optional_rate(report.summary.citation['expected_source_consistency_rate'])} |",
        f"| Expected-source case count | {report.summary.citation['expected_source_case_count']} |",
        "",
        "## Latency Summary",
        "",
        "| Scope | Avg (ms) | P50 (ms) | P95 (ms) | Max (ms) | Samples |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        _latency_row("overall", report.summary.latency["overall"]),
    ]
    for task_type, stats in report.summary.latency["by_task_type"].items():
        lines.append(_latency_row(task_type, stats))

    lines.extend(
        [
            "",
            "## Failed Cases",
            "",
        ]
    )
    failed = [result for result in report.results if result.failure_reasons]
    if not failed:
        lines.append("All benchmark cases passed the current deterministic checks.")
    else:
        lines.extend(
            f"- `{result.case_id}` ({result.task_type}): {', '.join(result.failure_reasons)}"
            for result in failed
        )

    lines.extend(
        [
            "",
            "## Case Details",
            "",
            "| Case | Task | hit@1 | hit@3 | hit@5 | Citation | Latency (ms) |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        (
            f"| `{result.case_id}` | {result.task_type} | "
            f"{_bool_flag(result.retrieval.hit_at_1)} | "
            f"{_bool_flag(result.retrieval.hit_at_3)} | "
            f"{_bool_flag(result.retrieval.hit_at_5)} | "
            f"{_bool_flag(result.citation.overall_consistent)} | "
            f"{result.latency_ms:.2f} |"
        )
        for result in report.results
    )
    return "\n".join(lines)


def write_report_files(report: EvaluationReport, *, output_dir: str | Path, dataset_stem: str) -> tuple[str, str]:
    """Persist JSON and Markdown reports to disk."""

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / f"{dataset_stem}_evaluation_report.json"
    markdown_path = target_dir / f"{dataset_stem}_evaluation_report.md"
    json_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
    return str(json_path), str(markdown_path)


def _format_task_counts(task_counts: dict[str, int]) -> str:
    return ", ".join(f"{task}={count}" for task, count in sorted(task_counts.items()))


def _format_optional_rate(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2%}"


def _latency_row(scope: str, stats: dict[str, float | int]) -> str:
    return (
        f"| {scope} | {stats['avg_ms']:.2f} | {stats['p50_ms']:.2f} | "
        f"{stats['p95_ms']:.2f} | {stats['max_ms']:.2f} | {stats['sample_count']} |"
    )


def _bool_flag(value: bool) -> str:
    return "Y" if value else "N"
