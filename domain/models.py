"""Stable domain data contracts for the PKM assistant.

This module contains only data schemas and no runtime logic.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RawDoc:
    """Normalized document shape before ingestion."""

    source: str
    source_uri: str
    title: str
    content: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    tags: Optional[List[str]] = None
    meta: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class Chunk:
    """Smallest retrievable evidence unit used by retrieval and citation."""

    doc_id: str
    chunk_id: str
    text: str
    location: str
    section_path: Optional[List[str]] = None
    meta: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class Citation:
    """Traceable citation for answer claims."""

    ref: str
    quote: str
    location: str
    chunk_id: str


@dataclass(frozen=True)
class RetrievalConfig:
    """Profile-level retrieval parameters."""

    top_k: int = 8
    rerank: bool = False
    filters: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Profile:
    """Scenario profile contract injected into orchestration."""

    name: str
    enabled_skills: List[str]
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    language: str = "zh"
    output_template: str = "{{answer}}\n{{citations}}"
    citation_style: str = "list"
