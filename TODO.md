# Production-ready reorg TODO

## Step 1 — Baseline & structure
- [x] Create a clean normalized project root layout (backend/ and frontend/)
- [x] Add a single authoritative root README.md for the repo.

## Step 2 — Backend production hygiene
- [x] Update cache persistence path in `app/services/ceipal_service.py` to use an env-configurable directory (safe default outside source tree).
- [x] Add `backend/.env.example` and backend README with run commands.
- [x] Ensure imports and working-directory assumptions are correct after moves.

## Step 3 — Frontend production hygiene
- [x] Standardize API client location/namespace (moved `src/services/*` to `src/lib/api/*` and updated imports).
- [x] Add `frontend/.env.example` documenting `VITE_API_BASE_URL` behavior.
- [x] Verify build output is correct (`npm run build`).

## Step 4 — Deployment docs
- [x] Document a production run mode (reverse proxy approach) and/or backend-served SPA approach.

## Step 5 — Verification
- [x] Run backend compile smoke check: `python -m compileall`.
- [x] Run frontend build: `npm ci && npm run build`.
- [ ] (Optional) Smoke test endpoints via `curl`/browser.