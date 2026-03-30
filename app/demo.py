"""Thin demo command layer for presentation-friendly local workflows."""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from typing import Any
from urllib import error, request

from app.core.config import get_settings
from app.core.logging import setup_logging

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_QUERY = "MindDock stores document chunks and metadata in a local Chroma database"
DEFAULT_TOPIC = "MindDock stores document chunks and metadata in a local Chroma database"
DEFAULT_TOP_K = 3


def _base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _pretty_print(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    data: bytes | None = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = request.Request(url=url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req) as response:
            text = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Request failed: {exc.code} {exc.reason}", file=sys.stderr)
        print(body, file=sys.stderr)
        raise SystemExit(1) from exc
    except error.URLError as exc:
        print(f"Cannot reach demo server at {url}: {exc.reason}", file=sys.stderr)
        raise SystemExit(1) from exc

    if not text.strip():
        return {}
    return json.loads(text)


def _setup_demo_logging() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_dir, settings.app_name)


def cmd_ingest(args: argparse.Namespace) -> None:
    from app.services.ingest_service import IngestService

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    _setup_demo_logging()
    print(f"Running local ingest (rebuild={args.rebuild})...")
    result = IngestService().ingest(rebuild=args.rebuild)
    print(f"Loaded {result['documents']} documents")
    print(f"Created {result['chunks']} chunks")
    print("Stored to Chroma")


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    print(f"Starting MindDock demo server at {_base_url(args.host, args.port)}")
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=False)


def cmd_watch(_args: argparse.Namespace) -> None:
    os.environ["WATCH_ENABLED"] = "true"
    from app.rag.watcher import run_watcher

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    print("Starting watcher in demo mode (WATCH_ENABLED=true)...")
    run_watcher()


def cmd_health(args: argparse.Namespace) -> None:
    data = _request_json("GET", f"{_base_url(args.host, args.port)}/health")
    _pretty_print(data)


def cmd_root(args: argparse.Namespace) -> None:
    data = _request_json("GET", f"{_base_url(args.host, args.port)}/")
    _pretty_print(data)


def cmd_search(args: argparse.Namespace) -> None:
    payload = {
        "query": args.query,
        "top_k": args.top_k,
    }
    data = _request_json("POST", f"{_base_url(args.host, args.port)}/search", payload=payload)
    _pretty_print(data)


def cmd_chat(args: argparse.Namespace) -> None:
    payload = {
        "query": args.query,
        "top_k": args.top_k,
    }
    data = _request_json("POST", f"{_base_url(args.host, args.port)}/chat", payload=payload)
    _pretty_print(data)


def cmd_summarize(args: argparse.Namespace) -> None:
    payload = {
        "topic": args.topic,
        "top_k": args.top_k,
    }
    data = _request_json("POST", f"{_base_url(args.host, args.port)}/summarize", payload=payload)
    _pretty_print(data)


def _add_common_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default=DEFAULT_HOST, help="Demo server host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Demo server port")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.demo",
        description="Presentation-friendly demo commands for MindDock.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Run full local ingest for demo use")
    ingest_parser.add_argument(
        "--no-rebuild",
        dest="rebuild",
        action="store_false",
        help="Skip deleting the existing Chroma directory before ingest",
    )
    ingest_parser.set_defaults(func=cmd_ingest, rebuild=True)

    serve_parser = subparsers.add_parser("serve", help="Start the FastAPI demo server")
    _add_common_connection_args(serve_parser)
    serve_parser.set_defaults(func=cmd_serve)

    watch_parser = subparsers.add_parser("watch", help="Start watcher mode with demo-safe defaults")
    watch_parser.set_defaults(func=cmd_watch)

    root_parser = subparsers.add_parser("root", help="Call GET /")
    _add_common_connection_args(root_parser)
    root_parser.set_defaults(func=cmd_root)

    health_parser = subparsers.add_parser("health", help="Call GET /health")
    _add_common_connection_args(health_parser)
    health_parser.set_defaults(func=cmd_health)

    for name in ("search", "s"):
        search_parser = subparsers.add_parser(name, help="Call POST /search")
        _add_common_connection_args(search_parser)
        search_parser.add_argument("--query", default=DEFAULT_QUERY, help="Search query")
        search_parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Number of hits to request")
        search_parser.set_defaults(func=cmd_search)

    for name in ("chat", "c"):
        chat_parser = subparsers.add_parser(name, help="Call POST /chat")
        _add_common_connection_args(chat_parser)
        chat_parser.add_argument("--query", default=DEFAULT_QUERY, help="Chat query")
        chat_parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Number of hits to request")
        chat_parser.set_defaults(func=cmd_chat)

    for name in ("summarize", "sum"):
        summarize_parser = subparsers.add_parser(name, help="Call POST /summarize")
        _add_common_connection_args(summarize_parser)
        summarize_parser.add_argument("--topic", default=DEFAULT_TOPIC, help="Summary topic")
        summarize_parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Number of hits to request")
        summarize_parser.set_defaults(func=cmd_summarize)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
