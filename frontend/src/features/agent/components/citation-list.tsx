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

    // chunk_index is the authoritative numeric index; chunk_id may be a compound id
    const chunkIndex = citation.chunk_index != null
      ? String(citation.chunk_index)
      : citation.chunk_id?.split(':').pop() ?? null;

    // Open drawer (true) so scroll effect in source-drawer.tsx can run
    setSelectedDoc(citation.doc_id, null, true);
    setHighlightedChunkId(chunkIndex);
  };

  return (
    <div style={{
      marginTop: '20px',
      paddingTop: '16px',
      borderTop: '1px solid #e2e8f0'
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        fontSize: '12px',
        fontWeight: '600',
        color: '#64748b',
        marginBottom: '12px',
        textTransform: 'uppercase',
        letterSpacing: '0.05em'
      }}>
        <span style={{ fontSize: '13px' }}>🔗</span>
        <span>References</span>
        <span style={{
          fontSize: '11px',
          color: '#64748b',
          background: '#f1f5f9',
          padding: '1px 6px',
          borderRadius: '4px',
          fontWeight: '500'
        }}>
          {citations.length}
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {citations.map((c, i) => (
          <div
            key={i}
            onClick={() => handleCitationClick(c, i)}
            style={{
              background: clickedIndex === i ? '#eff6ff' : '#fff',
              border: '1px solid',
              borderColor: clickedIndex === i ? '#3b82f6' : '#e2e8f0',
              borderRadius: '12px',
              padding: '14px 16px',
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
              transform: clickedIndex === i ? 'scale(0.99)' : 'scale(1)',
              boxShadow: clickedIndex === i ? '0 2px 8px rgba(59, 130, 246, 0.15)' : '0 1px 3px rgba(0,0,0,0.04)'
            }}
            onMouseOver={(e) => {
              if (clickedIndex !== i) {
                e.currentTarget.style.borderColor = '#94a3b8';
                e.currentTarget.style.background = '#f8fafc';
              }
            }}
            onMouseOut={(e) => {
              if (clickedIndex !== i) {
                e.currentTarget.style.borderColor = '#e2e8f0';
                e.currentTarget.style.background = '#fff';
              }
            }}
          >
            {/* Header: Reference number and source */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '22px',
                height: '22px',
                background: '#3b82f6',
                color: '#fff',
                borderRadius: '6px',
                fontSize: '11px',
                fontWeight: '600'
              }}>
                {c.inline_ref || (i + 1)}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{
                  fontSize: '14px',
                  color: '#1e293b',
                  fontWeight: '600'
                }}>
                  {c.title || c.doc_id}
                </span>
                {c.source && (
                  <span style={{
                    fontSize: '12px',
                    color: '#64748b'
                  }}>
                    {c.source}
                  </span>
                )}
              </div>
            </div>

            {/* Snippet */}
            {c.snippet && (
              <div style={{
                fontSize: '13px',
                color: '#475569',
                lineHeight: '1.6',
                background: '#f8fafc',
                padding: '10px 12px',
                borderRadius: '6px',
                borderLeft: '3px solid #cbd5e1',
                fontStyle: 'italic'
              }}>
                "{c.snippet}"
              </div>
            )}

            {/* Footer: Location info */}
            <div style={{ display: 'flex', gap: '12px', fontSize: '11px', color: '#94a3b8' }}>
              {c.page_num && (
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  📄 Page {c.page_num}
                </span>
              )}
              {c.chunk_index !== undefined && (
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  📍 Chunk {c.chunk_index + 1}
                </span>
              )}
              {c.section && (
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  📑 {c.section}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
