"""Compatibility provider wrappers for OpenAI-compatible chat completion backends."""

from __future__ import annotations

import logging

from ports.llm import EvidenceItem, LLMProvider

logger = logging.getLogger(__name__)


class OpenAICompatibleLLM(LLMProvider):
    """Compatibility wrapper used by fallback-capable provider callers."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
    ) -> None:
        from langchain_openai import ChatOpenAI

        self._llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout_seconds,
            temperature=0,
        )

    def name(self) -> str:
        return "langchain-chatopenai"

    def generate(self, query: str, evidence: list[EvidenceItem]) -> str:
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "You are a grounded assistant for MindDock. "
                        "Answer only from the provided evidence. "
                        "If the evidence is insufficient, say so explicitly. "
                        "Do not invent citations or unsupported facts."
                    ),
                ),
                (
                    "human",
                    "Question or task:\n{query}\n\nEvidence:\n{evidence_block}",
                ),
            ]
        )
        chain = prompt | self._llm | StrOutputParser()
        response = chain.invoke(
            {
                "query": query,
                "evidence_block": self._build_evidence_block(evidence),
            }
        )
        return response.strip()

    def _build_evidence_block(self, evidence: list[EvidenceItem]) -> str:
        if not evidence:
            return "(no evidence provided)"

        evidence_lines: list[str] = []
        for item in evidence:
            ref = str(item.get("ref") or item.get("source") or item.get("chunk_id") or "").strip()
            chunk_id = str(item.get("chunk_id", "")).strip()
            text = str(item.get("text", "")).strip().replace("\n", " ")
            evidence_lines.append(f"[{ref} | {chunk_id}] {text}")
        return "\n".join(evidence_lines)


class FallbackLLM(LLMProvider):
    """Compatibility wrapper that falls back without changing service-layer call sites."""

    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    def name(self) -> str:
        return f"{self._primary.name()}+fallback"

    def generate(self, query: str, evidence: list[EvidenceItem]) -> str:
        try:
            return self._primary.generate(query=query, evidence=evidence)
        except Exception:
            logger.exception(
                "LLM provider failed, falling back to mock provider",
                extra={"provider": self._primary.name()},
            )
            return self._fallback.generate(query=query, evidence=evidence)
