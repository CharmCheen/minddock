"""Static tests for evaluation fixtures and golden set consistency."""

import hashlib
import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parents[2] / "eval" / "benchmark" / "fixtures"
GOLDEN_SET_PATH = Path(__file__).parents[2] / "eval" / "benchmark" / "golden_eval_set.jsonl"
SAMPLE_SET_PATH = Path(__file__).parents[2] / "eval" / "benchmark" / "sample_eval_set.jsonl"

EXPECTED_FIXTURES = {"example.md", "architecture.md", "rag_pipeline.md", "api_usage.md", "README.md"}


def _compute_doc_id(filename: str) -> str:
    return hashlib.sha1(filename.encode("utf-8")).hexdigest()


def _load_cases(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------------------
# Fixture file tests
# ---------------------------------------------------------------------------


def test_fixtures_directory_exists() -> None:
    assert FIXTURES_DIR.is_dir(), f"Fixtures directory not found: {FIXTURES_DIR}"


def test_all_expected_fixtures_exist() -> None:
    existing = {f.name for f in FIXTURES_DIR.iterdir() if f.is_file()}
    missing = EXPECTED_FIXTURES - existing
    assert not missing, f"Missing fixture files: {missing}"


def test_fixture_documents_are_non_empty() -> None:
    for name in EXPECTED_FIXTURES:
        if name == "README.md":
            continue
        path = FIXTURES_DIR / name
        content = path.read_text(encoding="utf-8").strip()
        assert len(content) > 100, f"Fixture {name} is too short ({len(content)} chars)"


def test_fixture_documents_have_headings() -> None:
    """Fixture markdown files should have section headings for stable chunking."""
    for name in EXPECTED_FIXTURES:
        if name == "README.md":
            continue
        path = FIXTURES_DIR / name
        content = path.read_text(encoding="utf-8")
        headings = [line for line in content.splitlines() if line.strip().startswith("#")]
        assert len(headings) >= 2, f"Fixture {name} has fewer than 2 headings ({len(headings)})"


# ---------------------------------------------------------------------------
# Doc ID stability tests
# ---------------------------------------------------------------------------


def test_fixture_doc_ids_match_golden_set() -> None:
    """All expected_doc_ids in the golden set should map to known fixture files."""
    cases = _load_cases(GOLDEN_SET_PATH)
    fixture_doc_ids = {_compute_doc_id(f): f for f in EXPECTED_FIXTURES if f != "README.md"}

    for case in cases:
        if case.get("expected_insufficient_evidence"):
            continue
        for doc_id in case.get("expected_doc_ids", []):
            assert doc_id in fixture_doc_ids, (
                f"Case '{case['id']}': expected_doc_id '{doc_id[:16]}...' "
                f"does not match any fixture file"
            )


def test_fixture_doc_ids_match_sample_set() -> None:
    """All expected_doc_ids in the sample set should map to known fixture files."""
    cases = _load_cases(SAMPLE_SET_PATH)
    fixture_doc_ids = {_compute_doc_id(f): f for f in EXPECTED_FIXTURES if f != "README.md"}

    for case in cases:
        if case.get("expected_insufficient_evidence"):
            continue
        for doc_id in case.get("expected_doc_ids", []):
            assert doc_id in fixture_doc_ids, (
                f"Case '{case['id']}': expected_doc_id '{doc_id[:16]}...' "
                f"does not match any fixture file"
            )


# ---------------------------------------------------------------------------
# Golden set structure tests
# ---------------------------------------------------------------------------


def test_golden_set_is_parseable() -> None:
    cases = _load_cases(GOLDEN_SET_PATH)
    assert len(cases) > 0, "Golden set is empty"


def test_golden_set_covers_all_task_types() -> None:
    from collections import Counter

    cases = _load_cases(GOLDEN_SET_PATH)
    task_counts = Counter(c["task_type"] for c in cases)
    assert "search" in task_counts
    assert "chat" in task_counts
    assert "compare" in task_counts


def test_golden_set_has_insufficient_evidence_cases() -> None:
    cases = _load_cases(GOLDEN_SET_PATH)
    ie_cases = [c for c in cases if c.get("expected_insufficient_evidence")]
    assert len(ie_cases) >= 3, f"Expected at least 3 IE cases, got {len(ie_cases)}"


def test_supported_cases_have_expected_doc_ids() -> None:
    """Every non-IE case should have at least one expected_doc_id."""
    cases = _load_cases(GOLDEN_SET_PATH)
    for case in cases:
        if case.get("expected_insufficient_evidence"):
            continue
        assert case.get("expected_doc_ids"), (
            f"Supported case '{case['id']}' has no expected_doc_ids"
        )


def test_ie_cases_have_empty_expected_doc_ids() -> None:
    """IE cases should not expect any document hits."""
    cases = _load_cases(GOLDEN_SET_PATH)
    for case in cases:
        if not case.get("expected_insufficient_evidence"):
            continue
        assert case.get("expected_doc_ids") == [] or case.get("expected_doc_ids") is None, (
            f"IE case '{case['id']}' should have empty expected_doc_ids"
        )
        assert case.get("expected_citation_doc_ids") == [] or case.get("expected_citation_doc_ids") is None, (
            f"IE case '{case['id']}' should have empty expected_citation_doc_ids"
        )


def test_all_cases_have_non_empty_query() -> None:
    cases = _load_cases(GOLDEN_SET_PATH)
    for case in cases:
        assert case.get("query", "").strip(), f"Case '{case['id']}' has empty query"


def test_all_cases_have_unique_ids() -> None:
    cases = _load_cases(GOLDEN_SET_PATH)
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "Golden set has duplicate case IDs"


# ---------------------------------------------------------------------------
# Sample set structure tests
# ---------------------------------------------------------------------------


def test_sample_set_is_parseable() -> None:
    cases = _load_cases(SAMPLE_SET_PATH)
    assert len(cases) > 0, "Sample set is empty"


def test_sample_set_has_ie_case() -> None:
    cases = _load_cases(SAMPLE_SET_PATH)
    ie_cases = [c for c in cases if c.get("expected_insufficient_evidence")]
    assert len(ie_cases) >= 1, "Sample set should have at least 1 IE case"


# ---------------------------------------------------------------------------
# Query-fixture alignment tests
# ---------------------------------------------------------------------------


def _fixture_content(filename: str) -> str:
    return (FIXTURES_DIR / filename).read_text(encoding="utf-8").lower()


def test_golden_queries_have_keyword_hits_in_fixtures() -> None:
    """Each supported golden set query should have at least one keyword hit in its fixture."""
    cases = _load_cases(GOLDEN_SET_PATH)
    fixture_doc_ids = {_compute_doc_id(f): f for f in EXPECTED_FIXTURES if f != "README.md"}

    stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                 "being", "have", "has", "had", "do", "does", "did", "will",
                 "would", "could", "should", "may", "might", "can", "shall",
                 "to", "of", "in", "for", "on", "with", "at", "by", "from",
                 "as", "into", "through", "during", "before", "after", "and",
                 "but", "or", "nor", "not", "no", "so", "if", "then", "than",
                 "that", "this", "these", "those", "it", "its", "they", "them",
                 "their", "what", "which", "who", "whom", "how", "when", "where",
                 "why", "does", "do", "did", "each", "every", "all", "both",
                 "few", "more", "most", "other", "some", "such", "only", "own",
                 "same", "about", "above", "across", "after", "against", "along",
                 "among", "around", "because", "before", "behind", "below",
                 "beneath", "beside", "between", "beyond", "down", "inside",
                 "near", "off", "onto", "out", "over", "past", "since", "through",
                 "toward", "under", "until", "up", "upon", "within", "without"}

    for case in cases:
        if case.get("expected_insufficient_evidence"):
            continue
        query_words = {w.lower() for w in case["query"].split() if len(w) > 2} - stopwords
        doc_ids = case.get("expected_doc_ids", [])
        for doc_id in doc_ids:
            filename = fixture_doc_ids.get(doc_id)
            if filename is None:
                continue
            content = _fixture_content(filename)
            hits = [w for w in query_words if w in content]
            assert len(hits) >= 2, (
                f"Case '{case['id']}': query keywords {query_words} "
                f"have fewer than 2 hits in {filename}"
            )
