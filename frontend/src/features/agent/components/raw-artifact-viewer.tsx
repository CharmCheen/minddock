import { ArtifactResponseItem, CitationItem } from '../../../core/types/api';
import { CitationList } from './citation-list';

export const RawArtifactViewer: React.FC<{ artifact: ArtifactResponseItem }> = ({ artifact }) => {
  const { kind, content, metadata } = artifact;
  const citations = (metadata?.grounded_answer as any)?.evidence as CitationItem[] | undefined;

  if (kind === 'text') {
    return (
      <div style={{ background: '#fff', border: '1px solid #f1f5f9', borderRadius: '12px', padding: '20px 24px', marginBottom: '16px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
        <div style={{ fontSize: '15px', lineHeight: '1.7', color: '#334155', whiteSpace: 'pre-wrap', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
          {String(content.text || '')}
        </div>
        {citations && citations.length > 0 && <CitationList citations={citations} />}
      </div>
    );
  }

  if (kind === 'mermaid') {
    return (
      <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '12px', padding: '16px 24px', marginBottom: '16px' }}>
        <div style={{ fontSize: '12px', color: '#6366f1', marginBottom: '12px', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Diagram Data (Mermaid)
        </div>
        <pre style={{ fontSize: '13px', overflowX: 'auto', whiteSpace: 'pre-wrap', color: '#1e293b', fontFamily: 'monospace' }}>
          {String(content.mermaid_code || '')}
        </pre>
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
      return (
        <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '12px', padding: '20px 24px', marginBottom: '16px' }}>
          
          {dataObj.common_points && dataObj.common_points.length > 0 && (
            <div style={{ marginBottom: '20px' }}>
              <h4 style={{ fontSize: '14px', color: '#10b981', margin: '0 0 8px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ fontSize: '16px' }}>🤝</span> Common Points
              </h4>
              <ul style={{ margin: 0, paddingLeft: '24px', color: '#334155', fontSize: '14px', lineHeight: '1.6' }}>
                {dataObj.common_points.map((pt: string, i: number) => <li key={i}>{pt}</li>)}
              </ul>
            </div>
          )}

          {dataObj.differences && dataObj.differences.length > 0 && (
            <div style={{ marginBottom: '20px' }}>
              <h4 style={{ fontSize: '14px', color: '#f59e0b', margin: '0 0 8px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ fontSize: '16px' }}>⚖️</span> Differences
              </h4>
              <ul style={{ margin: 0, paddingLeft: '24px', color: '#334155', fontSize: '14px', lineHeight: '1.6' }}>
                {dataObj.differences.map((diff: string, i: number) => <li key={i}>{diff}</li>)}
              </ul>
            </div>
          )}

          {dataObj.conflicts && dataObj.conflicts.length > 0 && (
            <div style={{ marginBottom: '12px' }}>
              <h4 style={{ fontSize: '14px', color: '#ef4444', margin: '0 0 8px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ fontSize: '16px' }}>⚠️</span> Conflicts
              </h4>
              <ul style={{ margin: 0, paddingLeft: '24px', color: '#334155', fontSize: '14px', lineHeight: '1.6' }}>
                {dataObj.conflicts.map((c: string, i: number) => <li key={i}>{c}</li>)}
              </ul>
            </div>
          )}

          {citations && citations.length > 0 && <div style={{ marginTop: '16px' }}><CitationList citations={citations} /></div>}
        </div>
      );
    }

    // Special rendering for Summarize Task schema (if it just returns a summary field)
    if (typeof rawData === 'object' && rawData !== null && 'summary' in rawData && Object.keys(rawData).length <= 3) {
      const dataObj = rawData as any;
      return (
        <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '12px', padding: '20px 24px', marginBottom: '16px' }}>
          <div style={{ fontSize: '15px', lineHeight: '1.7', color: '#334155', whiteSpace: 'pre-wrap', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
            {String(dataObj.summary || '')}
          </div>
          {citations && citations.length > 0 && <CitationList citations={citations} />}
        </div>
      );
    }

    // Default JSON Dump
    return (
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '12px', padding: '16px 24px', marginBottom: '16px' }}>
        <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '12px', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Structured Data
        </div>
        <pre style={{ fontSize: '13px', overflowX: 'auto', whiteSpace: 'pre-wrap', color: '#22d3ee', fontFamily: 'monospace' }}>
          {parsed}
        </pre>
        {citations && citations.length > 0 && <CitationList citations={citations} />}
      </div>
    );
  }

  return null;
};
