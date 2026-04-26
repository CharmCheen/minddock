"""Trusted source-skill handler allowlists.

Local manifests may bind only to these built-in handler identifiers. They do not
name Python modules, entrypoints, or user-controlled code.
"""

from __future__ import annotations


TRUSTED_SOURCE_HANDLERS: frozenset[str] = frozenset(
    {
        "file.pdf",
        "file.markdown",
        "file.text",
        "url.extract",
        "image.ocr",
        "csv.extract",
    }
)

ALLOWED_SOURCE_SKILL_PERMISSIONS: frozenset[str] = frozenset(
    {
        "read_file",
        "read_url",
        "use_ocr",
        "write_index",
    }
)

FORBIDDEN_SOURCE_SKILL_PERMISSIONS: frozenset[str] = frozenset(
    {
        "subprocess",
        "read_env",
        "write_file",
        "delete_file",
        "network_any",
        "execute_code",
    }
)

DANGEROUS_MANIFEST_FIELDS: frozenset[str] = frozenset(
    {
        "entrypoint",
        "module_path",
        "script_path",
        "python_path",
        "execute",
        "run",
        "subprocess",
        "env",
        "api_key",
        "secret",
        "token",
    }
)
