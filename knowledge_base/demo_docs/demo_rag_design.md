# RAG System Design

## Hybrid Retrieval

A modern RAG system combines dense vector retrieval with sparse keyword matching. The vector store indexes document chunks by their semantic embeddings, while BM25 or TF-IDF handles exact term matches. This hybrid approach ensures that both semantic similarity and keyword overlap contribute to the final retrieved set. The retrieval pipeline accepts a query, encodes it into the same embedding space, and returns the top-K chunks by cosine similarity.

## Citation Grounding

Citation grounding binds each generated claim to a specific source chunk. Every answer segment that references a document carries a citation that includes the doc_id, chunk_id, section heading, and a snippet. The grounding layer ensures that no claim is presented as bare assertion — it must be traceable to retrieved evidence. Grounding also enables the source drawer to highlight the exact passage that supports a given claim when users click a citation marker.

## Workflow Trace

The workflow trace records every step of the RAG pipeline as an observable event. Events include retrieval_started, retrieval_completed, rerank_completed, compress_completed, and retrieval_pipeline_completed. Each event carries a payload with the stage name and relevant counts such as retrieved_hits and reranked_hits. The trace is attached to the response metadata so clients can visualize the pipeline execution even when streaming is not used. This observability is essential for debugging retrieval quality issues.

## Reflection and Quality Gates

A quality gate runs after compression to decide whether the current evidence is sufficient for a reliable answer. The gate applies rule-based checks: empty hits fail immediately, thin compression fails for summarize tasks, and weak retrieval distances flag low confidence. When evidence is insufficient, the pipeline can perform one bounded retry with an expanded query. This reflection mechanism prevents the system from generating confident-sounding answers based on inadequate evidence. The reflection result includes attempt count, failure reasons, and a low-confidence flag, all recorded in the workflow trace.
