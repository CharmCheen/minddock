"""Unit tests for skill catalog, typed I/O, and invocation policy."""

import pytest

from app.application.artifacts import SkillResultArtifact
from app.application.models import SkillPolicy, SkillPolicyMode, TaskType, UnifiedExecutionRequest
from app.application.orchestrators import ChatOrchestrator, FrontendFacade, SkillOrchestrator
from app.application.run_control import RunControlConfig, RunRegistry
from app.core.exceptions import (
    InvalidSkillInputError,
    SkillDisabledError,
    SkillInvocationModeMismatchError,
    SkillNotAllowlistedError,
    SkillNotFoundError,
    SkillNotPublicError,
)
from app.runtime.factory import RuntimeFactory
from app.runtime.models import ExecutionPolicy, RuntimeCapabilities, RuntimeProfile, RuntimeSelectionMode
from app.runtime.profiles import RuntimeProfileRegistry
from app.runtime.registry import RuntimeRegistry
from app.runtime.resolver import RuntimeResolver
from app.services.service_models import ChatServiceResult, UseCaseMetadata
from app.skills import (
    SkillCapabilityTag,
    SkillDescriptor,
    SkillExecutionContext,
    SkillInputSchema,
    SkillInvocationMode,
    SkillInvocationRequest,
    SkillInvocationResult,
    SkillInvocationSource,
    SkillOutputSchema,
    SkillRegistry,
    SkillSchemaField,
)
from app.skills.policy import SkillAccessEvaluator
from app.skills.registry import Skill


class ManualUtilitySkill(Skill):
    descriptor = SkillDescriptor(
        skill_id="manual_skill",
        display_name="Manual Skill",
        description="A manual-only utility skill.",
        capability_tags=(SkillCapabilityTag.UTILITY,),
        input_schema=SkillInputSchema(
            schema_name="manual.input.v1",
            description="Manual input.",
            fields=(SkillSchemaField(name="text", field_type="string", description="Text"),),
        ),
        output_schema=SkillOutputSchema(
            schema_name="manual.output.v1",
            description="Manual output.",
            fields=(SkillSchemaField(name="text", field_type="string", description="Text"),),
        ),
        invocation_mode=SkillInvocationMode.MANUAL_ONLY,
    )

    def execute(self, request: SkillInvocationRequest, context: SkillExecutionContext) -> SkillInvocationResult:
        return SkillInvocationResult(skill_id=self.descriptor.skill_id, success=True, output={"text": request.arguments["text"]})


class HiddenSkill(Skill):
    descriptor = SkillDescriptor(
        skill_id="hidden_skill",
        display_name="Hidden Skill",
        description="A non-public diagnostic skill.",
        capability_tags=(SkillCapabilityTag.DIAGNOSTIC,),
        safe_for_public_listing=False,
        invocation_mode=SkillInvocationMode.ALLOWLISTED,
    )

    def execute(self, request: SkillInvocationRequest, context: SkillExecutionContext) -> SkillInvocationResult:
        return SkillInvocationResult(skill_id=self.descriptor.skill_id, success=True, output={"text": "hidden"})


class DisabledSkill(Skill):
    descriptor = SkillDescriptor(
        skill_id="disabled_skill",
        display_name="Disabled Skill",
        description="A disabled skill.",
        enabled=False,
        invocation_mode=SkillInvocationMode.ALLOWLISTED,
    )

    def execute(self, request: SkillInvocationRequest, context: SkillExecutionContext) -> SkillInvocationResult:
        return SkillInvocationResult(skill_id=self.descriptor.skill_id, success=True, output={})


class FakeRuntime:
    runtime_name = "langchain"
    provider_name = "fake-provider"
    capabilities = RuntimeCapabilities(supports_chat=True, supports_summarize=True)


def _runtime_stack():
    profile_registry = RuntimeProfileRegistry()
    profile_registry.register(
        RuntimeProfile(
            profile_id="default_cloud",
            display_name="Default Cloud",
            adapter_kind="langchain",
            provider_kind="openai_compatible",
            model_name="gpt-4o-mini",
            tags=("cloud", "quality"),
        )
    )
    runtime_registry = RuntimeRegistry(default_adapter_kind="langchain")
    runtime_registry.register(
        "langchain",
        lambda profile: FakeRuntime(),
        default_capabilities=RuntimeCapabilities(supports_chat=True, supports_summarize=True),
        make_default=True,
    )
    resolver = RuntimeResolver(runtime_registry=runtime_registry, profile_registry=profile_registry)
    factory = RuntimeFactory(runtime_registry=runtime_registry, profile_registry=profile_registry)
    return profile_registry, resolver, factory


def _run_registry() -> RunRegistry:
    return RunRegistry(config=RunControlConfig(max_runs=20, recent_event_buffer_size=20, completed_run_ttl_seconds=60, heartbeat_interval_seconds=2))


def test_skill_catalog_lists_safe_summaries() -> None:
    registry = SkillRegistry()
    from app.skills.registry import EchoSkill, BulletNormalizeSkill

    registry.register(EchoSkill())
    registry.register(BulletNormalizeSkill())

    catalog = registry.catalog()

    assert [entry.skill_id for entry in catalog] == ["bullet_normalize", "echo"]
    assert catalog[0].produces_artifact_kind == "skill_result"


def test_skill_detail_returns_schema_summary() -> None:
    registry = SkillRegistry()
    from app.skills.registry import EchoSkill

    registry.register(EchoSkill())

    detail = registry.catalog_detail("echo")

    assert detail is not None
    assert detail.input_schema is not None
    assert detail.input_schema.fields[0].name == "text"
    assert detail.output_schema is not None


def test_typed_skill_input_validation_rejects_invalid_payload() -> None:
    registry = SkillRegistry()
    from app.skills.registry import BulletNormalizeSkill

    registry.register(BulletNormalizeSkill())

    with pytest.raises(InvalidSkillInputError, match="expects 'text' to be a string"):
        registry.execute(
            SkillInvocationRequest(skill_id="bullet_normalize", arguments={"text": 123}),
            SkillExecutionContext(),
        )


def test_skill_access_policy_handles_not_found_disabled_not_public_and_not_allowlisted() -> None:
    registry = SkillRegistry()
    registry.register(ManualUtilitySkill())
    registry.register(HiddenSkill())
    registry.register(DisabledSkill())
    evaluator = SkillAccessEvaluator(registry)

    with pytest.raises(SkillNotFoundError):
        evaluator.evaluate(
            skill_id="missing_skill",
            policy=SkillPolicy(mode=SkillPolicyMode.ALLOWLISTED, allowed_skill_ids=("missing_skill",)),
            invocation_source=SkillInvocationSource.MANUAL,
        )
    with pytest.raises(SkillDisabledError):
        evaluator.evaluate(
            skill_id="disabled_skill",
            policy=SkillPolicy(mode=SkillPolicyMode.ALLOWLISTED, allowed_skill_ids=("disabled_skill",)),
            invocation_source=SkillInvocationSource.MANUAL,
        )
    with pytest.raises(SkillNotPublicError):
        evaluator.evaluate(
            skill_id="hidden_skill",
            policy=SkillPolicy(mode=SkillPolicyMode.ALLOWLISTED, allowed_skill_ids=("hidden_skill",), require_public_listing=True),
            invocation_source=SkillInvocationSource.MANUAL,
        )
    with pytest.raises(SkillNotAllowlistedError):
        evaluator.evaluate(
            skill_id="manual_skill",
            policy=SkillPolicy(mode=SkillPolicyMode.ALLOWLISTED, allowed_skill_ids=("echo",)),
            invocation_source=SkillInvocationSource.MANUAL,
        )


def test_manual_only_skill_requires_manual_invocation_source() -> None:
    registry = SkillRegistry()
    registry.register(ManualUtilitySkill())
    evaluator = SkillAccessEvaluator(registry)

    with pytest.raises(SkillInvocationModeMismatchError):
        evaluator.evaluate(
            skill_id="manual_skill",
            policy=SkillPolicy(mode=SkillPolicyMode.ALLOWLISTED, allowed_skill_ids=("manual_skill",)),
            invocation_source=SkillInvocationSource.PLAN,
        )


def test_echo_skill_typed_io_still_executes() -> None:
    result = SkillOrchestrator().execute_skill(name="echo", arguments={"text": "hello"}, debug=True)

    assert result.success is True
    assert result.output["text"] == "hello"
    assert result.output["debug"] is True


def test_unified_execution_requested_skill_binds_plan_step_and_returns_skill_artifact(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        skills=SkillOrchestrator(),
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=_run_registry(),
    )

    def fake_run_chat_with_runtime(*, request, runtime):
        return ChatServiceResult(answer="chat response", citations=[], metadata=UseCaseMetadata(retrieved_count=1))

    monkeypatch.setattr(chat_orchestrator, "run_chat_with_runtime", fake_run_chat_with_runtime)

    response = facade.execute(
        UnifiedExecutionRequest(
            task_type=TaskType.CHAT,
            user_input="one\ntwo",
            execution_policy=ExecutionPolicy(
                preferred_profile_id="default_cloud",
                selection_mode=RuntimeSelectionMode.PREFERRED,
            ),
            requested_skill_id="bullet_normalize",
            requested_skill_arguments={"text": "one\ntwo", "marker": "*"},
            skill_policy=SkillPolicy(mode=SkillPolicyMode.ALLOWLISTED, allowed_skill_ids=("bullet_normalize",)),
            include_metadata=True,
        )
    )

    assert response.execution_summary.skill_invocations[0].name == "bullet_normalize"
    artifact = next(artifact for artifact in response.artifacts if isinstance(artifact, SkillResultArtifact))
    assert artifact.payload["normalized_text"] == "* one\n* two"


def test_skill_result_flows_into_run_replay(monkeypatch) -> None:
    chat_orchestrator = ChatOrchestrator()
    profile_registry, resolver, factory = _runtime_stack()
    registry = _run_registry()
    facade = FrontendFacade(
        chat=chat_orchestrator,
        skills=SkillOrchestrator(),
        runtime_profile_registry=profile_registry,
        runtime_resolver=resolver,
        runtime_factory=factory,
        run_registry=registry,
    )

    def fake_run_chat_with_runtime(*, request, runtime):
        return ChatServiceResult(answer="chat response", citations=[], metadata=UseCaseMetadata(retrieved_count=1))

    monkeypatch.setattr(chat_orchestrator, "run_chat_with_runtime", fake_run_chat_with_runtime)

    run = facade.execute_run(
        UnifiedExecutionRequest(
            task_type=TaskType.CHAT,
            user_input="echo me",
            execution_policy=ExecutionPolicy(
                preferred_profile_id="default_cloud",
                selection_mode=RuntimeSelectionMode.PREFERRED,
            ),
            requested_skill_id="echo",
            requested_skill_arguments={"text": "echo me"},
            skill_policy=SkillPolicy(mode=SkillPolicyMode.ALLOWLISTED, allowed_skill_ids=("echo",)),
            include_events=True,
        )
    )

    replay_events = registry.get_recent_client_events(run.run_id)

    assert run.final_response is not None
    assert any(isinstance(artifact, SkillResultArtifact) for artifact in run.final_response.artifacts)
    assert any(
        event.kind.value == "artifact" and event.payload.artifact.kind.value == "skill_result"
        for event in replay_events
    )
