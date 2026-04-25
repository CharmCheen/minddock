"""Shared tokenizer for accurate token counting across RAG modules.

Uses the Qwen3 tokenizer for consistent, model-specific counts.
Falls back to a character-based estimate if the tokenizer cannot be loaded.
"""

from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=1)
def _get_tokenizer():
    """Load and cache the Qwen3 tokenizer. Returns None if unavailable."""
    try:
        from transformers import AutoTokenizer

        return AutoTokenizer.from_pretrained(
            "Qwen/Qwen3-Embedding-0.6B",
            trust_remote_code=True,
            use_fast=False,
        )
    except Exception:
        return None


def token_count(text: str) -> int:
    """Return the number of tokens in ``text`` using the Qwen3 tokenizer.

    Falls back to a CJK-aware character estimate when the tokenizer
    is unavailable (e.g., in minimal environments).
    """
    tok = _get_tokenizer()
    if tok is not None:
        return len(tok.encode(text, add_special_tokens=False))

    # Fallback: CJK-aware heuristic (mirrors the old structured_chunker estimate)
    words = re.findall(r"[\w一-鿿]+", text)
    cjk_chars = sum(len(w) for w in re.findall(r"[一-鿿]", text))
    english_words = len([w for w in words if re.match(r"[\w]", w)])
    return int(cjk_chars / 1.5) + english_words
