"""Run MindDock benchmark evaluation against a JSONL dataset.

This is a thin alias for `python -m app.demo evaluate`.
New code should prefer `python -m app.demo evaluate` directly.

Usage:
    python scripts/evaluate_rag.py
    python scripts/evaluate_rag.py --retrieval-mode dense
    python scripts/evaluate_rag.py --retrieval-mode hybrid
    python scripts/evaluate_rag.py --retrieval-mode compare
    python -m app.demo evaluate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.demo import _check_chroma_available, run_cli_with_benchmark_error_handling
from app.evaluation import render_console_summary, run_comparison_evaluation, run_evaluation_from_dataset

DEFAULT_DATASET = "eval/benchmark/sample_eval_set.jsonl"
DEFAULT_OUTPUT = "data/eval"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run MindDock benchmark evaluation.")
    parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET,
        help="JSONL benchmark dataset path",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT,
        help="Directory for JSON and Markdown reports",
    )
    parser.add_argument(
        "--retrieval-mode",
        choices=["dense", "hybrid", "compare"],
        default=None,
        help="Retrieval strategy: dense (default setting), hybrid (BM25+RRF), compare (run both and show delta)",
    )
    args = parser.parse_args(argv)

    _check_chroma_available()

    if args.retrieval_mode == "compare":
        result = run_comparison_evaluation(
            dataset_path=Path(args.dataset),
            output_dir=Path(args.output_dir),
        )
        print("=== Dense-Only Report ===")
        print(render_console_summary(result.dense_report, json_path=result.dense_json_path, markdown_path=result.dense_markdown_path))
        print()
        print("=== Hybrid Report ===")
        print(render_console_summary(result.hybrid_report, json_path=result.hybrid_json_path, markdown_path=result.hybrid_markdown_path))
        print()
        print("=== Comparison Delta ===")
        print(json.dumps(result.comparison, indent=2, ensure_ascii=False))
    else:
        result = run_evaluation_from_dataset(
            dataset_path=Path(args.dataset),
            output_dir=Path(args.output_dir),
            retrieval_mode=args.retrieval_mode,
        )
        print(
            render_console_summary(
                result.report,
                json_path=result.json_path,
                markdown_path=result.markdown_path,
            )
        )


def _run_script_cli(argv: list[str] | None = None) -> int:
    """CLI entry for scripts/evaluate_rag.py. Returns 0 on success; raises SystemExit(1) on preflight error."""
    return run_cli_with_benchmark_error_handling(main, argv)


if __name__ == "__main__":
    try:
        _run_script_cli()
    except SystemExit as exc:
        sys.exit(exc.code)
