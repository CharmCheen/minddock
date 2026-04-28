# Agentic Knowledge Assistant

## Intent Detection

An agentic knowledge assistant detects user intent before selecting a retrieval or generation strategy. Rule-based classifiers inspect query text for keywords such as compare, summarize, or question marks. When no keyword matches, the system defaults to a chat-style conversational response. Intent detection also distinguishes between single-document and cross-document queries — a compare intent targeting two named documents triggers a source-grounded comparison rather than a standard RAG chat. The detected intent is recorded in the workflow trace with a confidence score and a user_override flag for explicit manual routing.

## Reflection Retry

When the retrieval quality gate determines that evidence is insufficient, the pipeline triggers a reflection retry. The retry expands the original query by stripping instruction words, then re-executes the retrieve, rerank, and compress cycle with an increased top-K. This is bounded to a single retry to avoid excessive latency. The retry does not call an LLM — it is a deterministic query expansion. If the retry also fails to produce sufficient evidence, the response carries a low-confidence warning appended to the metadata. This mechanism ensures the system acknowledges its limits rather than hallucinating answers.

## Source-Grounded Compare

The compare path differs from the standard chat pipeline in that it operates over a filtered set of candidate documents. It retrieves chunks from multiple sources, identifies shared themes as common points, and surfaces differences where sources conflict. Each compared point carries paired evidence objects — left_evidence and right_evidence — that cite the specific chunks from each source. The compare result artifact includes common_points, differences, and conflicts. Conflict detection identifies statements that directly contradict each other across sources, which is valuable for literature reviews or multi-source analysis.

## Workflow Trace and Observability

Both the chat and summarize pipelines emit a structured workflow trace as part of their response metadata. The trace records the pipeline steps executed, artifact kinds returned, retrieval statistics, and any warnings. Events are emitted progressively as each stage completes, which enables real-time progress UI. The trace also records the detected intent and whether the user manually overrode it. This transparency helps users understand why the system produced a particular answer, especially when evidence was thin and a retry occurred.
