import { ClientEvent, ArtifactResponseItem, CitationItem } from '../../core/types/api';

export interface ConversationTurn {
  id: string;
  runId?: string;
  taskType: 'auto' | 'chat' | 'summarize' | 'compare';
  query: string;
  selectedSources: string[];
  status: 'running' | 'completed' | 'failed' | 'cancelled';
  artifacts: ArtifactResponseItem[];
  citations: CitationItem[];
  events: ClientEvent[];
  error?: string;
  createdAt: string;
  completedAt?: string;
}
