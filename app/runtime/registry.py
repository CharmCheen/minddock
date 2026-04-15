"""Adapter registry for extension-friendly runtime instantiation."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache

from app.core.exceptions import RuntimeProfileInvalidConfigError, RuntimeResolutionFailedError
from app.llm.mock import MockLLM
from app.llm.openai_compatible import FallbackLLM, OpenAICompatibleLLM
from app.runtime.adapters import LangChainAdapter
from app.runtime.base import GenerationRuntime
from app.runtime.models import RuntimeCapabilities, RuntimeProfile


def _read_api_key(profile: RuntimeProfile) -> str:
    if not profile.api_key_env:
        return ""
    return os.getenv(profile.api_key_env, "").strip()


def _build_langchain_chat_model(profile: RuntimeProfile, *, base_url: str | None = None):
    api_key = _read_api_key(profile)
    if not api_key:
        return None

    from langchain_openai import ChatOpenAI

    temperature = float(profile.default_generation_params.get("temperature", 0))
    timeout = float(profile.default_generation_params.get("timeout_seconds", 30.0))
    # base_url resolved by caller from os.environ override or profile default
    resolved_base_url = base_url or profile.base_url or ""
    return ChatOpenAI(
        api_key=api_key,
        base_url=resolved_base_url,
        model=profile.model_name,
        timeout=timeout,
        temperature=temperature,
    )


def _build_langchain_runtime(profile: RuntimeProfile) -> GenerationRuntime:
    if not profile.model_name.strip():
        raise RuntimeProfileInvalidConfigError(detail=f"Runtime profile '{profile.profile_id}' is missing model_name.")

    # Allow live base_url override via env var (set by user via settings UI)
    base_url = os.environ.get("LLM_RUNTIME_BASE_URL") or profile.base_url

    mock = MockLLM()
    llm = _build_langchain_chat_model(profile, base_url=base_url)
    api_key = _read_api_key(profile)
    if llm is None:
        return LangChainAdapter(
            llm=None,
            provider=mock,
            fallback=mock,
            provider_name="mock",
            runtime_mode=profile.adapter_kind,
        )

    provider = FallbackLLM(
        primary=OpenAICompatibleLLM(
            api_key=api_key,
            base_url=base_url or "",
            model=profile.model_name,
            timeout_seconds=float(profile.default_generation_params.get("timeout_seconds", 30.0)),
        ),
        fallback=mock,
    )
    return LangChainAdapter(
        llm=llm,
        provider=provider,
        fallback=mock,
        provider_name=profile.provider_kind,
        runtime_mode=profile.adapter_kind,
    )


@dataclass(frozen=True)
class RuntimeAdapterRegistration:
    """Registered adapter factory plus its default capabilities."""

    adapter_kind: str
    builder: Callable[[RuntimeProfile], GenerationRuntime]
    default_capabilities: RuntimeCapabilities


@dataclass
class RuntimeRegistry:
    """Registry for adapter kinds, not profile configuration."""

    adapters: dict[str, RuntimeAdapterRegistration] = field(default_factory=dict)
    default_adapter_kind: str = "langchain"

    def register(
        self,
        adapter_kind: str,
        builder: Callable[[RuntimeProfile], GenerationRuntime],
        *,
        default_capabilities: RuntimeCapabilities,
        make_default: bool = False,
    ) -> None:
        self.adapters[adapter_kind] = RuntimeAdapterRegistration(
            adapter_kind=adapter_kind,
            builder=builder,
            default_capabilities=default_capabilities,
        )
        if make_default:
            self.default_adapter_kind = adapter_kind

    def create(self, adapter_kind: str, profile: RuntimeProfile) -> GenerationRuntime:
        if adapter_kind not in self.adapters:
            raise RuntimeResolutionFailedError(detail=f"Adapter kind '{adapter_kind}' is not registered.")
        return self.adapters[adapter_kind].builder(profile)

    def resolve_capabilities(self, profile: RuntimeProfile) -> RuntimeCapabilities:
        if profile.adapter_kind not in self.adapters:
            raise RuntimeResolutionFailedError(detail=f"Adapter kind '{profile.adapter_kind}' is not registered.")
        base = self.adapters[profile.adapter_kind].default_capabilities
        return base.merged_with(profile.declared_capabilities)

    def has_adapter(self, adapter_kind: str) -> bool:
        return adapter_kind in self.adapters

    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self.adapters))


@lru_cache(maxsize=1)
def get_runtime_registry() -> RuntimeRegistry:
    registry = RuntimeRegistry()
    registry.register(
        "langchain",
        _build_langchain_runtime,
        default_capabilities=RuntimeCapabilities(
            supports_chat=True,
            supports_summarize=True,
            supports_structured_output=False,
            supports_tool_or_skill_invocation=False,
            supports_streaming=False,
            supports_json_mode=False,
            provider_family="langchain",
        ),
        make_default=True,
    )
    return registry
