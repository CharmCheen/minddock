# MindDock API Usage

## Unified Execution Endpoint

The primary execution endpoint is POST /frontend/execute. It accepts a UnifiedExecutionRequestBody with task_type, user_input, top_k, filters, execution_policy, output_mode, citation_policy, and skill_policy. The response includes artifacts, citations, grounded_answer, metadata, and execution_summary. Supported task types are chat, summarize, search, and compare.

## Streaming Execution

The POST /frontend/execute/stream endpoint delivers real-time execution events via Server-Sent Events. Each event has a kind field indicating the event type: run_started, plan_built, step_started, step_completed, artifact_emitted, metadata_updated, warning_emitted, run_completed, or run_failed. The client can track execution progress and display intermediate results.

## Runtime Configuration

The runtime provider is configured via the /frontend/runtime-config endpoint. Configuration includes provider kind, base_url, api_key, and model name. The API key is never returned to the frontend; only a boolean api_key_configured flag is exposed. The configuration supports OpenAI-compatible providers and can be updated at runtime without restarting the server.

## Mock Runtime

When no real LLM runtime is configured, the system falls back to a mock runtime that returns deterministic placeholder responses. The mock_used flag in the response metadata indicates whether the mock runtime was used. This enables development and testing without external API dependencies.

## Fail-Closed Behavior

The runtime system follows fail-closed behavior. If the configured runtime fails during execution, the system raises a RuntimeInvocationError rather than silently falling back to mock output. The error is propagated to the client with a clear error message. This prevents the system from producing ungrounded answers without the user's knowledge.

## Source Management

Sources can be listed via GET /sources, inspected via GET /sources/{doc_id}/chunks, deleted via DELETE /sources/{doc_id}, and reingested via POST /sources/{doc_id}/reingest. These operations are available for managing indexed sources. The source catalog includes chunk count, sections, pages, and source state. Metadata filters support source, source_type, section, title_contains, and page range.

## Security

API keys are stored in environment variables and never written to disk. The test runtime endpoint at POST /frontend/runtime-config/test validates connectivity without persisting credentials. Error messages strip internal file paths to prevent information leakage.
