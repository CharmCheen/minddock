"""Unit tests for runtime adapter, profile registry, resolver, and factory behavior."""

import pytest

from app.core.exceptions import (
    RuntimeProfileCapabilityMismatchError,
    RuntimeProfileDisabledError,
    RuntimeProfileNotFoundError,
)
from app.runtime.adapters import LangChainAdapter, _strip_visible_thinking
from app.runtime.base import GenerationRuntime
from app.runtime.factory import RuntimeFactory
from app.runtime.models import (
    ExecutionPolicy,
    LocalityPreference,
    OptimizationTarget,
    RuntimeCapabilities,
    RuntimeProfile,
    RuntimeRequest,
    RuntimeSelectionMode,
    RuntimeSelectionRequest,
)
from app.runtime.profiles import RuntimeProfileRegistry
from app.runtime.registry import RuntimeRegistry
from app.runtime.resolver import RuntimeResolver


class FakeProvider:
    def __init__(self, name: str = "fake-provider", fail: bool = False) -> None:
        self._name = name
        self._fail = fail

    def name(self) -> str:
        return self._name

    def generate(self, query: str, evidence: list[dict[str, object]]) -> str:
        if self._fail:
            raise RuntimeError("boom")
        return f"{self._name}:{query}:{len(evidence)}"


def test_langchain_adapter_uses_fallback_when_llm_missing() -> None:
    adapter = LangChainAdapter(
        llm=None,
        provider=FakeProvider("primary"),
        fallback=FakeProvider("fallback"),
        provider_name="langchain-chatopenai",
        runtime_mode="langchain",
    )

    response = adapter.generate(
        RuntimeRequest(
            prompt=None,
            inputs={},
            fallback_query="storage",
            fallback_evidence=[{"text": "value"}],
        )
    )

    assert response.text == "fallback:storage:1"
    assert response.used_fallback is True
    assert response.provider_name == "fallback"


def test_langchain_adapter_honors_override_provider() -> None:
    adapter = LangChainAdapter(
        llm=object(),
        provider=FakeProvider("primary"),
        fallback=FakeProvider("fallback"),
        provider_name="langchain-chatopenai",
        runtime_mode="langchain",
    )

    response = adapter.generate(
        RuntimeRequest(
            prompt=None,
            inputs={},
            fallback_query="storage",
            fallback_evidence=[{"text": "value"}],
            llm_override=FakeProvider("override"),
        )
    )

    assert response.text == "override:storage:1"
    assert response.used_fallback is False


def test_strip_visible_thinking_removes_complete_multiline_blocks() -> None:
    text = """<think>
I should reason privately.
</think>

Final answer grounded in evidence.
<think>second hidden block</think>
More answer."""

    assert _strip_visible_thinking(text) == "Final answer grounded in evidence.\nMore answer."


def test_strip_visible_thinking_keeps_incomplete_blocks() -> None:
    text = "<think>unfinished reasoning\nFinal answer"

    assert _strip_visible_thinking(text) == text


class FakeRuntime(GenerationRuntime):
    def __init__(self, name: str, capabilities: RuntimeCapabilities) -> None:
        self.runtime_name = name
        self.provider_name = f"{name}-provider"
        self.capabilities = capabilities

    def generate(self, request: RuntimeRequest):
        raise NotImplementedError


def _runtime_registry() -> RuntimeRegistry:
    registry = RuntimeRegistry(default_adapter_kind="langchain")
    registry.register(
        "langchain",
        lambda profile: FakeRuntime(profile.profile_id, RuntimeCapabilities(supports_chat=True, supports_summarize=True)),
        default_capabilities=RuntimeCapabilities(supports_chat=True, supports_summarize=True),
        make_default=True,
    )
    registry.register(
        "agent_runtime",
        lambda profile: FakeRuntime(
            profile.profile_id,
            RuntimeCapabilities(supports_chat=True, supports_summarize=True, supports_tool_or_skill_invocation=True),
        ),
        default_capabilities=RuntimeCapabilities(
            supports_chat=True,
            supports_summarize=True,
            supports_tool_or_skill_invocation=True,
        ),
    )
    return registry


def _profile_registry() -> RuntimeProfileRegistry:
    registry = RuntimeProfileRegistry()
    registry.register(
        RuntimeProfile(
            profile_id="default_cloud",
            display_name="Default Cloud",
            adapter_kind="langchain",
            provider_kind="openai_compatible",
            model_name="gpt-4o-mini",
            api_key_env="LLM_API_KEY",
            tags=("cloud", "quality"),
            priority=100,
        )
    )
    registry.register(
        RuntimeProfile(
            profile_id="deepseek_fast",
            display_name="DeepSeek Fast",
            adapter_kind="langchain",
            provider_kind="openai_compatible",
            model_name="deepseek-chat",
            api_key_env="DEEPSEEK_API_KEY",
            tags=("cloud", "fast", "cheap"),
            priority=90,
        )
    )
    registry.register(
        RuntimeProfile(
            profile_id="local_ollama",
            display_name="Local Ollama",
            adapter_kind="langchain",
            provider_kind="ollama",
            model_name="llama3.1",
            base_url="http://localhost:11434/v1",
            tags=("local", "private"),
            priority=80,
        )
    )
    registry.register(
        RuntimeProfile(
            profile_id="disabled_profile",
            display_name="Disabled",
            adapter_kind="langchain",
            provider_kind="openai_compatible",
            model_name="disabled",
            enabled=False,
            priority=70,
        )
    )
    registry.register(
        RuntimeProfile(
            profile_id="agent_skill",
            display_name="Agent Skill",
            adapter_kind="agent_runtime",
            provider_kind="agent_stub",
            model_name="agent-model",
            tags=("cloud", "quality"),
            priority=95,
        )
    )
    return registry


def test_runtime_profile_registry_loads_multiple_profiles() -> None:
    registry = _profile_registry()

    profiles = registry.list_profiles(include_disabled=True)

    assert len(profiles) == 5
    assert profiles[0].profile_id == "default_cloud"


def test_runtime_resolver_auto_mode_selects_best_matching_profile() -> None:
    resolver = RuntimeResolver(runtime_registry=_runtime_registry(), profile_registry=_profile_registry())

    result = resolver.resolve(
        RuntimeSelectionRequest(
            task_type="chat",
            execution_policy=ExecutionPolicy(
                selection_mode=RuntimeSelectionMode.AUTO,
                optimization_target=OptimizationTarget.LATENCY,
            ),
        )
    )

    assert result.binding.selected_profile_id == "deepseek_fast"
    assert result.binding.selection_reason == "auto:policy_score"


def test_runtime_resolver_preferred_mode_falls_back_when_needed() -> None:
    registry = _profile_registry()
    registry.register(
        RuntimeProfile(
            profile_id="preferred_no_skill",
            display_name="Preferred No Skill",
            adapter_kind="langchain",
            provider_kind="openai_compatible",
            model_name="gpt-4o-mini",
            tags=("cloud",),
            priority=110,
        )
    )
    runtime_registry = _runtime_registry()
    runtime_registry.register(
        "langchain",
        lambda profile: FakeRuntime(profile.profile_id, RuntimeCapabilities(supports_chat=True, supports_summarize=True)),
        default_capabilities=RuntimeCapabilities(supports_chat=True, supports_summarize=True),
        make_default=True,
    )
    resolver = RuntimeResolver(runtime_registry=runtime_registry, profile_registry=registry)

    result = resolver.resolve(
        RuntimeSelectionRequest(
            task_type="chat",
            execution_policy=ExecutionPolicy(
                preferred_profile_id="preferred_no_skill",
                selection_mode=RuntimeSelectionMode.PREFERRED,
                require_skill_support=True,
            ),
        )
    )

    assert result.binding.selected_profile_id != "preferred_no_skill"
    assert result.binding.fallback_used is True


def test_runtime_resolver_strict_mode_returns_structured_error_for_missing_profile() -> None:
    resolver = RuntimeResolver(runtime_registry=_runtime_registry(), profile_registry=_profile_registry())

    with pytest.raises(RuntimeProfileNotFoundError):
        resolver.resolve(
            RuntimeSelectionRequest(
                task_type="chat",
                execution_policy=ExecutionPolicy(
                    preferred_profile_id="missing",
                    selection_mode=RuntimeSelectionMode.STRICT,
                ),
            )
        )


def test_runtime_resolver_returns_structured_error_for_disabled_profile() -> None:
    resolver = RuntimeResolver(runtime_registry=_runtime_registry(), profile_registry=_profile_registry())

    with pytest.raises(RuntimeProfileDisabledError):
        resolver.resolve(
            RuntimeSelectionRequest(
                task_type="chat",
                execution_policy=ExecutionPolicy(
                    preferred_profile_id="disabled_profile",
                    selection_mode=RuntimeSelectionMode.STRICT,
                ),
            )
        )


def test_runtime_resolver_returns_structured_error_for_capability_mismatch() -> None:
    resolver = RuntimeResolver(runtime_registry=_runtime_registry(), profile_registry=_profile_registry())

    with pytest.raises(RuntimeProfileCapabilityMismatchError):
        resolver.resolve(
            RuntimeSelectionRequest(
                task_type="chat",
                execution_policy=ExecutionPolicy(
                    preferred_profile_id="default_cloud",
                    selection_mode=RuntimeSelectionMode.STRICT,
                    require_skill_support=True,
                ),
            )
        )


def test_same_adapter_kind_profiles_can_be_selected_independently() -> None:
    resolver = RuntimeResolver(runtime_registry=_runtime_registry(), profile_registry=_profile_registry())

    local = resolver.resolve(
        RuntimeSelectionRequest(
            task_type="chat",
            execution_policy=ExecutionPolicy(
                selection_mode=RuntimeSelectionMode.AUTO,
                locality_preference=LocalityPreference.LOCAL_ONLY,
                optimization_target=OptimizationTarget.PRIVACY,
            ),
        )
    )
    cloud = resolver.resolve(
        RuntimeSelectionRequest(
            task_type="chat",
            execution_policy=ExecutionPolicy(
                selection_mode=RuntimeSelectionMode.AUTO,
                locality_preference=LocalityPreference.CLOUD_PREFERRED,
                optimization_target=OptimizationTarget.QUALITY,
            ),
        )
    )

    assert local.binding.selected_profile_id == "local_ollama"
    assert cloud.binding.selected_profile_id == "default_cloud"


def test_runtime_factory_builds_runtime_from_resolved_binding() -> None:
    runtime_registry = _runtime_registry()
    profile_registry = _profile_registry()
    resolver = RuntimeResolver(runtime_registry=runtime_registry, profile_registry=profile_registry)
    factory = RuntimeFactory(runtime_registry=runtime_registry, profile_registry=profile_registry)

    result = resolver.resolve(RuntimeSelectionRequest(task_type="chat"))
    runtime = factory.create(result.binding)

    assert runtime.runtime_name == "langchain"
    assert runtime.capabilities.supports_chat is True
