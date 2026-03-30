# Architecture Overview

## Design Principles
MindDock follows a layered architecture with clear separation of concerns.
The API layer handles HTTP routing and request validation.
The Service layer contains business logic and orchestrates the RAG pipeline.
The RAG layer manages document processing, embedding, and vector storage.

## Project Structure
The project is organized into several key packages:
- `app/api/` contains FastAPI routes and Pydantic schemas
- `app/services/` contains application services for search, chat, summarize, and ingest
- `app/rag/` contains the retrieval-augmented generation pipeline components
- `app/llm/` contains LLM provider implementations and fallback logic
- `app/core/` contains configuration, logging, and exception handling
- `ports/` defines abstract contracts for external dependencies
- `domain/` holds stable data models shared across the system

## Data Flow
The main data flow follows this path:
1. Documents enter through ingestion (CLI or API)
2. Text is split into chunks with section metadata preserved
3. Each chunk is embedded into a vector representation
4. Vectors and metadata are stored in ChromaDB
5. At query time, the question is embedded and matched against stored vectors
6. Retrieved chunks are filtered, reranked, and compressed
7. The LLM generates a grounded answer from the evidence
8. Citations are built from the matched chunks for traceability

## Extension Points
The architecture provides several extension points for future development:
- New document parsers can be added via the DocumentParser port
- Alternative vector stores can implement the VectorStore port
- Different LLM providers can implement the LLMProvider port
- Rerankers and compressors have abstract base classes ready for real implementations
