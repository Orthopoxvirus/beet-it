# Development guide

This is the workflow that actually works against the codebase. Use it instead of generic Python/React instructions — the containerised-production-only setup has a few surprises.

## Prerequisites

- Docker Engine 20.10+ and Docker Compose v2 (`docker compose` subcommand).
- Git.

You do not need a local Python or Node install to run the app or its tests — everything runs in containers. You'll want them if you're iterating quickly on one service at a time (see [Faster inner loop](#faster-inner-loop) below).

## First-run setup

```bash
# 1. Copy env templates. The root .env is what compose reads.
cp .env.example .env
cp backend/.env.example backend/.env          # optional, the compose file already supplies defaults

# 2. Set a real SECRET_KEY and POSTGRES_PASSWORD in .env.

# 3. Make sure the bind-mounted host dirs exist.
mkdir -p data/import data/upload config

# 4. Build and start the stack.
docker compose build
docker compose up -d

# 5. Apply Alembic migrations to create the app schema.
docker compose exec backend alembic upgrade head
```

The compose file publishes no host ports. To reach the UI locally, copy `docker-compose.override.yaml.example` to `docker-compose.override.yaml` (it publishes the frontend on `http://localhost:8080/`) and run `docker compose up -d --force-recreate frontend`.

## The core rule: no hot reload

Neither the backend nor the frontend bind-mount source — both are copied in at image build time. Any change to Python or TypeScript requires a rebuild:

```bash
# Backend (and the two celery services that share its image)
docker compose build backend celery-worker celery-beat
docker compose up -d --force-recreate backend celery-worker celery-beat

# Frontend
docker compose build frontend
docker compose up -d --force-recreate frontend
```

If you skip `--force-recreate`, compose will keep the old container running on the new image — a common "why aren't my changes live?" trap.

### Inspecting running code

Because source is copied in, `ls backend/app/` on the host tells you what the *next* image will contain, **not** what's currently running. To inspect what's actually live:

```bash
docker compose exec backend ls /app/app/
docker compose exec backend cat /app/app/services/beets_autotag_service.py
```

### Faster inner loop

For quick iteration on a single service, skip the rebuild and copy files straight into the container after editing:

```bash
# Backend: copy one file and restart the process
docker cp backend/app/services/beets_autotag_service.py \
          beet-it-dev-backend:/app/app/services/beets_autotag_service.py
docker compose restart backend    # uvicorn doesn't auto-reload; restart the process

# Or for a test-only change, no restart needed — pytest reads files fresh each run.
docker cp backend/tests/unit/test_foo.py beet-it-dev-backend:/app/tests/unit/test_foo.py
docker compose exec backend pytest tests/unit/test_foo.py
```

When you've converged, do a proper rebuild so the image reflects reality.

Frontend iteration is fastest by running Vite directly against your host:

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to http://localhost:8000
```

That requires the backend to be reachable on `localhost:8000` — either add `ports: ["8000:8000"]` to the `backend` service, or run the backend locally (see below).

## Running services locally without Docker

Rarely worth it, but the option exists:

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# In another shell, run the Celery worker
celery -A app.celery_app worker --loglevel=info
```

You'll need local Postgres + Redis, or you can point the locally-run backend at the containerised ones by publishing their ports.

## Conventions

### Commits

Conventional-commit prefixes match the existing history. Read `git log --oneline | head -30` for the established style. The most common prefixes in this repo are `feat:`, `fix:`, `docs:`, `test:`.

### Python

- Black (line length 100), ruff for lint, mypy for types — all configured in `backend/pyproject.toml`.
- Async functions must not call blocking I/O — use `await asyncio.to_thread(...)` if unavoidable. A single blocking call in an async endpoint stalls the whole event loop; see `docs/testing.md` for the SSE blocking bug we've already tripped on once.
- Pydantic v2 `ConfigDict`, not the deprecated nested `class Config`.

### TypeScript / React

- Strict TypeScript (`tsconfig.json` `"strict": true`).
- Functional components with hooks; avoid class components.
- TanStack Query for all server state. Don't roll your own `useEffect` fetching.
- All API response types are **camelCase** — match the wire shape, never paper over with a snake_case→camelCase transform layer in API clients.

### Component tests (vitest)

- Global ResizeObserver / scrollIntoView / pointer-capture mocks live in `frontend/src/__tests__/setup.ts`. ResizeObserver is a real class (not a `vi.fn()`) so `vi.restoreAllMocks()` in afterEach doesn't strip it.
- Prefer `getByLabelText`, `getByRole`, or `getByText` with a `selector` (e.g. `{ selector: 'label' }`) over broad `getByText` when the same text appears in multiple places (e.g. tag field labels AND tracks-table column headers both say "Title").

## Running tests

See `docs/testing.md` for the full matrix. Short version:

```bash
# Frontend (host, from frontend/ directory)
cd frontend && npm install && npm run test:run

# Backend (inside the container, one-time dev deps install)
docker compose exec backend pip install -r requirements-dev.txt
docker compose exec backend pytest
```

## Common gotchas

- **"My change isn't showing up."** You built the image but didn't `--force-recreate`. See [The core rule](#the-core-rule-no-hot-reload).
- **"The config file I edited inside the container didn't appear on the host."** FUSE-mount lag. `docker exec` to confirm the authoritative state.
- **"Celery beat is unhealthy."** The healthcheck uses `pgrep -f 'celery.*beat'` which is flaky in minimal images; the scheduler itself is running. Not a blocker for dev.
- **"Tests pass locally but fail in CI."** Check: did you install `requirements-dev.txt`? Did you run from the `frontend/` dir (vitest.config is there, not at repo root)?
- **"The backend returns 500 with a PyYAML error."** Your library's `*.yaml` config in `./config/` is probably invalid. Edit it (via the web UI or your editor) and restart the backend.
