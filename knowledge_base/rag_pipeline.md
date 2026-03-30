# RAG Pipeline

## Overview
MindDock uses a Retrieval-Augmented Generation (RAG) pipeline to ground AI answers in user-uploaded documents.
The pipeline follows a standard flow: ingest documents, split into chunks, generate embeddings, store in a vector database, then retrieve relevant chunks at query time.

## Ingestion
Documents are ingested from the local `knowledge_base/` directory.
Supported formats in the current version include Markdown (.md) and plain text (.txt).
Each document is split into chunks using a section-aware splitter that preserves heading context.

## Embedding
Embeddings are generated using sentence-transformers (default model: all-MiniLM-L6-v2).
If the model is unavailable, a deterministic hash-based fallback is used for development and testing.
Each chunk receives a 384-dimensional vector that captures its semantic meaning.

## Retrieval
At query time, the user's question is embedded using the same model.
A cosine similarity search is performed against the Chroma vector store.
The top-k most similar chunks are returned as search hits.

## Generation
For chat queries, the retrieved chunks are assembled into an evidence context.
This context is sent to an LLM (OpenAI-compatible API or a local mock) along with the user's question.
The LLM generates a grounded answer that references only the provided evidence.
