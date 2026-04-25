import React, { useState } from 'react';
import { CitationItem } from '../../../core/types/api';
import { useWorkspaceStore } from '../../workspace/store';
import { useWorkspacePreferences } from '../../settings/workspace-preferences';

export const CitationList: React.FC<{ citations: CitationItem[] }> = ({ citations }) => {
  const { openCitationSource } = useWorkspaceStore();
  const { showTechnicalCitationMetadata, setShowTechnicalCitationMetadata, density } = useWorkspacePreferences();
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
    if (pageStart != null && pageEnd != null && pageEnd !== pageStart) return `pp. ${pageStart}-${pageEnd}`;
    if (pageStart != null) return `p. ${pageStart}`;
    return citation.section_title || citation.section || null;
  };

  const getCitationPreview = (citation: CitationItem): string | null => {
    return citation.evidence_preview || citation.snippet || null;
  };

  const d = density;
  const itemGap = d === 'compact' ? '8px' : '12px';
  const itemPadding = d === 'compact' ? '10px 12px' : '14px 16px';
  const titleSize = '14px';
  const labelSize = '12px';
  const previewSize = '13px';

  return (
    <div style={{
      marginTop: d === 'compact' ? '16px' : '24px',
      padding: d === 'compact' ? '12px' : '16px',
      background: 'var(--color-surface)',
      border: '1px solid var(--color-border-subtle)',
      borderRadius: 'var(--radius-lg)',
      boxShadow: 'var(--shadow-sm)',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        marginBottom: d === 'compact' ? '10px' : '14px',
      }}>
        <span style={{
          fontSize: '13px',
          fontWeight: 600,
          color: 'var(--color-text-secondary)',
        }}>
          Sources
        </span>
        <span style={{
          background: 'var(--color-canvas)',
          color: 'var(--color-text-tertiary)',
          padding: '2px 8px',
          borderRadius: 'var(--radius-full)',
          fontSize: '11px',
          fontWeight: 600,
          border: '1px solid var(--color-border-subtle)',
        }}>
          {citations.length}
        </span>
      </div>

      {/* Citation Items */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: itemGap }}>
        {citations.map((c, i) => (
          <div
            key={i}
            onClick={() => handleCitationClick(c, i)}
            className="citation-card"
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: d === 'compact' ? '10px' : '14px',
              padding: itemPadding,
              background: clickedIndex === i ? 'var(--color-brand-50)' : 'var(--color-surface)',
              border: '1px solid',
              borderColor: clickedIndex === i ? 'var(--color-brand-200)' : 'var(--color-border-subtle)',
              borderRadius: 'var(--radius-md)',
              cursor: 'pointer',
              transition: 'all var(--transition-fast)',
              boxShadow: clickedIndex === i ? '0 0 0 1px var(--color-brand-200)' : 'none',
            }}
            onMouseOver={(e) => {
              if (clickedIndex !== i) {
                e.currentTarget.style.borderColor = 'var(--color-border-default)';
                e.currentTarget.style.boxShadow = 'var(--shadow-md)';
                e.currentTarget.style.transform = 'translateY(-1px)';
              }
            }}
            onMouseOut={(e) => {
              if (clickedIndex !== i) {
                e.currentTarget.style.borderColor = 'var(--color-border-subtle)';
                e.currentTarget.style.boxShadow = 'none';
                e.currentTarget.style.transform = 'translateY(0)';
              }
            }}
          >
            {/* Index Badge */}
            <span style={{
              flexShrink: 0,
              width: d === 'compact' ? '22px' : '26px',
              height: d === 'compact' ? '22px' : '26px',
              background: 'var(--color-brand-50)',
              color: 'var(--color-brand-600)',
              borderRadius: '6px',
              fontSize: d === 'compact' ? '11px' : '12px',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginTop: '1px',
              border: '1px solid var(--color-brand-200)',
            }}>
              {c.inline_ref || (i + 1)}
            </span>

            <div style={{ flex: 1, minWidth: 0 }}>
              {/* Title */}
              <div style={{
                fontSize: titleSize,
                fontWeight: 600,
                color: 'var(--color-text-primary)',
                marginBottom: '3px',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {getCitationTitle(c)}
              </div>

              {/* Label (page / section) */}
              {getCitationLabel(c) && (
                <div style={{
                  fontSize: labelSize,
                  color: 'var(--color-text-tertiary)',
                  fontWeight: 500,
                  marginBottom: '6px',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {getCitationLabel(c)}
                </div>
              )}

              {/* Preview blockquote style */}
              {getCitationPreview(c) && (
                <div style={{
                  fontSize: previewSize,
                  color: 'var(--color-text-secondary)',
                  lineHeight: '1.6',
                  overflow: 'hidden',
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  paddingLeft: '10px',
                  borderLeft: '3px solid var(--color-brand-200)',
                  background: 'var(--color-canvas-subtle)',
                  padding: '8px 10px',
                  borderRadius: '0 6px 6px 0',
                }}>
                  {getCitationPreview(c)}
                </div>
              )}

              {/* Technical metadata */}
              {showTechnicalCitationMetadata && (
                <div style={{
                  display: 'flex',
                  gap: '6px',
                  marginTop: '8px',
                  fontSize: '11px',
                  color: 'var(--color-text-tertiary)',
                  flexWrap: 'wrap',
                }}>
                  {c.window_chunk_count != null && c.window_chunk_count > 0 && (
                    <span style={{
                      background: 'var(--color-canvas)',
                      padding: '2px 8px',
                      borderRadius: 'var(--radius-full)',
                      border: '1px solid var(--color-border-subtle)',
                    }}>
                      Window: {c.window_chunk_count} chunk{c.window_chunk_count === 1 ? '' : 's'}
                    </span>
                  )}
                  {c.hit_in_window && (
                    <span style={{
                      background: 'var(--color-brand-50)',
                      color: 'var(--color-brand-600)',
                      padding: '2px 8px',
                      borderRadius: 'var(--radius-full)',
                      border: '1px solid var(--color-brand-200)',
                    }}>
                      Hit in window
                    </span>
                  )}
                  {c.is_hit_only_fallback && (
                    <span style={{
                      background: 'var(--color-warning-bg)',
                      color: 'var(--color-warning-text)',
                      padding: '2px 8px',
                      borderRadius: 'var(--radius-full)',
                      border: '1px solid var(--color-warning-border)',
                    }}>
                      Hit-only fallback
                    </span>
                  )}
                  {c.section && !c.citation_label && (
                    <span style={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      maxWidth: '200px',
                      background: 'var(--color-canvas)',
                      padding: '2px 8px',
                      borderRadius: 'var(--radius-full)',
                      border: '1px solid var(--color-border-subtle)',
                    }}>
                      {c.section}
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Toggle technical details */}
      <div style={{ marginTop: d === 'compact' ? '8px' : '12px', paddingTop: '8px', borderTop: '1px solid var(--color-border-subtle)' }}>
        <button
          type="button"
          onClick={() => setShowTechnicalCitationMetadata(!showTechnicalCitationMetadata)}
          style={{
            fontSize: '12px',
            color: 'var(--color-text-tertiary)',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '4px 8px',
            borderRadius: 'var(--radius-sm)',
            fontWeight: 500,
            transition: 'all var(--transition-fast)',
          }}
          onMouseOver={(e) => {
            e.currentTarget.style.color = 'var(--color-text-secondary)';
            e.currentTarget.style.background = 'var(--color-canvas)';
          }}
          onMouseOut={(e) => {
            e.currentTarget.style.color = 'var(--color-text-tertiary)';
            e.currentTarget.style.background = 'none';
          }}
        >
          {showTechnicalCitationMetadata ? 'Hide technical details' : 'Show technical details'}
        </button>
      </div>
    </div>
  );
};
