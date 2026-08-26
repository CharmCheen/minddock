"""MindDock read-only MCP server POC (PRD FR-8).

Exposes MindDock retrieval as an MCP tool so MCP-aware clients (Claude
Desktop, Cursor, ...) can use the local knowledge base as grounded memory.
Protocol: Model Context Protocol over stdio — newline-delimited JSON-RPC 2.0
messages; no third-party SDK required.

Tools:
- ``minddock_search``: semantic search over the indexed knowledge base,
  returning hits plus citation metadata (read-only; no write tools by design).

Run:
    python tools/minddock_mcp_server.py

Configuration:
    MINDDOCK_MCP_BACKEND_URL   backend base URL (default http://127.0.0.1:8000)

This is a bounded POC per PRD: transport and dispatch are separated from I/O
so the protocol layer is unit-testable without sockets.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "minddock"
SERVER_VERSION = "0.1.0"

DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
_SEARCH_PATH = "/search"
_HTTP_TIMEOUT_SECONDS = 10.0

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "minddock_search",
        "description": (
            "Semantic search over the user's local MindDock knowledge base. "
            "Returns matched chunks with source/page/citation metadata."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of hits to return.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": ["query"],
        },
    }
]


def backend_base_url() -> str:
    return os.environ.get("MINDDOCK_MCP_BACKEND_URL", DEFAULT_BACKEND_URL).rstrip("/")


# ---------------------------------------------------------------------------
# Protocol handling (pure, unit-testable)
# ---------------------------------------------------------------------------


def handle_message(
    message: dict[str, Any],
    *,
    http_post: Callable[[str, str, dict[str, Any], float], dict[str, Any]],
    base_url: str | None = None,
) -> dict[str, Any] | None:
    """Handle one incoming JSON-RPC message; return the response or None."""

    if not isinstance(message, dict):
        return _error(None, -32600, "Invalid request: message must be an object.")

    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}

    # Notifications carry no id and expect no response.
    if msg_id is None:
        return None

    if method == "initialize":
        return _result(msg_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        return _result(msg_id, {"tools": TOOL_DEFINITIONS})
    if method == "tools/call":
        return _handle_tools_call(msg_id, params, http_post=http_post, base_url=base_url)
    return _error(msg_id, -32601, f"Method not found: {method}")


def _handle_tools_call(
    msg_id: Any,
    params: dict[str, Any],
    *,
    http_post: Callable[[str, str, dict[str, Any], float], dict[str, Any]],
    base_url: str | None,
) -> dict[str, Any]:
    name = str(params.get("name") or "")
    arguments = params.get("arguments") or {}
    if name != "minddock_search":
        return _tool_error(msg_id, f"Unknown tool: {name}")

    query = str(arguments.get("query") or "").strip()
    if not query:
        return _tool_error(msg_id, "Missing required argument: query")
    try:
        top_k = int(arguments.get("top_k", 5))
    except (TypeError, ValueError):
        top_k = 5
    top_k = max(1, min(top_k, 20))

    url = (base_url or backend_base_url()) + _SEARCH_PATH
    try:
        payload = http_post(url, _SEARCH_PATH, {"query": query, "top_k": top_k}, _HTTP_TIMEOUT_SECONDS)
    except Exception as exc:
        return _tool_error(msg_id, f"Backend unreachable at {url}: {exc.__class__.__name__}")

    hits = payload.get("hits") or []
    text_lines = [f"Found {len(hits)} hit(s) for: {query}", ""]
    for index, hit in enumerate(hits, start=1):
        citation = hit.get("citation") or {}
        title = citation.get("title") or hit.get("title") or hit.get("source") or "unknown"
        location = citation.get("section_title") or citation.get("section") or ""
        page = citation.get("page_start") or hit.get("page")
        locator = " · ".join(part for part in (str(title), str(location) if location else "", f"p.{page}" if page else "") if part)
        snippet = str(hit.get("text") or "").replace("\n", " ")[:300]
        text_lines.append(f"[{index}] {locator}")
        text_lines.append(f"    doc_id={hit.get('doc_id', '')} chunk_id={hit.get('chunk_id', '')}")
        text_lines.append(f"    {snippet}")
        text_lines.append("")

    return _result(msg_id, {
        "content": [
            {
                "type": "text",
                "text": "\n".join(text_lines).strip(),
            }
        ],
        # Structured payload lives at result level (never inside typed content
        # items, which strict MCP clients validate against {type, text}).
        "structuredContent": {"query": query, "hit_count": len(hits), "hits": hits},
        "isError": False,
    })


def _result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _tool_error(msg_id: Any, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {"content": [{"type": "text", "text": message}], "isError": True},
    }


# ---------------------------------------------------------------------------
# stdio transport (thin loop; kept out of unit tests)
# ---------------------------------------------------------------------------


def default_http_post(url: str, path: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def serve(stdin=sys.stdin, stdout=sys.stdout) -> None:  # pragma: no cover - transport loop
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = _error(None, -32700, "Parse error")
        else:
            response = handle_message(message, http_post=default_http_post)
        if response is None:
            continue
        stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        stdout.flush()


if __name__ == "__main__":  # pragma: no cover
    serve()
