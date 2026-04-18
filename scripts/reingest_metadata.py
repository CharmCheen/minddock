# -*- coding: utf-8 -*-
"""Safe re-ingest migration script for adding new metadata fields (section_path, semantic_type)
to existing Chroma chunks without losing data.

Usage:
    # Backup first (always)
    python scripts/reingest_metadata.py --backup

    # Dry-run: see what would be rebuilt without writing anything
    python scripts/reingest_metadata.py --dry-run
    python scripts/reingest_metadata.py --dry-run --doc-id <id>
    python scripts/reingest_metadata.py --dry-run --source "knowledge_base/some.pdf"

    # Rebuild specific document(s)
    python scripts/reingest_metadata.py --doc-id <id>
    python scripts/reingest_metadata.py --source "knowledge_base/05_crad.pdf"

    # Rebuild all documents
    python scripts/reingest_metadata.py --all

    # Verify rebuilt chunks have the new fields
    python scripts/reingest_metadata.py --verify
    python scripts/reingest_metadata.py --verify --doc-id <id>
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure the app package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.rag.embeddings import get_embedding_backend
from app.rag.ingest import build_langchain_documents, iter_file_descriptors
from app.rag.vectorstore import delete_document, get_vectorstore, replace_document


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chroma_dir() -> Path:
    return Path(get_settings().chroma_dir)


def _kb_dir() -> Path:
    return Path(get_settings().kb_dir)


def _backup_dir() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _chroma_dir().parent / f"chroma_backup_{ts}"


def _list_all_doc_ids(vs) -> list[str]:
    """Return all distinct doc_ids in the Chroma store."""
    details = vs.list_source_details()
    return [d.entry.doc_id for d in details]


def _get_chroma_chunk_count(vs, doc_id: str) -> int:
    """Return number of chunks for a doc_id in Chroma."""
    result = vs._store.get(where={"doc_id": doc_id}, include=["metadatas"])
    return len(result.get("metadatas") or [])


def _check_metadata_fields(vs, doc_id: str) -> dict[str, object]:
    """Check whether chunks for a doc_id have the new metadata fields."""
    result = vs._store.get(where={"doc_id": doc_id}, include=["metadatas"])
    metas = result.get("metadatas") or []
    if not metas:
        return {"status": "not_found", "count": 0}

    has_section_path = sum(1 for m in metas if m.get("section_path"))
    has_semantic_type = sum(1 for m in metas if m.get("semantic_type"))
    total = len(metas)
    return {
        "status": "ok" if (has_section_path == total and has_semantic_type == total) else "stale",
        "count": total,
        "has_section_path": has_section_path,
        "has_semantic_type": has_semantic_type,
        "complete": has_section_path == total and has_semantic_type == total,
    }


def _iter_matching_descriptors(
    doc_id: str | None = None,
    source: str | None = None,
) -> list[tuple[Path, str]]:
    """Yield (file_path, doc_id) for matching documents.

    If doc_id is given, finds the file with that doc_id.
    If source is given, finds the file matching that source path.
    If both None, yields all file descriptors.
    """
    kb = _kb_dir()
    if not kb.exists():
        return []

    if doc_id is not None:
        # Scan all descriptors to find the one with matching doc_id
        for descriptor in iter_file_descriptors(kb):
            if descriptor.doc_id == doc_id and descriptor.local_path:
                return [(Path(descriptor.local_path), descriptor.doc_id)]
        return []

    if source is not None:
        # Find by source path
        source_path = Path(source)
        if not source_path.is_absolute():
            source_path = kb / source_path
        if source_path.exists():
            from app.rag.ingest import build_file_descriptor
            descriptor = build_file_descriptor(source_path, kb)
            return [(source_path, descriptor.doc_id)]
        return []

    # All files
    results = []
    for descriptor in iter_file_descriptors(kb):
        if descriptor.local_path:
            results.append((Path(descriptor.local_path), descriptor.doc_id))
    return results


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def do_backup() -> Path:
    """Backup current Chroma directory to a timestamped sibling."""
    src = _chroma_dir()
    dst = _backup_dir()
    if not src.exists():
        print(f"[backup] Chroma dir does not exist: {src}")
        return dst
    print(f"[backup] Copying {src} → {dst}")
    shutil.copytree(src, dst, dirs_exist_ok=False)
    print(f"[backup] Done: {dst}")
    return dst


def do_dry_run(
    doc_id: str | None = None,
    source: str | None = None,
    all_docs: bool = False,
) -> None:
    """Report what would be rebuilt without writing anything."""
    vs = get_vectorstore()
    embedder = get_embedding_backend(get_settings().embedding_model)

    if all_docs:
        matches = _iter_matching_descriptors()
    else:
        matches = _iter_matching_descriptors(doc_id=doc_id, source=source)

    if not matches:
        print("[dry-run] No matching documents found.")
        return

    print(f"[dry-run] Would rebuild {len(matches)} document(s):\n")
    for file_path, did in matches:
        meta_info = _check_metadata_fields(vs, did)
        new_docs = build_langchain_documents(file_path, _kb_dir())
        new_chunk_count = len(new_docs)
        existing_count = meta_info.get("count", 0)
        status = "COMPLETE" if meta_info.get("complete") else "STALE"
        print(f"  doc_id={did}")
        print(f"    file:    {file_path}")
        print(f"    status:  {status}")
        print(f"    existing_chunks: {existing_count}")
        print(f"    new_chunks:     {new_chunk_count}")
        if not meta_info.get("complete"):
            missing_sp = existing_count - meta_info.get("has_section_path", 0)
            missing_st = existing_count - meta_info.get("has_semantic_type", 0)
            print(f"    missing section_path: {missing_sp}/{existing_count}")
            print(f"    missing semantic_type: {missing_st}/{existing_count}")
        print()


def do_rebuild(
    doc_id: str | None = None,
    source: str | None = None,
    all_docs: bool = False,
) -> list[dict]:
    """Rebuild document(s) with fresh embeddings and new metadata fields.

    Returns a list of per-document result dicts.
    """
    vs = get_vectorstore()
    embedder = get_embedding_backend(get_settings().embedding_model)

    if all_docs:
        matches = _iter_matching_descriptors()
    else:
        matches = _iter_matching_descriptors(doc_id=doc_id, source=source)

    if not matches:
        print("[rebuild] No matching documents found.")
        return []

    results = []
    for file_path, did in matches:
        print(f"[rebuild] Processing doc_id={did}  file={file_path.name}")
        existing_count = _get_chroma_chunk_count(vs, did)
        print(f"  existing chunks: {existing_count}")

        # Build new Document objects (with new metadata)
        new_docs = build_langchain_documents(file_path, _kb_dir())
        if not new_docs:
            print(f"  WARNING: no chunks generated, skipping")
            results.append({"doc_id": did, "status": "empty", "upserted": 0})
            continue

        # Compute fresh embeddings
        texts = [doc.page_content for doc in new_docs]
        embeddings = embedder.embed_texts(texts)

        # Replace in Chroma atomically (delete old + upsert new)
        ids = [doc.metadata["chunk_id"] for doc in new_docs]
        metadatas = [{k: str(v) for k, v in doc.metadata.items()} for doc in new_docs]

        result = replace_document(
            doc_id=did,
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings,
        )

        print(f"  deleted: {result.deleted}  upserted: {result.upserted}")
        results.append({
            "doc_id": did,
            "status": "ok",
            "deleted": result.deleted,
            "upserted": result.upserted,
        })

    return results


def do_verify(
    doc_id: str | None = None,
    source: str | None = None,
    all_docs: bool = False,
) -> None:
    """Verify that rebuilt chunks have section_path and semantic_type in Chroma."""
    vs = get_vectorstore()

    if all_docs:
        matches = _iter_matching_descriptors()
    elif doc_id or source:
        matches = _iter_matching_descriptors(doc_id=doc_id, source=source)
    else:
        # Verify all
        all_ids = _list_all_doc_ids(vs)
        print(f"[verify] Checking {len(all_ids)} document(s) in Chroma:\n")
        stale = []
        complete = []
        for did in all_ids:
            meta = _check_metadata_fields(vs, did)
            if meta.get("complete"):
                complete.append(did)
            else:
                stale.append((did, meta))
        print(f"  COMPLETE (section_path + semantic_type present): {len(complete)}")
        print(f"  STALE (missing fields):                          {len(stale)}")
        if stale:
            print("\n  Stale documents:")
            for did, meta in stale[:10]:
                print(f"    {did}: {meta['has_section_path']}/{meta['count']} sp, {meta['has_semantic_type']}/{meta['count']} st")
            if len(stale) > 10:
                print(f"    ... and {len(stale) - 10} more")
        return

    if not matches:
        print("[verify] No matching documents found.")
        return

    print(f"[verify] Checking {len(matches)} document(s):\n")
    for file_path, did in matches:
        meta = _check_metadata_fields(vs, did)
        status = "COMPLETE" if meta.get("complete") else "STALE"
        print(f"  doc_id={did}  status={status}")
        print(f"    chunks:        {meta.get('count', 0)}")
        print(f"    section_path:  {meta.get('has_section_path', 0)}/{meta.get('count', 0)}")
        print(f"    semantic_type:  {meta.get('has_semantic_type', 0)}/{meta.get('count', 0)}")

        # Show a sample chunk metadata
        result = vs._store.get(where={"doc_id": did}, limit=1, include=["metadatas", "documents"])
        metas = result.get("metadatas") or []
        if metas:
            m = metas[0]
            print(f"    sample: section_path={m.get('section_path')!r}  semantic_type={m.get('semantic_type')!r}  block_type={m.get('block_type')!r}")
        print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safe re-ingest migration: adds section_path and semantic_type to Chroma chunks.",
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--backup", action="store_true", help="Backup Chroma directory before any rebuild")
    group.add_argument("--dry-run", action="store_true", help="Show what would be rebuilt without writing")
    group.add_argument("--verify", action="store_true", help="Verify metadata fields in rebuilt chunks")

    parser.add_argument("--doc-id", type=str, default=None, help="Rebuild/verify specific document by doc_id")
    parser.add_argument("--source", type=str, default=None, help="Rebuild/verify by source path (relative to kb_dir or absolute)")
    parser.add_argument("--all", action="store_true", help="Rebuild/verify all documents")

    args = parser.parse_args()

    # Always print settings info
    print(f"Chroma dir: {_chroma_dir()}")
    print(f"Knowledge base: {_kb_dir()}")
    print()

    if args.backup:
        do_backup()
        return

    if args.verify:
        do_verify(doc_id=args.doc_id, source=args.source, all_docs=args.all)
        return

    if args.dry_run:
        do_dry_run(doc_id=args.doc_id, source=args.source, all_docs=args.all)
        return

    # Default: rebuild
    if not (args.doc_id or args.source or args.all):
        print("No --doc-id, --source, or --all specified. Nothing to do.")
        print("Use --dry-run to preview, --backup to create a backup first.")
        print("Use --help for full usage.")
        return

    print("WARNING: Rebuild will modify the Chroma store. Use --dry-run first to preview.")
    print("   If this is the first rebuild, run with --backup first.\n")
    results = do_rebuild(doc_id=args.doc_id, source=args.source, all_docs=args.all)
    print(f"\nRebuild complete: {len(results)} document(s) processed.")


if __name__ == "__main__":
    main()
