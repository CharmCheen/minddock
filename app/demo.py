"""Thin demo command layer for presentation-friendly local workflows."""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib import error, request

from app.application import get_frontend_facade
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.evaluation import render_console_summary, run_evaluation_from_dataset
from app.services.service_models import (
    CatalogServiceResult,
    ChatServiceResult,
    CompareServiceResult,
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
    if metadata.workflow_trace is not None:
        payload["workflow_trace"] = metadata.workflow_trace
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


def _serialize_compare_result(result: CompareServiceResult) -> dict[str, Any]:
    return {
        "query": result.compare_result.query,
        "common_points": [point.to_api_dict() for point in result.compare_result.common_points],
        "differences": [point.to_api_dict() for point in result.compare_result.differences],
        "conflicts": [point.to_api_dict() for point in result.compare_result.conflicts],
        "support_status": result.compare_result.support_status.value,
        "refusal_reason": result.compare_result.refusal_reason.value if result.compare_result.refusal_reason else None,
        "citations": [item.to_api_dict() for item in result.citations],
        "retrieved_count": result.metadata.retrieved_count,
        "mode": result.metadata.mode or "grounded_compare",
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


def cmd_watch(args: argparse.Namespace) -> None:
    os.environ["WATCH_ENABLED"] = "true"
    from app.rag.watcher import run_watcher

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    mode = "sync-once" if args.once else "watch"
    dry_run = " dry-run" if args.dry_run else ""
    print(f"Starting {mode}{dry_run} in demo mode (WATCH_ENABLED=true)...")
    run_watcher(
        path=args.path,
        debounce_seconds=args.debounce,
        once=args.once,
        dry_run=args.dry_run,
    )


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
        if args.trace and "workflow_trace" in data:
            data["trace"] = data["workflow_trace"]
        _pretty_print(data)
        return

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    _setup_demo_logging()
    result = get_frontend_facade().chat.chat(query=args.query, top_k=args.top_k)
    data = _serialize_chat_result(result)
    if args.trace:
        data["trace"] = data["metadata"].get("workflow_trace")
    _pretty_print(data)


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


def cmd_compare(args: argparse.Namespace) -> None:
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    _setup_demo_logging()

    if args.filters:
        from app.rag.retrieval_models import RetrievalFilters
        sources = tuple(s.strip() for s in args.filters.split(",") if s.strip())
        filters = RetrievalFilters(sources=sources)
    else:
        filters = None

    if args.via_api:
        source_list = None
        if args.filters:
            source_list = [s.strip() for s in args.filters.split(",") if s.strip()]
        payload = {
            "task_type": "compare",
            "user_input": args.question,
            "top_k": args.top_k,
            "output_mode": "structured",
        }
        if source_list:
            payload["filters"] = {"source": source_list}
        data = _request_json("POST", f"{_base_url(args.host, args.port)}/frontend/execute", payload=payload)
        _pretty_print(data)
        return

    # Local mode: go through unified execution via execute_compare_request
    result = get_frontend_facade().execute_compare_request(
        question=args.question,
        top_k=args.top_k,
        filters=filters,
    )
    _pretty_print(_serialize_compare_result(result))


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


def _serialize_source_skill(skill) -> dict[str, Any]:
    return skill.to_dict()


def _serialize_source_handler(handler) -> dict[str, Any]:
    return handler.to_dict()


def cmd_skills(args: argparse.Namespace) -> None:
    from app.skills.source_registry import get_source_skill_registry

    registry = get_source_skill_registry()
    if args.local:
        skills = registry.list_local_skills()
    elif args.implemented:
        skills = registry.list_implemented_skills()
    else:
        skills = registry.list_skills(include_future=not args.no_future, include_local=not args.no_local)
    _pretty_print({"items": [_serialize_source_skill(skill) for skill in skills], "total": len(skills)})


def cmd_skill_detail(args: argparse.Namespace) -> None:
    from app.skills.source_registry import get_source_skill_registry

    skill = get_source_skill_registry().get_skill(args.id)
    if skill is None:
        print(f"Source skill not found: {args.id}", file=sys.stderr)
        raise SystemExit(1)
    _pretty_print(_serialize_source_skill(skill))


def cmd_skill_handlers(args: argparse.Namespace) -> None:
    from app.skills.handlers import list_trusted_source_handlers

    handlers = list_trusted_source_handlers()
    _pretty_print({"items": [_serialize_source_handler(handler) for handler in handlers], "total": len(handlers)})


def cmd_skill_handler_detail(args: argparse.Namespace) -> None:
    from app.skills.handlers import get_trusted_source_handler

    handler = get_trusted_source_handler(args.id)
    if handler is None:
        print(f"Trusted source handler not found: {args.id}", file=sys.stderr)
        raise SystemExit(1)
    _pretty_print(_serialize_source_handler(handler))


def cmd_skill_resolve(args: argparse.Namespace) -> None:
    from app.skills.source_binding import resolve_source_skill_binding_with_reason

    result = resolve_source_skill_binding_with_reason(args.source)
    payload: dict[str, Any] = {
        "source": args.source,
        "matched": result.binding is not None,
        "warning": result.warning,
        "reason": result.reason,
        "matches": list(result.matches),
        "binding": None,
    }
    if result.binding is not None:
        payload["binding"] = {
            "skill_id": result.binding.skill_id,
            "skill_name": result.binding.skill_name,
            "skill_version": result.binding.skill_version,
            "skill_origin": result.binding.skill_origin,
            "handler": result.binding.handler,
            "input_kinds": list(result.binding.input_kinds),
            "config_keys": sorted(result.binding.config),
        }
    _pretty_print(payload)


def cmd_skill_validate(args: argparse.Namespace) -> None:
    from app.skills.manifest import SkillManifestError, load_manifest_file
    from app.skills.source_registry import get_source_skill_registry

    try:
        manifest = load_manifest_file(Path(args.manifest))
    except SkillManifestError as exc:
        _pretty_print({"ok": False, "errors": [str(exc)], "warnings": [], "executable": False})
        raise SystemExit(1) from exc
    result = get_source_skill_registry().validate_manifest(manifest)
    _pretty_print(result.to_dict())
    if not result.ok:
        raise SystemExit(1)


def cmd_skill_register(args: argparse.Namespace) -> None:
    from app.skills.manifest import SkillManifestError, load_manifest_file
    from app.skills.source_registry import get_source_skill_registry

    try:
        manifest = load_manifest_file(Path(args.manifest))
    except SkillManifestError as exc:
        _pretty_print({"ok": False, "errors": [str(exc)], "warnings": [], "executable": False})
        raise SystemExit(1) from exc
    result = get_source_skill_registry().register_manifest(manifest)
    _pretty_print(result.to_dict())
    if not result.ok:
        raise SystemExit(1)


def cmd_skill_enable(args: argparse.Namespace) -> None:
    from app.skills.source_registry import get_source_skill_registry

    result = get_source_skill_registry().enable_skill(args.id)
    _pretty_print(result.to_dict())
    if not result.ok:
        raise SystemExit(1)


def cmd_skill_disable(args: argparse.Namespace) -> None:
    from app.skills.source_registry import get_source_skill_registry

    result = get_source_skill_registry().disable_skill(args.id)
    _pretty_print(result.to_dict())
    if not result.ok:
        raise SystemExit(1)


def _check_chroma_available() -> None:
    """Raise a clear error if langchain-chroma is not installed.

    This is the benchmark entry-layer preflight for both:
        python -m app.demo evaluate
        python scripts/evaluate_rag.py
    """
    from app.rag.vectorstore import get_vectorstore

    try:
        get_vectorstore()
    except RuntimeError as exc:
        raise ValueError(
            f"langchain-chroma is required for benchmark evaluation: {exc}"
        ) from exc


def cmd_evaluate(args: argparse.Namespace) -> None:
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    _setup_demo_logging()
    _check_chroma_available()
    result = run_evaluation_from_dataset(
        dataset_path=Path(args.dataset),
        output_dir=Path(args.output_dir),
        task_types=tuple(args.task_type),
    )
    print(
        render_console_summary(
            result.report,
            json_path=result.json_path,
            markdown_path=result.markdown_path,
        )
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
    watch_parser.add_argument("--once", action="store_true", help="Run one directory sync and exit")
    watch_parser.add_argument("--dry-run", action="store_true", help="Preview sync changes without writing Chroma or HashStore")
    watch_parser.add_argument("--path", default=None, help="Knowledge base directory to watch")
    watch_parser.add_argument("--debounce", type=float, default=None, help="Debounce seconds for filesystem events")
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

    skills_parser = subparsers.add_parser("skills", help="List source skill catalog entries")
    skills_parser.add_argument("--implemented", action="store_true", help="Only list enabled implemented/local source skills")
    skills_parser.add_argument("--local", action="store_true", help="Only list local source skill manifests")
    skills_parser.add_argument("--no-future", action="store_true", help="Exclude future source skills")
    skills_parser.add_argument("--no-local", action="store_true", help="Exclude local source skill manifests")
    skills_parser.set_defaults(func=cmd_skills)

    skill_detail_parser = subparsers.add_parser("skill-detail", help="Show one source skill catalog entry")
    skill_detail_parser.add_argument("--id", required=True, help="Source skill id, e.g. csv.extract")
    skill_detail_parser.set_defaults(func=cmd_skill_detail)

    skill_handlers_parser = subparsers.add_parser("skill-handlers", help="List trusted source handler contracts")
    skill_handlers_parser.set_defaults(func=cmd_skill_handlers)

    skill_handler_detail_parser = subparsers.add_parser("skill-handler-detail", help="Show one trusted source handler contract")
    skill_handler_detail_parser.add_argument("--id", required=True, help="Trusted handler id, e.g. csv.extract")
    skill_handler_detail_parser.set_defaults(func=cmd_skill_handler_detail)

    skill_resolve_parser = subparsers.add_parser("skill-resolve", help="Resolve a source path or URL to a local source skill binding")
    skill_resolve_parser.add_argument("--source", required=True, help="Source path or URL to resolve")
    skill_resolve_parser.set_defaults(func=cmd_skill_resolve)

    skill_validate_parser = subparsers.add_parser("skill-validate", help="Validate a local source skill JSON manifest")
    skill_validate_parser.add_argument("--manifest", required=True, help="Path to skill.json")
    skill_validate_parser.set_defaults(func=cmd_skill_validate)

    skill_register_parser = subparsers.add_parser("skill-register", help="Register a local source skill JSON manifest")
    skill_register_parser.add_argument("--manifest", required=True, help="Path to skill.json")
    skill_register_parser.set_defaults(func=cmd_skill_register)

    skill_disable_parser = subparsers.add_parser("skill-disable", help="Disable a local source skill")
    skill_disable_parser.add_argument("--id", required=True, help="Local source skill id")
    skill_disable_parser.set_defaults(func=cmd_skill_disable)

    skill_enable_parser = subparsers.add_parser("skill-enable", help="Enable a local source skill")
    skill_enable_parser.add_argument("--id", required=True, help="Local source skill id")
    skill_enable_parser.set_defaults(func=cmd_skill_enable)

    evaluate_parser = subparsers.add_parser("evaluate", help="Run the local benchmark evaluation workflow")
    evaluate_parser.add_argument(
        "--dataset",
        default="eval/benchmark/sample_eval_set.jsonl",
        help="JSONL benchmark dataset path",
    )
    evaluate_parser.add_argument(
        "--output-dir",
        default="data/eval",
        help="Directory where JSON and Markdown reports will be written",
    )
    evaluate_parser.add_argument(
        "--task-type",
        action="append",
        default=[],
        choices=["search", "chat", "compare"],
        help="Optional task-type filter. Can be passed multiple times.",
    )
    evaluate_parser.set_defaults(func=cmd_evaluate)

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
        chat_parser.add_argument("--trace", action="store_true", help="Print safe workflow trace metadata for the chat pipeline")
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

    for name in ("compare", "cmp"):
        compare_parser = subparsers.add_parser(
            name,
            help="Run compare locally; with --via-api, call POST /frontend/execute (task_type=compare)",
        )
        _add_demo_transport_args(compare_parser)
        compare_parser.add_argument("--question", default="Compare the storage approaches across documents", help="Compare question")
        compare_parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Number of hits to request")
        compare_parser.add_argument(
            "--filters",
            default=None,
            help="Comma-separated source names to compare (e.g. doc_a.md,doc_b.md)",
        )
        compare_parser.set_defaults(func=cmd_compare)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


def run_cli_with_benchmark_error_handling(fn, argv: list[str] | None = None) -> int:
    """Call fn(argv) and translate a benchmark ValueError into a short stderr message + SystemExit(1).
    On success fn returns normally and we return 0.

    Both app.demo and scripts/evaluate_rag.py use this to share the same
    error-translation pattern without sharing a main function.
    """
    try:
        fn(argv)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    return 0


def _run_demo_cli(argv: list[str] | None = None) -> int:
    """CLI entry for app.demo. Returns 0 on success; raises SystemExit(1) on preflight error."""
    return run_cli_with_benchmark_error_handling(main, argv)


if __name__ == "__main__":
    try:
        _run_demo_cli()
    except SystemExit as exc:
        sys.exit(exc.code)
