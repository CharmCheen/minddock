# Application Layer

## Purpose

This document describes the lightweight application/orchestrator layer added for future frontend and desktop integration.

The goal is not to introduce a heavy framework. The goal is to provide a cleaner entrypoint above the service layer so future UI consumers do not need to understand every low-level service directly.

## Current Objects

### `FrontendFacade`

Top-level facade that groups the main orchestrators:

- `chat`
- `knowledge_base`
- `skills`

### `ChatOrchestrator`

High-level query entrypoint for:

- search
- grounded chat
- summarize

### `KnowledgeBaseOrchestrator`

High-level knowledge-base management entrypoint for:

- ingest
- list sources
- source detail
- source inspect
- delete source
- reingest source

### `SkillOrchestrator`

Controlled execution boundary over the skill registry.

## Intended Consumer Order

Preferred order for future consumers:

1. frontend or desktop UI: application facade
2. internal tooling that needs use-case detail: service layer
3. HTTP clients: API routes + presenters + schemas

## What This Layer Should Not Do

- it should not duplicate business logic already owned by services
- it should not become a separate domain model layer
- it should not be a large CQRS or command-bus framework

## Current Limits

- the facade is intentionally thin
- it mainly delegates to formal services today
- richer cross-use-case workflows can be added later if they are actually needed by frontend or runtime integrations
