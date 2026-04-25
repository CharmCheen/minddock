# Contributing to MindDock

## Ground Rules

- Keep changes small and reviewable.
- Preserve the ports-and-adapters boundary defined in `docs/CONTRACT_SCOPE.md`.
- Add or update tests for behavior changes.
- Update `docs/CHANGELOG.md` before every push.
- Do not rewrite historical stage reports under `docs/reports/`.

## Recommended Workflow

1. Create a focused branch.
2. Make code and documentation changes together.
3. Update validation or demo docs if project status or risks changed.
4. Add a dated entry to `docs/CHANGELOG.md` before pushing.
5. Run the relevant tests locally.
6. Open a pull request with scope, validation, and known gaps.

## Commit Guidance

- Prefer conventional commit prefixes such as `feat`, `fix`, `docs`, `test`, and `chore`.
- Keep one logical concern per commit where practical.

## Testing Expectations

- Unit tests for pure logic and schema validation.
- Integration tests for HTTP routes and service wiring.
- Contract tests when `domain` or `ports` change.

## Documentation Expectations

- `README.md` describes current public capabilities only.
- `docs/ROADMAP.md` tracks planned milestones.
- `docs/FINAL_VALIDATION_V4.md` tracks current implementation status.
- `docs/CHANGELOG.md` is the active push-time change record.
