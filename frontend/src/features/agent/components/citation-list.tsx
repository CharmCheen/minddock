import React, { useState } from 'react';
import { CitationItem } from '../../../core/types/api';
import { useWorkspaceStore } from '../../workspace/store';
import { SourceService } from '../../../lib/api/services/sources';

export const CitationList: React.FC<{ citations: CitationItem[] }> = ({ citations }) => {
  const { setSelectedDoc, setHighlightedChunkId } = useWorkspaceStore();
  const [clickedIndex, setClickedIndex] = useState<number | null>(null);

  if (!citations || citations.length === 0) return null;

  const handleCitationClick = async (citation: CitationItem, index: number) => {
    setClickedIndex(index);
    setTimeout(() => setClickedIndex(null), 300);

    // Set highlight state synchronously before source switch
    // so the detail panel can scroll to it after chunks load
    const chunkId = citation.chunk_id || String(citation.chunk_index ?? null);
    setHighlightedChunkId(chunkId, citation.highlighted_sentence ?? null);

    // Load real source metadata instead of synthetic object
    try {
      const source = await SourceService.getSource(citation.doc_id);
      setSelectedDoc(citation.doc_id, source);
    } catch {
      // Fallback to minimal info if API fails
      setSelectedDoc(citation.doc_id, {
        doc_id: citation.doc_id,
        title: citation.title || citation.doc_id,
        category: 'reference',
        ingest_status: 'ready',
        uploaded_at: new Date().toISOString()
      });
    }
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

            {/* Snippet — prefer highlighted_sentence (precise match), fall back to snippet */}
            {(c.highlighted_sentence || c.snippet) && (
              <div style={{
                fontSize: '13px',
                color: '#475569',
                lineHeight: '1.6',
                background: '#f8fafc',
                padding: '10px 12px',
                borderRadius: '6px',
                borderLeft: '3px solid #3b82f6',
                fontStyle: 'italic'
              }}>
                "{c.highlighted_sentence || c.snippet}"
              </div>
            )}

            {/* Footer: Location info */}
            <div style={{ display: 'flex', gap: '12px', fontSize: '11px', color: '#94a3b8', flexWrap: 'wrap' }}>
              {c.page_num && (
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  📄 {c.page_num}
                </span>
              )}
              {c.location && (
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  📍 {c.location}
                </span>
              )}
              {(c.section_path || c.section) && (
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  📑 {c.section_path || c.section}
                </span>
              )}
              {c.highlighted_sentence && (
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#3b82f6' }}>
                  ✓ 已精确匹配
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
