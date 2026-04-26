"""Unit tests for the rule-based intent classifier."""

import pytest

from app.application.intent_classifier import IntentClassifier, IntentClassificationResult
from app.application.models import TaskType


class TestIntentClassifier:
    """Tests for IntentClassifier.classify()."""

    @pytest.fixture
    def classifier(self) -> IntentClassifier:
        return IntentClassifier()

    # --- Compare classification ---

    @pytest.mark.parametrize("text", [
        "比较这两个方法",
        "对比一下A和B",
        "有什么区别",
        "差异在哪里",
        "异同分析",
        "相同点和不同点",
        "冲突点",
        "哪个更好",
        "compare these two",
        "make a comparison",
        "what is the difference",
        "find the differences",
        "in contrast to",
        "A versus B",
        "A vs B",
    ])
    def test_strong_compare_keywords(self, classifier: IntentClassifier, text: str) -> None:
        result = classifier.classify(text)
        assert result.task_type == TaskType.COMPARE
        assert result.confidence == pytest.approx(0.9)
        assert result.matched_keyword is not None
        assert result.user_override is False

    @pytest.mark.parametrize("text", [
        "vs.",
        "A相比B",
        "优劣分析",
        "差别大吗",
    ])
    def test_weak_compare_keywords(self, classifier: IntentClassifier, text: str) -> None:
        result = classifier.classify(text)
        assert result.task_type == TaskType.COMPARE
        assert result.confidence == pytest.approx(0.65)
        assert result.matched_keyword is not None

    # --- Summarize classification ---

    @pytest.mark.parametrize("text", [
        "总结一下",
        "概括主要内容",
        "归纳观点",
        "摘要提取",
        "提炼重点",
        "梳理逻辑",
        "summarize this document",
        "give me a summary",
        "recap the meeting",
        "outline the paper",
    ])
    def test_strong_summarize_keywords(self, classifier: IntentClassifier, text: str) -> None:
        result = classifier.classify(text)
        assert result.task_type == TaskType.SUMMARIZE
        assert result.confidence == pytest.approx(0.9)
        assert result.matched_keyword is not None

    @pytest.mark.parametrize("text", [
        "概要说明",
        "概述背景",
        "综述现状",
        "brief introduction",
    ])
    def test_weak_summarize_keywords(self, classifier: IntentClassifier, text: str) -> None:
        result = classifier.classify(text)
        assert result.task_type == TaskType.SUMMARIZE
        assert result.confidence == pytest.approx(0.65)
        assert result.matched_keyword is not None

    # --- Chat fallback ---

    @pytest.mark.parametrize("text", [
        "What is the capital of France?",
        "告诉我关于这个项目的信息",
        "random question",
        "hello",
    ])
    def test_chat_fallback(self, classifier: IntentClassifier, text: str) -> None:
        result = classifier.classify(text)
        assert result.task_type == TaskType.CHAT
        assert result.confidence == pytest.approx(0.5)
        assert result.matched_keyword is None
        assert "defaulting to chat" in result.reason

    def test_empty_input(self, classifier: IntentClassifier) -> None:
        result = classifier.classify("")
        assert result.task_type == TaskType.CHAT
        assert result.confidence == pytest.approx(0.5)
        assert "Empty input" in result.reason

    def test_whitespace_only_input(self, classifier: IntentClassifier) -> None:
        result = classifier.classify("   \t\n  ")
        assert result.task_type == TaskType.CHAT
        assert result.confidence == pytest.approx(0.5)

    # --- Precedence ---

    def test_compare_takes_precedence_over_summarize(self, classifier: IntentClassifier) -> None:
        """If both compare and summarize keywords appear, the first strong match wins.

        Current implementation checks compare keywords first, so compare wins.
        """
        result = classifier.classify("compare and summarize these two papers")
        assert result.task_type == TaskType.COMPARE
        assert result.confidence == pytest.approx(0.9)

    def test_strong_overrides_weak(self, classifier: IntentClassifier) -> None:
        """Strong keywords are checked before weak keywords."""
        result = classifier.classify("compare the优劣")
        # "compare" is a strong keyword, so it should match before "优劣"
        assert result.task_type == TaskType.COMPARE
        assert result.confidence == pytest.approx(0.9)
        assert result.matched_keyword == "compare"

    # --- Result structure ---

    def test_result_is_frozen(self, classifier: IntentClassifier) -> None:
        result = classifier.classify("compare A and B")
        with pytest.raises(AttributeError):
            result.confidence = 0.5  # type: ignore[misc]

    def test_result_fields(self, classifier: IntentClassifier) -> None:
        result = classifier.classify("summary please")
        assert isinstance(result, IntentClassificationResult)
        assert hasattr(result, "task_type")
        assert hasattr(result, "confidence")
        assert hasattr(result, "reason")
        assert hasattr(result, "matched_keyword")
        assert hasattr(result, "user_override")
