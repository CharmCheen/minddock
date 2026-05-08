"""Concrete runtime adapters for current generation backends."""

from __future__ import annotations

import logging
import re

from app.core.exceptions import RuntimeInvocationError
from app.runtime.base import GenerationRuntime
from app.runtime.models import RuntimeCapabilities, RuntimeRequest, RuntimeResponse
from ports.llm import LLMProvider

logger = logging.getLogger(__name__)

_VISIBLE_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>\s*", re.IGNORECASE | re.DOTALL)


def _strip_visible_thinking(text: str) -> str:
    """Remove provider-emitted visible reasoning blocks from user-facing output."""

    return _VISIBLE_THINK_BLOCK_RE.sub("", text).strip()


class LangChainAdapter(GenerationRuntime):
    """Primary runtime adapter backed by LangChain and an explicit fallback provider."""

    def __init__(
        self,
        *,
        llm: object | None,
        provider: LLMProvider,
        fallback: LLMProvider,
        provider_name: str,
        runtime_mode: str,
        selected_model_name: str | None = None,
        base_url: str | None = None,
        config_source: str | None = None,
    ) -> None:
        self.llm = llm
        self.provider = provider
        self.fallback = fallback
        self.provider_name = provider_name
        self.runtime_name = runtime_mode
        self.selected_model_name = selected_model_name
        self.base_url = base_url
        self.config_source = config_source
        self.capabilities = RuntimeCapabilities(
            supports_chat=True,
            supports_summarize=True,
            supports_structured_output=False,
            supports_tool_or_skill_invocation=False,
            supports_streaming=False,
            supports_json_mode=False,
            provider_family="langchain",
        )

    def generate(self, request: RuntimeRequest) -> RuntimeResponse:
        if request.llm_override is not None:
            return RuntimeResponse(
                text=request.llm_override.generate(
                    query=request.fallback_query,
                    evidence=request.fallback_evidence,
                ),
                runtime_name=self.runtime_name,
                provider_name=type(request.llm_override).__name__,
                runtime_status="real",
            )

        if self.llm is None:
            return RuntimeResponse(
                text=self.fallback.generate(
                    query=request.fallback_query,
                    evidence=request.fallback_evidence,
                ),
                runtime_name=self.runtime_name,
                provider_name=self.fallback.name(),
                used_fallback=True,
                mock_used=True,
                runtime_status="mock",
                runtime_warning="Using mock runtime because no API key is configured.",
                selected_model_name=self.selected_model_name,
                base_url=self.base_url,
                config_source=self.config_source or "mock_no_api_key",
                debug_notes=("langchain_llm_unavailable", "mock_used"),
            )

        from langchain_core.output_parsers import StrOutputParser

        chain = request.prompt | self.llm | StrOutputParser()
        try:
            generated_text = _strip_visible_thinking(str(chain.invoke(request.inputs)))
        except Exception as exc:
            logger.exception("Configured LangChain generation failed", extra={"provider": self.provider_name})
            try:
                from app.runtime.active_config import record_runtime_error

                record_runtime_error(exc.__class__.__name__)
            except Exception:
                logger.debug("Unable to persist runtime error status", exc_info=True)
            raise RuntimeInvocationError(
                detail=(
                    "Configured LLM runtime failed to respond. "
                    "Check the runtime base URL, model name, API key, and network connectivity."
                ),
                metadata={
                    "runtime_status": "failed",
                    "fallback_used": False,
                    "mock_used": False,
                    "selected_model_name": self.selected_model_name,
                    "selected_provider_kind": self.provider_name,
                    "selected_base_url": self.base_url,
                    "config_source": self.config_source,
                    "runtime_error": exc.__class__.__name__,
                },
            ) from exc
        try:
            from app.runtime.active_config import clear_runtime_error

            clear_runtime_error()
        except Exception:
            logger.debug("Unable to clear runtime error status", exc_info=True)
        return RuntimeResponse(
            text=generated_text,
            runtime_name=self.runtime_name,
            provider_name=self.provider_name,
            used_fallback=False,
            mock_used=False,
            runtime_status="real",
            selected_model_name=self.selected_model_name,
            base_url=self.base_url,
            config_source=self.config_source,
        )
