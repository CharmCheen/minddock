"""Integration tests for schedule extraction skill registration."""

import pytest

from app.skills.registry import get_skill_registry


class TestScheduleSkillRegistration:
    def test_skill_in_registry(self):
        registry = get_skill_registry()
        skill = registry.skills.get("schedule_extraction")
        assert skill is not None

    def test_skill_descriptor(self):
        registry = get_skill_registry()
        desc = registry.get_descriptor("schedule_extraction")
        assert desc is not None
        assert desc.skill_id == "schedule_extraction"
        assert desc.display_name == "日程候选识别"
        assert desc.safe_for_public_listing is True
        assert desc.enabled is True

    def test_skill_in_catalog(self):
        registry = get_skill_registry()
        catalog = registry.catalog(public_only=True, enabled_only=True)
        ids = [entry.skill_id for entry in catalog]
        assert "schedule_extraction" in ids

    def test_skill_catalog_detail(self):
        registry = get_skill_registry()
        detail = registry.catalog_detail("schedule_extraction")
        assert detail is not None
        assert detail.input_schema is not None
        assert detail.output_schema is not None
        assert len(detail.safety_notes) > 0

    def test_skill_invocation_with_isolated_store(self, tmp_path, monkeypatch):
        """Test skill invocation with an isolated store to avoid polluting real data."""
        from app.schedule.store import ScheduleCandidateStore
        from app.services.schedule_candidate_service import ScheduleCandidateService
        from app.skills.models import SkillExecutionContext, SkillInvocationRequest

        # Patch ScheduleCandidateService to use tmp store
        store_file = tmp_path / "schedule_candidates.json"
        test_store = ScheduleCandidateStore(file_path=store_file)
        original_init = ScheduleCandidateService.__init__

        def patched_init(self, *, store=None, vectorstore=None):
            original_init(self, store=test_store, vectorstore=vectorstore)

        monkeypatch.setattr(ScheduleCandidateService, "__init__", patched_init)

        # Clear registry cache so it picks up patched service
        get_skill_registry.cache_clear()

        registry = get_skill_registry()
        request = SkillInvocationRequest(
            skill_id="schedule_extraction",
            arguments={},
        )
        result = registry.execute(request, SkillExecutionContext())
        assert result.success is True
        assert result.skill_id == "schedule_extraction"

        # Verify no real data file was created
        import pathlib
        real_data_file = pathlib.Path("data/schedule_candidates.json")
        assert not real_data_file.exists()
