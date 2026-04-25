import React, { useState } from 'react';
import { CitationItem } from '../../../core/types/api';
import { useWorkspaceStore } from '../../workspace/store';

export const CitationList: React.FC<{ citations: CitationItem[] }> = ({ citations }) => {
  const { openCitationSource } = useWorkspaceStore();
  const [clickedIndex, setClickedIndex] = useState<number | null>(null);

  if (!citations || citations.length === 0) return null;

  const handleCitationClick = (citation: CitationItem, index: number) => {
    setClickedIndex(index);
    setTimeout(() => setClickedIndex(null), 300);
    openCitationSource(citation);
  };

  const getCitationTitle = (citation: CitationItem): string => {
    return citation.source || citation.title || citation.doc_id;
  };

  const getCitationLabel = (citation: CitationItem): string | null => {
    if (citation.citation_label) return citation.citation_label;
    const pageStart = citation.page_start ?? citation.page_num ?? citation.page;
    const pageEnd = citation.page_end ?? citation.page_num ?? citation.page;
    if (pageStart != null && pageEnd != null && pageEnd !== pageStart) return `pp.${pageStart}-${pageEnd}`;
    if (pageStart != null) return `p.${pageStart}`;
    return citation.section_title || citation.section || null;
  };

  const getCitationPreview = (citation: CitationItem): string | null => {
    return citation.evidence_preview || citation.snippet || null;
  };

  return (
    <div style={{
      marginTop: '24px',
      paddingTop: '18px',
      borderTop: '1px solid #e5e7eb'
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        fontSize: '11px',
        fontWeight: '600',
        color: '#94a3b8',
        marginBottom: '12px',
        textTransform: 'uppercase',
        letterSpacing: '0.08em'
      }}>
        <span>Sources</span>
        <span style={{
          background: '#f1f5f9',
          color: '#64748b',
          padding: '1px 6px',
          borderRadius: '4px',
          fontSize: '10px'
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
              display: 'flex',
              alignItems: 'flex-start',
              gap: '12px',
              padding: '12px 14px',
              background: clickedIndex === i ? '#eff6ff' : '#ffffff',
              border: '1px solid',
              borderColor: clickedIndex === i ? '#bfdbfe' : '#e5e7eb',
              borderRadius: '10px',
              cursor: 'pointer',
              transition: 'background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease',
              boxShadow: clickedIndex === i ? '0 0 0 1px rgba(59, 130, 246, 0.08)' : 'none',
            }}
            onMouseOver={(e) => {
              if (clickedIndex !== i) {
                e.currentTarget.style.background = '#f8fafc';
                e.currentTarget.style.borderColor = '#cbd5e1';
              }
            }}
            onMouseOut={(e) => {
              if (clickedIndex !== i) {
                e.currentTarget.style.background = '#ffffff';
                e.currentTarget.style.borderColor = '#e5e7eb';
              }
            }}
          >
            <span style={{
              flexShrink: 0,
              width: '20px',
              height: '20px',
              background: '#e2e8f0',
              color: '#475569',
              borderRadius: '4px',
              fontSize: '11px',
              fontWeight: '700',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginTop: '1px'
            }}>
              {c.inline_ref || (i + 1)}
            </span>

            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontSize: '13px',
                fontWeight: '600',
                color: '#1e293b',
                marginBottom: '4px',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap'
              }}>
                {getCitationTitle(c)}
              </div>
              {getCitationLabel(c) && (
                <div style={{
                  fontSize: '11px',
                  color: '#2563eb',
                  fontWeight: 600,
                  marginBottom: '5px',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap'
                }}>
                  {getCitationLabel(c)}
                </div>
              )}
              {getCitationPreview(c) && (
                <div style={{
                  fontSize: '12px',
                  color: '#475569',
                  lineHeight: '1.55',
                  overflow: 'hidden',
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                }}>
                  {getCitationPreview(c)}
                </div>
              )}
              <div style={{
                display: 'flex',
                gap: '8px',
                marginTop: '6px',
                fontSize: '11px',
                color: '#94a3b8',
                flexWrap: 'wrap'
              }}>
                {c.window_chunk_count != null && c.window_chunk_count > 0 && (
                  <span>Window: {c.window_chunk_count} chunk{c.window_chunk_count === 1 ? '' : 's'}</span>
                )}
                {c.hit_in_window && <span>Hit in window</span>}
                {c.is_hit_only_fallback && <span>Hit-only fallback</span>}
                {c.section && !c.citation_label && (
                  <span style={{
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    maxWidth: '200px'
                  }}>
                    {c.section}
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
