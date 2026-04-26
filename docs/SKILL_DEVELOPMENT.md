# Skill Development

## Skill System v1.2

MindDock Skill System v1.2 supports declaration-only local source skill manifests
and trusted handler binding metadata.

Users can register a `skill.json` file that describes a source skill and binds it
to a trusted built-in handler. MindDock does not execute arbitrary user code from
the manifest.

## What A Local Manifest Can Do

A local manifest can:

- describe a source skill
- declare input kinds, capabilities, limitations, permissions, and safety notes
- bind to a trusted built-in handler such as `csv.extract`
- appear in `/frontend/source-skills`
- appear in Settings > Sources
- be enabled or disabled
- provide safe handler config keys validated against a trusted handler schema
- mark ingest chunk metadata with local skill identity when exactly one enabled
  local skill matches a source

A local manifest cannot:

- define Python code
- point to a module, entrypoint, script, or executable
- run subprocesses
- read environment variables
- provide API keys or secrets
- trigger ingest at registration time
- write Chroma directly
- join autonomous LLM tool selection
- change loader selection, embedding models, retrieval ranking, rerank, citation,
  or answer generation

## Manifest Format

P0 supports JSON only. YAML manifests are not supported in v1.2 because PyYAML is
not a project dependency.

Example `skill.json`:

```json
{
  "id": "local.project_csv",
  "name": "Project CSV Skill",
  "kind": "source",
  "version": "0.1.0",
  "description": "Convert project CSV rows into searchable text.",
  "handler": "csv.extract",
  "input_kinds": [".csv"],
  "output_type": "SourceLoadResult",
  "source_media": "text",
  "source_kind": "csv_file",
  "loader_name": "csv.extract",
  "capabilities": ["csv_rows_as_text"],
  "limitations": ["no_excel"],
  "permissions": ["read_file", "write_index"],
  "config": {
    "max_rows": 500,
    "include_header": true
  },
  "safety_notes": ["uses_builtin_handler"]
}
```

The id must match `local.<safe-id>`. Path traversal, slashes, backslashes, drive
letters, and absolute paths are rejected.

## Trusted Handler Binding

Local manifests can bind only to trusted built-in source handlers:

- `file.pdf`
- `file.markdown`
- `file.text`
- `url.extract`
- `image.ocr`
- `csv.extract`
- `audio.transcribe`
- `video.transcribe`

The manifest names a handler id, not a Python function. The trusted handler
contract records:

- input kinds
- output type
- source media/kind
- loader name
- permissions
- capabilities and limitations
- optional config schema

This contract is metadata, not an executable entrypoint. Execution remains
inside MindDock's existing `SourceLoaderRegistry` and ingest pipeline.

When one enabled local source skill matches an ingested source, MindDock annotates
chunk metadata with:

- `skill_id`
- `skill_name`
- `skill_handler`
- `skill_origin`
- `skill_version`
- `skill_config_keys`

The full config is not written to chunk metadata. If multiple local skills match
the same source, MindDock does not pick randomly and records a short binding
warning instead.

## Handler Config

Manifest `config` must be a JSON object and must match the trusted handler's
schema. Unknown keys, wrong types, out-of-range values, and dangerous keys are
rejected.

Dangerous config keys include:

- `api_key`
- `token`
- `secret`
- `env`
- `command`
- `script`
- `subprocess`
- `path`

Current examples:

- `csv.extract`: `max_rows`, `max_chars`, `include_header`
- `url.extract`: `timeout_seconds`
- `image.ocr`: `max_chars`
- `audio.transcribe`: `provider`, `language`, `max_chars`, `include_timestamps`
- `video.transcribe`: `provider`, `language`, `max_chars`, `include_timestamps`

v1.2 validates these values but does not yet change loader behavior from local
manifest config.

## Contributing a New Trusted Handler

MindDock does not execute arbitrary user scripts. If you want to add a new
source-processing capability, contribute it as a **trusted built-in handler**
through a Pull Request.

### What to include

1. **Register handler metadata** in `app/skills/handlers.py`:
   - `handler id`
   - `input_kinds`
   - `permissions` (from the allowed set)
   - `source_media` / `source_kind`
   - `loader_name`
   - `capabilities` and `limitations`
   - Safe `config_schema` (no `api_key`, `secret`, `token`, `env`)

2. **Implement a safe loader** under `app/rag/` or `app/rag/source_skills/`:
   - Return `SourceLoadResult` with normalized text and metadata.
   - Include `source_media`, `source_kind`, `loader_name`, `retrieval_basis`.
   - Provide a **mock provider** that works without external dependencies.
   - Provide a **disabled provider** that returns empty text + warning.
   - Stub or implement a real **API provider** with fallback to mock when unconfigured.
   - Do not store raw media bytes, absolute paths, or API keys in metadata.
   - Reference implementation: `app/rag/media_loader.py` (v1.3)

3. **Register the loader** in `app/rag/source_loader.py`:
   - Add to `SourceLoaderRegistry` at the correct priority.
   - Add extensions to `SUPPORTED_EXTENSIONS` if applicable.

4. **Add tests** covering:
   - Handler registry presence
   - Manifest validation (bindable, rejects unsafe config)
   - Loader support for expected extensions
   - Mock provider returns safe placeholder text
   - Empty output does not create chunks
   - Metadata contract (no leaked paths, keys, or bytes)
   - Incremental ingest add/delete
   - Skill binding metadata when enabled

5. **Add docs and example manifest**:
   - Update `docs/SKILL_DEVELOPMENT.md` and `docs/INGEST_PIPELINE.md`.
   - Add an example under `examples/skills/local.<name>/skill.json`.

6. **PR description must include**:
   - Input types supported
   - Permissions required
   - Provider behavior (mock / disabled / api)
   - Limitations and safety notes
   - Test results

### Three layers

| Layer | What it is | Who controls it |
|---|---|---|
| **Manifest skill** | User-created `skill.json` — declarative, no code | End user |
| **Trusted handler** | Built-in, reviewed, safe processing logic | MindDock maintainers |
| **External plugin** | Future sandboxed execution model | Out of scope for v1.3 |

## Rejected Fields

Validation rejects these fields:

- `entrypoint`
- `module_path`
- `script_path`
- `python_path`
- `execute`
- `run`
- `subprocess`
- `env`
- `api_key`
- `secret`
- `token`

The validation error is explicit: arbitrary entrypoints are not allowed in Skill
System v1.1/v1.2.

## Permissions

Allowed permissions:

- `read_file`
- `read_url`
- `use_ocr`
- `write_index`

Rejected permissions include:

- `subprocess`
- `read_env`
- `write_file`
- `delete_file`
- `network_any`
- `execute_code`

`write_index` means MindDock's normal ingest pipeline may write the index. The
skill itself does not write vector-store records.

## Local Store

By default, local manifests are stored under:

```text
skills/local/<skill-id>/skill.json
```

The directory can be overridden with:

```text
MINDDOCK_SKILLS_DIR
```

Registering a manifest writes only the manifest file. It does not execute the
handler, trigger ingest, or write Chroma.

## CLI

```powershell
python -m app.demo skills
python -m app.demo skills --implemented
python -m app.demo skills --local
python -m app.demo skill-detail --id csv.extract
python -m app.demo skill-handlers
python -m app.demo skill-handler-detail --id csv.extract
python -m app.demo skill-resolve --source path\to\data.csv
python -m app.demo skill-validate --manifest path\to\skill.json
python -m app.demo skill-register --manifest path\to\skill.json
python -m app.demo skill-disable --id local.project_csv
python -m app.demo skill-enable --id local.project_csv
```

Enable and disable only apply to local skills. Built-in implemented skills cannot
be disabled by local manifests, and future skills cannot be enabled.

## API

```text
GET  /frontend/source-skills
GET  /frontend/source-skills/{id}
POST /frontend/source-skills/validate
POST /frontend/source-skills/register
POST /frontend/source-skills/{id}/enable
POST /frontend/source-skills/{id}/disable
```

The existing `/frontend/skills` API remains for executable application skills and
is not used for local source skill execution.

## Future Work

Community skills would require sandboxing, signing, permission review, and a
separate installer/update model. Those are intentionally out of scope for v1.1
and especially important for a Windows desktop EXE scenario, where executing
unknown local plugins would create a large security surface.

`audio.transcribe` and `video.transcribe` entered MindDock as trusted handlers
in Skill System v1.3. They serve as the reference implementation for future
contributors.

Future capabilities such as `notion.import` should follow the same pattern:
implement the trusted handler in the codebase first, then users can bind local
manifests to it without ever supplying arbitrary Python code.
