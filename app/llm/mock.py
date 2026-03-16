"""Minimal mock LLM for grounded chat responses."""

from __future__ import annotations

from ports.llm import LLMProvider

INSUFFICIENT_EVIDENCE = "证据不足，无法可靠回答。"


class MockLLM(LLMProvider):
    """Generate conservative answers from retrieved evidence only."""

    def name(self) -> str:
        return "mock"

    def generate(self, query: str, evidence: list[dict[str, object]]) -> str:
        if not evidence:
            return INSUFFICIENT_EVIDENCE

        snippets = []
        for item in evidence[:2]:
            text = str(item.get("text", "")).strip().replace("\n", " ")
            if text:
                snippets.append(text[:120])

        if not snippets:
            return INSUFFICIENT_EVIDENCE

        joined = "；".join(snippets)
        return f"根据已检索到的证据，和“{query}”最相关的信息是：{joined}"
