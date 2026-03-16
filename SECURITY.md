# Security Policy

## Supported Scope

MindDock is currently an early-stage open-source backend project. Security fixes are handled on a best-effort basis.

## Reporting a Vulnerability

- Do not open a public issue for a suspected vulnerability.
- Report the issue privately to the maintainer with:
  - affected files or endpoints
  - reproduction steps
  - impact assessment
  - proposed mitigation if available

## Secrets Handling

- Never commit API keys, tokens, or private datasets.
- Keep local secrets in `.env` files that are ignored by git.
- Sanitize logs before sharing them publicly.
