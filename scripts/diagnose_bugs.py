# -*- coding: utf-8 -*-
"""Targeted bug diagnosis for structured_chunker."""
import sys
sys.path.insert(0, '.')

from app.rag.pdf_parser import extract_page_blocks
from app.rag.structured_chunker import (
    extract_blocks_from_page, _classify_block, BlockType,
    HEADING_PATTERNS, _split_front_matter_heading,
)
from pathlib import Path
import re

print('=== BUG 1: digit\\nTitle headings in English papers ===')
# ArXiv-2501 page 2 should have "2\nFoundations of RAG" heading
pb_list = extract_page_blocks(Path('knowledge_base/15_arxiv_2501.09136v1.pdf'))
page2_blocks = extract_blocks_from_page(2, pb_list[1].blocks)
print(f'ArXiv-2501 page 2 block 0: {page2_blocks[0].block_type.value}: {page2_blocks[0].text[:50]!r}')

# What does _classify_block say?
raw_text = '2\nFoundations of Retrieval-Augmented Generation'
lines = [{'spans': [{'text': '2'}, {'text': 'Foundations of Retrieval-Augmented Generation'}]}]
bt, hl = _classify_block(raw_text, lines, page_num=2, block_index=0)
print(f'_classify_block result: {bt.value}, level={hl}')

# Test HEADING_PATTERNS
for i, pat in enumerate(HEADING_PATTERNS):
    m = pat.match(raw_text)
    if m:
        print(f'Pattern {i} matches: groups={m.groups()[:2]}')
        break
else:
    print('NO pattern matched!')

# What about "2\nMulti-Document Question Answering" (Lost in Middle page 3)
print()
print('Lost in Middle page 3 "2\\nMulti-Document...":')
raw_text2 = '2\nMulti-Document Question Answering'
for i, pat in enumerate(HEADING_PATTERNS):
    m = pat.match(raw_text2)
    if m:
        print(f'Pattern {i} matches: groups={m.groups()[:2]}')
        break
else:
    print('NO pattern matched!')

print()
print('=== BUG 2: Multi-page abstract in ArXiv-2501 ===')
# Check what the block looks like on page 2
page2_pblist = pb_list[1].blocks
print(f'Page 2 has {len(page2_pblist)} raw pymupdf blocks')
for i, b in enumerate(page2_pblist[:3]):
    print(f'  Block {i}: type={b.get("type")}, text={b.get("lines", [{}])[0].get("spans", [{}])[0].get("text", "")[:30]!r}')

# What does extract_blocks_from_page give us for page 2?
page2_pdfblocks = extract_blocks_from_page(2, pb_list[1].blocks)
print(f'Page 2 PDFBlocks: {len(page2_pdfblocks)}')
for b in page2_pdfblocks[:3]:
    print(f'  {b.block_type.value}: {b.text[:40]!r}')

print()
print('=== BUG 3: Reference section detection ===')
# Check CRAD reference section - page 12 content
pb_list_crad = extract_page_blocks(Path('knowledge_base/05_crad_10.7544_issn1000-1239.202110867.pdf'))
print('CRAD page 12 first 3 blocks:')
page12_blocks = extract_blocks_from_page(12, pb_list_crad[11].blocks)
for b in page12_blocks[:3]:
    print(f'  {b.block_type.value}: {b.text[:50]!r}')

# Check if REFERENCE marker detection exists
from app.rag.structured_chunker import _ABSTRACT_MARKER_RE, _KEYWORDS_MARKER_RE
ref_tests = [
    '参考文献',
    'References',
    'REFERENCE',
    'REFERENCES',
    '[1] Author. Title...',
]
print('Reference marker detection:')
for t in ref_tests:
    m = _ABSTRACT_MARKER_RE.match(t)
    k = _KEYWORDS_MARKER_RE.match(t)
    print(f'  {t!r}: abstract={bool(m)}, keywords={bool(k)}')

print()
print('=== BUG 4: Front matter section_path tracking ===')
# CRAD page 1: Abstract heading should track section_path
# but front matter doesn't have numbered headings
# Check what section_path the abstract body paragraph gets
pb_list = extract_page_blocks(Path('knowledge_base/05_crad_10.7544_issn1000-1239.202110867.pdf'))
page1_blocks = extract_blocks_from_page(1, pb_list[0].blocks)
print('CRAD page 1 blocks:')
for b in page1_blocks[:8]:
    print(f'  {b.block_type.value}: {b.text[:50]!r}')

print()
print('=== BUG 5: _split_front_matter_heading behavior ===')
# Check split behavior for "Key words..." text
key_tests = [
    'Key words edge computing; edge intelligence; machine learning',
    'Abstract At present, the continuous change of information technology along with the drama',
    'Abstract',
]
for t in key_tests:
    result = _split_front_matter_heading(t)
    print(f'  {t[:50]!r} -> {result}')
