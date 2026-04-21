"""Runtime ports used by application services."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.runtime.models import RuntimeCapabilities, RuntimeRequest, RuntimeResponse


class GenerationRuntime(ABC):
    """Stable runtime port for grounded generation."""

    runtime_name: str = "unknown"
    provider_name: str = "unknown"
    capabilities: RuntimeCapabilities = RuntimeCapabilities()

    @abstractmethod
    def generate(self, request: RuntimeRequest) -> RuntimeResponse:
        """Generate text from a normalized runtime request."""

    def get_capabilities(self) -> RuntimeCapabilities:
        """Return declared runtime capabilities."""

        return self.capabilities

    def invoke(
        self,
        *,
        prompt,
        inputs: dict[str, object],
        fallback_query: str,
        fallback_evidence: list[dict[str, object]],
        llm_override=None,
    ) -> str:
        """Compatibility helper for legacy callers and tests."""

        response = self.generate(
            RuntimeRequest(
                prompt=prompt,
                inputs=inputs,
                fallback_query=fallback_query,
                fallback_evidence=fallback_evidence,
                llm_override=llm_override,
            )
        )
        return response.text
