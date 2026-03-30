# API Usage Guide

## Authentication
The current version does not require authentication for API access.
All endpoints are accessible via HTTP POST requests with JSON bodies.

## Search Endpoint
The `/search` endpoint performs semantic search over the knowledge base.
Send a POST request with a JSON body containing `query` (required) and `top_k` (optional, default 5).
Each result includes the matched text, metadata, and a structured citation for evidence display.

## Chat Endpoint
The `/chat` endpoint provides grounded question answering.
It retrieves relevant chunks, assembles them as evidence, and generates an answer using the configured LLM.
The response includes the generated answer, a list of citations, and the count of retrieved evidence chunks.

## Ingest Endpoint
The `/ingest` endpoint triggers a batch ingestion of all documents in the knowledge base directory.
Send a POST request with `{"rebuild": true}` to clear existing data and re-ingest, or `{"rebuild": false}` for incremental updates.

## Error Handling
All endpoints return structured error responses on failure.
Error responses include an `error` category, a human-readable `detail` message, and an optional `request_id` for tracing.

## Filters
Both `/search` and `/chat` support optional metadata filters.
Currently supported filter fields are `source` (document path) and `section` (heading name).
