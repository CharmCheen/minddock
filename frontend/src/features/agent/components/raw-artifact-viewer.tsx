import { ArtifactResponseItem, CitationItem } from '../../../core/types/api';
import { useEffect } from 'react';
import { CitationList } from './citation-list';

// Mermaid diagram renderer — loads mermaid from CDN on demand
const MermaidRenderer: React.FC<{ code: string; chartId: string }> = ({ code, chartId }) => {
  useEffect(() => {
    if (!code) return;
    const render = () => {
      const el = document.getElementById(chartId);
      if (!el || el.dataset.processed) return;
      window.mermaid?.run({ nodes: [el] });
      el.dataset.processed = 'true';
    };
    if (!window.mermaid) {
      const script = document.createElement('script');
      script.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
      script.onload = () => { window.mermaid?.initialize({ startOnLoad: false }); render(); };
      document.head.appendChild(script);
    } else {
      render();
    }
  }, [code, chartId]);
  return <div className="mermaid" id={chartId}>{code}</div>;
};

// Helper to normalize evidence items to CitationItem format
function normalizeToCitationItem(item: any): CitationItem {
  return {
    doc_id: item.doc_id || '',
    chunk_id: item.chunk_id || item.ref || '',
    chunk_index: item.chunk_index ?? 0,
    inline_ref: item.inline_ref || item.ref || item.chunk_id || String(item.chunk_index ?? ''),
    page_num: item.page_num ?? item.page ?? null,
    snippet: item.snippet || item.text || '',
    source: item.source || '',
    page: item.page ?? null,
    anchor: item.anchor ?? null,
    title: item.title ?? null,
    section: item.section ?? null,
    location: item.location ?? null,
    ref: item.ref ?? null,
  };
}

export const RawArtifactViewer: React.FC<{ artifact: ArtifactResponseItem }> = ({ artifact }) => {
  const { kind, content, metadata, citations: artifactCitations } = artifact;

  // Extract citations from multiple possible locations
  let citations: CitationItem[] | undefined;
  if (artifactCitations && artifactCitations.length > 0) {
    citations = artifactCitations.map(normalizeToCitationItem);
  } else if (metadata?.grounded_answer) {
    const evidence = (metadata.grounded_answer as any)?.evidence;
    if (Array.isArray(evidence) && evidence.length > 0) {
      citations = evidence.map(normalizeToCitationItem);
    }
  }

  if (kind === 'text') {
    return (
      <div style={{
        background: '#fff',
        border: '1px solid #e2e8f0',
        borderRadius: '12px',
        padding: '20px 24px',
        boxShadow: '0 1px 4px rgba(0,0,0,0.04)'
      }}>
        {/* Artifact Type Badge */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
          <span style={{
            fontSize: '11px',
            fontWeight: '600',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            color: '#3b82f6',
            background: '#eff6ff',
            padding: '3px 10px',
            borderRadius: '6px'
          }}>
            Text Response
          </span>
        </div>
        <div style={{
          fontSize: '15px',
          lineHeight: '1.8',
          color: '#334155',
          whiteSpace: 'pre-wrap',
          fontFamily: 'system-ui, -apple-system, sans-serif'
        }}>
          {String(content.text || '')}
        </div>
        {citations && citations.length > 0 && <CitationList citations={citations} />}
      </div>
    );
  }

  if (kind === 'mermaid') {
    const code = String(content.mermaid_code || '');
    const chartId = `mermaid-${code.slice(0, 32).replace(/[^a-zA-Z0-9]/g, '')}`;
    return (
      <div style={{
        background: '#fff',
        border: '1px solid #e2e8f0',
        borderRadius: '12px',
        padding: '20px 24px',
        boxShadow: '0 1px 4px rgba(0,0,0,0.04)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
          <span style={{
            fontSize: '11px',
            fontWeight: '600',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            color: '#8b5cf6',
            background: '#f3e8ff',
            padding: '3px 10px',
            borderRadius: '6px'
          }}>
            Diagram
          </span>
        </div>
        <div style={{
          background: '#f8fafc',
          border: '1px solid #e2e8f0',
          borderRadius: '8px',
          padding: '16px 20px',
          overflowX: 'auto'
        }}>
        <MermaidRenderer code={code} chartId={chartId} />
        </div>
        {citations && citations.length > 0 && <CitationList citations={citations} />}
      </div>
    );
  }

  if (kind === 'structured_json') {
    const rawData = content.data !== undefined ? content.data : content;
    let parsed = '';
    try {
      parsed = JSON.stringify(rawData, null, 2);
    } catch {
      parsed = String(rawData);
    }

    // Special rendering for Compare Task schema
    if (typeof rawData === 'object' && rawData !== null && ('common_points' in rawData || 'differences' in rawData)) {
      const dataObj = rawData as any;

      // Helper to extract statement from compared point item
      const getStatement = (pt: any): string => {
        return pt?.statement || pt?.summary_note || String(pt) || '';
      };

      return (
        <div style={{
          background: '#fff',
          border: '1px solid #e2e8f0',
          borderRadius: '12px',
          padding: '20px 24px',
          boxShadow: '0 1px 4px rgba(0,0,0,0.04)'
        }}>
          {/* Artifact Type Badge */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px' }}>
            <span style={{
              fontSize: '11px',
              fontWeight: '600',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              color: '#8b5cf6',
              background: '#f3e8ff',
              padding: '3px 10px',
              borderRadius: '6px'
            }}>
              Comparison Result
            </span>
          </div>

          {dataObj.common_points && dataObj.common_points.length > 0 && (
            <div style={{ marginBottom: '20px' }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                marginBottom: '10px',
                padding: '8px 12px',
                background: '#f0fdf4',
                border: '1px solid #bbf7d0',
                borderRadius: '8px'
              }}>
                <h4 style={{
                  fontSize: '12px',
                  color: '#15803d',
                  margin: 0,
                  fontWeight: '700',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em'
                }}>
                  Common Points
                </h4>
                <span style={{
                  fontSize: '11px',
                  color: '#15803d',
                  background: '#dcfce7',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  marginLeft: 'auto',
                  fontWeight: '500'
                }}>
                  {dataObj.common_points.length}
                </span>
              </div>
              <ul style={{ margin: 0, paddingLeft: '24px', color: '#334155', fontSize: '14px', lineHeight: '1.8' }}>
                {dataObj.common_points.map((pt: any, i: number) => <li key={i} style={{ marginBottom: '6px' }}>{getStatement(pt)}</li>)}
              </ul>
            </div>
          )}

          {dataObj.differences && dataObj.differences.length > 0 && (
            <div style={{ marginBottom: '20px' }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                marginBottom: '10px',
                padding: '8px 12px',
                background: '#fffbeb',
                border: '1px solid #fde68a',
                borderRadius: '8px'
              }}>
                <h4 style={{
                  fontSize: '12px',
                  color: '#b45309',
                  margin: 0,
                  fontWeight: '700',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em'
                }}>
                  Differences
                </h4>
                <span style={{
                  fontSize: '11px',
                  color: '#b45309',
                  background: '#fef3c7',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  marginLeft: 'auto',
                  fontWeight: '500'
                }}>
                  {dataObj.differences.length}
                </span>
              </div>
              <ul style={{ margin: 0, paddingLeft: '24px', color: '#334155', fontSize: '14px', lineHeight: '1.8' }}>
                {dataObj.differences.map((pt: any, i: number) => <li key={i} style={{ marginBottom: '6px' }}>{getStatement(pt)}</li>)}
              </ul>
            </div>
          )}

          {dataObj.conflicts && dataObj.conflicts.length > 0 && (
            <div>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                marginBottom: '10px',
                padding: '8px 12px',
                background: '#fef2f2',
                border: '1px solid #fecaca',
                borderRadius: '8px'
              }}>
                <h4 style={{
                  fontSize: '12px',
                  color: '#dc2626',
                  margin: 0,
                  fontWeight: '700',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em'
                }}>
                  Conflicts
                </h4>
                <span style={{
                  fontSize: '11px',
                  color: '#dc2626',
                  background: '#fee2e2',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  marginLeft: 'auto',
                  fontWeight: '500'
                }}>
                  {dataObj.conflicts.length}
                </span>
              </div>
              <ul style={{ margin: 0, paddingLeft: '24px', color: '#334155', fontSize: '14px', lineHeight: '1.8' }}>
                {dataObj.conflicts.map((pt: any, i: number) => <li key={i} style={{ marginBottom: '6px' }}>{getStatement(pt)}</li>)}
              </ul>
            </div>
          )}

          {citations && citations.length > 0 && <div style={{ marginTop: '20px' }}><CitationList citations={citations} /></div>}
        </div>
      );
    }

    // Special rendering for Summarize Task schema (if it just returns a summary field)
    if (typeof rawData === 'object' && rawData !== null && 'summary' in rawData && Object.keys(rawData).length <= 3) {
      const dataObj = rawData as any;
      return (
        <div style={{
          background: '#fff',
          border: '1px solid #e2e8f0',
          borderRadius: '12px',
          padding: '20px 24px',
          boxShadow: '0 1px 4px rgba(0,0,0,0.04)'
        }}>
          {/* Artifact Type Badge */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
            <span style={{
              fontSize: '11px',
              fontWeight: '600',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              color: '#10b981',
              background: '#d1fae5',
              padding: '3px 10px',
              borderRadius: '6px'
            }}>
              Summary
            </span>
          </div>
          <div style={{
            fontSize: '15px',
            lineHeight: '1.8',
            color: '#334155',
            whiteSpace: 'pre-wrap',
            fontFamily: 'system-ui, -apple-system, sans-serif'
          }}>
            {String(dataObj.summary || '')}
          </div>
          {citations && citations.length > 0 && <CitationList citations={citations} />}
        </div>
      );
    }

    // Default JSON Dump - improved styling
    return (
      <div style={{
        background: '#1e293b',
        border: '1px solid #334155',
        borderRadius: '12px',
        padding: '16px 20px',
        boxShadow: '0 1px 4px rgba(0,0,0,0.08)'
      }}>
        {/* Artifact Type Badge */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
          <span style={{
            fontSize: '11px',
            fontWeight: '600',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            color: '#94a3b8',
            background: 'rgba(148,163,184,0.15)',
            padding: '3px 10px',
            borderRadius: '6px'
          }}>
            Data
          </span>
        </div>
        <pre style={{
          fontSize: '13px',
          overflowX: 'auto',
          whiteSpace: 'pre-wrap',
          color: '#e2e8f0',
          fontFamily: 'monospace',
          margin: 0
        }}>
          {parsed}
        </pre>
        {citations && citations.length > 0 && <CitationList citations={citations} />}
      </div>
    );
  }

  return null;
};
