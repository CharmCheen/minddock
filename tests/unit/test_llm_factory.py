"""Unit tests for generation runtime factory compatibility helpers."""

from app.llm.factory import get_generation_runtime, get_llm_provider
from app.runtime.base import GenerationRuntime
from app.runtime.models import ResolvedRuntimeBinding, RuntimeCapabilities, RuntimeProfile, RuntimeRequest, RuntimeResponse
from app.runtime.profiles import RuntimeProfileRegistry
from app.runtime.registry import RuntimeRegistry, get_runtime_registry


class FakeProvider:
    def name(self) -> str:
        return "fake-provider"

    def generate(self, query: str, evidence: list[dict[str, object]]) -> str:
        return f"generated:{query}:{len(evidence)}"


class FakeRuntime(GenerationRuntime):
    runtime_name = "fake-runtime"
    provider_name = "fake-provider"

    def __init__(self) -> None:
        self.provider = FakeProvider()

    def generate(self, request: RuntimeRequest) -> RuntimeResponse:
        return RuntimeResponse(
            text="ok",
            runtime_name=self.runtime_name,
            provider_name=self.provider_name,
        )


def test_factory_uses_default_registered_runtime(monkeypatch) -> None:
    get_generation_runtime.cache_clear()
    get_runtime_registry.cache_clear()

    profile_registry = RuntimeProfileRegistry()
    profile_registry.register(
        RuntimeProfile(
            profile_id="default_cloud",
            display_name="Default Cloud",
            adapter_kind="fake",
            provider_kind="fake",
            model_name="fake-model",
        )
    )
    registry = RuntimeRegistry()
    registry.register(
        "fake",
        lambda profile: FakeRuntime(),
        default_capabilities=RuntimeCapabilities(supports_chat=True),
        make_default=True,
    )

    class FakeFactory:
        runtime_registry = registry

        def create(self, binding: ResolvedRuntimeBinding):
            return FakeRuntime()

    monkeypatch.setattr("app.llm.factory.get_runtime_profile_registry", lambda: profile_registry)
    monkeypatch.setattr("app.llm.factory.get_runtime_factory", lambda: FakeFactory())

    runtime = get_generation_runtime()

    assert runtime.runtime_name == "fake-runtime"
    assert get_llm_provider().name() == "fake-provider"
    get_generation_runtime.cache_clear()
    get_runtime_registry.cache_clear()


def test_runtime_registry_registers_and_lists_builders() -> None:
    registry = RuntimeRegistry()
    profile = RuntimeProfile(
        profile_id="default_cloud",
        display_name="Default Cloud",
        adapter_kind="fake",
        provider_kind="fake",
        model_name="fake-model",
    )
    registry.register(
        "fake",
        lambda profile: FakeRuntime(),
        default_capabilities=RuntimeCapabilities(supports_chat=True),
        make_default=True,
    )

    runtime = registry.create("fake", profile)

    assert runtime.runtime_name == "fake-runtime"
    assert registry.available() == ("fake",)
