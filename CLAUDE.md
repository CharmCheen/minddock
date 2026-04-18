# MindDock Project Instructions

## Project
- This is a graduation project: AI-powered personal knowledge management assistant.
- Backend: FastAPI, Ports & Adapters architecture.
- Frontend: Vite + React + TypeScript + Tailwind + shadcn/ui.
- Desktop target: Windows, Tauri planned later.

## Current frontend direction
- UI pattern: split-pane workspace
- Left pane: document workspace
- Right pane: agent/chat workspace
- Frontend must use artifacts[] as the primary rendering source of truth
- Do not assume token-level streaming
- Current stream is phase-based SSE + whole-artifact emission

## Backend contract
- Read `docs/api_contracts.md` before editing frontend integration
- `/frontend/execute/stream` uses POST + SSE-like stream
- Use fetch + ReadableStream, not EventSource POST
- `ErrorResponse.category` should be treated as optional on frontend
- `ingest_status` is currently string | null, not a formal enum yet

## Engineering rules
- Do not overbuild
- Prefer minimum runnable implementation first
- Keep types strict
- Keep business logic out of UI components
- Report modified files clearly after each phase

## Current priority
- Finish Day 1 frontend integration first
- Do not work on PDF viewer, citation highlight, mermaid real rendering, or Tauri sidecar unless explicitly asked