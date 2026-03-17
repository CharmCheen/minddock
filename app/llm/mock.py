"""Minimal mock LLM for grounded chat and summary responses."""

from __future__ import annotations

from ports.llm import EvidenceItem, LLMProvider

INSUFFICIENT_EVIDENCE = "证据不足，无法给出可靠结论。"
MAX_SNIPPETS = 2
MAX_SNIPPET_LENGTH = 120


class MockLLM(LLMProvider):
    """Generate readable grounded output using retrieved evidence only."""

    def name(self) -> str:
        return "mock"

    def generate(self, query: str, evidence: list[EvidenceItem]) -> str:
        snippets = self._collect_snippets(evidence)
        if not snippets:
            return INSUFFICIENT_EVIDENCE

        if self._is_summary_query(query):
            return self._build_summary(query=query, snippets=snippets, evidence_count=len(evidence))
        return self._build_answer(query=query, snippets=snippets, evidence_count=len(evidence))

    def _collect_snippets(self, evidence: list[EvidenceItem]) -> list[str]:
        snippets: list[str] = []
        for item in evidence[:MAX_SNIPPETS]:
            text = str(item.get("text", "")).strip().replace("\n", " ")
            if not text:
                continue
            snippets.append(text[:MAX_SNIPPET_LENGTH])
        return snippets

    def _is_summary_query(self, query: str) -> bool:
        lowered = query.lower()
        return "summarize the topic" in lowered or "总结主题" in query or lowered.startswith("summarize:")

    def _build_answer(self, query: str, snippets: list[str], evidence_count: int) -> str:
        answer_lines = [
            f"根据当前检索到的证据，针对“{query}”可以先给出一个保守结论：",
            "；".join(snippets) + "。",
        ]
        if evidence_count > len(snippets):
            answer_lines.append("其余证据与上述结论方向一致，可结合引用继续查看原文。")
        return "\n".join(answer_lines)

    def _build_summary(self, query: str, snippets: list[str], evidence_count: int) -> str:
        topic = query.split("Topic:", 1)[-1].strip() if "Topic:" in query else query
        summary_lines = [
            f"围绕“{topic}”，当前证据主要反映出以下要点：",
            "；".join(snippets) + "。",
        ]
        if evidence_count > len(snippets):
            summary_lines.append("更多细节可结合下方引用继续展开。")
        return "\n".join(summary_lines)
