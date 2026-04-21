"""Lightweight application assembly for shared extension points."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.application.orchestrators import FrontendFacade
from app.application.run_control import RunRegistry, get_run_registry
from app.rag.source_loader import SourceLoaderRegistry
from app.runtime.factory import RuntimeFactory, get_runtime_factory
from app.runtime.profiles import RuntimeProfileRegistry, get_runtime_profile_registry
from app.runtime.registry import RuntimeRegistry, get_runtime_registry
from app.runtime.resolver import RuntimeResolver, get_runtime_resolver
from app.skills import SkillRegistry, get_skill_registry


@dataclass(frozen=True)
class ExtensionRegistryBundle:
    """Grouped system extension points used by the application layer."""

    runtime_registry: RuntimeRegistry
    runtime_profile_registry: RuntimeProfileRegistry
    runtime_resolver: RuntimeResolver
    runtime_factory: RuntimeFactory
    run_registry: RunRegistry
    skill_registry: SkillRegistry
    source_loader_registry: SourceLoaderRegistry


@lru_cache(maxsize=1)
def get_extension_registries() -> ExtensionRegistryBundle:
    return ExtensionRegistryBundle(
        runtime_registry=get_runtime_registry(),
        runtime_profile_registry=get_runtime_profile_registry(),
        runtime_resolver=get_runtime_resolver(),
        runtime_factory=get_runtime_factory(),
        run_registry=get_run_registry(),
        skill_registry=get_skill_registry(),
        source_loader_registry=SourceLoaderRegistry(),
    )


@lru_cache(maxsize=1)
def get_frontend_facade() -> FrontendFacade:
    """Return the primary frontend-facing facade."""

    return FrontendFacade()
