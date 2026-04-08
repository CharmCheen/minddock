"""Run the local MindDock evaluation workflow for demos and thesis screenshots."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.evaluation import render_console_summary, run_evaluation_from_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MindDock's local benchmark evaluation.")
    parser.add_argument("--dataset", default="eval/benchmark/sample_eval_set.jsonl", help="JSONL benchmark dataset path")
    parser.add_argument("--output-dir", default="data/eval", help="Directory for JSON and Markdown reports")
    args = parser.parse_args()

    result = run_evaluation_from_dataset(
        dataset_path=Path(args.dataset),
        output_dir=Path(args.output_dir),
    )
    print(
        render_console_summary(
            result.report,
            json_path=result.json_path,
            markdown_path=result.markdown_path,
        )
    )


if __name__ == "__main__":
    main()
