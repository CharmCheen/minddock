"""Prompt profile models.

Prompt profiles are intentionally separate from runtime profiles. Runtime
profiles choose model adapters and providers; prompt profiles describe the
task-facing instruction contract used by grounded workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


PromptBuilder = Callable[..., object]


@dataclass(frozen=True)
class PromptProfile:
    """Versioned prompt contract for one task family."""

    id: str
    version: str
    task_type: str
    description: str
    evidence_policy: str
    citation_policy: str
    output_policy: str
    builder: PromptBuilder
    template: str | None = None

    def policy_dict(self) -> dict[str, str]:
        """Return frontend/documentation-safe policy metadata."""

        return {
            "evidence_policy": self.evidence_policy,
            "citation_policy": self.citation_policy,
            "output_policy": self.output_policy,
        }
