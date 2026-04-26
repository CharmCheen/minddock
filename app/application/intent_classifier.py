"""Rule-based intent classifier for unified execution requests.

This is a lightweight, deterministic classifier that maps user input to
TaskType based on keyword matching. It does not use LLM inference.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.models import TaskType


@dataclass(frozen=True)
class IntentClassificationResult:
    """Output of the rule-based intent classifier."""

    task_type: TaskType
    confidence: float
    reason: str
    matched_keyword: str | None = None
    user_override: bool = False


class IntentClassifier:
    """Deterministic keyword-based intent classifier.

    Confidence levels:
    - 0.9: strong keyword match (explicit compare/summarize terms)
    - 0.65: weak/ambiguous match
    - 0.5: default chat fallback
    """

    _COMPARE_KEYWORDS_STRONG: tuple[str, ...] = (
        # Chinese
        "比较",
        "对比",
        "区别",
        "差异",
        "异同",
        "相同点",
        "不同点",
        "冲突",
        "哪个更",
        # English
        "compare",
        "comparison",
        "difference",
        "differences",
        "contrast",
        "versus",
        " vs ",
    )

    _SUMMARIZE_KEYWORDS_STRONG: tuple[str, ...] = (
        # Chinese
        "总结",
        "概括",
        "归纳",
        "摘要",
        "提炼",
        "梳理",
        # English
        "summarize",
        "summary",
        "recap",
        "outline",
    )

    _COMPARE_KEYWORDS_WEAK: tuple[str, ...] = (
        "vs.",
        "相对",
        "相比",
        "优劣",
        "差别",
    )

    _SUMMARIZE_KEYWORDS_WEAK: tuple[str, ...] = (
        "概要",
        "概述",
        "综述",
        "brief",
    )

    def classify(self, user_input: str) -> IntentClassificationResult:
        """Classify user input into a TaskType.

        Returns the most confident match. Defaults to CHAT if no strong
        or weak keyword is found.
        """
        if not user_input or not user_input.strip():
            return IntentClassificationResult(
                task_type=TaskType.CHAT,
                confidence=0.5,
                reason="Empty input; defaulting to chat.",
            )

        normalized = user_input.lower().strip()

        # Strong compare match
        for keyword in self._COMPARE_KEYWORDS_STRONG:
            if keyword in normalized:
                return IntentClassificationResult(
                    task_type=TaskType.COMPARE,
                    confidence=0.9,
                    reason="Strong compare keyword match.",
                    matched_keyword=keyword,
                )

        # Strong summarize match
        for keyword in self._SUMMARIZE_KEYWORDS_STRONG:
            if keyword in normalized:
                return IntentClassificationResult(
                    task_type=TaskType.SUMMARIZE,
                    confidence=0.9,
                    reason="Strong summarize keyword match.",
                    matched_keyword=keyword,
                )

        # Weak compare match
        for keyword in self._COMPARE_KEYWORDS_WEAK:
            if keyword in normalized:
                return IntentClassificationResult(
                    task_type=TaskType.COMPARE,
                    confidence=0.65,
                    reason="Weak compare keyword match.",
                    matched_keyword=keyword,
                )

        # Weak summarize match
        for keyword in self._SUMMARIZE_KEYWORDS_WEAK:
            if keyword in normalized:
                return IntentClassificationResult(
                    task_type=TaskType.SUMMARIZE,
                    confidence=0.65,
                    reason="Weak summarize keyword match.",
                    matched_keyword=keyword,
                )

        # Default
        return IntentClassificationResult(
            task_type=TaskType.CHAT,
            confidence=0.5,
            reason="No matching keyword; defaulting to chat.",
        )
