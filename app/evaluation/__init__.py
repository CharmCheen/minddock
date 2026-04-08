"""Evaluation helpers for local benchmark execution and reporting."""

from app.evaluation.datasets import load_benchmark_dataset
from app.evaluation.models import BenchmarkCase, EvaluationReport, EvaluationRunArtifacts
from app.evaluation.reporting import render_console_summary, render_markdown_report
from app.evaluation.runner import run_evaluation_from_dataset

__all__ = [
    "BenchmarkCase",
    "EvaluationReport",
    "EvaluationRunArtifacts",
    "load_benchmark_dataset",
    "render_console_summary",
    "render_markdown_report",
    "run_evaluation_from_dataset",
]
