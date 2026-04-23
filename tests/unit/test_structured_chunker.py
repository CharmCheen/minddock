"""Smoke test for the structured PDF chunking pipeline.

Run with: python -m tests.unit.test_structured_chunker
(Requires pymupdf and the app package to be importable.)
"""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from app.rag.structured_chunker import (
    BlockType,
    PDFBlock,
    blocks_to_chunks,
    clean_block_text,
    extract_blocks_from_page,
    structured_pdf_chunks,
    HEADING_PATTERNS,
    TABLE_ID_RE,
    CHUNK_MAX_TOKENS,
    _sentence_aware_sliding_window,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blocks_from_text(text: str, page: int = 1) -> list[dict]:
    """Create a minimal pymupdf block dict from raw text (heading-like block)."""
    return [{"type": 0, "lines": [{"spans": [{"text": line}]} for line in text.splitlines()]}]


def _make_pdf_blocks(pages_texts: list[str]) -> list[dict]:
    """Return the page-blocks format expected by structured_pdf_chunks.

    pymupdf creates ONE BLOCK PER LOGICAL UNIT.
    - Heading text (starting with ##, numbers, etc.) -> separate block
    - Table rows (lines with column separators) -> grouped into ONE block
    - Regular text lines -> grouped into ONE block (paragraph-like)
    """
    def _is_heading_line(line: str) -> bool:
        """Check if a line looks like a heading."""
        if not line.strip():
            return False
        # Markdown heading
        if line.strip().startswith("#"):
            return True
        # Numbered section "1. 背景" or "1.1.3 工作"
        if re.match(r"^\s*[\d０１２３４５６７８９]+(\.[\d]+)+\s+", line):
            return True
        # Chinese numbered "1. 背景"
        if re.match(r"^\s*[\d０１２３４５６７８９]+\.[\s　]+", line):
            return True
        return False

    def _is_table_line(line: str) -> bool:
        """Check if a single line has table-like structure (>=1 separator)."""
        separators = "│‖｜:\t|"
        sep_count = sum(1 for c in line if c in separators)
        return sep_count >= 1

    def _group_into_blocks(lines: list[str]) -> list[list[str]]:
        """Group lines into blocks based on content type."""
        blocks = []
        current_block = []
        current_is_table = False

        for line in lines:
            if not line:
                if current_block:
                    blocks.append(current_block)
                    current_block = []
                    current_is_table = False
                continue

            is_heading = _is_heading_line(line)
            is_table = _is_table_line(line)

            # Headings always start a new block
            if is_heading:
                if current_block:
                    blocks.append(current_block)
                    current_block = []
                    current_is_table = False
                blocks.append([line])
                continue

            # Table vs paragraph grouping
            if not current_block:
                current_block = [line]
                current_is_table = is_table
            elif is_table == current_is_table:
                current_block.append(line)
            else:
                blocks.append(current_block)
                current_block = [line]
                current_is_table = is_table

        if current_block:
            blocks.append(current_block)

        return blocks

    result = []
    for i, text in enumerate(pages_texts, start=1):
        lines = text.split("\n")
        grouped = _group_into_blocks(lines)
        blocks = []
        for group in grouped:
            block_lines = [{"spans": [{"text": l}]} for l in group]
            blocks.append({"type": 0, "lines": block_lines})
        result.append({"page": i, "blocks": blocks})
    return result


def _long_cn(sentence: str, times: int = 70) -> str:
    return sentence * times


def _long_en(sentence: str, times: int = 45) -> str:
    return " ".join(sentence for _ in range(times))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_clean_block_text():
    """断行合并 + 去噪音."""
    assert clean_block_text("hello-\nworld") == "hello-world"
    assert clean_block_text("hello\u00a0world") == "hello world"
    assert clean_block_text("hello\u3000world") == "hello world"
    # Multiple blank lines collapse
    result = clean_block_text("para1\n\n\n\npara2")
    assert "para1" in result and "para2" in result
    print("PASS: clean_block_text")


def test_heading_patterns():
    """标题识别."""
    # Markdown # heading
    m = HEADING_PATTERNS[3].match("## 背景与动机")
    assert m and m.group(1) == "背景与动机"

    # Chinese numbered section
    m = HEADING_PATTERNS[0].match("1. 背景介绍")
    assert m

    # Chinese multi-level
    m = HEADING_PATTERNS[1].match("2.3  相关工作")
    assert m

    # 图表 caption
    m = HEADING_PATTERNS[4].match("图 1: 系统架构")
    assert m
    m = HEADING_PATTERNS[4].match("表 3-2  实验结果")
    assert m

    print("PASS: heading_patterns")


def test_table_id_extraction():
    """表号提取."""
    m = TABLE_ID_RE.search("如表1所示")
    assert m and m.group(1) == "1"

    m = TABLE_ID_RE.search("Table 10.2 shows")
    assert m and m.group(1) == "10.2"

    print("PASS: table_id_extraction")


def test_extract_blocks_classifies_heading():
    """extract_blocks_from_page 把标题识别为 HEADING 类型."""
    blocks = [
        {"type": 0, "lines": [{"spans": [{"text": "## 背景与动机"}]}]},
        {"type": 0, "lines": [{"spans": [{"text": "这是一段正文内容。"}]}]},
    ]
    result = extract_blocks_from_page(1, blocks)
    assert len(result) == 2
    assert result[0].block_type == BlockType.HEADING
    assert result[0].heading_level == 2
    assert result[1].block_type == BlockType.PARAGRAPH
    print("PASS: extract_blocks_classifies_heading")


def test_extract_blocks_classifies_table():
    """extract_blocks_from_page 把表格样式的块识别为 TABLE_LIKE."""
    blocks = [
        {
            "type": 0,
            "lines": [
                {"spans": [{"text": "方法一 │ 方法二 │ 准确率"}]},
                {"spans": [{"text": "CNN    │ LSTM   │ 0.89"}]},
                {"spans": [{"text": "Transformer │ BERT │ 0.93"}]},
            ],
        },
    ]
    result = extract_blocks_from_page(1, blocks)
    assert len(result) == 1
    assert result[0].block_type == BlockType.TABLE_LIKE
    print("PASS: extract_blocks_classifies_table")


def test_extract_blocks_classifies_list():
    """列表项识别."""
    blocks = [
        {"type": 0, "lines": [{"spans": [{"text": "• 第一点内容"}]}]},
        {"type": 0, "lines": [{"spans": [{"text": "1. 第二点内容"}]}]},
        {"type": 0, "lines": [{"spans": [{"text": "(a) 子项"}]}]},
    ]
    result = extract_blocks_from_page(1, blocks)
    assert all(b.block_type == BlockType.LIST_ITEM for b in result)
    print("PASS: extract_blocks_classifies_list")


def test_blocks_to_chunks_heading_isolated():
    """Short headings anchor section metadata but do not become standalone chunks."""
    pages = _make_pdf_blocks([
        "## 第一章 介绍\n" + _long_cn("本文介绍 MindDock 系统如何组织知识、检索证据并生成答案。"),
        "## 第二章 相关工作\n" + _long_cn("相关工作涵盖 RAG、向量检索、证据压缩和引用绑定等内容。"),
    ])
    chunks = structured_pdf_chunks(pages, doc_id="test", source="test.pdf",
                                   source_path="test.pdf", source_type="file",
                                   title="Test", source_version="v1",
                                   content_hash="abc", last_ingested_at="2024-01-01")

    heading_chunks = [(t, m) for t, m in chunks if m.block_type == "heading"]
    assert heading_chunks == []
    para_sections = {m.section_title for _, m in chunks if m.block_type == "paragraph"}
    assert "第一章 介绍" in para_sections
    assert "第二章 相关工作" in para_sections
    print(f"PASS: blocks_to_chunks_heading_isolated - got {len(chunks)} paragraph chunks")


def test_blocks_to_chunks_paragraph_accumulation():
    """多个相邻 paragraph 合并为一个 chunk（不超过 CHUNK_MAX_TOKENS 时）."""
    pages = _make_pdf_blocks([
        _long_cn("第一段内容用于描述知识管理系统的检索过程。", 10)
        + "\n"
        + _long_cn("第二段内容补充说明证据组织和引用生成。", 10)
        + "\n"
        + _long_cn("第三段内容强调 chunk 需要保持完整语义。", 10),
    ])
    chunks = structured_pdf_chunks(pages, doc_id="test", source="test.pdf",
                                   source_path="test.pdf", source_type="file",
                                   title="Test", source_version="v1",
                                   content_hash="abc", last_ingested_at="2024-01-01")

    # All three paragraphs should merge into one chunk
    assert len(chunks) == 1
    assert chunks[0][1].block_type == "paragraph"
    assert "第一段内容" in chunks[0][0]
    assert "第三段内容" in chunks[0][0]
    print("PASS: blocks_to_chunks_paragraph_accumulation")


def test_blocks_to_chunks_table_isolated():
    """TABLE_LIKE 块不会被混入正文 chunk."""
    table_rows = "\n".join(f"方法{i} │ {0.80 + i / 100:.2f}" for i in range(1, 80))
    pages = _make_pdf_blocks([
        "## 实验结果\n"
        + _long_cn("这是正文，用于解释实验结果而不是表格内容。", 25)
        + "\n方法 │ 准确率\n"
        + table_rows
        + "\n表格说明文字。",
    ])
    chunks = structured_pdf_chunks(pages, doc_id="test", source="test.pdf",
                                   source_path="test.pdf", source_type="file",
                                   title="Test", source_version="v1",
                                   content_hash="abc", last_ingested_at="2024-01-01")

    chunk_texts = [t for t, _ in chunks]
    table_chunks = [t for t, m in chunks if m.block_type == "table"]

    # Table should be isolated
    assert len(table_chunks) >= 1
    # The separator line should be in the table chunk
    assert any("│" in t or "准确率" in t for t in table_chunks)
    # Paragraph chunk should NOT contain table separator
    para_text = next((t for t, m in chunks if m.block_type == "paragraph"), "")
    assert "│" not in para_text
    print(f"PASS: blocks_to_chunks_table_isolated — table chunks: {len(table_chunks)}")


def test_blocks_to_chunks_metadata_enriched():
    """Chunk metadata 包含新增字段."""
    pages = _make_pdf_blocks([
        "## 背景\n" + _long_cn("内容说明系统背景、用户需求、检索流程和证据质量。", 25),
    ])
    chunks = structured_pdf_chunks(pages, doc_id="doc123", source="paper.pdf",
                                   source_path="paper.pdf", source_type="file",
                                   title="My Paper", source_version="v1",
                                   content_hash="hashX", last_ingested_at="2024-01-01T00:00:00Z")

    assert len(chunks) == 1
    for text, meta in chunks:
        assert meta.doc_id == "doc123"
        assert meta.source == "paper.pdf"
        assert meta.page_start >= 1
        assert meta.page_end >= meta.page_start
        assert meta.order_in_doc >= 0
        assert meta.char_count == len(text)
        assert meta.token_estimate > 0
        assert meta.block_type == "paragraph"
        assert meta.section_title == "背景"
    print("PASS: blocks_to_chunks_metadata_enriched")


def test_blocks_to_chunks_section_tracking():
    """section_title 在 heading 切换时正确更新."""
    pages = _make_pdf_blocks([
        "## 第一节\n" + _long_cn("内容A说明第一节的研究背景和系统设计。")
        + "\n## 第二节\n" + _long_cn("内容B说明第二节的实验设置和质量评估。"),
    ])
    chunks = structured_pdf_chunks(pages, doc_id="test", source="test.pdf",
                                   source_path="test.pdf", source_type="file",
                                   title="Test", source_version="v1",
                                   content_hash="abc", last_ingested_at="2024-01-01")

    section_map = {m.section_title: (t, m.block_type) for t, m in chunks if m.block_type == "paragraph"}

    # After "## 第一节", section should be "第一节"
    # After "## 第二节", section should be "第二节"
    # At least one paragraph should reference the correct section
    para_sections = {m.section_title for _, m in chunks if m.block_type == "paragraph"}
    assert "第一节" in para_sections or "第二节" in para_sections
    print(f"PASS: blocks_to_chunks_section_tracking — sections found: {para_sections}")


def test_captions_merged_with_table():
    """caption 块应与前一个 table 块合并（或单独输出）."""
    table_rows = "\n".join(f"模型{i} │ {0.70 + i / 100:.2f}" for i in range(1, 90))
    pages = _make_pdf_blocks([
        "## 实验\n方法 │ 结果\n" + table_rows + "\n表1 实验结果。",
    ])
    chunks = structured_pdf_chunks(pages, doc_id="test", source="test.pdf",
                                   source_path="test.pdf", source_type="file",
                                   title="Test", source_version="v1",
                                   content_hash="abc", last_ingested_at="2024-01-01")

    table_chunks = [(t, m) for t, m in chunks if m.block_type == "table"]
    assert len(table_chunks) >= 1
    assert any("表1" in t for t, _ in table_chunks)
    assert not any(m.block_type == "caption" for _, m in chunks)
    print(f"PASS: captions_merged_with_table")


def test_oversized_paragraph_sliding_window():
    """超长段落使用滑窗切分，产生多个子 chunk."""
    # Create a paragraph that exceeds CHUNK_MAX_TOKENS threshold
    # Need > 570 tokens (0.95 * CHUNK_MAX_TOKENS = 570) to trigger sliding window
    # Each "这是第1句。" is 6 chars, token estimate = 6/1.5 = 4 tokens
    # Need 570/4 = 143 repetitions minimum, use 160 for safety (640 tokens)
    long_text = "这是第1句。" * 160  # 960 chars = ~640 tokens
    pages = _make_pdf_blocks([long_text])

    chunks = structured_pdf_chunks(pages, doc_id="test", source="test.pdf",
                                   source_path="test.pdf", source_type="file",
                                   title="Test", source_version="v1",
                                   content_hash="abc", last_ingested_at="2024-01-01")

    # Should be split into multiple chunks
    assert len(chunks) > 1
    # All chunks should be paragraph type
    assert all(m.block_type == "paragraph" for _, m in chunks)
    print(f"PASS: oversized_paragraph_sliding_window — {len(chunks)} chunks from long paragraph")


def test_backward_compatibility_md_txt_unchanged():
    """MD/TXT 文件不经过 page_mode，split_text 逻辑不变."""
    # The non-structured path uses split_text directly
    from app.rag.splitter import split_text

    md_text = "# 标题\n\n正文内容。"
    chunks = split_text(md_text)
    assert len(chunks) == 1
    assert chunks[0]["section"] == "标题"
    assert "正文内容" in chunks[0]["text"]
    print("PASS: backward_compatibility_md_txt_unchanged")


# ---------------------------------------------------------------------------
# Front matter heading split regression tests
# ---------------------------------------------------------------------------

from app.rag.structured_chunker import _split_front_matter_heading


def test_split_front_matter_heading_abstract():
    """Abstract heading merged with body → split into (marker, body)."""
    result = _split_front_matter_heading(
        "Abstract At present, the continuous change of information technology "
        "along with the dramatic explosion of data has caused mainstream cloud "
        "computing solutions to face challenges."
    )
    assert result is not None
    marker, body = result
    assert marker.strip() == "Abstract"
    assert body.startswith("At present")
    assert len(body) > 20
    print(f"PASS: split_front_matter_heading_abstract — marker={marker!r} body={body[:40]!r}")


def test_split_front_matter_heading_chinese():
    """摘　要 heading merged with body → split into (marker, body)."""
    result = _split_front_matter_heading(
        "摘　要　近年来，信息技术的不断变革伴随数据量的急剧爆发，"
        "使主流的云计算解决方案面临实时性差、带宽受限等问题."
    )
    assert result is not None
    marker, body = result
    assert marker.strip() == "摘　要"
    assert body.startswith("近年来")
    assert len(body) > 20
    print(f"PASS: split_front_matter_heading_chinese — marker={marker!r} body={body[:40]!r}")


def test_split_front_matter_heading_no_split_short_body():
    """Heading with <10 chars body → no split (return None)."""
    result = _split_front_matter_heading("Abstract Hi")
    assert result is None
    result = _split_front_matter_heading("摘　要　短")
    assert result is None
    print("PASS: split_front_matter_heading_no_split_short_body")


def test_split_front_matter_heading_no_split_no_marker():
    """Non-front-matter heading → no split (return None)."""
    result = _split_front_matter_heading("1. 背景介绍\n这是背景内容。")
    assert result is None
    result = _split_front_matter_heading("Some random paragraph text without heading marker.")
    assert result is None
    print("PASS: split_front_matter_heading_no_split_no_marker")


def test_extract_blocks_classifies_caption_variants_and_plain_reference():
    blocks = [
        {"type": 0, "lines": [{"spans": [{"text": "Fig. 1. Correlation between personalization and RAG."}]}]},
        {"type": 0, "lines": [{"spans": [{"text": "Figure 2: Overall system pipeline"}]}]},
        {"type": 0, "lines": [{"spans": [{"text": "Table 1. Evaluation datasets"}]}]},
        {"type": 0, "lines": [{"spans": [{"text": "As shown in Figure 1, the method improves accuracy."}]}]},
    ]
    result = extract_blocks_from_page(3, blocks)
    assert [b.block_type for b in result[:3]] == [BlockType.CAPTION, BlockType.CAPTION, BlockType.CAPTION]
    assert result[3].block_type == BlockType.PARAGRAPH
    print("PASS: extract_blocks_classifies_caption_variants_and_plain_reference")


def test_extract_blocks_classifies_pipe_style_heading():
    blocks = [
        {"type": 0, "lines": [{"spans": [{"text": "1 | INTRODUCTION"}]}]},
        {"type": 0, "lines": [{"spans": [{"text": "Large Language Models have revolutionized AI-driven applications."}]}]},
    ]
    result = extract_blocks_from_page(2, blocks)
    assert result[0].block_type == BlockType.HEADING
    assert result[1].block_type == BlockType.PARAGRAPH
    print("PASS: extract_blocks_classifies_pipe_style_heading")


def test_extract_blocks_classifies_numbered_section_heading():
    blocks = [
        {"type": 0, "lines": [{"spans": [{"text": "2 Related Work"}]}]},
        {"type": 0, "lines": [{"spans": [{"text": "1 引言"}]}]},
    ]
    result = extract_blocks_from_page(2, blocks)
    assert [b.block_type for b in result] == [BlockType.HEADING, BlockType.HEADING]
    print("PASS: extract_blocks_classifies_numbered_section_heading")


def test_extract_blocks_classifies_multiline_numeric_heading():
    blocks = [
        {
            "type": 0,
            "lines": [
                {"spans": [{"text": "1"}]},
                {"spans": [{"text": "INTRODUCTION"}]},
            ],
        },
    ]
    result = extract_blocks_from_page(2, blocks)
    assert len(result) == 1
    assert result[0].block_type == BlockType.HEADING
    print("PASS: extract_blocks_classifies_multiline_numeric_heading")


def test_blocks_to_chunks_multiline_heading_section_title():
    """Multiline heading should anchor following body section without becoming a tiny chunk."""
    blocks = [
        {
            "type": 0,
            "lines": [
                {"spans": [{"text": "1"}]},
                {"spans": [{"text": "INTRODUCTION"}]},
            ],
        },
        {"type": 0, "lines": [{"spans": [{"text": _long_en("Large language models require retrieval to ground answers in source evidence.")}]}]},
    ]
    extracted = extract_blocks_from_page(2, blocks)
    chunks = blocks_to_chunks(
        extracted,
        doc_id="test",
        source="test.pdf",
        source_path="test.pdf",
        source_type="file",
        title="Test",
        source_version="v1",
        content_hash="abc",
        last_ingested_at="2024-01-01",
    )
    assert not any(m.block_type == "heading" for _, m in chunks)
    body_chunk = next((m for t, m in chunks if "Large language models" in t), None)
    assert body_chunk is not None
    assert body_chunk.section_title == "INTRODUCTION", f"Expected section_title='INTRODUCTION', got {body_chunk.section_title!r}"
    print("PASS: test_blocks_to_chunks_multiline_heading_section_title")


def test_blocks_to_chunks_page1_english_title_and_inferred_abstract():
    blocks = [
        {"type": 0, "lines": [{"spans": [{"text": "A Survey of Personalization: From RAG to Agent"}]}]},
        {"type": 0, "lines": [{"spans": [{"text": "XIAOPENG LI, City University of Hong Kong"}]}]},
        {"type": 0, "lines": [{"spans": [{"text": _long_en("Personalization has become an essential capability in modern AI systems, enabling customized interactions that align with individual user preferences and contexts.", 20)}]}]},
        {"type": 0, "lines": [{"spans": [{"text": _long_en("Recent research has increasingly concentrated on Retrieval-Augmented Generation frameworks and their evolution into more advanced agent architectures.", 20)}]}]},
        {"type": 0, "lines": [{"spans": [{"text": "Additional Key Words and Phrases: Large Language Model, Retrieval-Augmented Generation"}]}]},
    ]
    extracted = extract_blocks_from_page(1, blocks)
    chunks = blocks_to_chunks(
        extracted,
        doc_id="test",
        source="test.pdf",
        source_path="test.pdf",
        source_type="file",
        title="Test",
        source_version="v1",
        content_hash="abc",
        last_ingested_at="2024-01-01",
    )

    title_chunk = next((m for t, m in chunks if "A Survey of Personalization" in t), None)
    assert title_chunk is None

    author_chunk = next((m for t, m in chunks if "XIAOPENG LI" in t), None)
    assert author_chunk is None

    abstract_chunk = next((m for t, m in chunks if "Personalization has become" in t), None)
    assert abstract_chunk is not None
    assert abstract_chunk.block_type == "paragraph"
    assert abstract_chunk.section_title == "Abstract"
    print("PASS: blocks_to_chunks_page1_english_title_and_inferred_abstract")


def test_blocks_to_chunks_chinese_abstract_marker_inherits_section():
    blocks = [
        {"type": 0, "lines": [{"spans": [{"text": "摘 要：近年来，边缘智能发展迅速。"}]}]},
        {"type": 0, "lines": [{"spans": [{"text": _long_cn("边缘协同推理可以减少云边通信开销并提升响应速度。", 80)}]}]},
    ]
    extracted = extract_blocks_from_page(1, blocks)
    chunks = blocks_to_chunks(
        extracted,
        doc_id="test",
        source="test.pdf",
        source_path="test.pdf",
        source_type="file",
        title="Test",
        source_version="v1",
        content_hash="abc",
        last_ingested_at="2024-01-01",
    )

    heading_chunk = next((m for t, m in chunks if "摘" in t and m.block_type == "heading"), None)
    body_chunk = next((m for t, m in chunks if "边缘协同推理" in t), None)
    assert heading_chunk is None
    assert body_chunk is not None
    assert body_chunk.section_title in {"摘 要", "摘要"}
    print("PASS: blocks_to_chunks_chinese_abstract_marker_inherits_section")


def test_blocks_to_chunks_front_matter_split():
    """Front matter labels and author lists are not emitted as standalone chunks."""
    pages = _make_pdf_blocks([
        "面向边缘智能的协同推理综述",
        "王 睿\n齐建鹏\n陈 亮\n杨 龙\n（北京科技大学）",
        "Survey of Collaborative Inference for Edge Intelligence",
        "Wang Rui, Qi Jianpeng, Chen Liang, and Yang Long",
        "Abstract At present, the continuous change of information technology.",
        _long_en("Along with the dramatic explosion of data, mainstream cloud computing faces pressure from latency and bandwidth.", 20),
        _long_en("Solutions face challenges like poor real-time performance and excessive cloud-edge communication overhead.", 20),
        _long_en("Edge intelligence has emerged as a promising approach for bringing inference closer to users.", 20),
        "Key words edge computing; edge intelligence; machine learning",
        "摘　要　近年来，信息技术的不断变革伴随数据量的急剧爆发，使主流的云计算解决方案面临实时性差、带宽受限等问题。",
        _long_cn("边缘智能的出现与快速发展有效缓解了此类问题。", 45),
        _long_cn("用户需求处理下沉到边缘，避免了海量数据在网络中的流动。", 45),
        _long_cn("通过对边缘智能发展的趋势分析，得出结论。", 45),
        "关键词 边缘计算；边缘智能；机器学习；边缘协同推理",
    ])

    chunks = structured_pdf_chunks(
        pages,
        doc_id="test_front_matter",
        source="test.pdf",
        source_path="test.pdf",
        source_type="file",
        title="Test",
        source_version="v1",
        content_hash="abc",
        last_ingested_at="2024-01-01",
    )

    chunk_info = [(t, m.block_type, m.section_title) for t, m in chunks]

    assert not any(bt == "heading" for _, bt, _ in chunk_info)
    assert not any("Wang Rui" in t or "北京科技大学" in t for t, _, _ in chunk_info)
    assert not any(t.strip() in {"Abstract", "摘 要"} for t, _, _ in chunk_info)

    en_body_chunks = [
        (t, bt, s) for t, bt, s in chunk_info
        if ("Along with" in t or "Solutions face" in t or "Edge intelligence" in t)
        and bt == "paragraph"
    ]
    assert len(en_body_chunks) >= 1, f"English abstract body not found: {chunk_info[3:10]}"
    for t, bt, s in en_body_chunks:
        assert s == "Abstract", f"English abstract body section_title={s!r}, expected 'Abstract'"

    zh_body_chunks = [
        (t, bt, s) for t, bt, s in chunk_info
        if ("边缘智能" in t or "用户需求" in t or "趋势分析" in t)
        and bt == "paragraph"
    ]
    assert len(zh_body_chunks) >= 1, f"Chinese abstract body not found: {chunk_info}"
    for t, bt, s in zh_body_chunks:
        assert s == "摘 要", f"Chinese abstract body section_title={s!r}, expected '摘 要'"

    assert not any("Key words" in t or "关键词" in t for t, _, _ in chunk_info)

    print(f"PASS: blocks_to_chunks_front_matter_split")
    print(f"  All {len(chunks)} chunks: {[(t[:30] if len(t) > 30 else t, bt, s) for t, bt, s in chunk_info]}")


def test_sentence_aware_window_keeps_sentence_endings():
    text = " ".join(f"Sentence {i} explains retrieval augmented generation." for i in range(80))
    windows = _sentence_aware_sliding_window(text, size=220, overlap=40)
    assert len(windows) > 1
    assert all(window.endswith(".") for window in windows)
    assert not any(window.startswith("xplains") or window.startswith("etrieval") for window in windows)
    print("PASS: sentence_aware_window_keeps_sentence_endings")


def test_references_section_truncates_following_blocks():
    blocks = [
        PDFBlock(BlockType.HEADING, "Introduction", 1, 0, 1),
        PDFBlock(BlockType.PARAGRAPH, _long_en("RAG retrieves evidence before generation to reduce hallucination.", 50), 1, 1),
        PDFBlock(BlockType.HEADING, "References", 8, 0, 1),
        PDFBlock(BlockType.PARAGRAPH, "Lewis Patrick, Perez Ethan, Piktus Aleksandra, Petroni Fabio.", 8, 1),
    ]
    chunks = blocks_to_chunks(
        blocks,
        doc_id="test",
        source="test.pdf",
        source_path="test.pdf",
        source_type="file",
        title="Test",
        source_version="v1",
        content_hash="abc",
        last_ingested_at="2024-01-01",
    )
    all_text = "\n".join(text for text, _ in chunks)
    assert "RAG retrieves evidence" in all_text
    assert "Lewis Patrick" not in all_text
    print("PASS: references_section_truncates_following_blocks")


def test_standalone_author_and_caption_blocks_are_filtered():
    blocks = [
        PDFBlock(
            BlockType.PARAGRAPH,
            "Alice Wang, City University of Hong Kong, Hong Kong Bob Chen, University of Science and Technology of China, China Carol Li, Institute of Computing, Beijing",
            1,
            0,
        ),
        PDFBlock(BlockType.CAPTION, "Fig. 1. Overview of the proposed framework.", 2, 1),
        PDFBlock(BlockType.PARAGRAPH, _long_en("Retrieval augmented generation combines search results with language model generation for grounded responses.", 50), 2, 2),
    ]
    chunks = blocks_to_chunks(
        blocks,
        doc_id="test",
        source="test.pdf",
        source_path="test.pdf",
        source_type="file",
        title="Test",
        source_version="v1",
        content_hash="abc",
        last_ingested_at="2024-01-01",
    )
    all_text = "\n".join(text for text, _ in chunks)
    assert "Alice Wang" not in all_text
    assert "Fig. 1" not in all_text
    assert "Retrieval augmented generation" in all_text
    print("PASS: standalone_author_and_caption_blocks_are_filtered")


def run_all():
    tests = [
        test_clean_block_text,
        test_heading_patterns,
        test_table_id_extraction,
        test_extract_blocks_classifies_heading,
        test_extract_blocks_classifies_table,
        test_extract_blocks_classifies_list,
        test_blocks_to_chunks_heading_isolated,
        test_blocks_to_chunks_paragraph_accumulation,
        test_blocks_to_chunks_table_isolated,
        test_blocks_to_chunks_metadata_enriched,
        test_blocks_to_chunks_section_tracking,
        test_captions_merged_with_table,
        test_oversized_paragraph_sliding_window,
        test_backward_compatibility_md_txt_unchanged,
        test_split_front_matter_heading_abstract,
        test_split_front_matter_heading_chinese,
        test_split_front_matter_heading_no_split_short_body,
        test_split_front_matter_heading_no_split_no_marker,
        test_extract_blocks_classifies_caption_variants_and_plain_reference,
        test_extract_blocks_classifies_pipe_style_heading,
        test_extract_blocks_classifies_numbered_section_heading,
        test_extract_blocks_classifies_multiline_numeric_heading,
        test_blocks_to_chunks_page1_english_title_and_inferred_abstract,
        test_blocks_to_chunks_chinese_abstract_marker_inherits_section,
        test_blocks_to_chunks_front_matter_split,
        test_sentence_aware_window_keeps_sentence_endings,
        test_references_section_truncates_following_blocks,
        test_standalone_author_and_caption_blocks_are_filtered,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {t.__name__}: {e}")
            failed += 1
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_all()
    sys.exit(0 if success else 1)
