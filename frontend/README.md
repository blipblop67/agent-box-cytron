# Agent Hub — frontend

The flow builder UI: a node canvas for wiring up agents, plus the supporting
screens (knowledge bases, connections, team, settings). Talks to the FastAPI
backend in `../backend`.

## Stack

React + Vite, [`@xyflow/react`](https://reactflow.dev) for the canvas,
Tailwind v4 for styling, `zustand` for state, `lucide-react` for icons.

## Development

```bash
npm install
npm run dev
```

This starts Vite's dev server (default `http://localhost:5173`) and proxies
`/api/*` to `http://localhost:8811` (see `vite.config.js`) — so run the
backend (`uvicorn app.main:app --port 8811`) alongside it.

## Building for the hub

The backend serves this app as static files from `app/static`, so the two
ship as one process on one port:

```bash
npm run build
rm -rf ../backend/app/static
cp -r dist ../backend/app/static
```

Then `uvicorn app.main:app --host 0.0.0.0 --port 8811` serves both the API
and the UI. Re-run this whenever the frontend changes — `app/static` is a
build artifact, not something to hand-edit.

## Visual QA

`screenshot.mjs` drives the app with Playwright and screenshots every major
screen — useful after a design change to sanity-check nothing broke, without
needing a real browser open. Not required for normal development:

```bash
npx playwright install chromium   # one-time
BASE_URL=http://localhost:8811 node screenshot.mjs
```

## How the pieces fit together

- `src/lib/api.js` — fetch wrapper. Adds the `X-User-Name` header the
  backend's auth stub expects (see the backend README's auth section).
- `src/state/` — `zustand` stores: `userStore` (who's logged in),
  `catalogStore` (knowledge bases + connection status, shared by a few
  pages), `flowEditorStore` (the canvas currently open).
- `src/flow/` — everything specific to the canvas: `nodeRegistry.js` is the
  single source of truth for what node types exist, their icons, and their
  default config; `FlowNode.jsx` is one generic card component all node
  types share (styled per-category, not per-type); `ConfigPanel.jsx` renders
  different fields depending on which node is selected; `TraceEdge.jsx` is
  the custom copper/signal-green edge styling.
- `src/pages/` — one file per route.

## Design system

Dark, PCB-inspired palette (`src/index.css`) — copper for the primary
accent, signal-green for success/connected/executed states, both chosen to
tie back to the hardware this actually runs on rather than a generic
AI-product blue/purple gradient. IBM Plex Sans for UI text, IBM Plex Mono for
technical values (model names, node subtitles, IDs).

Colors and fonts are CSS variables defined once in `@theme` (Tailwind v4's
CSS-first config) and consumed as Tailwind utilities (`bg-copper`,
`text-signal`, etc.). If you add a new color that gets picked dynamically
(e.g. from a lookup object like `CATEGORY_CLASSES`), keep the *full* class
name as a literal string somewhere in the source — Tailwind's scanner can't
see classes assembled via string interpolation like `` `bg-${x}` ``.

## Not done yet

- Real auth UI (the name-entry gate matches the backend's current stub -
  see the backend README)
- Editing an existing Drive file's content from a "Drive" node (create and
  read are wired; update isn't exposed in the config panel yet, though the
  API supports it)
- Branching/conditional flows - the engine executes any DAG, but there's no
  node type yet that branches on a condition
- Mobile layout for the canvas itself (the list-style pages are responsive;
  a node canvas is inherently a desktop-first surface)
