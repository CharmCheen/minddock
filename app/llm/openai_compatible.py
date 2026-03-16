"""OpenAI-compatible chat completion provider."""

from __future__ import annotations

import logging

import httpx

from ports.llm import LLMProvider

logger = logging.getLogger(__name__)


class OpenAICompatibleLLM(LLMProvider):
    """Minimal provider for OpenAI-compatible chat completions APIs."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds

    def name(self) -> str:
        return "openai-compatible"

    def generate(self, query: str, evidence: list[dict[str, object]]) -> str:
        messages = self._build_messages(query=query, evidence=evidence)
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self._timeout_seconds) as client:
            response = client.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("LLM response did not include any choices")

        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

        if isinstance(content, list):
            text_parts = [
                str(item.get("text", "")).strip()
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            joined = "\n".join(part for part in text_parts if part)
            if joined:
                return joined

        raise RuntimeError("LLM response did not include textual content")

    def _build_messages(self, query: str, evidence: list[dict[str, object]]) -> list[dict[str, str]]:
        evidence_lines = []
        for item in evidence:
            source = str(item.get("source", ""))
            chunk_id = str(item.get("chunk_id", ""))
            text = str(item.get("text", "")).strip().replace("\n", " ")
            evidence_lines.append(f"[{source} | {chunk_id}] {text}")

        evidence_block = "\n".join(evidence_lines)
        return [
            {
                "role": "system",
                "content": (
                    "Answer only from the provided evidence. "
                    "If the evidence is insufficient, say so explicitly."
                ),
            },
            {
                "role": "user",
                "content": f"Question: {query}\n\nEvidence:\n{evidence_block}",
            },
        ]


class FallbackLLM(LLMProvider):
    """Use a primary provider and fall back to MockLLM on failure."""

    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    def name(self) -> str:
        return f"{self._primary.name()}+fallback"

    def generate(self, query: str, evidence: list[dict[str, object]]) -> str:
        try:
            return self._primary.generate(query=query, evidence=evidence)
        except Exception:
            logger.exception(
                "LLM provider failed, falling back to mock provider",
                extra={"provider": self._primary.name()},
            )
            return self._fallback.generate(query=query, evidence=evidence)
