# Copilot instructions — finathon (frontend + backend)

This file gives focused, actionable guidance for AI coding agents working in this repository.

- **Architecture (big picture):** two main folders: `frontend/` (React app built with webpack + Babel) and `backend/` (API/server). The frontend talks to the backend at runtime; several pages call `http://localhost:4000` (see `src/pages/dashboard/DashboardPage.jsx`).

- **Where to look first:**
  - Frontend entry & scripts: [frontend/package.json](frontend/package.json)
  - Dev server config: [frontend/webpack.config.js](frontend/webpack.config.js)
  - Public HTML: [frontend/public/index.html](frontend/public/index.html)
  - React pages: [frontend/src/pages](frontend/src/pages)
  - Layout & UI primitives: [frontend/src/components/layout](frontend/src/components/layout) and [frontend/src/components/ui](frontend/src/components/ui)
  - Shared helpers: [frontend/src/lib/utils.js](frontend/src/lib/utils.js)

- **Run & build (frontend):**
  - Install: `cd frontend && npm install`
  - Dev server: `npm start` (runs `webpack serve --mode development` from `frontend/package.json`).
  - Production build (no script present): use `npx webpack --mode production` in `frontend/` or add a `build` script instead of editing existing `start` behavior.

- **Backend expectations:**
  - Frontend code assumes an API at `http://localhost:4000` (see `src/pages/dashboard/DashboardPage.jsx` which POSTs to `/upload-test` using a FormData key `testFile`).
  - Before changing frontend API URLs, check `backend/` for its start script and CORS behavior; prefer introducing an env variable (or config) rather than hardcoding replacements across pages.

- **Codebase conventions & patterns:**
  - Functional React components in `*.jsx` files; components are exported as named exports (examples: `DashboardLayout`, `Card`, `Button`). Import style: `import { Card } from "../../components/ui/card"`.
  - UI primitives live in `src/components/ui/*` (badge, button, card, input, select). Preserve named exports and props shapes when modifying.
  - Pages live under `src/pages/*` (e.g., `dashboard/DashboardPage.jsx`). Add new routes by creating pages and wiring them into the router in `src/index.jsx` (router uses `react-router-dom`).
  - Styling uses Tailwind CSS and utility class merging. Use the `cn()` helper from `src/lib/utils.js` (wraps `clsx` + `tailwind-merge`) when composing dynamic classNames.
  - Files often use lowercase filenames but export PascalCase components; preserve that naming pattern for consistency.

- **Integration details agents must respect:**
  - File uploads: DashboardPage uses FormData key `testFile`. Keep that key when interacting with the upload endpoint unless backend changes are coordinated.
  - Dev server: frontend relies on `webpack-dev-server`. Avoid replacing it with CRA or other runners without updating configs and scripts.
  - Dependencies: key libs declared in `frontend/package.json` (React 19, webpack, Babel, Tailwind, recharts, Radix UI). When adding code, prefer these libs unless a clear migration is needed.

- **Safe edit guidelines for AI:**
  - Small, targeted changes only; do not refactor global build configs without CI approval.
  - When introducing env/config values (e.g., API base), add a single source (config file or `.env`) and document usage, then update callers.
  - Preserve named exports and public component APIs in `src/components/*` to avoid breaking imports across pages.

- **Quick verification steps:**
  - Start backend (see `backend/package.json`) and confirm it listens on port 4000.
  - In `frontend/`: `npm install` then `npm start` and open `http://localhost:8080` (or the port `webpack-dev-server` logs). Upload a sample `.xlsx` using the Dashboard page to exercise `/upload-test`.
  - Example curl for upload: `curl -X POST -F "testFile=@/path/to/file.xlsx" http://localhost:4000/upload-test`

- **When merging existing instructions:** preserve any project notes about CI, secrets, or bespoke dev flows. No existing agent docs were found in this scan; add more examples if you have backend start commands or CI scripts.

If anything here is unclear or you want me to expand a section (run the app, add a `build` script, or wire a router example), tell me which part to iterate on.
