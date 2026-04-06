"""Application-layer exports with lazy loading to keep boundaries lightweight."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "ArtifactBuilder",
    "ArtifactKind",
    "ArtifactMapper",
    "BaseArtifact",
    "CitationPolicy",
    "ChatOrchestrator",
    "ClientArtifactPayload",
    "ClientCompletedPayload",
    "ClientEvent",
    "ClientEventChannel",
    "ClientEventKind",
    "ClientFailedPayload",
    "ClientProgressPayload",
    "ClientRunStartedPayload",
    "ClientWarningPayload",
    "EventChannelPolicy",
    "EventCollector",
    "EventProjector",
    "ExecutionEvent",
    "ExecutionEventKind",
    "ExecutionPlan",
    "ExecutionRun",
    "ExecutionRunStatus",
    "ExecutionStep",
    "ExecutionSummary",
    "ExecutionPolicy",
    "ExtensionRegistryBundle",
    "FrontendFacade",
    "KnowledgeBaseOrchestrator",
    "ManagedRun",
    "EventVisibility",
    "EventVisibilityPolicy",
    "OutputMode",
    "MermaidArtifact",
    "ProgressPhase",
    "RetrievalOptions",
    "RunCompletedPayload",
    "RunFailedPayload",
    "RunRegistry",
    "RunStartedPayload",
    "SearchResultsArtifact",
    "SkillPolicy",
    "SkillPolicyMode",
    "SkillResultArtifact",
    "SkillOrchestrator",
    "StepKind",
    "StructuredJsonArtifact",
    "TaskType",
    "TextArtifact",
    "UnifiedExecutionRequest",
    "UnifiedExecutionResponse",
    "get_extension_registries",
    "get_frontend_facade",
    "get_run_registry",
]


def __getattr__(name: str):
    if name in {
        "ArtifactBuilder",
        "ArtifactKind",
        "ArtifactMapper",
        "BaseArtifact",
        "MermaidArtifact",
        "SearchResultsArtifact",
        "SkillResultArtifact",
        "StructuredJsonArtifact",
        "TextArtifact",
    }:
        module = import_module("app.application.artifacts")
        return getattr(module, name)
    if name in {
        "ClientArtifactPayload",
        "ClientCompletedPayload",
        "ClientEvent",
        "ClientEventChannel",
        "ClientEventKind",
        "ClientFailedPayload",
        "ClientProgressPayload",
        "ClientRunStartedPayload",
        "ClientWarningPayload",
        "EventChannelPolicy",
        "EventProjector",
        "EventVisibility",
        "EventVisibilityPolicy",
        "ProgressPhase",
    }:
        module = import_module("app.application.client_events")
        return getattr(module, name)
    if name in {
        "EventCollector",
        "ExecutionEvent",
        "ExecutionEventKind",
        "ExecutionRun",
        "ExecutionRunStatus",
        "RunCompletedPayload",
        "RunFailedPayload",
        "RunStartedPayload",
    }:
        module = import_module("app.application.events")
        return getattr(module, name)
    if name in {
        "ManagedRun",
        "RunRegistry",
    }:
        module = import_module("app.application.run_control")
        return getattr(module, name)
    if name in {
        "CitationPolicy",
        "ExecutionPlan",
        "ExecutionStep",
        "ExecutionSummary",
        "ExecutionPolicy",
        "OutputMode",
        "RetrievalOptions",
        "SkillPolicy",
        "SkillPolicyMode",
        "StepKind",
        "TaskType",
        "UnifiedExecutionRequest",
        "UnifiedExecutionResponse",
    }:
        module = import_module("app.application.models")
        return getattr(module, name)
    if name in {
        "ChatOrchestrator",
        "FrontendFacade",
        "KnowledgeBaseOrchestrator",
        "SkillOrchestrator",
    }:
        module = import_module("app.application.orchestrators")
        return getattr(module, name)
    if name in {"ExtensionRegistryBundle", "get_extension_registries", "get_frontend_facade"}:
        module = import_module("app.application.assembly")
        return getattr(module, name)
    if name in {"get_run_registry"}:
        module = import_module("app.application.run_control")
        return getattr(module, name)
    raise AttributeError(name)
