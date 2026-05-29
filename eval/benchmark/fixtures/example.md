# MindDock Example

## Overview

MindDock is an evidence-first personal knowledge assistant. It helps users ingest local documents, retrieve relevant evidence, and generate grounded answers with citations. This example describes search and chat related interfaces through the evidence and citation workflow. The system is designed for individual use on a local machine, not as a cloud service.

## Storage

MindDock stores document chunks and metadata in ChromaDB, a persistent vector store. Each document is split into chunks during ingestion. Each chunk is embedded using a local embedding model and stored with its text, metadata, and vector representation. The storage layer uses langchain-chroma as the integration wrapper.

## Citations

Every grounded answer includes structured citation records. Chat and summarize responses return citation fields for doc_id, chunk_id, source path, snippet text, page number, section heading, and anchor. Citations are derived from the retrieved evidence chunks, not from the model's internal knowledge. When evidence is insufficient, the system returns an empty citation list and marks the response as insufficient_evidence.

## Workflow Trace

Each execution produces a workflow trace that records the steps taken: retrieval, reranking, compression, generation, and output formatting. The trace includes timing information, retrieval statistics, and any warnings or issues encountered during execution.
