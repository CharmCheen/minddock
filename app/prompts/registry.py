"""Versioned prompt registry for grounded RAG services."""

from __future__ import annotations

from functools import lru_cache

from app.prompts.models import PromptProfile

EVIDENCE_FIRST_CHAT_PROFILE_ID = "evidence_first_chat_v1"
GROUNDED_SUMMARY_PROFILE_ID = "grounded_summary_v1"
GROUNDED_COMPARE_JSON_PROFILE_ID = "grounded_compare_json_v1"


def _chat_prompt_builder():
    template = _chat_template()
    try:
        from langchain_core.prompts import ChatPromptTemplate
    except ModuleNotFoundError:
        return "minddock-grounded-chat-prompt"

    return ChatPromptTemplate.from_messages(
        [
            ("system", template["system"]),
            ("human", template["human"]),
        ]
    )


def _summary_prompt_builder(*, mode: str = "basic"):
    templates = {
        "basic": _summary_basic_template(),
        "map": _summary_map_template(),
        "reduce": _summary_reduce_template(),
    }
    selected = templates.get(mode, templates["basic"])
    try:
        from langchain_core.prompts import ChatPromptTemplate
    except ModuleNotFoundError:
        return f"minddock-grounded-summary-{mode}-prompt"

    return ChatPromptTemplate.from_messages(
        [
            ("system", selected["system"]),
            ("human", selected["human"]),
        ]
    )


def _compare_json_prompt_builder(
    *,
    question: str,
    left_label: str,
    left_evidence: tuple[str, ...] | list[str],
    right_label: str,
    right_evidence: tuple[str, ...] | list[str],
) -> str:
    lines: list[str] = [
        _compare_json_template()["system"],
        "",
        f"Question: {question}",
        "",
        f"Left source evidence ({left_label}):",
    ]
    for index, text in enumerate(left_evidence, start=1):
        lines.append(f"  L{index}: {str(text).strip()}")
    lines.append("")
    lines.append(f"Right source evidence ({right_label}):")
    for index, text in enumerate(right_evidence, start=1):
        lines.append(f"  R{index}: {str(text).strip()}")
    lines.extend(
        [
            "",
            _compare_json_template()["output_contract"],
            "",
            "Rules:",
            "1. Evidence ids MUST come from the L1..Ln and R1..Rn labels above.",
            "2. Every point must have evidence from BOTH sides. Omit any point that cannot be supported by both left and right evidence.",
            "3. Do not invent evidence IDs or output one-sided points.",
            "4. Do not restate the user question in any statement.",
            "5. Do not produce generic relevance statements such as 'both are relevant', 'both discuss the requested topic', or 'they emphasize different details'.",
            "6. Focus on research direction, methodology, contribution, evaluation approach, assumptions, and key findings when relevant.",
            "7. If the provided evidence is insufficient for a common point, difference, or conflict, leave that list empty rather than inventing claims.",
            "8. Every statement must be a concrete comparison claim grounded in cited evidence, not a retrieval relevance statement.",
        ]
    )
    return "\n".join(lines)


def _chat_template() -> dict[str, str]:
    return {
        "system": (
            "You are MindDock's grounded answer assistant. "
            "Follow these rules strictly: "
            "1. Answer only from the provided evidence; do not add outside knowledge. "
            "2. If the evidence is missing, weak, contradictory, or not clearly aligned with the question, "
            "say the evidence is insufficient and briefly explain the gap. "
            "3. Synthesize all relevant evidence items; do not rely on the first item when other evidence "
            "adds, qualifies, or conflicts with it. "
            "4. If only part of the question is supported, answer that part and state what is not supported. "
            "Keep the answer concise and factual."
        ),
        "human": "Question:\n{query}\n\nEvidence:\n{evidence_block}",
    }


def _summary_basic_template() -> dict[str, str]:
    return {
        "system": (
            "You are MindDock's grounded summarization assistant. "
            "Summarize only from the provided evidence. "
            "If the evidence is insufficient, say so explicitly. "
            "Produce a short synthesis rather than a verbatim extract."
        ),
        "human": "Topic:\n{topic}\n\nEvidence:\n{evidence_block}",
    }


def _summary_map_template() -> dict[str, str]:
    return {
        "system": "Summarize the provided document evidence only. Keep the summary local to that document.",
        "human": "Topic:\n{topic}\n\nDocument:\n{document_ref}\n\nEvidence:\n{evidence_block}",
    }


def _summary_reduce_template() -> dict[str, str]:
    return {
        "system": (
            "Combine the partial summaries into one grounded synthesis. "
            "Highlight agreements, distinctions, and the overall takeaway."
        ),
        "human": "Topic:\n{topic}\n\nPartial summaries:\n{partial_summaries}",
    }


def _compare_json_template() -> dict[str, str]:
    return {
        "system": (
            "You are a grounded comparison assistant. "
            "Compare the evidence from two sources and produce a structured JSON response. "
            "Only use the evidence provided below. Do not add outside knowledge."
        ),
        "output_contract": (
            "Return strictly valid JSON with this structure:\n"
            "{\n"
            '  "common_points": [\n'
            "    {\n"
            '      "statement": "string",\n'
            '      "summary_note": "string",\n'
            '      "left_evidence_ids": ["L1"],\n'
            '      "right_evidence_ids": ["R1"]\n'
            "    }\n"
            "  ],\n"
            '  "differences": [...],\n'
            '  "conflicts": [...]\n'
            "}"
        ),
    }


@lru_cache(maxsize=1)
def get_prompt_registry() -> dict[str, PromptProfile]:
    """Return the built-in prompt profile registry."""

    return {
        EVIDENCE_FIRST_CHAT_PROFILE_ID: PromptProfile(
            id=EVIDENCE_FIRST_CHAT_PROFILE_ID,
            version="1.0.0",
            task_type="chat",
            description="Evidence-first grounded chat prompt with insufficient-evidence refusal rules.",
            evidence_policy="answer_only_from_provided_evidence; refuse_or_scope_down_when_evidence_is_missing_weak_contradictory_or_misaligned",
            citation_policy="citations_are_derived_from_retrieved_evidence_chunks; no_citations_when_evidence_is_insufficient",
            output_policy="concise_factual_answer; state_unsupported_parts_when_partial",
            builder=_chat_prompt_builder,
            template=str(_chat_template()),
        ),
        GROUNDED_SUMMARY_PROFILE_ID: PromptProfile(
            id=GROUNDED_SUMMARY_PROFILE_ID,
            version="1.0.0",
            task_type="summarize",
            description="Grounded summarization prompts for basic and map-reduce summary modes.",
            evidence_policy="summarize_only_from_provided_evidence; explicitly_note_insufficient_evidence",
            citation_policy="summary_citations_follow_compressed_evidence_chunks",
            output_policy="short_synthesis_not_verbatim_extract; map_reduce_combines_document_local_summaries",
            builder=_summary_prompt_builder,
            template=str(
                {
                    "basic": _summary_basic_template(),
                    "map": _summary_map_template(),
                    "reduce": _summary_reduce_template(),
                }
            ),
        ),
        GROUNDED_COMPARE_JSON_PROFILE_ID: PromptProfile(
            id=GROUNDED_COMPARE_JSON_PROFILE_ID,
            version="1.0.0",
            task_type="compare",
            description="Grounded two-source comparison prompt that asks for strict JSON and paired evidence ids.",
            evidence_policy="compare_only_left_and_right_evidence; every_point_requires_both_sides",
            citation_policy="compare_points_reference_Ln_Rn_evidence_ids_resolved_back_to_chunks",
            output_policy="strict_json_common_points_differences_conflicts; omit_unsupported_one_sided_points",
            builder=_compare_json_prompt_builder,
            template=str(_compare_json_template()),
        ),
    }


def get_prompt_profile(profile_id: str) -> PromptProfile:
    """Return a prompt profile by id."""

    registry = get_prompt_registry()
    try:
        return registry[profile_id]
    except KeyError as exc:
        raise KeyError(f"Unknown prompt profile: {profile_id}") from exc


def prompt_profile_trace(profile: PromptProfile) -> dict[str, object]:
    """Return workflow_trace metadata for a prompt profile."""

    return {
        "prompt_profile_id": profile.id,
        "prompt_profile_version": profile.version,
        "prompt_policy": profile.policy_dict(),
    }
