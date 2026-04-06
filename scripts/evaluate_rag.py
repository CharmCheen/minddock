"""Run a lightweight local RAG evaluation for demos and thesis screenshots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.eval.rag_eval import evaluate_cases, write_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MindDock's lightweight local RAG evaluation.")
    parser.add_argument("--output", default="data/eval/rag_eval_report.json", help="Where to write the JSON report")
    args = parser.parse_args()

    report = evaluate_cases()
    output_path = Path(args.output)
    write_report(report, output_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nSaved report to {output_path}")


if __name__ == "__main__":
    main()
