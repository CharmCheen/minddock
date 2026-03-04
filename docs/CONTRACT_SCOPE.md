# Contract Definition Scope

This phase defines only stable contracts and boundaries.

## Included
- Domain data contracts (`domain/models.py`)
- Extension port contracts (`ports/*.py`)
- Package exports (`domain/__init__.py`, `ports/__init__.py`)

## Excluded
- Adapter implementations
- Workflow runtime logic
- External SDK calls
- End-to-end execution paths

## Engineering Rules
- Core depends only on `ports` and `domain`.
- Adapter code must implement ports without changing core contracts.
- Contract changes require tests update in `tests/contract/`.
