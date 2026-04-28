"""Unit tests for safe workflow trace helpers."""

from app.services.workflow_trace import merge_quality_trace_fields


def test_merge_quality_trace_fields_handles_none_trace() -> None:
    trace = merge_quality_trace_fields(None, {"retry_count": 1})

    assert trace == {"retry_count": 1}


def test_merge_quality_trace_fields_does_not_mutate_input_trace() -> None:
    original = {"operation": "chat"}

    trace = merge_quality_trace_fields(original, {"retry_count": 1})

    assert original == {"operation": "chat"}
    assert trace == {"operation": "chat", "retry_count": 1}
    assert trace is not original


def test_merge_quality_trace_fields_preserves_existing_trace_values() -> None:
    trace = merge_quality_trace_fields(
        {"retry_count": 99, "quality_reasons": ["existing"]},
        {"retry_count": 1, "quality_reasons": ["No hits retrieved"]},
    )

    assert trace["retry_count"] == 99
    assert trace["quality_reasons"] == ["existing"]


def test_merge_quality_trace_fields_filters_to_valid_safe_fields() -> None:
    trace = merge_quality_trace_fields(
        {"operation": "chat"},
        {
            "retry_count": 1,
            "max_retries": 1,
            "quality_reasons": ["No hits retrieved", 123, None],
            "low_confidence": True,
            "quality_ok": False,
            "reflection": {
                "attempt": 2,
                "reasons": ["No hits retrieved", object()],
                "low_confidence": True,
                "prompt": "secret",
            },
            "hits": ["raw chunks"],
            "compressed_hits": ["raw chunks"],
            "prompt": "secret",
            "evidence": "full evidence text",
            "matched_keyword": "compare",
            "arbitrary_object": object(),
        },
    )

    assert trace == {
        "operation": "chat",
        "retry_count": 1,
        "max_retries": 1,
        "quality_reasons": ["No hits retrieved"],
        "low_confidence": True,
        "quality_ok": False,
        "reflection": {
            "attempt": 2,
            "reasons": ["No hits retrieved"],
            "low_confidence": True,
        },
    }


def test_merge_quality_trace_fields_rejects_bool_for_int_fields() -> None:
    trace = merge_quality_trace_fields(None, {"retry_count": True, "max_retries": False})

    assert "retry_count" not in trace
    assert "max_retries" not in trace


def test_merge_quality_trace_fields_omits_empty_string_lists_and_invalid_reflection() -> None:
    trace = merge_quality_trace_fields(
        None,
        {
            "quality_reasons": [1, None],
            "reflection": {
                "attempt": True,
                "reasons": [1, None],
                "low_confidence": "yes",
            },
        },
    )

    assert trace == {}


def test_merge_quality_trace_fields_omits_non_mapping_reflection() -> None:
    trace = merge_quality_trace_fields(None, {"reflection": ["not", "a", "mapping"]})

    assert trace == {}
