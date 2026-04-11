import React, { useState } from 'react';
import { CitationItem } from '../../../core/types/api';
import { useWorkspaceStore } from '../../workspace/store';

export const CitationList: React.FC<{ citations: CitationItem[] }> = ({ citations }) => {
  const { setSelectedDoc, setHighlightedChunkId } = useWorkspaceStore();
  const [clickedIndex, setClickedIndex] = useState<number | null>(null);

  if (!citations || citations.length === 0) return null;

  const handleCitationClick = (citation: CitationItem, index: number) => {
    setClickedIndex(index);
    setTimeout(() => setClickedIndex(null), 300);
    // 1. auto-switch to doc
    // Note: Since we might not have the full detail object, we pass null and it handles it simply
    // or we fetch the doc list separately. For linking, we just need the ID to trigger load.
    setSelectedDoc(citation.doc_id, {
      doc_id: citation.doc_id,
      title: citation.inline_ref || citation.doc_id,
      category: 'reference',
      ingest_status: 'ready',
      uploaded_at: new Date().toISOString()
    });

    // 2. highlight chunk
    // Extract chunk_index from chunk_id (format: "doc_id:index") or use chunk_index directly
    setTimeout(() => {
      const chunkIndex = citation.chunk_id
        ? citation.chunk_id.split(':').pop() ?? null
        : String(citation.chunk_index ?? null);
      setHighlightedChunkId(chunkIndex);
    }, 0);
  };

  return (
    <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: '1px dashed #e2e8f0' }}>
      <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#64748b', marginBottom: '8px', textTransform: 'uppercase' }}>
        References
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {citations.map((c, i) => (
          <div 
            key={i} 
            onClick={() => handleCitationClick(c, i)}
            style={{ 
              background: clickedIndex === i ? '#e0f2fe' : '#f8fafc',
              border: '1px solid',
              borderColor: clickedIndex === i ? '#3b82f6' : '#e2e8f0',
              borderRadius: '6px', 
              padding: '10px 14px', 
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
              transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
              transform: clickedIndex === i ? 'scale(0.98)' : 'none'
            }}
            onMouseOver={(e) => { if(clickedIndex !== i) e.currentTarget.style.borderColor = '#94a3b8'; }}
            onMouseOut={(e) => { if(clickedIndex !== i) e.currentTarget.style.borderColor = '#e2e8f0'; }}
          >
            <div style={{ fontSize: '13px', color: '#3b82f6', fontWeight: '500' }}>
              [{c.inline_ref || (i + 1)}] {c.doc_id}
            </div>
            {c.snippet && (
              <div style={{ fontSize: '13px', color: '#475569', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                "{c.snippet}"
              </div>
            )}
            {c.page_num && (
              <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                Page: {c.page_num}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
