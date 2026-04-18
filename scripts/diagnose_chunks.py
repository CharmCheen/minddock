# -*- coding: utf-8 -*-
"""Chunk quality diagnostic script."""
import sys
sys.path.insert(0, '.')

from app.rag.pdf_parser import extract_page_blocks
from app.rag.structured_chunker import structured_pdf_chunks
from pathlib import Path
import hashlib
from datetime import datetime

def diagnose(pdf_path, title):
    page_blocks_list = extract_page_blocks(Path(pdf_path))
    pages = [{'page': pb.page, 'blocks': pb.blocks} for pb in page_blocks_list]
    content_hash = hashlib.sha256(
        ''.join(pb.text for pb in page_blocks_list).encode('utf-8')
    ).hexdigest()
    last_ingested_at = datetime.now().isoformat()
    raw_chunks = structured_pdf_chunks(
        pages, doc_id=title, source='pdf', source_path=pdf_path, source_type='pdf',
        title=title, source_version='1.0', content_hash=content_hash,
        last_ingested_at=last_ingested_at,
    )
    total_pages = max(pb.page for pb in page_blocks_list)
    bt_counts = {}
    sp_count = st_count = sem_count = multi_page = 0
    for _, meta in raw_chunks:
        bt_counts[meta.block_type] = bt_counts.get(meta.block_type, 0) + 1
        if meta.section_path:
            sp_count += 1
        if meta.section_title:
            st_count += 1
        if meta.semantic_type:
            sem_count += 1
        if meta.page_start != meta.page_end:
            multi_page += 1

    print(f'=== {title} ===')
    print(f'Pages: {total_pages}, Chunks: {len(raw_chunks)}')
    print(f'block_type dist: {bt_counts}')
    print(f'section_path={sp_count}/{len(raw_chunks)}, section_title={st_count}/{len(raw_chunks)}, '
          f'semantic={sem_count}/{len(raw_chunks)}, multi-page={multi_page}')
    print()
    return raw_chunks

def show_chunks(chunks, start=0, end=None):
    end = end or len(chunks)
    for i, (text, meta) in enumerate(chunks[start:end], start=start):
        preview = text[:60].replace('\n', ' ')
        print(f'[{i:3d}] p{meta.page_start}-{meta.page_end} '
              f'{meta.block_type:12s} '
              f'sp={str(meta.section_path):15s} '
              f'sem={str(meta.semantic_type):10s} | {preview}')

if __name__ == '__main__':
    print('=== DIAGNOSIS: Structured Chunker Quality ===\n')

    # A-class: English/Chinese standard paper with numbered headings
    chunks_crad = diagnose(
        'knowledge_base/05_crad_10.7544_issn1000-1239.202110867.pdf',
        'CRAD: 边缘智能协同推理综述 (English/Chinese, numbered headings)'
    )

    # A-class: English academic
    chunks_litm = diagnose(
        'knowledge_base/18_acl_2024_tacl_1_9_lost_in_the_middle.pdf',
        'Lost in the Middle (English academic, ACL)'
    )

    # B-class: shorter review
    chunks_pkm = diagnose(
        'knowledge_base/10_rc_isiniu_PKM_review.pdf',
        'PKM Review (shorter academic review)'
    )

    # B-class: arxiv with digit\nTitle headings
    chunks_arxiv1 = diagnose(
        'knowledge_base/15_arxiv_2501.09136v1.pdf',
        'ArXiv 2501.09136 (Agentic RAG Survey, digit\\\\nTitle headings)'
    )

    # C-class: front matter complex
    chunks_arxiv2 = diagnose(
        'knowledge_base/16_arxiv_2504.10147.pdf',
        'ArXiv 2504.10147 (front matter complex)'
    )

    print('\n=== CRAD: First 30 chunks ===')
    show_chunks(chunks_crad, 0, 30)

    print('\n=== CRAD: chunks 60-80 (section transitions) ===')
    show_chunks(chunks_crad, 60, 80)

    print('\n=== Lost in Middle: First 20 chunks ===')
    show_chunks(chunks_litm, 0, 20)

    print('\n=== ArXiv 2501: First 20 chunks ===')
    show_chunks(chunks_arxiv1, 0, 20)

    # Find multi-page chunks
    print('\n=== Multi-page chunks across all documents ===')
    for name, chunks in [
        ('CRAD', chunks_crad),
        ('Lost in Middle', chunks_litm),
        ('PKM', chunks_pkm),
        ('ArXiv-2501', chunks_arxiv1),
        ('ArXiv-2504', chunks_arxiv2),
    ]:
        mp = [(i, c) for i, (t, c) in enumerate(chunks)
              if c.page_start != c.page_end]
        if mp:
            print(f'{name}: {mp}')
