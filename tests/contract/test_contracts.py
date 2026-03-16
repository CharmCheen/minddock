from dataclasses import fields

from domain.models import Chunk, Citation, Profile, RawDoc
from ports.llm import LLMProvider


def test_domain_contract_fields_remain_stable() -> None:
    assert [field.name for field in fields(RawDoc)] == [
        "source",
        "source_uri",
        "title",
        "content",
        "created_at",
        "updated_at",
        "tags",
        "meta",
    ]
    assert [field.name for field in fields(Chunk)] == [
        "doc_id",
        "chunk_id",
        "text",
        "location",
        "section_path",
        "meta",
    ]
    assert [field.name for field in fields(Citation)] == [
        "ref",
        "quote",
        "location",
        "chunk_id",
    ]
    assert [field.name for field in fields(Profile)] == [
        "name",
        "enabled_skills",
        "retrieval",
        "language",
        "output_template",
        "citation_style",
    ]


def test_llm_port_requires_generate_method() -> None:
    assert hasattr(LLMProvider, "generate")
    assert callable(LLMProvider.generate)
