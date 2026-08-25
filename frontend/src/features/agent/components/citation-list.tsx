import React, { useState } from 'react';
import { CitationItem } from '../../../core/types/api';
import { useWorkspaceStore } from '../../workspace/store';
import { useWorkspacePreferences } from '../../settings/workspace-preferences';
import { CitationExportFormat, exportCitations } from '../../../lib/api/services/citations';

const CHECK_STATUS_STYLE: Record<string, { label: string; color: string; background: string; border: string }> = {
  unsupported: { label: 'Not supported', color: '#b91c1c', background: '#fef2f2', border: '#fecaca' },
  partial: { label: 'Partial support', color: '#b45309', background: '#fffbeb', border: '#fde68a' },
};

export const CitationList: React.FC<{
  citations: CitationItem[];
  checkStatuses?: Record<number, string>;
}> = ({ citations, checkStatuses }) => {
  const { openCitationSource } = useWorkspaceStore();
  const { showTechnicalCitationMetadata, setShowTechnicalCitationMetadata, density } = useWorkspacePreferences();
  const [clickedIndex, setClickedIndex] = useState<number | null>(null);
  const [exportState, setExportState] = useState<{ format: string; ok: boolean } | null>(null);
  const [exporting, setExporting] = useState(false);

  if (!citations || citations.length === 0) return null;

  const getCheckStatus = (index: number): string | null => {
    if (!checkStatuses) return null;
    return checkStatuses[index] || null;
  };

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

  const getDerivedBadge = (citation: CitationItem): { label: string; kind: string } | null => {
    if (!citation.is_derived) return null;
    const kind = citation.derived_kind || '';
    const label = kind === 'media_summary' ? 'Summary' : kind === 'media_outline' ? 'Outline' : 'Derived';
    return { label, kind };
  };

  const getCitationPreview = (citation: CitationItem): string | null => {
    return citation.evidence_preview || citation.snippet || null;
  };

  const handleExport = async (format: CitationExportFormat) => {
    if (exporting) return;
    setExporting(true);
    try {
      const entries = citations.map((c) => ({
        doc_id: c.doc_id,
        title: c.title || c.source || c.doc_id,
        source: c.source || '',
        page: c.page_start ?? c.page_num ?? c.page ?? null,
        snippet: c.snippet || '',
      }));
      const result = await exportCitations(format, entries as unknown as Record<string, unknown>[]);
      await navigator.clipboard.writeText(result.text);
      setExportState({ format, ok: true });
      setTimeout(() => setExportState(null), 2000);
    } catch {
      setExportState({ format, ok: false });
      setTimeout(() => setExportState(null), 2500);
    } finally {
      setExporting(false);
    }
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
        {citations.map((c, i) => {
          const checkStatus = getCheckStatus(i);
          const checkStyle = checkStatus ? CHECK_STATUS_STYLE[checkStatus] : null;
          const isUnsupported = checkStatus === 'unsupported';
          return (
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
              borderColor: isUnsupported
                ? '#fecaca'
                : clickedIndex === i ? 'var(--color-brand-200)' : 'var(--color-border-subtle)',
              borderRadius: 'var(--radius-md)',
              cursor: 'pointer',
              transition: 'all var(--transition-fast)',
              boxShadow: clickedIndex === i ? '0 0 0 1px var(--color-brand-200)' : 'none',
              opacity: isUnsupported ? 0.62 : 1,
            }}
            onMouseOver={(e) => {
              if (clickedIndex !== i) {
                e.currentTarget.style.borderColor = isUnsupported ? '#fca5a5' : 'var(--color-border-default)';
                e.currentTarget.style.boxShadow = 'var(--shadow-md)';
                e.currentTarget.style.transform = 'translateY(-1px)';
              }
            }}
            onMouseOut={(e) => {
              if (clickedIndex !== i) {
                e.currentTarget.style.borderColor = isUnsupported ? '#fecaca' : 'var(--color-border-subtle)';
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

              {/* Label (page / section) + Derived badge + self-check status */}
              {(getCitationLabel(c) || getDerivedBadge(c) || checkStyle) && (
                <div style={{
                  fontSize: labelSize,
                  color: 'var(--color-text-tertiary)',
                  fontWeight: 500,
                  marginBottom: '6px',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}>
                  {getCitationLabel(c) && (
                    <span>{getCitationLabel(c)}</span>
                  )}
                  {getDerivedBadge(c) && (
                    <span style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px',
                      background: '#f5f3ff',
                      color: '#7c3aed',
                      padding: '1px 7px',
                      borderRadius: 'var(--radius-full)',
                      fontSize: '11px',
                      fontWeight: 600,
                      border: '1px solid #ddd6fe',
                      flexShrink: 0,
                    }}>
                      <span style={{
                        width: '5px',
                        height: '5px',
                        borderRadius: '50%',
                        background: '#a78bfa',
                        flexShrink: 0,
                      }} />
                      {getDerivedBadge(c)!.label} · Derived from transcript
                    </span>
                  )}
                  {checkStyle && (
                    <span style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px',
                      background: checkStyle.background,
                      color: checkStyle.color,
                      padding: '1px 7px',
                      borderRadius: 'var(--radius-full)',
                      fontSize: '11px',
                      fontWeight: 600,
                      border: `1px solid ${checkStyle.border}`,
                      flexShrink: 0,
                    }}>
                      ✕ {checkStyle.label}
                    </span>
                  )}
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
          );
        })}
      </div>

      {/* Citation export (PRD FR-4) */}
      <div style={{
        marginTop: d === 'compact' ? '8px' : '10px',
        paddingTop: '8px',
        borderTop: '1px solid var(--color-border-subtle)',
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        flexWrap: 'wrap',
      }}>
        <span style={{ fontSize: '11px', color: 'var(--color-text-tertiary)', fontWeight: 600, marginRight: '2px' }}>
          Export citations
        </span>
        {([
          ['bibtex', 'BibTeX'],
          ['gbt7714', 'GB/T 7714'],
          ['apa', 'APA'],
        ] as [CitationExportFormat, string][]).map(([format, label]) => (
          <button
            key={format}
            type="button"
            disabled={exporting}
            onClick={() => handleExport(format)}
            style={{
              fontSize: '11px',
              color: exportState?.format === format ? (exportState.ok ? 'var(--color-success-text)' : 'var(--color-error-text)') : 'var(--color-text-secondary)',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border-subtle)',
              cursor: exporting ? 'wait' : 'pointer',
              padding: '3px 10px',
              borderRadius: 'var(--radius-sm)',
              fontWeight: 600,
              transition: 'all var(--transition-fast)',
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.borderColor = 'var(--color-border-default)';
              e.currentTarget.style.background = 'var(--color-canvas)';
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.borderColor = 'var(--color-border-subtle)';
              e.currentTarget.style.background = 'var(--color-surface)';
            }}
          >
            {exportState?.format === format ? (exportState.ok ? 'Copied ✓' : 'Failed') : label}
          </button>
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
