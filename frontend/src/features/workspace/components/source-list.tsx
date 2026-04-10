import React, { useEffect, useState } from 'react';
import { SourceService } from '../../../lib/api/services/sources';
import { SourceCatalogResponse } from '../../../core/types/api';
import { useWorkspaceStore } from '../store';
import { SourceDetailPanel } from './source-detail-panel';

export const SourceList: React.FC = () => {
  const [sources, setSources] = useState<SourceCatalogResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const { selectedDocId, setSelectedDoc } = useWorkspaceStore();

  useEffect(() => {
    let mounted = true;
    SourceService.getSources()
      .then(data => {
        if (mounted) {
          setSources(data);
          setLoading(false);
        }
      })
      .catch(err => {
        if (mounted) {
          setError(err.message || 'Failed to load sources');
          setLoading(false);
        }
      });
    return () => { mounted = false; };
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#f8fafc' }}>
      <div style={{ padding: '16px 24px', borderBottom: '1px solid #e2e8f0', background: '#fff' }}>
        <h2 style={{ margin: 0, fontSize: '18px', fontWeight: '600', color: '#0f172a' }}>Document Workspace</h2>
      </div>
      
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Source List Column */}
        <div style={{ width: '40%', minWidth: '200px', borderRight: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column', background: '#fff' }}>
          <div style={{ padding: '12px 16px', background: '#f1f5f9', fontSize: '13px', fontWeight: '600', color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Knowledge Sources
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {loading && (
              <div style={{ padding: '24px 16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
                <span className="dot-pulse" style={{ color: '#3b82f6' }}>●●●</span>
                <span style={{ color: '#64748b', fontSize: '13px' }}>Loading Sources...</span>
              </div>
            )}
            {error && (
              <div style={{ padding: '24px 16px', textAlign: 'center' }}>
                <div style={{ color: '#ef4444', fontSize: '24px', marginBottom: '8px' }}>⚠️</div>
                <div style={{ color: '#ef4444', fontSize: '14px', fontWeight: '500' }}>Failed to load sources</div>
                <div style={{ color: '#f87171', fontSize: '12px', marginTop: '4px' }}>{error}</div>
              </div>
            )}
            {!loading && !error && sources.length === 0 && (
              <div style={{ padding: '32px 16px', textAlign: 'center' }}>
                <div style={{ color: '#cbd5e1', fontSize: '32px', marginBottom: '12px' }}>🗂️</div>
                <div style={{ color: '#475569', fontSize: '14px', fontWeight: '500' }}>No Sources Found</div>
                <div style={{ color: '#94a3b8', fontSize: '12px', marginTop: '4px' }}>Upload documents to build your knowledge base.</div>
              </div>
            )}
            {sources.map(src => (
              <div 
                key={src.doc_id}
                onClick={() => setSelectedDoc(src.doc_id, src)}
                style={{ 
                  padding: '12px 16px', 
                  borderBottom: '1px solid #f1f5f9',
                  cursor: 'pointer',
                  background: selectedDocId === src.doc_id ? '#eff6ff' : '#fff',
                  borderLeft: selectedDocId === src.doc_id ? '3px solid #3b82f6' : '3px solid transparent'
                }}
              >
                <div style={{ fontSize: '14px', fontWeight: '500', color: '#1e293b', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {src.title || src.doc_id}
                </div>
                <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px', display: 'flex', justifyContent: 'space-between' }}>
                  <span>{src.category}</span>
                  <span>{src.ingest_status || 'unknown'}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Source Detail Preview */}
        <div style={{ flex: 1, background: '#f8fafc', display: 'flex', flexDirection: 'column', padding: '24px', overflow: 'hidden' }}>
          <SourceDetailPanel />
        </div>
      </div>
    </div>
  );
};
