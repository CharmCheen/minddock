"""Thin demo command layer for presentation-friendly local workflows."""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from typing import Any
from urllib.parse import quote
from urllib import error, request

from app.application import get_frontend_facade
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.services.service_models import (
    CatalogServiceResult,
    ChatServiceResult,
    DeleteSourceServiceResult,
    IngestServiceResult,
    ReingestSourceServiceResult,
    SearchServiceResult,
    SourceDetailServiceResult,
    SourceInspectServiceResult,
    SummarizeServiceResult,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_QUERY = "MindDock stores document chunks and metadata in a local Chroma database"
DEFAULT_TOPIC = "MindDock stores document chunks and metadata in a local Chroma database"
DEFAULT_TOP_K = 3


def _base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _pretty_print(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _metadata_to_dict(metadata) -> dict[str, Any]:
    issues = [
        {
            "code": issue.code,
            "message": issue.message,
            "severity": issue.severity,
            "source": issue.source,
        }
        for issue in metadata.issues
    ]
    timing = {
        "total_ms": metadata.timing.total_ms,
        "retrieval_ms": metadata.timing.retrieval_ms,
        "rerank_ms": metadata.timing.rerank_ms,
        "compress_ms": metadata.timing.compress_ms,
        "generation_ms": metadata.timing.generation_ms,
    }
    payload: dict[str, Any] = {
        "retrieved_count": metadata.retrieved_count,
        "mode": metadata.mode,
        "output_format": metadata.output_format,
        "partial_failure": metadata.partial_failure,
        "insufficient_evidence": metadata.insufficient_evidence,
        "empty_result": metadata.empty_result,
        "warnings": list(metadata.warnings),
        "issues": issues,
        "timing": timing,
        "runtime_mode": metadata.runtime_mode,
        "provider_mode": metadata.provider_mode,
        "filter_applied": metadata.filter_applied,
        "debug_notes": list(metadata.debug_notes),
    }
    if metadata.source_stats is not None:
        payload["source_stats"] = {
            "requested_sources": metadata.source_stats.requested_sources,
            "succeeded_sources": metadata.source_stats.succeeded_sources,
            "failed_sources": metadata.source_stats.failed_sources,
        }
    if metadata.retrieval_stats is not None:
        payload["retrieval_stats"] = {
            "retrieved_hits": metadata.retrieval_stats.retrieved_hits,
            "grounded_hits": metadata.retrieval_stats.grounded_hits,
            "reranked_hits": metadata.retrieval_stats.reranked_hits,
            "returned_hits": metadata.retrieval_stats.returned_hits,
        }
    return payload


def _serialize_search_result(result: SearchServiceResult) -> dict[str, Any]:
    return {
        "query": result.query,
        "top_k": result.top_k,
        "hits": [
            {
                "text": hit.chunk.text,
                "doc_id": hit.chunk.doc_id,
                "chunk_id": hit.chunk.chunk_id,
                "source": hit.chunk.source,
                "source_type": hit.chunk.source_type,
                "title": hit.chunk.title or None,
                "section": hit.chunk.section or None,
                "distance": hit.chunk.distance,
                "citation": hit.citation.to_api_dict(),
            }
            for hit in result.hits
        ],
        "metadata": _metadata_to_dict(result.metadata),
    }


def _serialize_chat_result(result: ChatServiceResult) -> dict[str, Any]:
    return {
        "answer": result.answer,
        "citations": [item.to_api_dict() for item in result.citations],
        "retrieved_count": result.metadata.retrieved_count,
        "mode": result.metadata.mode or "grounded",
        "metadata": _metadata_to_dict(result.metadata),
    }


def _serialize_summarize_result(result: SummarizeServiceResult) -> dict[str, Any]:
    return {
        "summary": result.summary,
        "citations": [item.to_api_dict() for item in result.citations],
        "retrieved_count": result.metadata.retrieved_count,
        "mode": result.metadata.mode or "basic",
        "output_format": result.metadata.output_format or "text",
        "structured_output": result.structured_output,
        "metadata": _metadata_to_dict(result.metadata),
    }


def _serialize_ingest_result(result: IngestServiceResult) -> dict[str, Any]:
    return {
        "documents": result.documents,
        "chunks": result.chunks,
        "ingested_sources": result.ingested_sources,
        "failed_sources": [item.to_api_dict() for item in result.failed_sources],
        "partial_failure": result.metadata.partial_failure,
        "metadata": _metadata_to_dict(result.metadata),
    }


def _serialize_catalog_result(result: CatalogServiceResult) -> dict[str, Any]:
    return {
        "items": [
            {
                "doc_id": item.doc_id,
                "source": item.source,
                "source_type": item.source_type,
                "title": item.title,
                "chunk_count": item.chunk_count,
                "sections": list(item.sections),
                "pages": list(item.pages),
                "requested_url": item.requested_url,
                "final_url": item.final_url,
            }
            for item in result.entries
        ],
        "total": len(result.entries),
        "metadata": _metadata_to_dict(result.metadata),
    }


def _serialize_source_detail_result(result: SourceDetailServiceResult) -> dict[str, Any]:
    if not result.found or result.detail is None:
        return {"found": False, "metadata": _metadata_to_dict(result.metadata)}
    entry = result.detail.entry
    payload = {
        "found": True,
        "item": {
            "doc_id": entry.doc_id,
            "source": entry.source,
            "source_type": entry.source_type,
            "title": entry.title,
            "chunk_count": entry.chunk_count,
            "sections": list(entry.sections),
            "pages": list(entry.pages),
            "requested_url": entry.requested_url,
            "final_url": entry.final_url,
        },
        "representative_metadata": result.detail.representative_metadata,
        "metadata": _metadata_to_dict(result.metadata),
    }
    if result.include_admin_metadata:
        payload["admin_metadata"] = result.admin_metadata
    return payload


def _serialize_source_inspect_result(result: SourceInspectServiceResult) -> dict[str, Any]:
    if not result.found or result.inspect is None:
        return {"found": False, "metadata": _metadata_to_dict(result.metadata)}
    entry = result.inspect.detail.entry
    payload = {
        "found": True,
        "item": {
            "doc_id": entry.doc_id,
            "source": entry.source,
            "source_type": entry.source_type,
            "title": entry.title,
            "chunk_count": entry.chunk_count,
            "sections": list(entry.sections),
            "pages": list(entry.pages),
            "requested_url": entry.requested_url,
            "final_url": entry.final_url,
        },
        "total_chunks": result.inspect.chunk_page.total_chunks,
        "returned_chunks": result.inspect.chunk_page.returned_chunks,
        "limit": result.inspect.chunk_page.limit,
        "offset": result.inspect.chunk_page.offset,
        "chunks": [
            {
                "chunk_id": item.chunk_id,
                "chunk_index": item.chunk_index,
                "preview_text": item.preview_text,
                "title": item.title,
                "section": item.section,
                "location": item.location,
                "ref": item.ref,
                "page": item.page,
                "anchor": item.anchor,
                "admin_metadata": item.admin_metadata,
            }
            for item in result.inspect.chunk_page.chunks
        ],
        "representative_metadata": result.inspect.detail.representative_metadata,
        "metadata": _metadata_to_dict(result.metadata),
    }
    if result.inspect.include_admin_metadata:
        payload["admin_metadata"] = result.inspect.admin_metadata
    return payload


def _serialize_delete_source_result(result: DeleteSourceServiceResult) -> dict[str, Any]:
    return {
        "found": result.result.found,
        "doc_id": result.result.doc_id,
        "source": result.result.source,
        "source_type": result.result.source_type,
        "deleted_chunks": result.result.deleted_chunks,
        "metadata": _metadata_to_dict(result.metadata),
    }


def _serialize_reingest_source_result(result: ReingestSourceServiceResult) -> dict[str, Any]:
    payload = {
        "found": result.found,
        "metadata": _metadata_to_dict(result.metadata),
    }
    if result.source_result is None:
        return payload
    payload.update(
        {
            "ok": result.source_result.ok,
            "doc_id": result.source_result.descriptor.doc_id,
            "source": result.source_result.descriptor.source,
            "source_type": result.source_result.descriptor.source_type,
            "chunks_upserted": result.source_result.chunks_upserted,
            "chunks_deleted": result.source_result.chunks_deleted,
            "failure": result.source_result.failure.to_api_dict() if result.source_result.failure is not None else None,
        }
    )
    return payload


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
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    _setup_demo_logging()
    print(f"Running local ingest (rebuild={args.rebuild}, urls={len(args.urls)})...")
    result = get_frontend_facade().knowledge_base.ingest(rebuild=args.rebuild, urls=args.urls)
    _pretty_print(_serialize_ingest_result(result))


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
    if args.via_api:
        payload = {
            "query": args.query,
            "top_k": args.top_k,
        }
        data = _request_json("POST", f"{_base_url(args.host, args.port)}/search", payload=payload)
        _pretty_print(data)
        return

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    _setup_demo_logging()
    result = get_frontend_facade().chat.search(query=args.query, top_k=args.top_k)
    _pretty_print(_serialize_search_result(result))


def cmd_chat(args: argparse.Namespace) -> None:
    if args.via_api:
        payload = {
            "query": args.query,
            "top_k": args.top_k,
        }
        data = _request_json("POST", f"{_base_url(args.host, args.port)}/chat", payload=payload)
        _pretty_print(data)
        return

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    _setup_demo_logging()
    result = get_frontend_facade().chat.chat(query=args.query, top_k=args.top_k)
    _pretty_print(_serialize_chat_result(result))


def cmd_summarize(args: argparse.Namespace) -> None:
    if args.via_api:
        payload = {
            "topic": args.topic,
            "top_k": args.top_k,
            "mode": args.mode,
            "output_format": args.output_format,
        }
        data = _request_json("POST", f"{_base_url(args.host, args.port)}/summarize", payload=payload)
        _pretty_print(data)
        return

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    _setup_demo_logging()
    result = get_frontend_facade().chat.summarize(
        topic=args.topic,
        top_k=args.top_k,
        mode=args.mode,
        output_format=args.output_format,
    )
    _pretty_print(_serialize_summarize_result(result))


def cmd_sources(args: argparse.Namespace) -> None:
    if args.via_api:
        url = f"{_base_url(args.host, args.port)}/sources"
        if args.source_type:
            url = f"{url}?source_type={args.source_type}"
        _pretty_print(_request_json("GET", url))
        return

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    _setup_demo_logging()
    result = get_frontend_facade().knowledge_base.list_sources(source_type=args.source_type)
    _pretty_print(_serialize_catalog_result(result))


def cmd_source_detail(args: argparse.Namespace) -> None:
    if args.via_api:
        if args.doc_id:
            url = f"{_base_url(args.host, args.port)}/sources/{args.doc_id}"
        else:
            url = f"{_base_url(args.host, args.port)}/sources/by-source?source={quote(args.source, safe='')}"
        if args.include_admin_metadata:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}include_admin_metadata=true"
        _pretty_print(_request_json("GET", url))
        return

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    _setup_demo_logging()
    result = get_frontend_facade().knowledge_base.get_source_detail(
        doc_id=args.doc_id,
        source=args.source,
        include_admin_metadata=args.include_admin_metadata,
    )
    _pretty_print(_serialize_source_detail_result(result))


def cmd_source_chunks(args: argparse.Namespace) -> None:
    if args.via_api:
        if args.doc_id:
            url = f"{_base_url(args.host, args.port)}/sources/{args.doc_id}/chunks"
        else:
            url = f"{_base_url(args.host, args.port)}/sources/by-source/chunks?source={quote(args.source, safe='')}"
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}limit={args.limit}&offset={args.offset}"
        if args.include_admin_metadata:
            url = f"{url}&include_admin_metadata=true"
        _pretty_print(_request_json("GET", url))
        return

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    _setup_demo_logging()
    result = get_frontend_facade().knowledge_base.inspect_source(
        doc_id=args.doc_id,
        source=args.source,
        limit=args.limit,
        offset=args.offset,
        include_admin_metadata=args.include_admin_metadata,
    )
    _pretty_print(_serialize_source_inspect_result(result))


def cmd_source_delete(args: argparse.Namespace) -> None:
    if args.via_api:
        if args.doc_id:
            url = f"{_base_url(args.host, args.port)}/sources/{args.doc_id}"
        else:
            url = f"{_base_url(args.host, args.port)}/sources/by-source?source={quote(args.source, safe='')}"
        _pretty_print(_request_json("DELETE", url))
        return

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    _setup_demo_logging()
    result = get_frontend_facade().knowledge_base.delete_source(doc_id=args.doc_id, source=args.source)
    _pretty_print(_serialize_delete_source_result(result))


def cmd_source_reingest(args: argparse.Namespace) -> None:
    if args.via_api:
        if args.doc_id:
            url = f"{_base_url(args.host, args.port)}/sources/{args.doc_id}/reingest"
        else:
            url = f"{_base_url(args.host, args.port)}/sources/by-source/reingest?source={quote(args.source, safe='')}"
        _pretty_print(_request_json("POST", url, payload={}))
        return

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    _setup_demo_logging()
    result = get_frontend_facade().knowledge_base.reingest_source(doc_id=args.doc_id, source=args.source)
    _pretty_print(_serialize_reingest_source_result(result))


def cmd_skill_run(args: argparse.Namespace) -> None:
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    _setup_demo_logging()
    result = get_frontend_facade().skills.execute_skill(
        name=args.name,
        arguments={"text": args.text},
        debug=args.debug,
    )
    _pretty_print(
        {
            "name": result.name,
            "ok": result.ok,
            "output": result.output,
            "message": result.message,
        }
    )


def _add_common_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default=DEFAULT_HOST, help="Demo server host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Demo server port")


def _add_demo_transport_args(parser: argparse.ArgumentParser) -> None:
    _add_common_connection_args(parser)
    parser.add_argument(
        "--via-api",
        action="store_true",
        help="Call the HTTP API instead of invoking services directly.",
    )


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
    ingest_parser.add_argument(
        "--url",
        dest="urls",
        action="append",
        default=[],
        help="Additional HTTP/HTTPS URL to fetch and ingest. Can be passed multiple times.",
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

    sources_parser = subparsers.add_parser("sources", help="List indexed sources")
    _add_demo_transport_args(sources_parser)
    sources_parser.add_argument("--source-type", choices=["file", "url"], default=None, help="Optional source-type filter")
    sources_parser.set_defaults(func=cmd_sources)

    detail_parser = subparsers.add_parser("source-detail", help="Show source detail by doc id or source")
    _add_demo_transport_args(detail_parser)
    detail_group = detail_parser.add_mutually_exclusive_group(required=True)
    detail_group.add_argument("--doc-id", help="Indexed source doc id")
    detail_group.add_argument("--source", help="Exact source identifier")
    detail_parser.add_argument(
        "--include-admin-metadata",
        action="store_true",
        help="Include a controlled admin/debug metadata block in the detail view.",
    )
    detail_parser.set_defaults(func=cmd_source_detail)

    chunks_parser = subparsers.add_parser("source-chunks", help="Show paginated chunk previews by doc id or source")
    _add_demo_transport_args(chunks_parser)
    chunks_group = chunks_parser.add_mutually_exclusive_group(required=True)
    chunks_group.add_argument("--doc-id", help="Indexed source doc id")
    chunks_group.add_argument("--source", help="Exact source identifier")
    chunks_parser.add_argument("--limit", type=int, default=10, help="Maximum number of chunk previews to return")
    chunks_parser.add_argument("--offset", type=int, default=0, help="Number of chunks to skip before previewing")
    chunks_parser.add_argument(
        "--include-admin-metadata",
        action="store_true",
        help="Include controlled admin/debug metadata for the source and each chunk preview.",
    )
    chunks_parser.set_defaults(func=cmd_source_chunks)

    skill_parser = subparsers.add_parser("skill-run", help="Run a registered example skill through the application facade")
    skill_parser.add_argument("--name", default="echo", help="Registered skill name")
    skill_parser.add_argument("--text", default="hello", help="Text payload for the skill")
    skill_parser.add_argument("--debug", action="store_true", help="Enable debug mode for skill execution")
    skill_parser.set_defaults(func=cmd_skill_run)

    delete_parser = subparsers.add_parser("source-delete", help="Delete source by doc id or source")
    _add_demo_transport_args(delete_parser)
    delete_group = delete_parser.add_mutually_exclusive_group(required=True)
    delete_group.add_argument("--doc-id", help="Indexed source doc id")
    delete_group.add_argument("--source", help="Exact source identifier")
    delete_parser.set_defaults(func=cmd_source_delete)

    reingest_parser = subparsers.add_parser("source-reingest", help="Reingest source by doc id or source")
    _add_demo_transport_args(reingest_parser)
    reingest_group = reingest_parser.add_mutually_exclusive_group(required=True)
    reingest_group.add_argument("--doc-id", help="Indexed source doc id")
    reingest_group.add_argument("--source", help="Exact source identifier")
    reingest_parser.set_defaults(func=cmd_source_reingest)

    for name in ("search", "s"):
        search_parser = subparsers.add_parser(name, help="Call POST /search")
        _add_demo_transport_args(search_parser)
        search_parser.add_argument("--query", default=DEFAULT_QUERY, help="Search query")
        search_parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Number of hits to request")
        search_parser.set_defaults(func=cmd_search)

    for name in ("chat", "c"):
        chat_parser = subparsers.add_parser(name, help="Call POST /chat")
        _add_demo_transport_args(chat_parser)
        chat_parser.add_argument("--query", default=DEFAULT_QUERY, help="Chat query")
        chat_parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Number of hits to request")
        chat_parser.set_defaults(func=cmd_chat)

    for name in ("summarize", "sum"):
        summarize_parser = subparsers.add_parser(name, help="Call POST /summarize")
        _add_demo_transport_args(summarize_parser)
        summarize_parser.add_argument("--topic", default=DEFAULT_TOPIC, help="Summary topic")
        summarize_parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Number of hits to request")
        summarize_parser.add_argument("--mode", default="basic", choices=["basic", "map_reduce"], help="Summary mode")
        summarize_parser.add_argument(
            "--output-format",
            default="text",
            choices=["text", "mermaid"],
            help="Optional structured output format",
        )
        summarize_parser.set_defaults(func=cmd_summarize)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
