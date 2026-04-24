# MindDock Frontend

MindDock frontend is a React + Vite + TypeScript application for demonstrating the local knowledge-base assistant.

## Tech Stack

- React 18
- TypeScript
- Vite
- Zustand
- Axios
- Playwright smoke test

## Start

```powershell
cd frontend
npm install
npm run dev
```

Default Vite URL:

```text
http://localhost:5173
```

Build check:

```powershell
npm run build
```

Smoke test:

```powershell
npm run test:smoke
```

## Main UI Areas

### Chat UI

The agent workspace supports chat, summarize, compare and structured output flows through the backend frontend facade.

### Citation List

Answers render citations with:

- source title / filename
- citation label, for example `SYSTEM DESIGN · p.3`
- compact evidence preview
- evidence window chunk count
- hit-in-window status

These fields are designed to make grounded answers easier to verify during the demo.

### Source Drawer

Clicking a citation opens the related source drawer. The drawer can show source details and chunk previews from the backend source catalog APIs.

Current limitation: the drawer does not yet fully expand the complete evidence window. It mainly provides source/chunk inspection and citation snippet context.

### Runtime Settings

The frontend includes runtime settings for selecting or testing backend model configuration. If no real API key is configured, the backend can fall back to mock generation.

### Selected Source / Scoped Retrieval

The context bar shows whether the current interaction is scoped to selected sources. Explicit source filters are respected by the backend and take priority over natural-language heuristics.

## Backend Relationship

The frontend talks to the FastAPI backend, mainly through:

- `/frontend/execute`
- `/frontend/execute/stream`
- `/sources`
- `/sources/{doc_id}`
- `/sources/{doc_id}/chunks`
- runtime configuration endpoints

Backend default:

```text
http://127.0.0.1:8000
```

## Known Limitations

- Source drawer does not yet display the full evidence window as a first-class UI object.
- Citation metadata such as `Window: N chunks` and `Hit in window` may need explanation for non-technical users.
- Figure/table object-level citation remains future work.
- The frontend is intended for graduation demo and system validation, not a polished commercial UI.
