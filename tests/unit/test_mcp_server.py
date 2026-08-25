"""Unit tests for the MindDock MCP server POC (PRD FR-8)."""

from __future__ import annotations

import json

import pytest

from tools.minddock_mcp_server import (
    PROTOCOL_VERSION,
    TOOL_DEFINITIONS,
    backend_base_url,
    handle_message,
)


def _canned_backend(monkeypatch=None, payload=None, fail=False):
    calls: list[tuple] = []

    def http_post(url, path, body, timeout):
        calls.append((url, path, body, timeout))
        if fail:
            raise ConnectionError("backend down")
        return payload

    return http_post, calls


SEARCH_PAYLOAD = {
    "hits": [
        {
            "text": "MindDock stores document chunks in a local Chroma database.",
            "doc_id": "doc123",
            "chunk_id": "doc123:0",
            "source": "example.md",
            "title": "Storage notes",
            "citation": {"title": "Storage notes", "section_title": "Storage", "page_start": 1},
        }
    ]
}


class TestInitialize:
    def test_initialize_returns_protocol_and_capabilities(self):
        http_post, calls = _canned_backend()
        response = handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, http_post=http_post)
        assert response["result"]["protocolVersion"] == PROTOCOL_VERSION
        assert response["result"]["serverInfo"]["name"] == "minddock"
        assert "tools" in response["result"]["capabilities"]
        assert calls == []

    def test_ping_returns_empty_result(self):
        response = handle_message({"jsonrpc": "2.0", "id": 2, "method": "ping"}, http_post=_canned_backend()[0])
        assert response["result"] == {}


class TestToolsList:
    def test_lists_minddock_search_with_schema(self):
        response = handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, http_post=_canned_backend()[0])
        tools = response["result"]["tools"]
        assert [t["name"] for t in tools] == ["minddock_search"]
        schema = tools[0]["inputSchema"]
        assert schema["required"] == ["query"]
        assert schema["properties"]["top_k"]["default"] == 5


class TestToolsCall:
    def test_search_returns_formatted_hits(self):
        http_post, calls = _canned_backend(payload=SEARCH_PAYLOAD)
        message = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "minddock_search", "arguments": {"query": "where are chunks stored?", "top_k": 3}},
        }
        response = handle_message(message, http_post=http_post)
        result = response["result"]
        assert result["isError"] is False
        text = result["content"][0]["text"]
        assert "Found 1 hit(s)" in text
        assert "doc_id=doc123" in text
        # Backend call used /search with normalized top_k and base url.
        url, path, body, _timeout = calls[0]
        assert path == "/search"
        assert body == {"query": "where are chunks stored?", "top_k": 3}

    def test_missing_query_is_tool_error(self):
        http_post, calls = _canned_backend()
        message = {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "minddock_search", "arguments": {}}}
        response = handle_message(message, http_post=http_post)
        assert response["result"]["isError"] is True
        assert "query" in response["result"]["content"][0]["text"]
        assert calls == []

    def test_unknown_tool_is_tool_error(self):
        http_post, _ = _canned_backend()
        message = {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "delete_everything"}}
        response = handle_message(message, http_post=http_post)
        assert response["result"]["isError"] is True

    def test_backend_failure_is_tool_error_not_crash(self):
        http_post, _ = _canned_backend(fail=True)
        message = {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "minddock_search", "arguments": {"query": "anything"}},
        }
        response = handle_message(message, http_post=http_post)
        assert response["result"]["isError"] is True
        assert "Backend unreachable" in response["result"]["content"][0]["text"]

    def test_top_k_clamped(self):
        http_post, calls = _canned_backend(payload=SEARCH_PAYLOAD)
        message = {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {"name": "minddock_search", "arguments": {"query": "q", "top_k": 999}},
        }
        handle_message(message, http_post=http_post)
        assert calls[0][2]["top_k"] == 20


class TestProtocolEdges:
    def test_unknown_method_is_rpc_error(self):
        response = handle_message({"jsonrpc": "2.0", "id": 9, "method": "resources/list"}, http_post=_canned_backend()[0])
        assert response["error"]["code"] == -32601

    def test_notifications_return_none(self):
        notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        assert handle_message(notification, http_post=_canned_backend()[0]) is None

    def test_invalid_payload_returns_parse_style_error(self):
        response = handle_message("not-a-dict", http_post=_canned_backend()[0])
        assert response["error"]["code"] == -32600

    def test_response_is_json_serializable(self):
        response = handle_message(
            {"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "minddock_search", "arguments": {"query": "x"}}},
            http_post=_canned_backend(payload=SEARCH_PAYLOAD)[0],
        )
        assert json.loads(json.dumps(response))["id"] == 10


def test_default_backend_url_from_env(monkeypatch):
    monkeypatch.setenv("MINDDOCK_MCP_BACKEND_URL", "http://localhost:9999/")
    assert backend_base_url() == "http://localhost:9999"
    monkeypatch.delenv("MINDDOCK_MCP_BACKEND_URL")
    assert backend_base_url() == "http://127.0.0.1:8000"
