"""Unit tests for the front-matter-aware reranker port (PRD FR-3b)."""

from __future__ import annotations

from app.rag.frontmatter_rerank import (
    FrontMatterAwareReranker,
    extract_query_intent,
    front_matter_role,
)
from app.rag.postprocess import HeuristicReranker
from app.rag.retrieval_models import RetrievedChunk


def _hit(
    chunk_id: str,
    text: str,
    *,
    page: int | None = None,
    block_type: str = "",
    order: int = 0,
    section: str = "",
    distance: float | None = 0.5,
) -> RetrievedChunk:
    return RetrievedChunk.from_raw(
        text=text,
        metadata={
            "doc_id": "doc1",
            "chunk_id": f"doc1:{chunk_id}",
            "source": "paper.pdf",
            "title": "Paper",
            "section": section,
            "page": page,
            "block_type": block_type,
            "order_in_doc": order,
        },
        distance=distance,
    )


def _page1_title_hit() -> RetrievedChunk:
    return _hit(
        "0",
        "Efficient Retrieval Augmented Generation for Knowledge Bases",
        page=1,
        block_type="heading",
        order=0,
        distance=0.9,
    )


class TestQueryIntent:
    def test_english_title_query(self):
        features = extract_query_intent("What is the article title of this paper?")
        assert features["intent"] == "title_query"
        assert features["wants_english"] is True

    def test_chinese_author_query(self):
        features = extract_query_intent("这篇论文的作者是谁")
        assert features["intent"] == "author_query"

    def test_affiliation_query_not_author(self):
        features = extract_query_intent("作者所属单位是什么")
        assert features["intent"] == "affiliation_query"

    def test_abstract_and_keywords(self):
        assert extract_query_intent("abstract of the paper")["intent"] == "abstract_query"
        assert extract_query_intent("论文关键词有哪些")["intent"] == "keywords_query"

    def test_fact_query(self):
        assert extract_query_intent("这篇论文的基金项目编号")["intent"] == "front_matter_fact_query"

    def test_plain_question_stays_fact_query(self):
        assert extract_query_intent("how does the system store data")["intent"] == "fact_query"


class TestRoleDetection:
    def test_english_title_role(self):
        hit = _page1_title_hit()
        assert front_matter_role(hit) == "title_en"

    def test_chinese_abstract_heading_role(self):
        hit = _hit("2", "摘 要", page=1, block_type="heading", order=2)
        assert front_matter_role(hit) == "abstract_heading_cn"

    def test_keywords_role(self):
        hit = _hit("3", "关键词 检索增强；知识库", page=1, block_type="heading", order=3)
        assert front_matter_role(hit) == "keywords_cn"

    def test_affiliation_paragraph_role(self):
        hit = _hit(
            "1",
            "Wang Rui@example.edu School of Computer Science",
            page=1,
            block_type="paragraph",
            order=1,
        )
        assert front_matter_role(hit) == "author_affiliation"

    def test_page_two_has_no_role(self):
        hit = _hit("9", "Abstract body text", page=2, block_type="paragraph", order=9)
        assert front_matter_role(hit) is None

    def test_abstract_body_role(self):
        hit = _hit("5", "We study retrieval augmented generation.", page=1, block_type="paragraph", order=5, section="Abstract")
        assert front_matter_role(hit) == "abstract_body_en"


class TestFrontMatterAwareReranker:
    def test_title_query_promotes_title_chunk(self):
        title_hit = _page1_title_hit()
        body_hit = _hit(
            "10",
            "The title of related systems differs. Title mentions appear here too.",
            page=3,
            block_type="paragraph",
            order=10,
            distance=0.4,
        )
        reranker = FrontMatterAwareReranker(HeuristicReranker())
        ranked = reranker.rerank("What is the English title of this paper?", [body_hit, title_hit])
        assert ranked[0].chunk_id == title_hit.chunk_id

    def test_author_query_promotes_affiliation_block(self):
        affil_hit = _hit(
            "1",
            "Sarah Chen, University of Example, chen@example.edu",
            page=1,
            block_type="paragraph",
            order=1,
            distance=0.8,
        )
        other = _hit(
            "12",
            "Authors of prior work used similar methods for ranking and evaluation pipelines.",
            page=2,
            block_type="paragraph",
            order=12,
            distance=0.3,
        )
        reranker = FrontMatterAwareReranker(HeuristicReranker())
        ranked = reranker.rerank("Who are the authors of this paper?", [other, affil_hit])
        assert ranked[0].chunk_id == affil_hit.chunk_id

    def test_non_frontmatter_query_matches_heuristic_order(self):
        hits = [
            _hit("a", "storage design uses chroma persistence", page=4, order=20, distance=0.6),
            _hit("b", "chroma storage layer keeps vectors on disk", page=5, order=21, distance=0.2),
        ]
        base_order = [h.chunk_id for h in HeuristicReranker().rerank("How does chroma storage persist data?", list(hits))]
        wrapped = FrontMatterAwareReranker(HeuristicReranker())
        fm_order = [h.chunk_id for h in wrapped.rerank("How does chroma storage persist data?", list(hits))]
        assert fm_order == base_order
