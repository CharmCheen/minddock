# MindDock Architecture

## Frontend Layer

The frontend is a React application built with Vite. It uses Zustand for state management. The agent panel supports chat, summarize, and compare task modes. The frontend communicates with the backend through REST endpoints and Server-Sent Events for streaming execution.

## API Layer

The API layer is built with FastAPI. It exposes endpoints for document ingestion, source management, search, chat, summarize, compare, and unified execution. The unified execution endpoint at /frontend/execute supports all task types through a single request contract. A streaming variant at /frontend/execute/stream delivers real-time execution events via SSE.

## Application Orchestration Layer

The application orchestration layer contains FrontendFacade, ChatOrchestrator, KnowledgeBaseOrchestrator, and SkillOrchestrator. FrontendFacade is the single entry point for all frontend requests. It handles intent classification, execution plan construction, runtime resolution, and response assembly. ChatOrchestrator manages retrieval-based tasks. KnowledgeBaseOrchestrator handles ingest and source management. SkillOrchestrator controls the skill system.

## RAG Layer

The RAG layer handles document ingestion, chunking, embedding, retrieval, reranking, compression, and evidence assembly. Documents are split into chunks using semantic-aware token chunking. Each chunk is embedded and stored in ChromaDB. At query time, the system retrieves relevant chunks, reranks them, compresses the context, and assembles evidence for generation.

## Generation Layer

The generation layer manages LLM runtime selection, prompt construction, and response generation. The RuntimeResolver selects the best runtime profile based on execution policy and capability matching. The RuntimeFactory creates runtime instances from resolved bindings. Prompt profiles define task-specific system prompts with evidence-first grounding rules. When evidence is insufficient, the system refuses to generate a grounded answer.

## Evaluation Layer

The evaluation layer provides deterministic metrics for retrieval quality, citation consistency, and insufficient-evidence detection. It loads benchmark datasets from JSONL files, executes each case through the unified execution chain, and produces JSON and Markdown reports. The evaluation runner supports task-type filtering and output directory configuration.
