"""Front-matter-aware reranker ported from the chunking experiments (PRD FR-3b).

This is the production adaptation of ``soft_rerank_v4_frontmatter`` from
``scripts/eval_chunking.py``. The experiment re-scored candidates with its own
dense/lexical/fusion pipeline; here the same role-bonus/penalty layer is
applied on top of the production heuristic base score, so the port changes
ordering only through front-matter evidence while keeping the existing
distance+lexical behavior intact.

Gated behind ``settings.frontmatter_rerank_enabled`` (default off) until the
multi-document regression harness reports a baseline (PRD: 先泛化验证再上线).
"""

from __future__ import annotations

import logging
import math
import re

from app.rag.retrieval_models import RetrievedChunk

logger = logging.getLogger(__name__)

FRONT_MATTER_INTENTS = frozenset(
    {
        "title_query",
        "author_query",
        "affiliation_query",
        "abstract_query",
        "keywords_query",
        "front_matter_fact_query",
    }
)

_TITLE_WORDS = ("标题", "题目", "title", "article title")
_ABSTRACT_WORDS = ("摘要", "abstract")
_KEYWORDS_WORDS = ("关键字", "关键词", "key words", "keywords")
_AUTHOR_WORDS = ("作者", "第一作者", "authors", "author")
_AFFILIATION_EXCLUDE_WORDS = ("单位", "机构", "affiliation", "school", "university", "邮箱", "email")
_AFFILIATION_WORDS = ("单位", "机构", "affiliation", "school", "university", "college", "邮箱", "email")
_FACT_WORDS = ("收稿", "修回", "分类号", "中图法", "基金", "项目", "doi", "作者简介")

_FACT_ANCHOR_ROLES = {
    "收稿": {"fact_recv"},
    "修回": {"fact_recv"},
    "分类号": {"fact_clc"},
    "中图法": {"fact_clc"},
    "基金": {"fact_funding", "fact_funding_body"},
    "项目": {"fact_funding", "fact_funding_body"},
    "doi": {"fact_funding_body"},
}
_FACT_TEXT_ANCHORS = ("收稿日期", "修回日期", "中图分类号", "基金项目", "DOI")

_SECTION_NUM_RE = re.compile(r"\d+(?:\.\d+)+")
_TABLE_RE = re.compile(r"(表\s*\d+|table\s*\d+)", re.IGNORECASE)
_FIGURE_RE = re.compile(r"(图\s*\d+|figure\s*\d+)", re.IGNORECASE)
_ASCII_LETTER_RE = re.compile(r"[A-Za-z]")
_WHITESPACE_RE = re.compile(r"\s+")


def extract_query_intent(query: str) -> dict[str, object]:
    """Port of the experiment's query-intent extraction for front matter."""

    q_lower = str(query or "").lower()
    section_nums = _SECTION_NUM_RE.findall(q_lower)
    title_query = any(word in q_lower for word in _TITLE_WORDS)
    table_query = bool(_TABLE_RE.search(query))
    figure_query = bool(_FIGURE_RE.search(query))
    section_query = bool(section_nums) or any(word in q_lower for word in ("节", "章", "section"))
    abstract_query = any(word in q_lower for word in _ABSTRACT_WORDS)
    keywords_query = any(word in q_lower for word in _KEYWORDS_WORDS)
    author_query = (
        any(word in q_lower for word in _AUTHOR_WORDS)
        and not any(word in q_lower for word in _AFFILIATION_EXCLUDE_WORDS)
    )
    affiliation_query = any(word in q_lower for word in _AFFILIATION_WORDS)
    fact_query = any(word in q_lower for word in _FACT_WORDS)

    intent = "fact_query"
    if title_query:
        intent = "title_query"
    elif author_query:
        intent = "author_query"
    elif affiliation_query:
        intent = "affiliation_query"
    elif table_query:
        intent = "table_query"
    elif figure_query:
        intent = "figure_query"
    elif section_query:
        intent = "section_query"
    elif abstract_query:
        intent = "abstract_query"
    elif keywords_query:
        intent = "keywords_query"
    elif fact_query:
        intent = "front_matter_fact_query"

    ascii_letters = len(_ASCII_LETTER_RE.findall(query))
    wants_english = ascii_letters >= max(2, int(len(q_lower.replace(" ", "")) * 0.3))
    wants_chinese = not wants_english
    wants_first_author = "第一作者" in q_lower or "first author" in q_lower

    return {
        "intent": intent,
        "wants_english": wants_english,
        "wants_chinese": wants_chinese,
        "wants_first_author": wants_first_author,
    }


def front_matter_role(hit: RetrievedChunk) -> str | None:
    """Classify one page-1 structured chunk into a front-matter role.

    Ported from the experiment's role detection; operates on production
    ``RetrievedChunk`` fields (``extra_metadata.block_type``, page ints).
    """

    if hit.page != 1:
        return None

    text = (hit.text or "").strip()
    if not text:
        return None
    text_n = _WHITESPACE_RE.sub(" ", text).strip().lower()
    block_type = str(hit.extra_metadata.get("block_type") or "")
    section_title = hit.section or str(hit.extra_metadata.get("section_title") or "")
    section_n = _WHITESPACE_RE.sub(" ", section_title).strip().lower()
    order = _chunk_order(hit)
    ascii_ratio = len(_ASCII_LETTER_RE.findall(text)) / max(len(text), 1)

    if block_type == "heading":
        if text_n == "abstract":
            return "abstract_heading_en"
        if text in {"摘 要", "摘要"}:
            return "abstract_heading_cn"
        if text.startswith("Key words") or text_n.startswith("keywords"):
            return "keywords_en"
        if text.startswith("关键词"):
            return "keywords_cn"
        if "中图分类号" in text:
            return "fact_clc"
        if "收稿日期" in text or "修回日期" in text:
            return "fact_recv"
        if "基金项目" in text:
            return "fact_funding"
        if "作者简介" in text:
            return "fact_author_bio"
        if order <= 4 and not section_n:
            if ascii_ratio >= 0.65 and "abstract" not in text.lower() and "key words" not in text.lower():
                return "title_en"
            if len(text) <= 40:
                return "title_cn"

    if block_type == "paragraph":
        if section_n == "abstract":
            return "abstract_body_en"
        if section_n == "摘要" or "摘要" in section_title:
            return "abstract_body_cn"
        if "国家自然科学基金" in text or "this work was supported" in text.lower():
            return "fact_funding_body"
        if order <= 4 and any(
            token in text
            for token in ("@", "大学", "学院", "研究院", "School", "University", "Institute", "Laboratory")
        ):
            return "author_affiliation"

    return None


class FrontMatterAwareReranker:
    """Heuristic reranker plus the v4 front-matter bonus/penalty layer."""

    def __init__(self, base) -> None:
        self._base = base

    def rerank(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        base_ranked = self._base.rerank(query, hits)
        features = extract_query_intent(query)
        if features["intent"] not in FRONT_MATTER_INTENTS or not base_ranked:
            return base_ranked

        query_terms = set(_lexical_terms(query))
        scored: list[tuple[float, RetrievedChunk]] = []
        for index, hit in enumerate(base_ranked):
            adjustment = self._front_matter_adjustment(features, hit, query_terms, index)
            score = (hit.rerank_score or 0.0) + adjustment
            scored.append((score, hit.with_updates(rerank_score=round(score, 6))))

        scored.sort(key=lambda item: item[0], reverse=True)
        result = [hit for _, hit in scored]
        logger.debug(
            "FrontMatterAwareReranker executed: intent=%s hits=%d",
            features["intent"],
            len(result),
        )
        return result

    def _front_matter_adjustment(
        self,
        features: dict[str, object],
        hit: RetrievedChunk,
        query_terms: set[str],
        index: int,
    ) -> float:
        text = (hit.text or "").strip()
        section_title = hit.section or str(hit.extra_metadata.get("section_title") or "")
        block_type = str(hit.extra_metadata.get("block_type") or "")
        page_one = hit.page == 1
        role = front_matter_role(hit)
        order = _chunk_order(hit)
        intent = str(features["intent"])

        combined_terms = set(_lexical_terms(f"{section_title} {text[:400]}"))
        overlap_ratio = (
            len(query_terms & combined_terms) / max(len(query_terms), 1)
            if query_terms
            else 0.0
        )

        front_bonus = 0.0
        front_penalty = 0.0
        anchor_bonus = 0.0
        block_type_bonus = 0.0
        generic_penalty = 0.0

        if page_one and role:
            front_bonus += 0.04
        if order <= 4 and page_one:
            front_bonus += 0.02

        wants_english = bool(features["wants_english"])

        if intent == "title_query":
            if role == "title_en" and wants_english:
                front_bonus += 0.52
            elif role == "title_cn" and not wants_english:
                front_bonus += 0.52
            elif role in {"title_cn", "title_en"}:
                front_bonus += 0.18
            elif role and role.startswith(("abstract_", "keywords_", "fact_")):
                front_penalty += 0.18
            if wants_english and role == "title_cn":
                front_penalty += 0.16
            if not wants_english and role == "title_en":
                front_penalty += 0.12
            if role == "author_affiliation":
                front_penalty += 0.10
            if block_type == "heading" and page_one:
                block_type_bonus += 0.08
        elif intent in {"author_query", "affiliation_query"}:
            if role == "author_affiliation":
                front_bonus += 0.34
                if features["wants_first_author"]:
                    front_bonus += 0.04
            elif role in {"title_cn", "title_en"}:
                front_penalty += 0.10
            elif role and role.startswith(("abstract_", "keywords_", "fact_")):
                front_penalty += 0.12
            if block_type == "paragraph" and page_one:
                block_type_bonus += 0.10
            if any(token in text for token in ("@", "大学", "学院", "研究院", "School", "University")):
                anchor_bonus += 0.08
        elif intent == "abstract_query":
            if wants_english:
                desired_roles = {"abstract_body_en"}
                heading_roles = {"abstract_heading_en"}
            elif features["wants_chinese"]:
                desired_roles = {"abstract_body_cn"}
                heading_roles = {"abstract_heading_cn"}
            else:
                desired_roles = {"abstract_body_cn", "abstract_body_en"}
                heading_roles = {"abstract_heading_cn", "abstract_heading_en"}
            if role in desired_roles:
                front_bonus += 0.48
            elif role in heading_roles:
                front_bonus += 0.12
            elif role and role.startswith(("title_", "keywords_", "fact_")):
                front_penalty += 0.14
            if role == "author_affiliation":
                front_penalty += 0.16
            if wants_english and role == "abstract_body_cn":
                front_penalty += 0.12
            if not wants_english and role == "abstract_body_en":
                front_penalty += 0.12
            if block_type == "paragraph" and page_one:
                block_type_bonus += 0.10
            if _section_match(section_title, "Abstract") or _section_match(section_title, "摘要"):
                anchor_bonus += 0.08
        elif intent == "keywords_query":
            desired_role = "keywords_en" if wants_english else "keywords_cn"
            if role == desired_role:
                front_bonus += 0.44
            elif role in {"keywords_cn", "keywords_en"}:
                front_bonus += 0.12
            elif role and role.startswith(("title_", "abstract_", "fact_")):
                front_penalty += 0.14
            if wants_english and role == "keywords_cn":
                front_penalty += 0.16
            if not wants_english and role == "keywords_en":
                front_penalty += 0.10
            if role == "author_affiliation":
                front_penalty += 0.10
            if text.startswith("关键词") or text.startswith("Key words"):
                anchor_bonus += 0.12
        elif intent == "front_matter_fact_query":
            matched_roles: set[str] = set()
            lowered_query = str(query).lower()
            for anchor, roles in _FACT_ANCHOR_ROLES.items():
                if anchor in lowered_query:
                    matched_roles |= roles
            if role in matched_roles:
                front_bonus += 0.30 if role and role.endswith("_body") else 0.38
            elif role and role.startswith("fact_"):
                front_bonus += 0.14
            elif role and role.startswith(("title_", "abstract_", "keywords_")):
                front_penalty += 0.14
            if role == "author_affiliation":
                front_penalty += 0.10
            if any(anchor.lower() in text.lower() for anchor in _FACT_TEXT_ANCHORS):
                anchor_bonus += 0.12

        if intent != "title_query" and _is_generic_title_chunk(text, block_type, page_one, section_title):
            generic_penalty = 0.06

        if not page_one:
            front_penalty += 0.10

        return (
            0.10 * overlap_ratio
            + block_type_bonus
            + anchor_bonus
            + front_bonus
            - front_penalty
            - generic_penalty
            - min(0.02 * index, 0.08)
        )


def _section_match(section_title: str, target: str) -> bool:
    return target.lower() in str(section_title or "").lower()


def _is_generic_title_chunk(text: str, block_type: str, page_one: bool, section_title: str) -> bool:
    stripped = (text or "").strip()
    if not page_one or block_type != "heading":
        return False
    if section_title.strip():
        return False
    if len(stripped) > 40 or re.match(r"^\d", stripped):
        return False
    return True


def _lexical_terms(text: str) -> list[str]:
    compact = str(text or "")
    terms: list[str] = []
    for token in re.findall(r"[a-z]{2,}|\d+(?:\.\d+)+", compact.lower()):
        terms.append(token)
    cjk_text = "".join(ch for ch in compact if "\u4e00" <= ch <= "\u9fff")
    terms.extend(cjk_text)
    terms.extend(cjk_text[i : i + 2] for i in range(len(cjk_text) - 1))
    return terms


def _chunk_order(hit: RetrievedChunk) -> int:
    raw = hit.extra_metadata.get("order_in_doc")
    try:
        return int(raw)
    except (TypeError, ValueError):
        tail = hit.chunk_id.rsplit(":", 1)[-1]
        try:
            return int(tail)
        except ValueError:
            return 999


def _short_log_guard(value: float) -> float:
    # Kept for parity with heuristic logging; avoids unused-import drift.
    return math.log(max(value, 1.0))
