"""Prompt profile registry for MindDock grounded workflows."""

from app.prompts.models import PromptProfile
from app.prompts.registry import (
    EVIDENCE_FIRST_CHAT_PROFILE_ID,
    GROUNDED_COMPARE_JSON_PROFILE_ID,
    GROUNDED_SUMMARY_PROFILE_ID,
    get_prompt_profile,
    get_prompt_registry,
    prompt_profile_trace,
)

__all__ = [
    "EVIDENCE_FIRST_CHAT_PROFILE_ID",
    "GROUNDED_COMPARE_JSON_PROFILE_ID",
    "GROUNDED_SUMMARY_PROFILE_ID",
    "PromptProfile",
    "get_prompt_profile",
    "get_prompt_registry",
    "prompt_profile_trace",
]
