# Skill Model

## Purpose

This document describes the minimal skill-system skeleton added for future tool/skill integration.

The intent is to create a clean extension seam without polluting current service or route logic.

## Core Objects

### `SkillDescriptor`

Static metadata for one skill:

- `name`
- `description`

### `SkillRequest`

Normalized invocation request:

- `name`
- `arguments`

### `SkillExecutionContext`

Minimal execution context:

- `request_id`
- `debug`

### `SkillResult`

Structured execution result:

- `name`
- `ok`
- `output`
- `message`

### `SkillRegistry`

Registry for skill implementations and descriptors.

### `SkillOrchestrator`

Application-layer entrypoint for controlled skill execution.

## Current Status

This is a skeleton, not a rich tool platform.

Current example skill:

- `echo`

Its purpose is only to prove:

- registration works
- invocation works
- the facade can execute skills without polluting route or service code

## Design Rule

Skills should not be inserted ad hoc into:

- route handlers
- core retrieval logic
- source-loading internals

Instead, future integrations should prefer:

- runtime -> skill orchestration
- facade/orchestrator -> skill orchestration

## Future Extension Guidance

Reasonable future additions:

- source lookup skills
- retrieval helper skills
- runtime-routed skill/tool selection
- external tool adapters

These should extend the registry/orchestrator path instead of creating scattered helper utilities.
