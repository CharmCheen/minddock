# Source Skill Trusted-Only Control Plane

## Current Scope

MindDock exposes Source Skills as a trusted-only control plane for ingestion capabilities. The current implementation is a catalog and manifest layer: it describes which built-in source handlers are available, what inputs they support, and what limitations apply.

This is not a Skill Market. MindDock does not download remote skills, does not import third-party packages, and does not execute user-provided Python or JavaScript code through Source Skill manifests.

## Demo Surface

For the defense demo, show Source Skills through:

- `GET /frontend/source-skills`
- Settings > Sources in the frontend

The expected visible fields are trusted / built-in status, enabled state, supported inputs, capabilities, and limitations. The recommended narration is that the feature is an auditable control plane over reviewed ingestion handlers, not a third-party plugin marketplace.

## Completed

| Capability | Implementation | Thesis Wording |
|---|---|---|
| Built-in trusted source skill catalog | `app/rag/source_skill_catalog.py` and `app/skills/source_registry.py` list implemented source extraction capabilities. | The system provides a trusted source skill catalog for explaining heterogeneous ingestion capabilities. |
| Frontend source skill visibility | `GET /frontend/source-skills` projects source skills for Settings > Sources. | The control plane exposes source capability metadata such as supported inputs, capabilities, limitations, and enabled state. |
| Trusted handler binding metadata | `app/skills/handlers.py` defines allowlisted handler contracts; local manifests may only bind to these handlers. | Local manifests are declaration-only and can bind only to reviewed built-in handlers. |
| Ingest metadata annotation | `app/skills/source_binding.py` and `app/rag/ingest.py` annotate chunks with matched source skill identity. | Ingestion records the source skill path used to normalize evidence. |

## Partially Completed

| Capability | Current Boundary |
|---|---|
| Manifest expression | Local `skill.json` manifests are supported as declaration-only metadata. They cannot provide executable entrypoints. |
| Enable / disable state | Local manifest enable/disable is available; built-in handlers remain system-owned. |
| File type mapping | Extension and input-kind mapping is exposed for common built-in handlers; MIME metadata is descriptive, not a full content negotiation engine. |
| Market readiness | Response metadata marks the catalog as future-market-ready at the data-model level only. There is no installer, trust store, review workflow, billing, or marketplace service. |

## Not Implemented / Future Work

| Future Capability | Status |
|---|---|
| User-developed executable skills | Future work. |
| Complete Skill Market | Future research direction. |
| Remote skill download or update | Not supported. |
| Plugin signature validation | Not supported. |
| Permission isolation and sandbox execution | Not supported. |
| OpenAPI / MCP tool import | Future work. |
| Rating, payment, version ecosystem | Future work. |

## Safe Thesis Wording

Recommended:

> MindDock introduces a trusted-only Source Skill control plane. It represents built-in ingestion handlers and declaration-only local manifests as auditable metadata, allowing the frontend and workflow trace to explain which source processing capability is used without enabling arbitrary third-party code execution.

Avoid:

> MindDock implements a complete Skill Market with remote plugin installation and sandboxed execution.

## Demo Boundary

During the demo, do not present Source Skills as downloadable or user-executable plugins. It is safe to say that the catalog and manifest shape are market-ready extension points, but installation, signatures, sandboxing, permissions, review workflows, and OpenAPI/MCP import remain future work.
