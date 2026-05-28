# MindDock RAG Pipeline

## Chunking

Documents are split into chunks using semantic-aware token chunking. The splitter detects markdown headings, numbered sections, and paragraph boundaries. Each section is split into token-bounded windows with configurable chunk size and overlap. For PDF documents, a structured block-level chunker preserves table boundaries, heading hierarchies, and page metadata.

## Embedding

Each chunk is embedded using a local sentence-transformers model. The default embedding model is Qwen3-Embedding-0.6B. Embeddings are computed in batch during ingestion and stored alongside chunk text in ChromaDB. The embedding backend supports lazy loading and caching.

## Dense Retrieval

At query time, the user's query is embedded using the same model. ChromaDB performs cosine similarity search to find the most relevant chunks. The retrieval returns hits ranked by distance score. Metadata filters can narrow the search to specific sources, source types, sections, or page ranges.

## BM25 and RRF

MindDock supports hybrid retrieval that combines dense vector search with BM25 lexical search. The BM25 index is built lazily from all chunks stored in Chroma. Reciprocal Rank Fusion merges the dense and lexical ranked lists into a unified result. Hybrid retrieval is disabled by default and can be enabled via configuration.

## Rerank

The pipeline includes a rerank stage that reorders retrieved chunks by relevance. The default reranker uses a heuristic scoring approach based on token overlap and answer cue detection. A cross-encoder reranker option is planned for future implementation.

## Compression

After reranking, the compressor trims chunk text to fit within context window limits. The default compressor uses character-based trimming. LLM-based extractive compression is planned for future implementation.

## Evidence Assembly

Compressed chunks are assembled into an evidence block for the generation prompt. Evidence windows expand retrieved chunks with their document neighbors to provide broader context. The evidence block is formatted as numbered items with source attribution.

## Citation Binding

Each evidence chunk produces a citation record with doc_id, chunk_id, source path, snippet, page, section, and anchor. Citations are bound to the evidence chunks, not to the generated answer. This ensures citations are always grounded in actual retrieved content.

## Insufficient Evidence Handling

The pipeline includes multiple evidence gates. Before generation, the system checks whether retrieved evidence aligns with the query. After generation, the system detects model refusal patterns that indicate insufficient evidence. When evidence is insufficient, the system returns an empty citation list and a helpful refusal message.
