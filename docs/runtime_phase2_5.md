# Runtime Configuration — Phase 2.5

## Status

Phase 2.5 is a small usability upgrade on top of Phase 1 / 1.5, adding connection testing, reset, and clearer state feedback. It does **not** introduce new providers, profiles, or secret management.

---

## What is supported now

| Feature | Status |
|---------|--------|
| Configure OpenAI-compatible endpoint | Done (Phase 1) |
| Test connection without saving | Done (Phase 2.5) |
| Save & activate immediately | Done (Phase 1) |
| Reset to default runtime | Done (Phase 1.5) |
| Clear feedback: active status, dirty state, test result | Done (Phase 2) |
| api_key never returned in API responses | Done (Phase 1) |
| Config persisted to `data/active_runtime.json` | Done (Phase 1) |
| Env vars bootstrapped from saved config at startup | Done (Phase 1) |

---

## What is NOT yet supported

- **Multiple providers** — only `openai_compatible` (provider selector is locked in the UI)
- **Profile management** — no named profiles or quick-switching
- **Secret manager** — API keys are stored in plain JSON (acceptable for local-only use)
- **Streaming-ready runtime** — not yet wired up
- **Auto-retry on connection failure** — falls back to default runtime gracefully

---

## Save vs. Test vs. Reset

### Save & Activate

- Writes config to `data/active_runtime.json`
- Immediately sets `LLM_API_KEY` / `LLM_RUNTIME_BASE_URL` env vars in the process
- Invalidates the profile registry cache so the next LLM request uses the new config
- **Effect is immediate** — no restart required

### Test Connection

- Sends a minimal `hi` message to the endpoint using the provided credentials
- **Does NOT persist anything** — safe to try before saving
- Classifies errors into: `invalid_url`, `auth_failure`, `model_not_found`, `timeout`, `network_error`, `unknown`
- Returns a human-readable message and structured `error_kind`

### Reset

- Writes a **disabled default config** to `data/active_runtime.json`
- Removes `LLM_API_KEY` / `LLM_RUNTIME_BASE_URL` from process env
- Invalidates the profile registry cache
- After reset, the system uses the **default OpenAI.com endpoint** with whatever is in `LLM_API_KEY` (from `.env` or environment)

---

## Active Config vs. Editing Form

The settings UI has two layers:

1. **"Currently Active" banner** — shows what is actually running right now (last saved config)
2. **Edit form** — shows what you are currently editing (may differ from active if you have unsaved changes)

These are kept separate intentionally:

- `isDirty` flag tells you whether the form differs from the last saved config
- If you have a stored key (`api_key_masked: true`), the API key field shows `••••••••` and leaving it blank on save preserves the existing key
- Test/Reset always operate on the **saved config**, not the form

---

## How Configuration Reaches the Runtime

```
User fills form
    ↓
PUT /frontend/runtime-config  (save)
    ↓
data/active_runtime.json  (persisted)
    ↓
bootstrap_env_from_active_config()  ← called in FastAPI lifespan at startup
    ↓
os.environ["LLM_API_KEY"]        ← picked up by registry
os.environ["LLM_RUNTIME_BASE_URL"]
    ↓
get_runtime_profile_registry.cache_clear()  ← registry invalidated
    ↓
Next LLM request → RuntimeResolver → RuntimeFactory → LangChainAdapter
    → uses env-overridden base_url / api_key
```

For **Test Connection** (does not persist):

```
User fills form + clicks "Test Connection"
    ↓
POST /frontend/runtime-config/test  (validates only)
    ↓
ChatOpenAI.invoke("hi")  ← fire-and-forget, no env modified, no file written
    ↓
error_kind classified and returned
```

---

## Key Files

| File | Role |
|------|------|
| `app/runtime/active_config.py` | Config dataclass, load/save, env bootstrap |
| `app/api/routes.py` | GET/PUT /runtime-config, POST /test, POST /reset |
| `app/api/schemas.py` | Request/response schemas |
| `app/main.py` | Calls `bootstrap_env_from_active_config()` in lifespan |
| `frontend/src/features/settings/store.ts` | Zustand store, all async actions |
| `frontend/src/features/settings/settings-view.tsx` | Settings modal UI |
| `tests/integration/test_runtime_config_api.py` | API integration tests |

---

## Fallback Logic

When the user-configured runtime is **disabled** or **unreachable**:

1. Registry falls back to the **default profile** (cloud OpenAI)
2. If `LLM_API_KEY` is set in `.env`, it is used
3. If neither user config nor env var is available, the request fails with a clear error

When the user-configured runtime is **enabled** but **connection fails**:

- The LLM call itself fails — no automatic retry with fallback
- User must manually Reset or correct the configuration
- Error classification in the test endpoint helps diagnose the issue

---

## Testing the Configuration

### Automated (recommended for CI)

```bash
# Run the runtime-config API integration tests
D:/conda_envs/minddock/python.exe -m pytest tests/integration/test_runtime_config_api.py -v
```

### Manual acceptance path

1. Open the app → Settings panel
2. Fill in Base URL, API Key, Model, check "Enable this runtime"
3. Click **Test Connection** — verify it shows "Connection OK" before saving
4. Click **Save & Activate**
5. Verify the "Currently Active" banner updates immediately
6. Click **Reset** — verify it returns to "Default Runtime"
7. Make a chat query — verify it still works against the default endpoint
