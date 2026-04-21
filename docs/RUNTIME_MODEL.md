# Runtime Model

## Purpose

This document describes the runtime port/adapter model added so the project is not architecturally locked to one concrete LangChain path.

## Core Objects

### `GenerationRuntime`

Stable runtime port used by services.

Current contract:

- `generate(RuntimeRequest) -> RuntimeResponse`

### `RuntimeRequest`

Normalized runtime input:

- prompt object
- prompt inputs
- fallback query
- fallback evidence
- optional provider override

### `RuntimeResponse`

Normalized runtime output:

- generated text
- runtime name
- provider name
- fallback indicator
- optional debug notes

### `RuntimeRegistry`

Named registry of runtime builders.

Current default:

- `langchain`

## Current Adapter

### `LangChainAdapter`

Current primary adapter implementation.

Behavior:

- uses LangChain prompt + chat model when available
- falls back to the mock provider when no API key exists
- also falls back when the primary LangChain call fails

## Compatibility Positioning

`app/llm/factory.py` remains as a compatibility bridge.

Its purpose is:

- preserve existing import paths
- return the default registered runtime
- avoid forcing a full immediate rewrite of callers/tests

## Extension Guidance

To add a new runtime later:

1. implement `GenerationRuntime`
2. normalize its inputs/outputs through `RuntimeRequest` / `RuntimeResponse`
3. register it in `RuntimeRegistry`
4. select it through application assembly/config rather than rewriting services

This is the intended path for future:

- AutoGen adapters
- multi-LLM routing adapters
- local model adapters
- cloud + local hybrid runtime strategies
