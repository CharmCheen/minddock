# Runtime Configuration — Phase 3: Security & Observability

## Overview

Phase 3 adds two focused improvements to the runtime configuration system:

1. **Security hardening** — `api_key` is no longer written to disk in plain text
2. **Observability** — `config_source` field tells you exactly where the active runtime credentials are coming from

Phase 3 does **not** add new providers, profiles, or secret management. It focuses on making the existing Phase 1/2 system safer and more transparent.

---

## Security: api_key Never Written to Disk

### The Problem (Phase 1-2)

In Phase 1 and 2, `save_active_config()` wrote the full `api_key` in plain text to `data/active_runtime.json`:

```json
{
  "provider": "openai_compatible",
  "base_url": "https://api.example.com/v1",
  "api_key": "sk-xxxxx...",   // ← plain text, committed accidentally
  "model": "gpt-4o",
  "enabled": true
}
```

This had two risks:
- The file was not in `.gitignore` — accidental commit could expose the key
- Even if gitignored, the key lived on disk unencrypted

### The Phase 3 Fix

The `api_key` is **never written to disk**. The file stores a marker:

```json
{
  "provider": "openai_compatible",
  "base_url": "https://api.example.com/v1",
  "api_key_source": "env",
  "model": "gpt-4o",
  "enabled": true
}
```

`api_key_source` values:
- `"env"` — a key was entered this session and is in `os.environ`
- `"none"` — no custom key configured

The actual key lives only in `os.environ["LLM_API_KEY"]`, set at save time and cleared on reset.

### Known Limitation

After a server restart, the user must re-enter the API key via Settings UI (it cannot be restored from the file). This is a deliberate trade-off:

> "Weak persistence + env-first" — prevents accidental key disclosure via git history, while keeping single-session UX functional.

For multi-session persistence without re-entry, a proper secret manager (Vault, AWS Secrets Manager, etc.) would be needed — out of scope for Phase 3.

### Security Invariants (enforced by tests)

1. `api_key` never appears in `data/active_runtime.json`
2. `api_key` never appears in any API response body
3. `PUT /frontend/runtime-config` sets `os.environ["LLM_API_KEY"]` but never writes it to disk
4. `POST /frontend/runtime-config/reset` clears the env var and sets `api_key_source="none"`

---

## Observability: config_source Field

Every `GET /frontend/runtime-config` response now includes a `config_source` field:

| `config_source` value | Meaning |
|---|---|
| `"active_config_env"` | Custom runtime enabled; `LLM_API_KEY` is set in the environment |
| `"active_config_disabled"` | Config file saved but disabled; using default runtime |
| `"env_override"` | No config file; `LLM_API_KEY` is set in the shell environment |
| `"default"` | No config file; no env key; using system defaults |

This lets the UI and operators distinguish:

- "Config exists but is disabled" vs "no config exists"
- "Key from this session" vs "key from shell environment"
- Whether a restart has cleared the session key

---

## config_source in the UI

The Settings panel now shows the credential source in the "Currently Active" banner:

- `"active_config_env"` → shows "Custom runtime (key from session)"
- `"active_config_disabled"` → shows "Custom runtime disabled"
- `"env_override"` → shows "Default runtime (key from environment)"
- `"default"` → shows "Default runtime (no config)"

The `api_key_masked` field still shows `true`/`false` to indicate whether any key is present, without revealing the value.

---

## Behavior of Save / Test / Reset

### Save & Activate

1. Writes `data/active_runtime.json` with `api_key_source="env"` (key itself goes only to `os.environ`)
2. Sets `os.environ["LLM_API_KEY"]` and `os.environ["LLM_RUNTIME_BASE_URL"]`
3. Invalidates the profile registry cache
4. **Effect is immediate** — no restart needed
5. **After restart**: key is gone from env; user must re-enter it

### Test Connection

1. Does NOT write to disk or env
2. Uses the provided credentials in-memory only
3. Returns structured result with `error_kind`

### Reset

1. Writes `data/active_runtime.json` with `enabled=False`, `api_key_source="none"`
2. Removes `LLM_API_KEY` and `LLM_RUNTIME_BASE_URL` from env
3. Invalidates the profile registry cache
4. Config source becomes `"active_config_disabled"`

---

## Configuration Priority / Flow

```
Startup:
  bootstrap_env_from_active_config()
    → reads data/active_runtime.json (if exists)
    → sets LLM_RUNTIME_BASE_URL if enabled
    → does NOT read api_key from file (security)

Runtime (per request):
  registry checks os.environ["LLM_API_KEY"]  ← this is the actual key
  registry checks os.environ["LLM_RUNTIME_BASE_URL"]  ← this is the override
```

The `api_key` in `os.environ` is set by:
- `PUT /frontend/runtime-config` (save) — session-only, not persisted
- Shell environment (pre-existing `LLM_API_KEY` env var)

---

## Testing

```bash
# Run Phase 3 security and observability tests
D:/conda_envs/minddock/python.exe -m pytest tests/integration/test_runtime_config_api.py -v

# Expected: 26 passed
```

Key test coverage:
- `test_api_key_never_persisted_to_disk` — critical security invariant
- `test_config_source_active_config_env_when_enabled_with_key_in_env` — observability
- `test_reset_clears_disk_config` — reset wipes api_key_source
- `test_save_with_key_sets_env_var` — save sets env, not file
- `test_save_disabled_clears_env` — disabled save clears env

---

## What Phase 3 Does NOT Do

- Does NOT add multiple providers
- Does NOT add profile management
- Does NOT add a secret manager
- Does NOT encrypt the `data/active_runtime.json` file
- Does NOT persist `api_key` across restarts

---

## File Changes

| File | Change |
|---|---|
| `app/runtime/active_config.py` | New `api_key_source` field, `save_active_config` refactored, `get_effective_runtime_status()` added |
| `app/api/routes.py` | Use new `save_active_config` signature, pass `config_source` to response |
| `app/api/schemas.py` | `RuntimeConfigResponse` gains `config_source` field |
| `frontend/src/core/types/api.ts` | TypeScript type updated |
| `frontend/src/features/settings/settings-view.tsx` | Display `config_source` in banner |
| `tests/integration/test_runtime_config_api.py` | Rewritten for Phase 3 invariants; 26 tests |
