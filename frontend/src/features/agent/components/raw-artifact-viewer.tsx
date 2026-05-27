import { ArtifactResponseItem, CitationItem } from '../../../core/types/api';
import { CitationList } from './citation-list';
import { useWorkspacePreferences } from '../../settings/workspace-preferences';

function truthyMetadataFlag(value: unknown): boolean {
  return value === true || String(value ?? '').toLowerCase() === 'true';
}

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
    hit_chunk_id: item.hit_chunk_id ?? item.chunk_id ?? null,
    window_chunk_ids: Array.isArray(item.window_chunk_ids)
      ? item.window_chunk_ids
      : item.hit_chunk_id || item.chunk_id
        ? [item.hit_chunk_id || item.chunk_id]
        : [],
    page_start: item.page_start ?? item.page ?? item.page_num ?? null,
    page_end: item.page_end ?? item.page ?? item.page_num ?? null,
    section_title: item.section_title ?? item.section ?? null,
    block_types: Array.isArray(item.block_types) ? item.block_types : [],
    table_id: item.table_id ?? null,
    hit_order_in_doc: item.hit_order_in_doc ?? null,
    hit_block_type: item.hit_block_type ?? null,
    hit_page: item.hit_page ?? item.page ?? item.page_num ?? null,
    is_windowed: Boolean(item.is_windowed),
    is_hit_only_fallback: Boolean(item.is_hit_only_fallback),
    citation_label: item.citation_label ?? null,
    evidence_preview: item.evidence_preview ?? null,
    window_chunk_count: item.window_chunk_count ?? (Array.isArray(item.window_chunk_ids) ? item.window_chunk_ids.length : 0),
    hit_in_window: item.hit_in_window ?? (
      Array.isArray(item.window_chunk_ids) && (item.hit_chunk_id || item.chunk_id)
        ? item.window_chunk_ids.includes(item.hit_chunk_id || item.chunk_id)
        : false
    ),
    evidence_window_reason: item.evidence_window_reason ?? null,
    is_derived: truthyMetadataFlag(item.is_derived),
    derived_kind: item.derived_kind ?? null,
    derived_from: item.derived_from ?? null,
    derived_basis: item.derived_basis ?? null,
    evidence_basis: item.evidence_basis ?? null,
    transcript_provider: item.transcript_provider ?? null,
    retrieval_basis: item.retrieval_basis ?? null,
  };
}

type StatusBadge = {
  label: string;
  color: string;
  background: string;
  border: string;
};

const SUPPORT_LABELS: Record<string, string> = {
  supported: 'Supported',
  partially_supported: 'Partial',
  insufficient_evidence: 'Insufficient',
  conflicting_evidence: 'Conflicting',
};

function humanizeStatus(value: string): string {
  return value
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function normalizeMetadataString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function nestedSupportStatus(value: unknown): string {
  if (!value || typeof value !== 'object') return '';
  return normalizeMetadataString((value as Record<string, unknown>).support_status);
}

function isInsufficientEvidenceRefusalText(value: string | undefined): boolean {
  if (!value) return false;
  const textStart = value.trim().slice(0, 300).toLowerCase();
  return /证据不足|根据.{0,30}证据.{0,30}无法|无法.{0,20}(回答|介绍|确定|判断|给出)|未包含.{0,20}(信息|内容)|不包含.{0,20}相关|insufficient evidence|not enough evidence|provided evidence.{0,80}(does not|doesn't|cannot|can't)|cannot answer/.test(textStart);
}

function isInsufficientEvidenceArtifact(
  metadata: Record<string, unknown> | undefined,
  content: Record<string, unknown>,
  answerText?: string,
): boolean {
  const grounded = metadata?.grounded_answer as Record<string, unknown> | undefined;
  const compare = metadata?.compare_result as Record<string, unknown> | undefined;
  const rawData = content.data as Record<string, unknown> | undefined;
  const refusalReason = metadata?.refusal_reason || grounded?.refusal_reason || compare?.refusal_reason || rawData?.refusal_reason;
  const hasRefusal = refusalReason !== null && refusalReason !== undefined && String(refusalReason).trim() !== '';

  return truthyMetadataFlag(metadata?.insufficient_evidence)
    || normalizeMetadataString(metadata?.support_status) === 'insufficient_evidence'
    || nestedSupportStatus(grounded) === 'insufficient_evidence'
    || nestedSupportStatus(compare) === 'insufficient_evidence'
    || nestedSupportStatus(rawData) === 'insufficient_evidence'
    || hasRefusal
    || isInsufficientEvidenceRefusalText(answerText);
}

function buildStatusBadges(metadata: Record<string, unknown> | undefined, answerText?: string): StatusBadge[] {
  if (!metadata) return [];

  const grounded = metadata.grounded_answer as Record<string, unknown> | undefined;
  const compare = metadata.compare_result as Record<string, unknown> | undefined;
  const metadataSupportStatus = normalizeMetadataString(metadata.support_status);
  const groundedSupportStatus = nestedSupportStatus(grounded);
  const compareSupportStatus = nestedSupportStatus(compare);
  const refusalReason = metadata.refusal_reason || grounded?.refusal_reason || compare?.refusal_reason;
  const fallbackUsed = metadata.fallback_used === true;
  const mockUsed = metadata.mock_used === true;
  const runtimeStatus = String(metadata.runtime_status || '');
  const hasRefusal = refusalReason !== null && refusalReason !== undefined && String(refusalReason).trim() !== '';
  const refusedByAnswerText = isInsufficientEvidenceRefusalText(answerText);
  const insufficientEvidence = truthyMetadataFlag(metadata.insufficient_evidence)
    || metadataSupportStatus === 'insufficient_evidence'
    || groundedSupportStatus === 'insufficient_evidence'
    || compareSupportStatus === 'insufficient_evidence'
    || hasRefusal
    || refusedByAnswerText;
  const supportStatus = insufficientEvidence
    ? 'insufficient_evidence'
    : metadataSupportStatus || groundedSupportStatus || compareSupportStatus;
  const badges: StatusBadge[] = [];

  if (runtimeStatus === 'mock' || mockUsed) {
    badges.push({
      label: 'Using mock/fallback',
      color: '#b45309',
      background: '#fffbeb',
      border: '#fde68a',
    });
  } else if (fallbackUsed) {
    badges.push({
      label: 'Using fallback',
      color: '#b45309',
      background: '#fffbeb',
      border: '#fde68a',
    });
  }

  // Mock / Demo mode: configured runtime not available, using mock LLM
  if (false && (runtimeStatus === 'mock' || mockUsed)) {
    badges.push({
      label: 'Mock 模式',
      color: '#b45309',
      background: '#fffbeb',
      border: '#fde68a',
    });
  } else if (false && fallbackUsed) {
    // Fallback without mock_used: degraded but not mock
    badges.push({
      label: 'Fallback',
      color: '#b45309',
      background: '#fffbeb',
      border: '#fde68a',
    });
  }

  if (supportStatus) {
    badges.push({
      label: SUPPORT_LABELS[supportStatus] || humanizeStatus(supportStatus),
      color: insufficientEvidence ? '#b91c1c' : supportStatus === 'supported' ? '#15803d' : '#0369a1',
      background: insufficientEvidence ? '#fef2f2' : supportStatus === 'supported' ? '#f0fdf4' : '#eff6ff',
      border: insufficientEvidence ? '#fecaca' : supportStatus === 'supported' ? '#bbf7d0' : '#bfdbfe',
    });
  }

  if (refusalReason) {
    badges.push({
      label: `Refusal: ${humanizeStatus(String(refusalReason))}`,
      color: '#b91c1c',
      background: '#fef2f2',
      border: '#fecaca',
    });
  }

  return badges;
}

function StatusBadges({ badges, density }: { badges: StatusBadge[]; density: 'compact' | 'comfortable' }) {
  if (badges.length === 0) return null;

  return (
    <>
      {badges.map((badge) => (
        <span
          key={badge.label}
          style={{
            fontSize: '11px',
            fontWeight: 600,
            color: badge.color,
            background: badge.background,
            border: `1px solid ${badge.border}`,
            padding: density === 'compact' ? '2px 8px' : '3px 10px',
            borderRadius: 'var(--radius-sm)',
          }}
        >
          {badge.label}
        </span>
      ))}
    </>
  );
}

function renderLightMarkdown(text: string, density: 'compact' | 'comfortable'): React.ReactNode {
  return text.split('\n').map((line, i) => {
    if (line.startsWith('## ')) {
      return (
        <div key={i} style={{
          fontSize: '16px',
          fontWeight: 700,
          color: 'var(--color-text-primary)',
          marginTop: density === 'compact' ? '14px' : '20px',
          marginBottom: density === 'compact' ? '8px' : '10px',
          paddingBottom: '6px',
          borderBottom: '1px solid var(--color-border-subtle)',
        }}>
          {line.replace(/^## /, '')}
        </div>
      );
    }
    if (line.startsWith('### ')) {
      return (
        <div key={i} style={{
          fontSize: '14px',
          fontWeight: 600,
          color: 'var(--color-text-primary)',
          marginTop: density === 'compact' ? '10px' : '14px',
          marginBottom: density === 'compact' ? '6px' : '8px',
          paddingLeft: '10px',
          borderLeft: '3px solid var(--color-brand-200)',
        }}>
          {line.replace(/^### /, '')}
        </div>
      );
    }
    if (line.trim() === '') {
      return <div key={i} style={{ height: density === 'compact' ? '8px' : '12px' }} />;
    }
    const parts = line.split(/(\*\*[^*]+\*\*)/g);
    return (
      <div key={i} style={{ marginBottom: density === 'compact' ? '3px' : '5px', lineHeight: '1.7' }}>
        {parts.map((part, j) =>
          part.startsWith('**') && part.endsWith('**')
            ? <strong key={j} style={{ color: 'var(--color-text-primary)', fontWeight: 600 }}>{part.slice(2, -2)}</strong>
            : part
        )}
      </div>
    );
  });
}

const cardBase = (density: 'compact' | 'comfortable'): React.CSSProperties => ({
  background: 'var(--color-surface)',
  border: '1px solid var(--color-border-subtle)',
  borderRadius: 'var(--radius-lg)',
  boxShadow: 'var(--shadow-sm)',
  padding: density === 'compact' ? '16px' : '22px',
});

const typeBadge = (color: string, bg: string, density: 'compact' | 'comfortable'): React.CSSProperties => ({
  fontSize: '11px',
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
  color,
  background: bg,
  padding: density === 'compact' ? '3px 10px' : '4px 12px',
  borderRadius: 'var(--radius-sm)',
  display: 'inline-flex',
  alignItems: 'center',
});

type CompareSectionKey = 'common_points' | 'differences' | 'conflicts';

const compareBadgeStyle = (color: string, bg: string, border: string): React.CSSProperties => ({
  display: 'inline-flex',
  alignItems: 'center',
  fontSize: '11px',
  fontWeight: 600,
  color,
  background: bg,
  border: `1px solid ${border}`,
  padding: '1px 7px',
  borderRadius: 'var(--radius-full)',
  lineHeight: 1.5,
});

function CompareTaxonomyBadge({ value }: { value: unknown }) {
  if (typeof value !== 'string' || value.trim() === '') return null;

  return (
    <span style={compareBadgeStyle('#475569', '#f8fafc', '#e2e8f0')}>
      {value}
    </span>
  );
}

const COVERAGE_LABELS: Record<string, string> = {
  balanced: 'balanced evidence',
  left_heavy: 'left-heavy evidence',
  right_heavy: 'right-heavy evidence',
  single_sided: 'single-sided evidence',
};

function CompareCoverageBadge({ pt, sectionKey }: { pt: any; sectionKey: CompareSectionKey }) {
  if (sectionKey === 'common_points') return null;

  const coverageLabel = pt?.evidence_coverage?.coverage_label;
  if (typeof coverageLabel !== 'string' || coverageLabel === 'unknown') return null;

  const label = COVERAGE_LABELS[coverageLabel];
  if (!label) return null;

  return (
    <span style={compareBadgeStyle('#0369a1', '#f0f9ff', '#bae6fd')}>
      {label}
    </span>
  );
}

function CompareConfidenceBadge({ value }: { value: unknown }) {
  if (value === null || value === undefined) return null;

  const confidence = Number(value);
  if (!Number.isFinite(confidence)) return null;

  const percent = Math.round((confidence <= 1 ? confidence * 100 : confidence));

  return (
    <span style={compareBadgeStyle('#6d28d9', '#f5f3ff', '#ddd6fe')}>
      confidence {percent}%
    </span>
  );
}

function renderComparePointBadges(pt: any, sectionKey: CompareSectionKey) {
  return (
    <span style={{ display: 'inline-flex', flexWrap: 'wrap', gap: '5px', marginLeft: '8px', verticalAlign: 'baseline' }}>
      <CompareTaxonomyBadge value={pt?.taxonomy} />
      <CompareCoverageBadge pt={pt} sectionKey={sectionKey} />
      <CompareConfidenceBadge value={pt?.confidence} />
    </span>
  );
}

export const RawArtifactViewer: React.FC<{ artifact: ArtifactResponseItem }> = ({ artifact }) => {
  const { kind, content, metadata, citations: artifactCitations } = artifact;
  const { density } = useWorkspacePreferences();
  const answerText = kind === 'text' ? String(content.text || '') : undefined;
  const statusBadges = buildStatusBadges(metadata, answerText);

  // Extract citations from multiple possible locations
  // Skip citations when evidence is insufficient (refusal response)
  const insufficientEvidence = isInsufficientEvidenceArtifact(metadata, content, answerText);

  let citations: CitationItem[] | undefined;
  if (!insufficientEvidence) {
    if (artifactCitations && artifactCitations.length > 0) {
      citations = artifactCitations.map(normalizeToCitationItem);
    } else if (metadata?.grounded_answer) {
      const evidence = (metadata.grounded_answer as any)?.evidence;
      if (Array.isArray(evidence) && evidence.length > 0) {
        citations = evidence.map(normalizeToCitationItem);
      }
    }
  }

  if (kind === 'text') {
    return (
      <div style={{
        ...cardBase(density),
        display: 'flex',
        flexDirection: 'column',
        gap: density === 'compact' ? '14px' : '18px',
        animation: 'fadeSlideUp 250ms ease-out forwards',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: density === 'compact' ? '6px' : '8px', flexWrap: 'wrap' }}>
          <StatusBadges badges={statusBadges} density={density} />
        </div>
        <div style={{
          fontSize: '15px',
          lineHeight: '1.7',
          color: 'var(--color-text-secondary)',
          whiteSpace: 'normal',
          fontFamily: 'var(--font-sans)',
        }}>
          {renderLightMarkdown(String(content.text || ''), density)}
        </div>
        {citations && citations.length > 0 && <CitationList citations={citations} />}
      </div>
    );
  }

  if (kind === 'mermaid') {
    return (
      <div style={{
        ...cardBase(density),
        animation: 'fadeSlideUp 250ms ease-out forwards',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: density === 'compact' ? '6px' : '8px', marginBottom: density === 'compact' ? '12px' : '16px' }}>
          <span style={typeBadge('#8b5cf6', '#f3e8ff', density)}>
            Diagram
          </span>
        </div>
        <div style={{
          background: 'var(--color-canvas-subtle)',
          border: '1px solid var(--color-border-subtle)',
          borderRadius: 'var(--radius-md)',
          padding: density === 'compact' ? '12px 14px' : '16px 20px',
          overflowX: 'auto',
        }}>
          <pre style={{
            fontSize: '13px',
            overflowX: 'auto',
            whiteSpace: 'pre-wrap',
            color: 'var(--color-text-primary)',
            fontFamily: 'var(--font-mono)',
            margin: 0,
            lineHeight: '1.6',
          }}>
            {String(content.mermaid_code || '')}
          </pre>
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
      const commonPoints = Array.isArray(dataObj.common_points) ? dataObj.common_points : [];
      const differences = Array.isArray(dataObj.differences) ? dataObj.differences : [];
      const conflicts = Array.isArray(dataObj.conflicts) ? dataObj.conflicts : [];
      const hasCompareContent = commonPoints.length > 0 || differences.length > 0 || conflicts.length > 0;

      if (!hasCompareContent) {
        // Check support_status from the data payload as well
        const dataSupportStatus = typeof dataObj.support_status === 'string' ? dataObj.support_status : '';
        const isInsufficient = insufficientEvidence || dataSupportStatus === 'insufficient_evidence';
        if (isInsufficient) {
          return null;
        }
        return (
          <div style={{
            ...cardBase(density),
            animation: 'fadeSlideUp 250ms ease-out forwards',
          }}>
            <span style={typeBadge('#b45309', '#fffbeb', density)}>
              Comparison
            </span>
            <div style={{ marginTop: '12px', color: 'var(--color-text-secondary)', fontSize: '14px', lineHeight: 1.7 }}>
              暂无可展示的结构化对比结果。
            </div>
          </div>
        );
      }

      const getStatement = (pt: any): string => {
        return pt?.statement || pt?.summary_note || String(pt) || '';
      };

      const sectionCard = (title: string, count: number, titleColor: string, titleBg: string, borderColor: string, items: any[], sectionKey: CompareSectionKey) => (
        <div style={{ marginBottom: density === 'compact' ? '14px' : '18px' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: density === 'compact' ? '6px' : '8px',
            marginBottom: density === 'compact' ? '8px' : '10px',
            padding: density === 'compact' ? '8px 12px' : '10px 14px',
            background: titleBg,
            border: `1px solid ${borderColor}`,
            borderRadius: 'var(--radius-md)',
          }}>
            <h4 style={{
              fontSize: '12px',
              color: titleColor,
              margin: 0,
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}>
              {title}
            </h4>
            <span style={{
              fontSize: '11px',
              color: titleColor,
              background: 'rgba(255,255,255,0.6)',
              padding: '2px 8px',
              borderRadius: 'var(--radius-full)',
              marginLeft: 'auto',
              fontWeight: 600,
            }}>
              {count}
            </span>
          </div>
          <ul style={{ margin: 0, paddingLeft: '24px', color: 'var(--color-text-secondary)', fontSize: '14px', lineHeight: '1.75' }}>
            {items.map((pt: any, i: number) => (
              <li key={i} style={{ marginBottom: density === 'compact' ? '4px' : '6px' }}>
                {getStatement(pt)}
                {renderComparePointBadges(pt, sectionKey)}
              </li>
            ))}
          </ul>
        </div>
      );

      return (
        <div style={{
          ...cardBase(density),
          animation: 'fadeSlideUp 250ms ease-out forwards',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: density === 'compact' ? '6px' : '8px', marginBottom: density === 'compact' ? '14px' : '20px' }}>
            <span style={typeBadge('#8b5cf6', '#f3e8ff', density)}>
              Comparison Result
            </span>
          </div>

          {commonPoints.length > 0 && sectionCard(
            'Common Points', commonPoints.length, '#15803d', '#f0fdf4', '#bbf7d0', commonPoints, 'common_points'
          )}

          {differences.length > 0 && sectionCard(
            'Differences', differences.length, '#b45309', '#fffbeb', '#fde68a', differences, 'differences'
          )}

          {conflicts.length > 0 && sectionCard(
            'Conflicts', conflicts.length, '#dc2626', '#fef2f2', '#fecaca', conflicts, 'conflicts'
          )}

          {citations && citations.length > 0 && <div style={{ marginTop: density === 'compact' ? '14px' : '20px' }}><CitationList citations={citations} /></div>}
        </div>
      );
    }

    // Special rendering for Summarize Task schema
    if (typeof rawData === 'object' && rawData !== null && 'summary' in rawData && Object.keys(rawData).length <= 3) {
      const dataObj = rawData as any;
      return (
        <div style={{
          ...cardBase(density),
          animation: 'fadeSlideUp 250ms ease-out forwards',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: density === 'compact' ? '6px' : '8px', marginBottom: density === 'compact' ? '12px' : '16px' }}>
            <span style={typeBadge('#10b981', '#d1fae5', density)}>
              Summary
            </span>
          </div>
          <div style={{
            fontSize: '15px',
            lineHeight: '1.75',
            color: 'var(--color-text-secondary)',
            whiteSpace: 'pre-wrap',
            fontFamily: 'var(--font-sans)',
          }}>
            {String(dataObj.summary || '')}
          </div>
          {citations && citations.length > 0 && <CitationList citations={citations} />}
        </div>
      );
    }

    // Default JSON Dump
    return (
      <div style={{
        ...cardBase(density),
        background: '#1e293b',
        border: '1px solid #334155',
        animation: 'fadeSlideUp 250ms ease-out forwards',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: density === 'compact' ? '6px' : '8px', marginBottom: density === 'compact' ? '10px' : '14px' }}>
          <span style={{
            ...typeBadge('#94a3b8', 'rgba(148,163,184,0.15)', density),
            textTransform: 'uppercase',
          }}>
            Data
          </span>
        </div>
        <pre style={{
          fontSize: '13px',
          overflowX: 'auto',
          whiteSpace: 'pre-wrap',
          color: '#e2e8f0',
          fontFamily: 'var(--font-mono)',
          margin: 0,
          lineHeight: '1.6',
        }}>
          {parsed}
        </pre>
        {citations && citations.length > 0 && <CitationList citations={citations} />}
      </div>
    );
  }

  return null;
};
