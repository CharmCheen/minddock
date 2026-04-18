# -*- coding: utf-8 -*-
"""
scripts/eval_chunking.py

v3: Enhanced comparison of page-mode vs structured vs structured+rerank PDF chunking.
Supports 4 modes: Page-Mode, Structured, Structured+Simple, Structured+HeuristicV2.

Usage:
    # Full 4-mode report with HeuristicV2 rerank
    python scripts/eval_chunking.py \
        --pdf knowledge_base/05_crad_10.7544_issn1000-1239.202110867.pdf \
        --cases eval/eval_cases_v2.json \
        --rerank heuristic_v2

    # Single mode (no rerank)
    python scripts/eval_chunking.py --pdf <path> --rerank none

    # With simple keyword rerank only
    python scripts/eval_chunking.py --pdf <path> --rerank simple

    # Single query
    python scripts/eval_chunking.py --pdf <path> --query "1.2 节主要讲了什么"
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.rag.pdf_parser import extract_page_blocks
from app.rag.source_models import SourceDescriptor, SourceLoadResult, utc_now_iso
from app.rag.splitter import _chunk_by_tokens
from app.rag.structured_chunker import structured_pdf_chunks


DEFAULT_DENSE_TOP_N = 30
DEFAULT_LEXICAL_TOP_N = 30
DEFAULT_FUSION_TOP_N = 30
DEFAULT_RRF_K = 60

QUERY_INTENTS = {
    "title_query",
    "section_query",
    "table_query",
    "figure_query",
    "abstract_query",
    "concept_query",
    "fact_query",
}


# ── Chunk builders ─────────────────────────────────────────────────────────────

def build_page_mode_chunks(pdf_path: str, title: str = "") -> list[dict]:
    page_blocks_list = extract_page_blocks(Path(pdf_path))
    page_texts = []
    for pb in page_blocks_list:
        text = pb.text.strip()
        if len(text) >= 20:
            page_texts.append(f"\n\n[page {pb.page}]\n{text}")
    normalized_text = "".join(page_texts).strip()
    content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    last_ingested_at = utc_now_iso()
    descriptor = SourceDescriptor(
        source=title or Path(pdf_path).stem, source_type="pdf",
        local_path=Path(pdf_path), requested_source=pdf_path,
    )
    load_result = SourceLoadResult(
        descriptor=descriptor, title=title or Path(pdf_path).stem,
        text=normalized_text, metadata={},
    )
    chunks = []
    idx = 0
    for page_block in normalized_text.split("\n\n[page "):
        block = page_block.strip()
        if not block:
            continue
        if block.startswith("[page "):
            header, _, page_text = block.partition("]\n")
        else:
            header, _, page_text = block.partition("\n")
            header = ""
        page_number = header.replace("[page ", "").strip() if header else "?"
        if not page_text.strip():
            continue
        for chunk_text in _chunk_by_tokens(page_text.strip(), chunk_size=600, overlap=80):
            chunk_text = chunk_text.strip()
            if not chunk_text:
                continue
            chunks.append({
                "chunk_index": idx,
                "text": chunk_text,
                "page": page_number,
                "location": f"page {page_number}",
                "ref": f"{title or Path(pdf_path).stem} > page {page_number}",
                "block_type": "unknown",
                "section_title": "",
                "doc_id": descriptor.source,
                "content_hash": content_hash,
                "last_ingested_at": last_ingested_at,
            })
            idx += 1
    return chunks


def build_structured_chunks(pdf_path: str, title: str = "") -> list[dict]:
    page_blocks_list = extract_page_blocks(Path(pdf_path))
    pages = [{"page": pb.page, "blocks": pb.blocks} for pb in page_blocks_list]
    doc_id = title or Path(pdf_path).stem
    content_hash = hashlib.sha256(
        "".join(pb.text for pb in page_blocks_list).encode("utf-8")
    ).hexdigest()
    last_ingested_at = utc_now_iso()
    raw_chunks = structured_pdf_chunks(
        pages,
        doc_id=doc_id, source="pdf", source_path=pdf_path, source_type="pdf",
        title=title or Path(pdf_path).stem,
        source_version="1.0", content_hash=content_hash,
        last_ingested_at=last_ingested_at,
    )
    chunks = []
    for chunk_text, meta in raw_chunks:
        chunks.append({
            "chunk_index": len(chunks),
            "text": chunk_text,
            "page": str(meta.page_start),
            "location": (f"page {meta.page_start}-{meta.page_end}"
                          if meta.page_end != meta.page_start
                          else f"page {meta.page_start}"),
            "ref": f"{title or Path(pdf_path).stem} > page {meta.page_start}",
            "block_type": meta.block_type,
            "section_title": meta.section_title,
            "doc_id": doc_id,
            "content_hash": content_hash,
            "last_ingested_at": last_ingested_at,
        })
    return chunks


# ── Embedding + similarity ────────────────────────────────────────────────────

def _get_embedding_backend():
    try:
        from app.rag.embeddings import get_embedding_backend
        return get_embedding_backend()
    except Exception:
        return None


def embed_texts(texts: list[str], backend):
    if not texts:
        return []
    if backend is None:
        return [[0.0] * 384 for _ in texts]
    try:
        return backend.embed_texts(texts)
    except (AttributeError, TypeError):
        try:
            return backend.embed_documents(texts)
        except Exception:
            return [[0.0] * 384 for _ in texts]


def embed_query(query: str, backend):
    if backend is None:
        return [0.0] * 384
    try:
        return backend.embed_query(query)
    except (AttributeError, TypeError):
        try:
            return backend.embed_texts([query])[0]
        except Exception:
            return [0.0] * 384


def cosine_scores(query_vec: list[float], doc_vecs: list[list[float]]) -> list[float]:
    return [sum(q * d for q, d in zip(query_vec, doc_vec)) for doc_vec in doc_vecs]


def top_k(scores: list[float], k: int) -> list[tuple[int, float]]:
    indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    return indexed[:k]


def _extract_query_intent(query: str) -> dict:
    q_lower = query.lower()
    section_nums = re.findall(r"\d+(?:\.\d+)+", query)
    title_query = any(w in q_lower for w in ["标题", "题目", "title", "article title"])
    table_query = bool(re.search(r"(表\s*\d+|table\s*\d+)", query, flags=re.I))
    figure_query = bool(re.search(r"(图\s*\d+|figure\s*\d+)", query, flags=re.I))
    section_query = bool(section_nums) or any(w in q_lower for w in ["第", "节", "section"])
    abstract_query = any(
        w in q_lower for w in ["摘要", "abstract", "关键词", "key words", "keywords"]
    )
    concept_query = any(
        w in q_lower for w in ["定义", "概念", "什么是", "是什么", "definition", "concept"]
    )

    intent = "fact_query"
    if title_query:
        intent = "title_query"
    elif table_query:
        intent = "table_query"
    elif figure_query:
        intent = "figure_query"
    elif section_query:
        intent = "section_query"
    elif abstract_query:
        intent = "abstract_query"
    elif concept_query:
        intent = "concept_query"

    return {
        "intent": intent,
        "section_numbers": section_nums,
        "title_query": title_query,
        "table_query": table_query,
        "figure_query": figure_query,
        "section_query": section_query,
        "abstract_query": abstract_query,
        "concept_query": concept_query,
        "author_like": any(w in q_lower for w in ["作者", "单位", "邮箱", "affiliation", "email"]),
        "front_matter_like": any(
            w in q_lower for w in ["基金", "收稿日期", "修回日期", "doi", "关键词", "摘要"]
        ),
    }


def _compact_text_for_lexical(text: str) -> str:
    return _normalize(text).replace("：", "").replace(":", "")


def _lexical_terms(text: str) -> list[str]:
    compact = _compact_text_for_lexical(text)
    terms: list[str] = []

    for anchor in re.findall(r"(?:第?\d+(?:\.\d+)+节?|[图表]\d+|table\d+|figure\d+)", compact, flags=re.I):
        terms.append(anchor.lower())

    for token in re.findall(r"[a-z]{2,}(?:[a-z]+)?|\d+(?:\.\d+)+", compact):
        terms.append(token.lower())

    cjk_text = "".join(ch for ch in compact if "\u4e00" <= ch <= "\u9fff")
    for ch in cjk_text:
        terms.append(ch)
    for i in range(len(cjk_text) - 1):
        terms.append(cjk_text[i:i + 2])

    return terms


def _build_lexical_index(chunks: list[dict]) -> dict:
    doc_freq: Counter = Counter()
    doc_term_freqs: list[Counter] = []
    doc_lengths: list[int] = []

    for chunk in chunks:
        combined_text = " ".join(
            filter(None, [chunk.get("section_title", ""), chunk.get("text", "")])
        )
        terms = _lexical_terms(combined_text)
        term_freq = Counter(terms)
        doc_term_freqs.append(term_freq)
        doc_lengths.append(sum(term_freq.values()) or 1)
        for term in term_freq:
            doc_freq[term] += 1

    avg_doc_len = (sum(doc_lengths) / len(doc_lengths)) if doc_lengths else 1.0
    return {
        "doc_freq": doc_freq,
        "doc_term_freqs": doc_term_freqs,
        "doc_lengths": doc_lengths,
        "avg_doc_len": avg_doc_len,
        "num_docs": len(chunks),
    }


def _lexical_scores(query: str, chunks: list[dict], lexical_index: dict) -> list[float]:
    query_terms = _lexical_terms(query)
    if not query_terms:
        return [0.0] * len(chunks)

    scores = [0.0] * len(chunks)
    num_docs = max(lexical_index.get("num_docs", 0), 1)
    avg_doc_len = max(lexical_index.get("avg_doc_len", 1.0), 1.0)
    k1 = 1.2
    b = 0.75

    for idx, term_freq in enumerate(lexical_index["doc_term_freqs"]):
        doc_len = lexical_index["doc_lengths"][idx]
        score = 0.0
        for term in query_terms:
            tf = term_freq.get(term, 0)
            if tf <= 0:
                continue
            df = lexical_index["doc_freq"].get(term, 0)
            idf = math.log(1 + (num_docs - df + 0.5) / (df + 0.5))
            denom = tf + k1 * (1 - b + b * doc_len / avg_doc_len)
            score += idf * (tf * (k1 + 1) / max(denom, 1e-8))
        scores[idx] = score
    return scores


def _rrf_fuse(rank_lists: list[list[tuple[int, float]]], limit: int, rrf_k: int = DEFAULT_RRF_K) -> list[tuple[int, float]]:
    fused: dict[int, float] = {}
    for ranked in rank_lists:
        for rank, (idx, _) in enumerate(ranked, start=1):
            fused[idx] = fused.get(idx, 0.0) + (1.0 / (rrf_k + rank))
    return sorted(fused.items(), key=lambda item: item[1], reverse=True)[:limit]


def _normalize_score_list(scores: list[float]) -> list[float]:
    if not scores:
        return []
    max_s = max(scores)
    min_s = min(scores)
    span = max(max_s - min_s, 1e-8)
    return [(s - min_s) / span for s in scores]


def prepare_retrieval_bundle(chunks: list[dict], backend) -> dict:
    texts = [chunk["text"] for chunk in chunks]
    return {
        "chunks": chunks,
        "texts": texts,
        "doc_vecs": embed_texts(texts, backend),
        "lexical_index": _build_lexical_index(chunks),
    }


# ── Reranker v1 (simple) ──────────────────────────────────────────────────────

def keyword_rerank(query: str, chunks: list[dict], scores: list[float], top_n: int = 20) -> list[float]:
    """
    Simple keyword-based rerank: boost caption/abstract/heading blocks
    by query intent keywords; demote generic title.
    """
    q_lower = query.lower()
    wants_caption = any(w in q_lower for w in ["表", "图", "figure", "table", "图表", "caption"])
    wants_abstract = any(w in q_lower for w in ["摘要", "abstract", "总结"])
    wants_heading = any(w in q_lower for w in ["节", "section"])
    is_title_query = any(w in q_lower for w in ["标题", "title"])

    adjustments = [0.0] * len(scores)
    for i, chunk in enumerate(chunks):
        bt = chunk.get("block_type", "")
        text = chunk.get("text", "") or ""
        pg = chunk.get("page", "")

        # Positive signals
        if wants_caption and bt == "caption":
            adjustments[i] += 0.15
        if wants_abstract and bt in ("paragraph", "heading"):
            st = chunk.get("section_title", "") or ""
            if any(w in st for w in ["Abstract", "摘要"]):
                adjustments[i] += 0.20
        if wants_heading and bt == "heading":
            adjustments[i] += 0.08

        # Keyword overlap bonus
        q_chars = set(_normalize(query))
        text_chars = set(_normalize(text[:300]))
        overlap = len(q_chars & text_chars)
        if overlap > 5:
            adjustments[i] += 0.03 * min(overlap, 15)

        # Negative: generic page-1 title demotion (only if NOT a title query)
        if not is_title_query and pg == "1" and bt == "heading" and len(text) < 40:
            adjustments[i] -= 0.12

    max_s = max(scores) if scores else 1.0
    min_s = min(scores) if scores else 0.0
    range_s = max(max_s - min_s, 1e-8)
    norm_scores = [(s - min_s) / range_s for s in scores]
    return [n + adj for n, adj in zip(norm_scores, adjustments)]


# ── Reranker v2 (heuristic_v2) ───────────────────────────────────────────────

def keyword_rerank_v2(query: str, chunks: list[dict], scores: list[float], top_n: int = 20) -> list[float]:
    """
    Structure-aware heuristic rerank v2.
    Signals:
      - query intent (caption/abstract/section/keyword/definition)
      - section_title exact or prefix match
      - heading block with matching section number
      - keyword character overlap bonus
      - page-1 generic title heading demotion (unless query explicitly asks for title)
    """
    q_lower = query.lower()

    # Intent detection
    wants_caption = any(w in q_lower for w in ["表", "图", "figure", "table", "图表", "caption"])
    wants_abstract = any(w in q_lower for w in ["摘要", "abstract", "总结"])
    wants_heading = any(w in q_lower for w in ["节", "section", "章节"])
    wants_definition = any(w in q_lower for w in ["定义", "概念", "是什么", "definition", "concept"])
    wants_keywords_kw = any(w in q_lower for w in ["关键词", "keyword", "关键字"])
    wants_author = any(w in q_lower for w in ["作者", "单位", "邮箱", "affiliation"])
    # Explicit title query: do NOT demote generic title
    is_title_query = any(w in q_lower for w in ["标题", "title", "叫什么"])

    # Section number extraction (e.g. "1.2", "2.1.1")
    section_nums = re.findall(r"\d+(?:\.\d+)+", query)

    adjustments = [0.0] * len(scores)

    for i, chunk in enumerate(chunks):
        bt = chunk.get("block_type", "")
        st = chunk.get("section_title", "") or ""
        text = chunk.get("text", "") or ""
        pg = chunk.get("page", "")

        # ── Positive signals ──────────────────────────────────────────
        # Caption: query mentions 图/表
        if wants_caption and bt == "caption":
            adjustments[i] += 0.18

        # Abstract: query mentions 摘要/abstract
        if wants_abstract and bt == "paragraph":
            if "Abstract" in st or "摘要" in st:
                adjustments[i] += 0.25
            elif st:  # any paragraph in structured mode may be relevant
                adjustments[i] += 0.05

        # Heading/section: query mentions 节/section
        if wants_heading and bt == "heading":
            adjustments[i] += 0.12
            # Check section number match
            for sn in section_nums:
                if sn in (chunk.get("text", "") or "") or sn in st:
                    adjustments[i] += 0.20
                    break

        # Definition/concept: prefer paragraph with definition-like text
        if wants_definition and bt == "paragraph":
            if any(w in text[:100] for w in ["定义", "概念", "是指", "即为", "定义为"]):
                adjustments[i] += 0.18

        # Keywords: query mentions 关键词/keyword
        if wants_keywords_kw and bt in ("heading", "paragraph"):
            if "关键词" in st or "keyword" in (st.lower()):
                adjustments[i] += 0.25

        # Author/unit: prefer paragraph on page 1
        if wants_author and bt == "paragraph" and pg == "1":
            adjustments[i] += 0.15

        # ── Section title exact match bonus ───────────────────────────
        if st and section_nums:
            for sn in section_nums:
                # e.g. "2.1 边缘协同推理的智能化方法" should match "2.1"
                if sn in st or any(sn in part for part in st.split() if part):
                    adjustments[i] += 0.20
                    break

        # ── Keyword overlap bonus (character-level for Chinese) ─────────
        q_chars = set(_normalize(query))
        text_chars = set(_normalize(text[:300]))
        overlap = len(q_chars & text_chars)
        if overlap > 5:
            adjustments[i] += 0.04 * min(overlap, 15)

        # ── Negative signals ───────────────────────────────────────────
        # Page-1 generic title heading demotion (only if NOT a title query)
        if not is_title_query and pg == "1" and bt == "heading" and len(text) < 40:
            # Likely a generic paper title like "Survey of ..."
            adjustments[i] -= 0.15

        # Page-1 English title on non-english-query demotion
        if not is_title_query and pg == "1" and bt == "heading":
            if re.search(r"[a-z]", text) and not re.search(r"[\u4e00-\u9fff]", text):
                adjustments[i] -= 0.08

    # Normalize embedding scores to [0, 1] then combine with adjustments
    max_s = max(scores) if scores else 1.0
    min_s = min(scores) if scores else 0.0
    range_s = max(max_s - min_s, 1e-8)
    norm_scores = [(s - min_s) / range_s for s in scores]
    return [n + adj for n, adj in zip(norm_scores, adjustments)]


# ── Retrieval ─────────────────────────────────────────────────────────────────

def _contains_anchor(text: str, query: str, prefixes: tuple[str, ...]) -> bool:
    normalized_text = _compact_text_for_lexical(text)
    normalized_query = _compact_text_for_lexical(query)
    for prefix in prefixes:
        pattern = rf"{prefix}\d+"
        for anchor in re.findall(pattern, normalized_query, flags=re.I):
            if anchor.lower() in normalized_text.lower():
                return True
    return False


def _is_generic_title_chunk(chunk: dict) -> bool:
    text = (chunk.get("text", "") or "").strip()
    section_title = (chunk.get("section_title", "") or "").strip()
    if chunk.get("page") != "1" or chunk.get("block_type") != "heading":
        return False
    if section_title:
        return False
    if len(text) > 40 or re.match(r"^\d", text):
        return False
    return True


def soft_rerank_v3(
    query: str,
    chunks: list[dict],
    dense_scores: list[float],
    lexical_scores: list[float],
    fusion_scores: list[float],
) -> list[float]:
    features = _extract_query_intent(query)
    dense_norm = _normalize_score_list(dense_scores)
    lexical_norm = _normalize_score_list(lexical_scores)
    fusion_norm = _normalize_score_list(fusion_scores)
    query_terms = set(_lexical_terms(query))
    reranked = []

    for idx, chunk in enumerate(chunks):
        chunk_text = chunk.get("text", "") or ""
        section_title = chunk.get("section_title", "") or ""
        block_type = chunk.get("block_type", "")
        page = chunk.get("page", "")
        combined_terms = set(_lexical_terms(f"{section_title} {chunk_text[:300]}"))
        overlap_ratio = (
            len(query_terms & combined_terms) / max(len(query_terms), 1)
            if query_terms else 0.0
        )
        section_title_match = 0.0
        if section_title and _section_match(section_title, query):
            section_title_match += 0.12
        elif section_title and any(term in _normalize(section_title) for term in list(query_terms)[:8]):
            section_title_match += 0.06

        block_type_bonus = 0.0
        anchor_bonus = 0.0
        generic_penalty = 0.0
        page_one_bonus = 0.0

        intent = features["intent"]
        if intent == "title_query":
            if page == "1" and block_type == "heading":
                block_type_bonus += 0.22
                if not section_title:
                    page_one_bonus += 0.08
        elif intent == "section_query":
            if block_type == "heading":
                block_type_bonus += 0.12
            for section_num in features["section_numbers"]:
                if section_num in chunk_text or section_num in section_title:
                    anchor_bonus += 0.18
                    break
            if section_title_match:
                block_type_bonus += 0.06
        elif intent == "table_query":
            if block_type == "caption":
                block_type_bonus += 0.12
            if _contains_anchor(f"{section_title} {chunk_text}", query, ("表", "table")):
                anchor_bonus += 0.18
        elif intent == "figure_query":
            if block_type == "caption":
                block_type_bonus += 0.12
            if _contains_anchor(f"{section_title} {chunk_text}", query, ("图", "figure")):
                anchor_bonus += 0.18
        elif intent == "abstract_query":
            if page == "1":
                page_one_bonus += 0.06
            if block_type == "paragraph" and any(w in (section_title or chunk_text[:20]).lower() for w in ["abstract", "摘要", "关键词", "key words"]):
                block_type_bonus += 0.14
            elif block_type == "heading" and any(w in chunk_text.lower() for w in ["abstract", "摘要", "关键词", "key words"]):
                block_type_bonus += 0.10
        elif intent == "concept_query":
            if block_type == "paragraph":
                block_type_bonus += 0.10
            elif block_type == "heading" and section_title_match:
                block_type_bonus += 0.04
        else:
            if features["author_like"] and page == "1" and block_type == "paragraph":
                page_one_bonus += 0.12
            elif features["front_matter_like"] and page == "1":
                page_one_bonus += 0.08

        if intent != "title_query" and _is_generic_title_chunk(chunk):
            generic_penalty = 0.08

        score = (
            0.55 * fusion_norm[idx]
            + 0.25 * dense_norm[idx]
            + 0.10 * lexical_norm[idx]
            + 0.10 * overlap_ratio
            + section_title_match
            + block_type_bonus
            + anchor_bonus
            + page_one_bonus
            - generic_penalty
        )
        reranked.append(score)

    return reranked


def run_query(
    bundle: dict,
    query: str,
    limit: int,
    backend,
    mode: str = "structured",
    rerank: str = "none",
    dense_top_n: int = DEFAULT_DENSE_TOP_N,
    lexical_top_n: int = DEFAULT_LEXICAL_TOP_N,
    fusion_top_n: int = DEFAULT_FUSION_TOP_N,
) -> list[dict]:
    chunks = bundle["chunks"]
    dense_scores_all = cosine_scores(embed_query(query, backend), bundle["doc_vecs"])
    lexical_scores_all = _lexical_scores(query, chunks, bundle["lexical_index"])

    dense_ranked = top_k(dense_scores_all, min(dense_top_n, len(chunks)))
    lexical_ranked = top_k(lexical_scores_all, min(lexical_top_n, len(chunks)))

    if mode == "structured_hybrid":
        fused_ranked = _rrf_fuse([dense_ranked, lexical_ranked], min(fusion_top_n, len(chunks)))
        candidate_indices = [idx for idx, _ in fused_ranked]
        fusion_score_map = {idx: score for idx, score in fused_ranked}
    else:
        candidate_indices = [idx for idx, _ in dense_ranked]
        fusion_score_map = {idx: dense_scores_all[idx] for idx in candidate_indices}

    candidate_chunks = [chunks[idx] for idx in candidate_indices]
    dense_scores = [dense_scores_all[idx] for idx in candidate_indices]
    lexical_scores = [lexical_scores_all[idx] for idx in candidate_indices]
    fusion_scores = [fusion_score_map[idx] for idx in candidate_indices]

    if rerank == "simple":
        final_scores = keyword_rerank(query, candidate_chunks, dense_scores, top_n=limit)
    elif rerank == "heuristic_v2":
        final_scores = keyword_rerank_v2_fixed(query, candidate_chunks, dense_scores, top_n=limit)
    elif rerank == "soft_v3":
        final_scores = soft_rerank_v3(query, candidate_chunks, dense_scores, lexical_scores, fusion_scores)
    else:
        final_scores = fusion_scores if mode == "structured_hybrid" else dense_scores

    ranked = sorted(enumerate(final_scores), key=lambda item: item[1], reverse=True)[:limit]
    return [
        {
            **candidate_chunks[local_idx],
            "score": round(score, 4),
            "dense_score": round(dense_scores[local_idx], 4),
            "lexical_score": round(lexical_scores[local_idx], 4),
            "fusion_score": round(fusion_scores[local_idx], 4),
            "text_preview": candidate_chunks[local_idx]["text"][:120].replace("\n", " "),
        }
        for local_idx, score in ranked
    ]


# ── Automatic Hit Metrics ──────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Lightweight normalization for keyword matching."""
    return re.sub(r"\s+", "", s).lower()


def _kw_match(text: str, keywords: list[str], threshold: int = 1) -> tuple[bool, int]:
    """Check if text contains at least `threshold` of the given keywords."""
    text_n = _normalize(text)
    hits = sum(1 for kw in keywords if _normalize(kw) in text_n)
    return hits >= threshold, hits


def _section_match(chunk_section: str, expected: str) -> bool:
    """Check section_title match (loose: expected is substring of section_title or vice versa)."""
    if not expected or not chunk_section:
        return False
    chunk_n = _normalize(chunk_section)
    exp_n = _normalize(expected)
    return (exp_n in chunk_n) or (chunk_n in exp_n) or (exp_n.split()[0] in chunk_n)


def compute_metrics(chunks: list[dict], results: list[dict], case: dict, k: int) -> dict:
    """
    Compute comprehensive metrics for a result set.
    Includes standard hit@k plus avg_match_rate@k, first_correct_rank, MRR,
    and title_attraction.
    """
    expected_page = str(case.get("expected_page", ""))
    expected_section = case.get("expected_section_title", "")
    expected_keywords = case.get("expected_keywords", [])
    expected_bt = case.get("expected_block_type", "")

    # Per-position hits
    page_hits_at = {1: 0, 3: 0, 5: 0}
    section_hits_at = {1: 0, 3: 0, 5: 0}
    keyword_hits_at = {1: 0, 3: 0, 5: 0}
    bt_hits_at = {1: 0, 3: 0, 5: 0}
    first_correct_rank_page = None
    first_correct_rank_section = None
    rr_page = 0.0
    rr_section = 0.0

    is_title_query = _extract_query_intent(case["query"])["intent"] == "title_query"

    for pos, r in enumerate(results[:k]):
        pos_k = pos + 1  # 1-based position

        pg = r.get("page", "")
        st = r.get("section_title", "") or ""
        bt = r.get("block_type", "")
        txt = r.get("text", "") or ""

        # Page hit
        if expected_page and pg == expected_page:
            if first_correct_rank_page is None:
                first_correct_rank_page = pos_k
                rr_page = 1.0 / pos_k
            if pos_k <= 5:
                page_hits_at[5] += 1
            if pos_k <= 3:
                page_hits_at[3] += 1
            if pos_k == 1:
                page_hits_at[1] += 1

        # Section hit
        if expected_section and _section_match(st, expected_section):
            if first_correct_rank_section is None:
                first_correct_rank_section = pos_k
                rr_section = 1.0 / pos_k
            if pos_k <= 5:
                section_hits_at[5] += 1
            if pos_k <= 3:
                section_hits_at[3] += 1
            if pos_k == 1:
                section_hits_at[1] += 1

        # Keyword hit
        if expected_keywords:
            matched, _ = _kw_match(txt, expected_keywords)
            if matched:
                if pos_k <= 5:
                    keyword_hits_at[5] += 1
                if pos_k <= 3:
                    keyword_hits_at[3] += 1
                if pos_k == 1:
                    keyword_hits_at[1] += 1

        # Block type hit
        if expected_bt and bt == expected_bt:
            if pos_k <= 5:
                bt_hits_at[5] += 1
            if pos_k <= 3:
                bt_hits_at[3] += 1
            if pos_k == 1:
                bt_hits_at[1] += 1

    k_actual = min(len(results), k)

    def avg_match_rate(hits_at_k, k_val):
        return round(hits_at_k / min(k_val, k_actual), 3) if k_actual else 0

    def hit_binary(hits_at_k):
        return 1.0 if hits_at_k > 0 else 0.0

    # Title attraction: top-1 falls onto a generic page-1 title for a non-title query.
    title_attraction = 0
    if results and not is_title_query:
        top1 = results[0]
        if _is_generic_title_chunk(top1):
            title_attraction = 1

    return {
        # standard hit@k
        "page_hit@1": hit_binary(page_hits_at[1]),
        "page_hit@3": hit_binary(page_hits_at[3]),
        "page_hit@5": hit_binary(page_hits_at[5]),
        "page_hits_total": page_hits_at[5],
        "section_hit@1": hit_binary(section_hits_at[1]),
        "section_hit@3": hit_binary(section_hits_at[3]),
        "section_hit@5": hit_binary(section_hits_at[5]),
        "section_hits_total": section_hits_at[5],
        "keyword_hit@1": hit_binary(keyword_hits_at[1]),
        "keyword_hit@3": hit_binary(keyword_hits_at[3]),
        "keyword_hit@5": hit_binary(keyword_hits_at[5]),
        "bt_hit@1": hit_binary(bt_hits_at[1]),
        "bt_hit@3": hit_binary(bt_hits_at[3]),
        "bt_hit@5": hit_binary(bt_hits_at[5]),
        # precision-like / avg match rate
        "page_avg_match_rate@1": avg_match_rate(page_hits_at[1], 1),
        "page_avg_match_rate@3": avg_match_rate(page_hits_at[3], 3),
        "page_avg_match_rate@5": avg_match_rate(page_hits_at[5], 5),
        "section_avg_match_rate@1": avg_match_rate(section_hits_at[1], 1),
        "section_avg_match_rate@3": avg_match_rate(section_hits_at[3], 3),
        "section_avg_match_rate@5": avg_match_rate(section_hits_at[5], 5),
        "keyword_avg_match_rate@1": avg_match_rate(keyword_hits_at[1], 1),
        "keyword_avg_match_rate@3": avg_match_rate(keyword_hits_at[3], 3),
        "keyword_avg_match_rate@5": avg_match_rate(keyword_hits_at[5], 5),
        "bt_avg_match_rate@1": avg_match_rate(bt_hits_at[1], 1),
        "bt_avg_match_rate@3": avg_match_rate(bt_hits_at[3], 3),
        "bt_avg_match_rate@5": avg_match_rate(bt_hits_at[5], 5),
        # rank & MRR
        "first_correct_rank_page": first_correct_rank_page or -1,
        "first_correct_rank_section": first_correct_rank_section or -1,
        "mrr_page": round(rr_page, 4),
        "mrr_section": round(rr_section, 4),
        # title attraction
        "title_attraction": title_attraction,
    }


def metadata_completeness(chunks: list[dict]) -> dict:
    """Compute metadata completeness stats for a chunk set."""
    total = len(chunks)
    if total == 0:
        return {}
    has_page = sum(1 for c in chunks if c.get("page") not in (None, "", "?"))
    has_section = sum(1 for c in chunks if c.get("section_title", ""))
    has_block_type = sum(1 for c in chunks if c.get("block_type", "") not in ("", "unknown"))
    return {
        "total": total,
        "page_start_complete": round(has_page / total, 3),
        "section_title_nonempty": round(has_section / total, 3),
        "block_type_known": round(has_block_type / total, 3),
    }


# ── Report builder v3 ──────────────────────────────────────────────────────────

def build_report(pdf_path: str, cases: list[dict], out_path: str, rerank_mode: str = "none"):
    title = Path(pdf_path).stem

    print("Building chunks...")
    page_chunks = build_page_mode_chunks(pdf_path, title=title)
    struct_chunks = build_structured_chunks(pdf_path, title=title)
    print(f"  page-mode: {len(page_chunks)} chunks")
    print(f"  structured: {len(struct_chunks)} chunks")

    backend = _get_embedding_backend()
    print(f"Embedding: {type(backend).__name__ if backend else 'dummy'}")

    # Determine active modes
    all_modes = ["page", "structured"]
    if rerank_mode == "simple":
        all_modes.append("structured+simple")
    elif rerank_mode == "heuristic_v2":
        all_modes.extend(["structured+simple", "structured+heuristic_v2"])

    mode_labels = {
        "page": "Page-Mode",
        "structured": "Structured",
        "structured+simple": "Structured+Simple",
        "structured+heuristic_v2": "Structured+HeuristicV2",
    }
    active_modes = all_modes

    # Run all queries for all modes
    all_results: dict[str, dict] = {}
    for case in cases:
        cid = case.get("id", case["query"][:30])
        all_results[cid] = {}
        k = case.get("top_k", 5)
        for mode in active_modes:
            if mode == "page":
                rk, chunks = "none", page_chunks
            elif mode == "structured":
                rk, chunks = "none", struct_chunks
            elif mode == "structured+simple":
                rk, chunks = "simple", struct_chunks
            elif mode == "structured+heuristic_v2":
                rk, chunks = "heuristic_v2", struct_chunks
            else:
                rk, chunks = "none", page_chunks
            all_results[cid][mode] = run_query(chunks, case["query"], k, backend, rerank=rk)

    # Chunk statistics
    page_stats = metadata_completeness(page_chunks)
    struct_stats = metadata_completeness(struct_chunks)

    def avg_chars(chunks):
        return round(sum(len(c["text"]) for c in chunks) / len(chunks), 1) if chunks else 0

    # Aggregate all metrics across all cases
    topk = cases[0].get("top_k", 5) if cases else 5
    agg: dict[str, dict] = {m: {} for m in active_modes}

    for m in active_modes:
        agg[m] = {
            "page_hit@1": [], "page_hit@3": [], "page_hit@5": [],
            "section_hit@1": [], "section_hit@3": [], "section_hit@5": [],
            "keyword_hit@1": [], "keyword_hit@3": [], "keyword_hit@5": [],
            "bt_hit@1": [], "bt_hit@3": [], "bt_hit@5": [],
            "mrr_page": [], "mrr_section": [],
            "title_attraction": [],
            "first_correct_rank_page": [],
            "first_correct_rank_section": [],
        }

    for case in cases:
        cid = case.get("id", case["query"][:30])
        for mode in active_modes:
            chunks = page_chunks if mode == "page" else struct_chunks
            met = compute_metrics(chunks, all_results[cid][mode], case, topk)
            for key in agg[mode]:
                agg[mode][key].append(met[key])

    def mean(lst):
        return round(sum(lst) / len(lst), 3) if lst else 0

    # Write report
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    mode_str = ", ".join(mode_labels[m] for m in active_modes)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Chunking Evaluation Report v3\n\n")
        f.write(f"**PDF:** `{pdf_path}`\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**Embedding:** {type(backend).__name__ if backend else 'dummy'}  ")
        f.write(f"**Rerank modes:** {rerank_mode}\n\n")

        # Section 1: Config
        f.write("## 1. Evaluation Config\n\n")
        f.write(f"- Cases: **{len(cases)}** query cases\n")
        f.write(f"- Top-k: **{topk}**\n")
        f.write(f"- Active modes: {mode_str}\n\n")

        # Section 2: Chunk Statistics
        f.write("## 2. Chunk Statistics\n\n")
        f.write("| Metric | Page-Mode | Structured |\n")
        f.write("|--------|-----------|------------|\n")
        f.write(f"| Total chunks | {len(page_chunks)} | {len(struct_chunks)} |\n")
        f.write(f"| Avg chars | {avg_chars(page_chunks)} | {avg_chars(struct_chunks)} |\n")
        f.write(f"| page_start complete | {page_stats.get('page_start_complete','N/A')} | {struct_stats.get('page_start_complete','N/A')} |\n")
        f.write(f"| section_title non-empty | {page_stats.get('section_title_nonempty','N/A')} | {struct_stats.get('section_title_nonempty','N/A')} |\n")
        f.write(f"| block_type known | {page_stats.get('block_type_known','N/A')} | {struct_stats.get('block_type_known','N/A')} |\n")

        bt_counts: dict[str, int] = {}
        for c in struct_chunks:
            bt = c.get("block_type", "unknown")
            bt_counts[bt] = bt_counts.get(bt, 0) + 1
        f.write(f"| block_type dist | (n/a) | {dict(bt_counts)} |\n\n")

        # Section 3: Comprehensive Metrics Summary
        f.write("## 3. Automatic Metrics Summary\n\n")
        f.write(f"_Mean over {len(cases)} cases_\n\n")

        # 3a. page_hit / section_hit table
        f.write("### 3a. Page & Section Hit Rate (@1 / @3 / @5)\n\n")
        f.write("| Mode | page_hit@1 | page_hit@3 | page_hit@5 | section_hit@1 | section_hit@3 | section_hit@5 |\n")
        f.write("|------|------------|------------|------------|---------------|---------------|---------------|\n")
        for mode in active_modes:
            lb = mode_labels[mode]
            f.write(f"| {lb} | "
                    f"{mean(agg[mode]['page_hit@1'])} | "
                    f"{mean(agg[mode]['page_hit@3'])} | "
                    f"{mean(agg[mode]['page_hit@5'])} | "
                    f"{mean(agg[mode]['section_hit@1'])} | "
                    f"{mean(agg[mode]['section_hit@3'])} | "
                    f"{mean(agg[mode]['section_hit@5'])} |\n")
        f.write("\n")

        # 3b. keyword_hit / bt_hit / MRR / title_attraction
        f.write("### 3b. Keyword & Block-Type Hit, MRR & Title Attraction\n\n")
        f.write("| Mode | keyword_hit@5 | bt_hit@5 | mrr_page | mrr_section | title_attraction% |\n")
        f.write("|------|---------------|----------|----------|-------------|------------------|\n")
        for mode in active_modes:
            lb = mode_labels[mode]
            ta_rate = mean(agg[mode]['title_attraction']) * 100
            f.write(f"| {lb} | "
                    f"{mean(agg[mode]['keyword_hit@5'])} | "
                    f"{mean(agg[mode]['bt_hit@5'])} | "
                    f"{mean(agg[mode]['mrr_page'])} | "
                    f"{mean(agg[mode]['mrr_section'])} | "
                    f"{ta_rate:.1f}% |\n")
        f.write("\n")

        # Section 4: Per-Case Metrics
        f.write("## 4. Per-Case Metrics (page_hit@5 / section_hit@5 / keyword_hit@5 / bt_hit@5)\n\n")

        # Header
        headers = []
        for m in active_modes:
            headers.append(f"_p@5_ | _s@5_ | _k@5_ | _bt@5_")
        f.write("| Case | " + " | ".join(headers) + " |\n")
        f.write("|------|" + "|".join(["---"] * len(active_modes)) + "|\n")

        for case in cases:
            cid = case.get("id", case["query"][:30])
            row_parts = [f"**{cid}**"]
            for mode in active_modes:
                chunks = page_chunks if mode == "page" else struct_chunks
                met = compute_metrics(chunks, all_results[cid][mode], case, topk)
                row_parts.append(
                    f"{met['page_hit@5']} | {met['section_hit@5']} | "
                    f"{met['keyword_hit@5']} | {met['bt_hit@5']}"
                )
            f.write("| " + " | ".join(row_parts) + " |\n")
        f.write("\n")

        # Section 5: Representative Query Comparison
        f.write("## 5. Representative Query Comparison\n\n")
        selected = cases[:6]
        for i, case in enumerate(selected):
            cid = case.get("id", case["query"][:30])
            f.write(f"### {i+1}. [{cid}] {case['query']}\n\n")
            if case.get("notes"):
                f.write(f"*Notes: {case['notes']}*\n\n")

            for mode in active_modes:
                label = mode_labels[mode]
                res = all_results[cid][mode]
                f.write(f"**{label}** (top-3):\n\n")
                for r_i, r in enumerate(res[:3]):
                    f.write(f"  [{r_i+1}] p{r['page']} "
                            f"[{r['block_type']}] "
                            f"section={r.get('section_title','')!r} "
                            f"score={r['score']} "
                            f"text={r['text_preview'][:80]}...\n")
                f.write("\n")

        # Section 6: Conclusions
        f.write("## 6. Conclusions\n\n")

        p5 = {m: mean(agg[m]["page_hit@5"]) for m in active_modes}
        s5 = {m: mean(agg[m]["section_hit@5"]) for m in active_modes}
        k5 = {m: mean(agg[m]["keyword_hit@5"]) for m in active_modes}

        if "structured" in active_modes and "page" in active_modes:
            diff = p5["structured"] - p5["page"]
            sign = "+" if diff > 0 else ""
            f.write(f"- **page_hit@5:** Structured={p5['structured']} vs Page={p5['page']} ({sign}{round(diff,3)})\n")
            diff_s = s5["structured"] - s5["page"]
            sign_s = "+" if diff_s > 0 else ""
            f.write(f"- **section_hit@5:** Structured={s5['structured']} vs Page={s5['page']} ({sign_s}{round(diff_s,3)})\n")
            diff_k = k5["structured"] - k5["page"]
            sign_k = "+" if diff_k > 0 else ""
            f.write(f"- **keyword_hit@5:** Structured={k5['structured']} vs Page={k5['page']} ({sign_k}{round(diff_k,3)})\n")
            f.write(f"  → **Note:** Page-mode has **{len(page_chunks)}** ~{avg_chars(page_chunks)}-char chunks vs Structured's **{len(struct_chunks)}** ~{avg_chars(struct_chunks)}-char chunks. "
                    f"Large chunks contain more character overlap with query keywords, so keyword_hit@5 is naturally higher for page-mode — this is a **big-chunk keyword bias**, not a quality advantage.\n")

        if "structured+simple" in active_modes and "structured" in active_modes:
            diff = p5["structured+simple"] - p5["structured"]
            sign = "+" if diff > 0 else ""
            f.write(f"- **Simple rerank effect:** page_hit@5 {sign}{round(diff,3)} "
                    f"({p5['structured+simple']} vs {p5['structured']})\n")

        if "structured+heuristic_v2" in active_modes and "structured" in active_modes:
            diff = p5["structured+heuristic_v2"] - p5["structured"]
            sign = "+" if diff > 0 else ""
            f.write(f"- **HeuristicV2 rerank effect:** page_hit@5 {sign}{round(diff,3)} "
                    f"({p5['structured+heuristic_v2']} vs {p5['structured']})\n")

        ta = {m: mean(agg[m]["title_attraction"]) * 100 for m in active_modes}
        if ta:
            f.write(f"- **Title attraction rate:** " + ", ".join(f"{mode_labels[m]}={v:.1f}%" for m, v in ta.items()) + "\n")
            ta_struct = ta.get("structured", 0) or ta.get("page", 0)
            f.write(f"  → Top-1 is a page-1 generic heading for ~{ta_struct:.0f}% of non-title queries. "
                    "This is an embedding model bias (English SentenceTransformer + Chinese title overlap).\n")

        f.write(f"- **Chunk count:** page={len(page_chunks)} structured={len(struct_chunks)}\n")
        f.write(f"- **Avg length:** page={avg_chars(page_chunks)} chars structured={avg_chars(struct_chunks)} chars\n")
        f.write("- **Metadata:** Structured adds `block_type` + `section_title` + precise `page_start/page_end`; page-mode has none.\n")

    print(f"\nReport: {out_path}")
    return out_path


# ── CLI ──────────────────────────────────────────────────────────────────────

def keyword_rerank_v2_fixed(query: str, chunks: list[dict], scores: list[float], top_n: int = 20) -> list[float]:
    q_lower = query.lower()
    wants_caption = any(w in q_lower for w in ["表", "图", "figure", "table", "图表", "caption"])
    wants_abstract = any(w in q_lower for w in ["摘要", "abstract", "总结"])
    wants_heading = any(w in q_lower for w in ["节", "section", "章节"])
    wants_definition = any(w in q_lower for w in ["定义", "概念", "是什么", "definition", "concept"])
    wants_keywords_kw = any(w in q_lower for w in ["关键词", "keyword", "关键字"])
    wants_author = any(w in q_lower for w in ["作者", "单位", "邮箱", "affiliation"])
    is_title_query = any(w in q_lower for w in ["标题", "题目", "title"])
    section_nums = re.findall(r"\d+(?:\.\d+)+", query)

    adjustments = [0.0] * len(scores)
    for i, chunk in enumerate(chunks):
        bt = chunk.get("block_type", "")
        st = chunk.get("section_title", "") or ""
        text = chunk.get("text", "") or ""
        pg = chunk.get("page", "")

        if wants_caption and bt == "caption":
            adjustments[i] += 0.18
        if wants_abstract and bt == "paragraph":
            if "Abstract" in st or "摘要" in st:
                adjustments[i] += 0.25
            elif st:
                adjustments[i] += 0.05
        if wants_heading and bt == "heading":
            adjustments[i] += 0.12
            for sn in section_nums:
                if sn in text or sn in st:
                    adjustments[i] += 0.20
                    break
        if wants_definition and bt == "paragraph":
            if any(w in text[:100] for w in ["定义", "概念", "是指", "即为", "定义为"]):
                adjustments[i] += 0.18
        if wants_keywords_kw and bt in ("heading", "paragraph"):
            if "关键词" in st or "keyword" in st.lower():
                adjustments[i] += 0.25
        if wants_author and bt == "paragraph" and pg == "1":
            adjustments[i] += 0.15
        if st and section_nums:
            for sn in section_nums:
                if sn in st or any(sn in part for part in st.split() if part):
                    adjustments[i] += 0.20
                    break

        overlap = len(set(_normalize(query)) & set(_normalize(text[:300])))
        if overlap > 5:
            adjustments[i] += 0.04 * min(overlap, 15)
        if not is_title_query and _is_generic_title_chunk(chunk):
            adjustments[i] -= 0.15
        if not is_title_query and pg == "1" and bt == "heading":
            if re.search(r"[a-z]", text) and not re.search(r"[\u4e00-\u9fff]", text):
                adjustments[i] -= 0.08

    return [n + adj for n, adj in zip(_normalize_score_list(scores), adjustments)]


def build_report_v4(pdf_path: str, cases: list[dict], out_path: str, mode: str = "all", rerank_mode: str = "none"):
    title = Path(pdf_path).stem

    print("Building chunks...")
    page_chunks = build_page_mode_chunks(pdf_path, title=title)
    struct_chunks = build_structured_chunks(pdf_path, title=title)
    print(f"  page-mode: {len(page_chunks)} chunks")
    print(f"  structured: {len(struct_chunks)} chunks")

    backend = _get_embedding_backend()
    print(f"Embedding: {type(backend).__name__ if backend else 'dummy'}")

    page_bundle = prepare_retrieval_bundle(page_chunks, backend)
    struct_bundle = prepare_retrieval_bundle(struct_chunks, backend)

    mode_labels = {
        "page": "Page-Mode",
        "structured": "Structured",
        "structured+simple": "Structured+Simple",
        "structured+heuristic_v2": "Structured+HeuristicV2",
        "structured+hybrid+soft_v3": "Structured+Hybrid+SoftV3",
        "structured_hybrid": "Structured+Hybrid",
    }
    mode_plans = {
        "page": {"bundle": page_bundle, "query_mode": "page", "rerank": "none", "chunk_source": page_chunks},
        "structured": {"bundle": struct_bundle, "query_mode": "structured", "rerank": "none", "chunk_source": struct_chunks},
        "structured+simple": {"bundle": struct_bundle, "query_mode": "structured", "rerank": "simple", "chunk_source": struct_chunks},
        "structured+heuristic_v2": {"bundle": struct_bundle, "query_mode": "structured", "rerank": "heuristic_v2", "chunk_source": struct_chunks},
        "structured+hybrid+soft_v3": {"bundle": struct_bundle, "query_mode": "structured_hybrid", "rerank": "soft_v3", "chunk_source": struct_chunks},
        "structured_hybrid": {"bundle": struct_bundle, "query_mode": "structured_hybrid", "rerank": "none", "chunk_source": struct_chunks},
    }

    if mode == "all":
        active_modes = [
            "page",
            "structured",
            "structured+simple",
            "structured+heuristic_v2",
            "structured+hybrid+soft_v3",
        ]
    elif mode == "page":
        active_modes = ["page"]
    elif mode == "structured":
        if rerank_mode == "none":
            active_modes = ["structured"]
        elif rerank_mode == "simple":
            active_modes = ["structured+simple"]
        elif rerank_mode == "heuristic_v2":
            active_modes = ["structured+heuristic_v2"]
        else:
            raise ValueError("--mode structured does not support --rerank soft_v3; use --mode structured_hybrid")
    elif mode == "structured_hybrid":
        active_modes = ["structured_hybrid" if rerank_mode == "none" else "structured+hybrid+soft_v3"]
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    all_results: dict[str, dict] = {}
    topk = max(case.get("top_k", 5) for case in cases) if cases else 5
    for case in cases:
        cid = case.get("id", case["query"][:30])
        all_results[cid] = {}
        case_limit = case.get("top_k", topk)
        for active_mode in active_modes:
            plan = mode_plans[active_mode]
            all_results[cid][active_mode] = run_query(
                plan["bundle"],
                case["query"],
                case_limit,
                backend,
                mode=plan["query_mode"],
                rerank=plan["rerank"],
                dense_top_n=DEFAULT_DENSE_TOP_N,
                lexical_top_n=DEFAULT_LEXICAL_TOP_N,
                fusion_top_n=DEFAULT_FUSION_TOP_N,
            )

    page_stats = metadata_completeness(page_chunks)
    struct_stats = metadata_completeness(struct_chunks)

    def avg_chars(chunks: list[dict]) -> float:
        return round(sum(len(c["text"]) for c in chunks) / len(chunks), 1) if chunks else 0.0

    def mean(values: list[float]) -> float:
        return round(sum(values) / len(values), 3) if values else 0.0

    def mean_positive(values: list[int]) -> float:
        positives = [value for value in values if value > 0]
        return round(sum(positives) / len(positives), 3) if positives else 0.0

    agg: dict[str, dict] = {}
    for active_mode in active_modes:
        agg[active_mode] = {
            "page_hit@1": [], "page_hit@3": [], "page_hit@5": [],
            "section_hit@1": [], "section_hit@3": [], "section_hit@5": [],
            "keyword_hit@1": [], "keyword_hit@3": [], "keyword_hit@5": [],
            "bt_hit@1": [], "bt_hit@3": [], "bt_hit@5": [],
            "page_avg_match_rate@1": [], "page_avg_match_rate@3": [], "page_avg_match_rate@5": [],
            "section_avg_match_rate@1": [], "section_avg_match_rate@3": [], "section_avg_match_rate@5": [],
            "keyword_avg_match_rate@1": [], "keyword_avg_match_rate@3": [], "keyword_avg_match_rate@5": [],
            "bt_avg_match_rate@1": [], "bt_avg_match_rate@3": [], "bt_avg_match_rate@5": [],
            "mrr_page": [], "mrr_section": [],
            "title_attraction": [],
            "first_correct_rank_page": [],
            "first_correct_rank_section": [],
        }

    for case in cases:
        cid = case.get("id", case["query"][:30])
        case_limit = case.get("top_k", topk)
        for active_mode in active_modes:
            met = compute_metrics(
                mode_plans[active_mode]["chunk_source"],
                all_results[cid][active_mode],
                case,
                case_limit,
            )
            for key in agg[active_mode]:
                agg[active_mode][key].append(met[key])

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    mode_str = ", ".join(mode_labels[m] for m in active_modes)
    bt_counts: dict[str, int] = {}
    for chunk in struct_chunks:
        bt = chunk.get("block_type", "unknown")
        bt_counts[bt] = bt_counts.get(bt, 0) + 1

    p5 = {m: mean(agg[m]["page_hit@5"]) for m in active_modes}
    s5 = {m: mean(agg[m]["section_hit@5"]) for m in active_modes}
    ta = {m: mean(agg[m]["title_attraction"]) * 100 for m in active_modes}

    selected_case_ids = ["title_ch", "fig2", "table1", "abstract_cn", "def_edge_intel"]
    selected_cases = [case for case in cases if case.get("id") in selected_case_ids]
    if len(selected_cases) < 3:
        selected_cases = cases[:max(3, min(len(cases), 5))]

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Chunking Evaluation Report v4\n\n")
        f.write(f"**PDF:** `{pdf_path}`\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**Embedding:** {type(backend).__name__ if backend else 'dummy'}  \n")
        f.write(f"**Mode selection:** {mode}  \n")
        f.write(f"**Active modes:** {mode_str}\n\n")

        f.write("## 1. Evaluation Config\n\n")
        f.write(f"- Cases: **{len(cases)}** query cases\n")
        f.write(f"- Top-k: **{topk}**\n")
        f.write(f"- Dense candidate top_n: **{DEFAULT_DENSE_TOP_N}**\n")
        f.write(f"- Lexical candidate top_n: **{DEFAULT_LEXICAL_TOP_N}**\n")
        f.write(f"- Fusion candidate top_n: **{DEFAULT_FUSION_TOP_N}**\n")
        f.write(f"- Fusion method: **RRF (k={DEFAULT_RRF_K})**\n")
        f.write("- Fairness note: all modes use the same dense retrieval budget; `structured_hybrid` adds a lexical candidate pool of the same size before fusion.\n")
        f.write("- Soft_v3 formula: `0.55*fusion_norm + 0.25*dense_norm + 0.10*lexical_norm + 0.10*keyword_overlap + intent bonuses - generic_title_penalty`\n")
        f.write("- Soft_v3 intent bonuses are small additive terms for `section_title match`, `block_type match`, `explicit anchor`, and `page-1 front matter`; it does not hard override the base retrieval score.\n\n")
        f.write("### Metric Definitions\n\n")
        f.write("- `hit@k = 1` if at least one correct result appears within top-k, else `0`.\n")
        f.write("- `avg_match_rate@k = (# correct results within top-k) / k_actual`, where `k_actual = min(k, returned_results)`.\n")
        f.write("- `MRR = 1 / first_correct_rank` if a correct result exists, else `0`.\n")
        f.write("- `first_correct_rank` is the 1-based rank of the first correct result; if no correct result exists, it is reported as `-1` in raw metrics and omitted from the mean-positive aggregate.\n\n")

        f.write("## 2. Chunk Statistics\n\n")
        f.write("| Metric | Page-Mode | Structured |\n")
        f.write("|--------|-----------|------------|\n")
        f.write(f"| Total chunks | {len(page_chunks)} | {len(struct_chunks)} |\n")
        f.write(f"| Avg chars | {avg_chars(page_chunks)} | {avg_chars(struct_chunks)} |\n")
        f.write(f"| page_start complete | {page_stats.get('page_start_complete', 'N/A')} | {struct_stats.get('page_start_complete', 'N/A')} |\n")
        f.write(f"| section_title non-empty | {page_stats.get('section_title_nonempty', 'N/A')} | {struct_stats.get('section_title_nonempty', 'N/A')} |\n")
        f.write(f"| block_type known | {page_stats.get('block_type_known', 'N/A')} | {struct_stats.get('block_type_known', 'N/A')} |\n")
        f.write(f"| block_type dist | (n/a) | {dict(bt_counts)} |\n\n")

        f.write("## 3. Automatic Metrics Summary\n\n")
        f.write(f"_Mean over {len(cases)} cases_\n\n")

        f.write("### 3a. Page / Section / Keyword Hit (@1 / @3 / @5)\n\n")
        f.write("| Mode | page_hit@1 | page_hit@3 | page_hit@5 | section_hit@1 | section_hit@3 | section_hit@5 | keyword_hit@1 | keyword_hit@3 | keyword_hit@5 |\n")
        f.write("|------|------------|------------|------------|---------------|---------------|---------------|---------------|---------------|---------------|\n")
        for active_mode in active_modes:
            f.write(
                f"| {mode_labels[active_mode]} | "
                f"{mean(agg[active_mode]['page_hit@1'])} | "
                f"{mean(agg[active_mode]['page_hit@3'])} | "
                f"{mean(agg[active_mode]['page_hit@5'])} | "
                f"{mean(agg[active_mode]['section_hit@1'])} | "
                f"{mean(agg[active_mode]['section_hit@3'])} | "
                f"{mean(agg[active_mode]['section_hit@5'])} | "
                f"{mean(agg[active_mode]['keyword_hit@1'])} | "
                f"{mean(agg[active_mode]['keyword_hit@3'])} | "
                f"{mean(agg[active_mode]['keyword_hit@5'])} |\n"
            )
        f.write("\n")

        f.write("### 3b. Block-Type Hit, First Correct Rank, MRR, Title Attraction\n\n")
        f.write("| Mode | bt_hit@1 | bt_hit@3 | bt_hit@5 | first_correct_rank(page) | first_correct_rank(section) | mrr_page | mrr_section | title_attraction% |\n")
        f.write("|------|----------|----------|----------|--------------------------|-----------------------------|----------|-------------|------------------|\n")
        for active_mode in active_modes:
            f.write(
                f"| {mode_labels[active_mode]} | "
                f"{mean(agg[active_mode]['bt_hit@1'])} | "
                f"{mean(agg[active_mode]['bt_hit@3'])} | "
                f"{mean(agg[active_mode]['bt_hit@5'])} | "
                f"{mean_positive(agg[active_mode]['first_correct_rank_page'])} | "
                f"{mean_positive(agg[active_mode]['first_correct_rank_section'])} | "
                f"{mean(agg[active_mode]['mrr_page'])} | "
                f"{mean(agg[active_mode]['mrr_section'])} | "
                f"{ta[active_mode]:.1f}% |\n"
            )
        f.write("\n")

        f.write("### 3c. Avg Match Rate (@1 / @3 / @5)\n\n")
        f.write("| Mode | page_avg_match_rate@1 | page_avg_match_rate@3 | page_avg_match_rate@5 | section_avg_match_rate@1 | section_avg_match_rate@3 | section_avg_match_rate@5 | keyword_avg_match_rate@1 | keyword_avg_match_rate@3 | keyword_avg_match_rate@5 |\n")
        f.write("|------|-----------------------|-----------------------|-----------------------|--------------------------|--------------------------|--------------------------|--------------------------|--------------------------|--------------------------|\n")
        for active_mode in active_modes:
            f.write(
                f"| {mode_labels[active_mode]} | "
                f"{mean(agg[active_mode]['page_avg_match_rate@1'])} | "
                f"{mean(agg[active_mode]['page_avg_match_rate@3'])} | "
                f"{mean(agg[active_mode]['page_avg_match_rate@5'])} | "
                f"{mean(agg[active_mode]['section_avg_match_rate@1'])} | "
                f"{mean(agg[active_mode]['section_avg_match_rate@3'])} | "
                f"{mean(agg[active_mode]['section_avg_match_rate@5'])} | "
                f"{mean(agg[active_mode]['keyword_avg_match_rate@1'])} | "
                f"{mean(agg[active_mode]['keyword_avg_match_rate@3'])} | "
                f"{mean(agg[active_mode]['keyword_avg_match_rate@5'])} |\n"
            )
        f.write("\n")

        f.write("## 4. Per-Case Metrics (standard hit@5)\n\n")
        headers = ["_p@5_ | _s@5_ | _k@5_ | _bt@5_" for _ in active_modes]
        f.write("| Case | " + " | ".join(headers) + " |\n")
        f.write("|------|" + "|".join(["---"] * len(active_modes)) + "|\n")
        for case in cases:
            cid = case.get("id", case["query"][:30])
            row_parts = [f"**{cid}**"]
            for active_mode in active_modes:
                met = compute_metrics(
                    mode_plans[active_mode]["chunk_source"],
                    all_results[cid][active_mode],
                    case,
                    case.get("top_k", topk),
                )
                row_parts.append(f"{met['page_hit@5']} | {met['section_hit@5']} | {met['keyword_hit@5']} | {met['bt_hit@5']}")
            f.write("| " + " | ".join(row_parts) + " |\n")
        f.write("\n")

        f.write("## 5. Representative Query Comparison\n\n")
        for idx, case in enumerate(selected_cases, start=1):
            cid = case.get("id", case["query"][:30])
            f.write(f"### {idx}. [{cid}] {case['query']}\n\n")
            if case.get("notes"):
                f.write(f"*Notes: {case['notes']}*\n\n")
            for active_mode in active_modes:
                f.write(f"**{mode_labels[active_mode]}** (top-3):\n\n")
                for rank, result in enumerate(all_results[cid][active_mode][:3], start=1):
                    f.write(
                        f"  [{rank}] p{result['page']} [{result['block_type']}] "
                        f"section={result.get('section_title', '')!r} "
                        f"score={result['score']} dense={result['dense_score']} lexical={result['lexical_score']} fusion={result['fusion_score']} "
                        f"text={result['text_preview'][:80]}...\n"
                    )
                f.write("\n")

        f.write("## 6. Conclusions\n\n")
        if "structured" in active_modes and "page" in active_modes:
            f.write(
                f"- Chunking gain: Structured page_hit@5={p5['structured']} vs Page-Mode={p5['page']}; "
                f"Structured section_hit@5={s5['structured']} vs Page-Mode={mean(agg['page']['section_hit@5'])}.\n"
            )
            f.write(
                f"- Page-mode keyword_hit@5 may still read higher because it has {len(page_chunks)} large chunks averaging {avg_chars(page_chunks)} chars, "
                f"while structured mode has {len(struct_chunks)} smaller chunks averaging {avg_chars(struct_chunks)} chars. "
                "This is a **big-chunk keyword bias**, not evidence that page-mode retrieval is better.\n"
            )
            f.write("- Interpretation: structured chunking already improved localization and metadata completeness; the remaining instability is mainly in retrieval / ranking rather than chunk construction.\n")
        if "structured+simple" in active_modes and "structured" in active_modes:
            f.write(f"- Ranking delta: Structured+Simple page_hit@5={p5['structured+simple']} vs Structured={p5['structured']}.\n")
        if "structured+heuristic_v2" in active_modes and "structured" in active_modes:
            f.write(
                f"- Ranking delta: Structured+HeuristicV2 page_hit@5={p5['structured+heuristic_v2']} vs Structured={p5['structured']}; "
                f"title_attraction={ta['structured+heuristic_v2']:.1f}% vs {ta['structured']:.1f}%.\n"
            )
        if "structured+hybrid+soft_v3" in active_modes and "structured" in active_modes:
            f.write(
                f"- Hybrid + Soft_v3 delta: Structured+Hybrid+SoftV3 page_hit@5={p5['structured+hybrid+soft_v3']} vs Structured={p5['structured']}; "
                f"section_hit@5={s5['structured+hybrid+soft_v3']} vs {s5['structured']}; "
                f"title_attraction={ta['structured+hybrid+soft_v3']:.1f}% vs {ta['structured']:.1f}%.\n"
            )
            f.write("- Interpretation: this comparison isolates retrieval / ranking changes on top of the existing structured chunking baseline.\n")

    print(f"\nReport: {out_path}")
    return out_path


DEFAULT_CASES = [
    # Title / front matter
    {"id": "title_ch", "query": "这篇论文的标题是什么？",
     "expected_page": 1, "expected_section_title": "", "expected_keywords": ["边缘智能", "协同推理"],
     "notes": "Chinese title → heading block on page 1"},
    {"id": "author", "query": "作者单位和联系邮箱是什么？",
     "expected_page": 1, "expected_keywords": ["北京科技大学", "wangrui"],
     "notes": "Author/affiliation → paragraph block page 1"},
    {"id": "abstract_en", "query": "Abstract讲了什么？",
     "expected_page": 1, "expected_section_title": "Abstract",
     "expected_keywords": ["edge intelligence", "collaborative inference"],
     "notes": "English Abstract with section_title=Abstract"},
    {"id": "abstract_cn", "query": "中文摘要主要说了什么？",
     "expected_page": 1, "expected_section_title": "摘 要",
     "expected_keywords": ["边缘智能", "云计算", "实时性"],
     "notes": "Chinese abstract with section_title=摘 要"},
    {"id": "keywords", "query": "论文的关键词有哪些？",
     "expected_page": 1, "expected_keywords": ["边缘计算", "边缘智能", "机器学习"],
     "notes": "Keywords heading page 1"},

    # Section-specific (precise section numbers)
    {"id": "sec_1_1", "query": "1.1 节标题和主要内容是什么？",
     "expected_page": 2, "expected_section_title": "边缘协同智能发展",
     "expected_keywords": ["边缘协同智能", "发展"],
     "notes": "Section 1.1 → heading on page 2"},
    {"id": "sec_1_2", "query": "1.2 节主要讲了什么过程？",
     "expected_page": 3, "expected_section_title": "边缘协同推理的整体过程",
     "expected_keywords": ["协同推理", "整体过程", "Docker"],
     "notes": "Section 1.2 → heading on page 3"},
    {"id": "sec_1_3", "query": "1.3 节说明本文与已有综述相比有什么贡献？",
     "expected_page": 4, "expected_section_title": "与已有综述研究的比较以及本文的贡献",
     "expected_keywords": ["贡献", "综述", "比较"],
     "notes": "Section 1.3 → heading on page 4"},

    # Technical methods
    {"id": "model_cut", "query": "2.1.1 模型切割方法有哪些？",
     "expected_page": 4, "expected_section_title": "模型切割",
     "expected_keywords": ["模型切割", "纵切", "横切"],
     "notes": "Section 2.1.1 → heading block_type=heading"},
    {"id": "compression", "query": "模型压缩方法有哪些？",
     "expected_page": 6, "expected_section_title": "模型压缩",
     "expected_keywords": ["模型压缩", "量化", "剪枝"],
     "notes": "Section 2.1.2 → heading block"},

    # Caption/figure questions
    {"id": "fig1", "query": "图 1 反映的是什么内容？",
     "expected_page": 2, "expected_keywords": ["边缘智能", "发展趋势", "图1"],
     "notes": "Figure 1 caption → block_type=caption page 2"},
    {"id": "table1", "query": "表 1 比较了哪些模型切割方法？",
     "expected_page": 5, "expected_section_title": "模型切割",
     "expected_keywords": ["模型切割", "纵切", "横切", "表1"],
     "notes": "Table 1 caption → block_type=caption page 5"},

    # Definition/concept
    {"id": "def_edge_intel", "query": "边缘智能的定义是什么？",
     "expected_page": 1, "expected_keywords": ["边缘智能", "定义"],
     "notes": "Definition question; top result should be page 1 content"},
    {"id": "overall_arch", "query": "2.2 节整体架构是怎样的？",
     "expected_page": 8, "expected_section_title": "整体架构",
     "expected_keywords": ["整体架构", "云", "边缘"],
     "notes": "Section 2.2 → heading on page 8"},
]


def main():
    parser = argparse.ArgumentParser(
        description="Compare page-mode vs structured PDF chunking with metrics")
    parser.add_argument("--pdf", required=True, help="Path to PDF file")
    parser.add_argument("--cases", default=None, help="Path to eval cases JSON")
    parser.add_argument("--report", default="eval/chunking_eval_report_v4.md")
    parser.add_argument("--query", default=None, help="Run single query only")
    parser.add_argument(
        "--mode",
        default="all",
        choices=["all", "page", "structured", "structured_hybrid"],
        help="Retrieval mode: all (default), page, structured, or structured_hybrid",
    )
    parser.add_argument("--rerank", default="none",
                        choices=["none", "simple", "heuristic_v2", "soft_v3"],
                        help="Rerank strategy: none, simple, heuristic_v2, or soft_v3")
    args = parser.parse_args()

    if args.cases:
        with open(args.cases, encoding="utf-8") as f:
            cases = json.load(f)
    else:
        cases = DEFAULT_CASES

    if args.query:
        cases = [{"id": "single", "query": args.query, "top_k": 5}]

    build_report_v4(args.pdf, cases, args.report, mode=args.mode, rerank_mode=args.rerank)


if __name__ == "__main__":
    main()
