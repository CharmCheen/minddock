# Changelog

This file is the active modification log for the repository.
Update it before every push.

## Unreleased

### Added

- Open-source governance files: `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and `SECURITY.md`
- Project tracking docs: `docs/ROADMAP.md`, `docs/STATUS.md`, and `docs/TEST_PLAN.md`
- Baseline automated tests for API routes, schemas, chat service, and contract definitions

### Changed

- Repository naming aligned to `MindDock`
- `.gitignore` updated to ignore runtime log files
- `pyproject.toml` now documents development test dependencies and pytest settings
- FastAPI startup logging moved from deprecated `on_event` hook to `lifespan`

### Notes

- Stage reports under `docs/reports/` remain unchanged by policy
