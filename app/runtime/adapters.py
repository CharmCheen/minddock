"""Concrete runtime adapters for current generation backends."""

from __future__ import annotations

import logging
import re

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
    ) -> None:
        self.llm = llm
        self.provider = provider
        self.fallback = fallback
        self.provider_name = provider_name
        self.runtime_name = runtime_mode
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
                debug_notes=("langchain_llm_unavailable",),
            )

        from langchain_core.output_parsers import StrOutputParser

        chain = request.prompt | self.llm | StrOutputParser()
        try:
            return RuntimeResponse(
                text=_strip_visible_thinking(str(chain.invoke(request.inputs))),
                runtime_name=self.runtime_name,
                provider_name=self.provider_name,
            )
        except Exception:
            logger.exception("LangChain generation failed; falling back to provider", extra={"provider": self.provider_name})
            return RuntimeResponse(
                text=self.fallback.generate(
                    query=request.fallback_query,
                    evidence=request.fallback_evidence,
                ),
                runtime_name=self.runtime_name,
                provider_name=self.fallback.name(),
                used_fallback=True,
                debug_notes=("langchain_primary_failed",),
            )
