"""Structured grounded outputs such as Mermaid diagrams."""

from __future__ import annotations

import re

from ports.llm import EvidenceItem

_TOKEN_RE = re.compile(r"[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff\s/_-]{1,40}")


def _sanitize_mermaid_label(text: str) -> str:
    cleaned = text.replace('"', "'").replace("\n", " ").strip()
    return cleaned or "Unknown"


def _extract_keywords(text: str, limit: int = 2) -> list[str]:
    seen: list[str] = []
    for match in _TOKEN_RE.findall(text):
        candidate = " ".join(match.split()).strip(" -_/")
        if len(candidate) < 4:
            continue
        lowered = candidate.lower()
        if lowered in {item.lower() for item in seen}:
            continue
        seen.append(candidate)
        if len(seen) >= limit:
            break
    return seen


class StructuredOutputService:
    """Generate grounded structured outputs from evidence."""

    def render_mermaid(self, topic: str, evidence: list[EvidenceItem]) -> str:
        root = _sanitize_mermaid_label(topic)
        lines = ["mindmap", f'  root["{root}"]']

        for index, item in enumerate(evidence, start=1):
            ref = _sanitize_mermaid_label(str(item.get("ref") or item.get("source") or f"Evidence {index}"))
            node_id = f"e{index}"
            lines.append(f'    {node_id}["{ref}"]')
            for keyword_index, keyword in enumerate(_extract_keywords(str(item.get("text", "")), limit=2), start=1):
                lines.append(f'      {node_id}_{keyword_index}["{_sanitize_mermaid_label(keyword)}"]')

        return "\n".join(lines)
