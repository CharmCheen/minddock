from pydantic import ValidationError

from app.api.schemas import ChatRequest, SearchRequest


def test_search_request_rejects_blank_query() -> None:
    try:
        SearchRequest(query="   ")
    except ValidationError as exc:
        assert "query must not be empty" in str(exc)
    else:
        raise AssertionError("blank query should fail validation")


def test_chat_request_trims_query() -> None:
    payload = ChatRequest(query="  hello  ")
    assert payload.query == "hello"
