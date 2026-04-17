"""Minimal CI baseline test runner.

This script runs the verified-stable baseline test set for MindDock's
shared contract baseline. It excludes known environment-dependent tests
(e.g. langchain_chroma availability) that are not part of the current
common-base closure.

Usage:
    python scripts/run_ci_baseline.py
    python -m pytest scripts/run_ci_baseline.py

The same command is used by .github/workflows/ci-baseline.yml and can
be reused locally for regression checks.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
TESTS_DIR = ROOT / "tests"

# Baseline test files — all tests in these files are verified stable
BASELINE_FILES = [
    TESTS_DIR / "contract" / "test_contracts.py",
    TESTS_DIR / "unit" / "test_application_orchestrators.py",
    TESTS_DIR / "unit" / "test_demo.py",
    TESTS_DIR / "unit" / "test_evaluation.py",
    TESTS_DIR / "unit" / "test_run_control.py",
    TESTS_DIR / "integration" / "test_system_pipeline.py",
]

# Integration tests — run stable subset by deselecting known environment-dependent test
# Excluded: test_compare_freshness_stale_possible_projected_in_response
#   Reason: requires langchain_chroma package not present in all CI environments
INTEGRATION_ARGS = [
    "--deselect=tests/integration/test_api_routes.py::test_compare_freshness_stale_possible_projected_in_response",
]


def _build_args() -> list[str]:
    baseline_args = [str(f) for f in BASELINE_FILES if f.exists()]
    baseline_args.append(str(TESTS_DIR / "integration" / "test_api_routes.py"))
    baseline_args.extend(INTEGRATION_ARGS)
    return baseline_args


def run() -> int:
    baseline_args = _build_args()
    cmd = [sys.executable, "-m", "pytest", "-v", "--tb=short"] + baseline_args
    print(f"Running baseline tests: {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=str(ROOT))
    return result.returncode


if __name__ == "__main__":
    sys.exit(run())
