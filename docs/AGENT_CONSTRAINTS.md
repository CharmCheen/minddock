# Agent Constraints for MindDock

## Purpose

This document defines the product philosophy, capability boundaries, and execution constraints that all future agents should follow when working on MindDock.

Use this document as injected context before planning features, editing APIs, changing workflows, or extending the product scope.

The goal is to prevent capability drift. MindDock is not a general assistant platform. It is a grounded, local-first knowledge backend for private knowledge assets.

## Product Definition

MindDock should be treated as:

- a private knowledge asset system
- an evidence-constrained retrieval and answer engine
- a workflow engine for knowledge tasks
- a stable knowledge backend callable by upper-layer agents

MindDock should not be treated as:

- a general-purpose chat assistant
- a universal tool-calling hub
- a generic external API orchestrator
- an everything-agent platform

## Core Capability Boundary

All work should stay inside these four layers.

### 1. Private Knowledge Asset Ingest and Evolution

MindDock must be strong at long-lived knowledge maintenance, not just one-time ingest.

This layer includes:

- multi-source ingest
- structured chunking
- metadata persistence
- provenance preservation
- hash-based deduplication
- incremental updates
- reindex and rebuild flows
- stable source identity and source-state tracking

This layer must preserve:

- source identity
- document lineage
- page anchors
- chunk anchors
- paragraph or section provenance when available

The knowledge base is a living system. If documents change, the system should update predictably without losing traceability.

### 2. Evidence-Constrained Retrieval and Answering

This is the primary differentiator of MindDock.

MindDock is not optimized for answering as many questions as possible. It is optimized for returning answers that can be checked against evidence.

The default principle is:

- answer only when evidence is sufficient
- degrade clearly when evidence is partial
- refuse when support is insufficient
- prefer verifiability over fluency

Outputs should be designed as knowledge objects, not plain free-form text.

Default output expectations:

- `answer`
- `evidence[]`
- `coverage` or `support_status`
- `refusal_reason` when needed
- source or doc identifiers
- chunk, page, or section anchors when available

Future agents should preserve support semantics such as:

- `supported`
- `partially_supported`
- `insufficient_evidence`
- `refused`

If a feature weakens citation quality, provenance quality, refusal behavior, or evidence visibility, it should be considered a regression.

### 3. Knowledge-Oriented Workflows

MindDock should support workflows centered on knowledge work only.

Examples of in-scope workflows:

- grounded question answering
- cross-document comparison
- map-reduce summarization
- structured outline generation
- Mermaid graph or mind-map generation
- evidence extraction
- citation-based review cards
- project retrospectives grounded in indexed material

Examples of out-of-scope workflows:

- arbitrary agentic task execution
- open-ended tool ecosystems unrelated to knowledge work
- generic automation for unrelated business processes
- broad assistant behavior with no evidence contract

When adding workflows, agents should ask one question internally:

Does this workflow improve how users ingest, verify, compare, summarize, organize, or express knowledge?

If the answer is no, it likely does not belong in MindDock.

### 4. Stable Knowledge Backend for Upper-Layer Agents

MindDock should behave like a predictable service backend for other agents and applications.

That means:

- stable APIs
- explicit schemas
- structured outputs
- predictable failure and refusal modes
- clear metadata contracts

Upper-layer systems should be able to consume MindDock responses as machine-usable knowledge objects rather than raw assistant prose.

## Differentiation Principles

MindDock's differentiation should be defined as product commitments, not just feature checklists.

### Commitment 1: Not "Can Answer", but "Can Prove"

The system's value is not that it produces language. The value is that it can connect conclusions to evidence and expose the support state clearly.

All future design choices should prefer:

- inspectable outputs
- explicit evidence objects
- support and coverage signals
- refusal when support is missing

### Commitment 2: Long-Term Private Knowledge Maintenance

MindDock is not a one-shot file reader. It is designed for long-term accumulation and maintenance of personal or private knowledge assets.

All future design should reinforce:

- sustained ingest
- update safety
- source tracking
- rebuild reliability
- asset lifecycle visibility

### Commitment 3: Knowledge Tasks, Not All Tasks

MindDock should remain specialized.

It should do fewer things, but do them in a more trustworthy and reusable way.

Priority tasks:

- answer
- compare
- summarize
- organize
- extract evidence
- express structure

### Commitment 4: Local-First and Edge-Aware Operation

MindDock should preserve the architectural principle that privacy-sensitive and repeatable knowledge-processing work happens locally when practical.

Prefer local or edge-side handling for:

- parsing
- cleaning
- chunking
- metadata extraction
- indexing
- vectorization when feasible

Cloud or heavier runtimes may be used for higher-cost reasoning, but this should not erase the local-first system identity.

This principle exists because it supports:

- privacy
- cost control
- operational control

## Product Shape Priority

Future agents should preserve this implementation order.

### First Shape: Independent Service

MindDock should first be a stable service with a clear HTTP or schema contract.

The service layer is the product core.

Representative endpoint families:

- knowledge ingest
- knowledge search
- grounded answer
- summarize
- compare
- source catalog
- reindex or refresh

The exact route names may evolve, but the service contract must remain stable and explicit.

### Second Shape: Plugin or Tool Wrapper

Integrations such as OpenClaw plugins should wrap the service rather than replace it.

Plugin responsibilities should stay thin:

- parameter adaptation
- permission narrowing
- return-shape mapping
- tool registration

Core knowledge logic must remain inside MindDock itself.

### Third Shape: SDK and Client Libraries

After the service contract is stable, lightweight SDKs may be added.

Good candidates:

- Python SDK
- optional TypeScript client
- reusable JSON schema contracts

MindDock should not become tightly bound to any single host framework.

## Design Guardrails

When proposing or implementing changes, future agents should follow these guardrails.

### Prefer

- source-aware models
- explicit provenance
- stable structured responses
- evidence-first UX and API contracts
- refusal and downgrade semantics
- compatibility with upper-layer agent consumption
- local-first processing where practical

### Avoid

- adding general assistant behaviors without evidence constraints
- optimizing for fluent answers at the cost of support visibility
- hiding provenance details behind presentation-only layers
- coupling the core system to one plugin host or one agent framework
- expanding into unrelated workflow automation
- introducing features that make the system harder to reason about as a backend

## Change Evaluation Checklist

Before implementing a feature, future agents should verify:

1. Does this strengthen one of the four core layers?
2. Does it improve evidence quality, provenance quality, or knowledge lifecycle management?
3. Can the output still be consumed as a structured knowledge object?
4. Does it preserve refusal and insufficient-evidence behavior?
5. Does it avoid turning MindDock into a general assistant platform?

If the answer to multiple questions is no, the change should usually be rejected, narrowed, or moved out of core scope.

## Suggested Injection Usage

When another agent is asked to modify MindDock, inject or summarize this document first.

Recommended instruction pattern:

"Read `docs/AGENT_CONSTRAINTS.md` before planning or coding. Treat it as the product-boundary and architectural-constraint document for MindDock. Do not expand scope beyond the boundaries defined there unless explicitly instructed by the user."

## Status of Authority

If there is any conflict between a broad implementation idea and this document, this document should win unless the user explicitly chooses to override it for a specific task.
