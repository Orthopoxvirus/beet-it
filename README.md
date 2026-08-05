# beet-it

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Images](https://github.com/Orthopoxvirus/beet-it/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/Orthopoxvirus/beet-it/actions/workflows/docker-publish.yml)
[![GHCR](https://img.shields.io/badge/ghcr.io-orthopoxvirus%2Fbeet--it-blue)](https://github.com/Orthopoxvirus/beet-it/pkgs/container/beet-it%2Fbackend)

A web-based UI for managing one or many [beets](https://beets.io/) music libraries. FastAPI + Celery backend, React frontend, Postgres + Redis for state — all containerised with Docker Compose.

## Features

- **Multi-library**: manage several independent beets libraries from one UI.
- **Import workflow**: drag-and-drop upload, folder-tree browser, per-folder analyse & import, MusicBrainz candidate selection, manual-candidate search, multi-part release splitting.
- **Album browsing**: paginated album grid per library, alphabet navigation, album detail page with inline audio playback and cover-art replacement (file / drag-and-drop / URL).
- **Titles view**: library-wide track search with BPM-range filtering, per-track preview playback, and per-title downloads.
- **BPM analysis**: automatic BPM detection on import plus a resumable library-wide backfill with live progress.
- **Batch tag editing**: rule-based edits (fixed / regex / sequence) across tracks already in a library, with automatic `beet update -a` sync back to the beets DB.
- **Maintenance tools**: single-cover guarantee (adopting stray images as album art), in-place WAV→FLAC conversion, duplicate-row cleanup.
- **Beets config editor**: edit `config.yaml` for any library through the UI — path templates with click-to-insert variables, plugin management, path validation with one-click initialisation.
- **Activity monitor**: live progress for imports, scans, analyses, and batch updates; history of completed and failed tasks.
- **Unsaved-changes guard**, **import-folder watchers**, **per-library beets config navigation**, and more.

## Tech stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2, Alembic, Celery, Pydantic v2.
- **Frontend**: React 18, TypeScript (strict), Vite, TanStack Query, shadcn/ui + Tailwind, React Hook Form + Zod.
- **Data**: PostgreSQL 15 for app metadata; one SQLite DB per beets library.
- **Infra**: Docker Compose v2. The production image is nginx serving a Vite build; there is no host-port publishing by default (see [Accessing the UI](#accessing-the-ui) below).

## Prerequisites

- Docker Engine **20.10+** and Docker Compose v2 (the `docker compose` subcommand, not the old `docker-compose`).
- Git.

Local Python / Node installs are **not required** — all services run in containers. See [`docs/development.md`](docs/development.md#faster-inner-loop) if you want to iterate on a service without rebuilding.

## Getting started

### 1. Clone

```bash
git clone https://github.com/Orthopoxvirus/beet-it.git
cd beet-it
```

### 2. Configure env

```bash
cp .env.example .env
# Edit .env and set at minimum:
#   POSTGRES_PASSWORD=<something real>
#   SECRET_KEY=<a long random string>
```

The `STACK_NAME` in `.env` (default `beet-it-dev`) controls container naming and compose project grouping. The defaults are fine for dev; change it if you run multiple instances side by side.

`backend/.env.example` documents backend-only overrides (`BASIC_AUTH_USER`/`BASIC_AUTH_PASSWORD`, `ENABLE_IMPORT_WATCHERS`, etc.); in practice compose reads everything from the root `.env` plus hard-coded defaults in `docker-compose.yaml`, so you rarely need a separate `backend/.env`.

### 3. Create bind-mount directories

```bash
mkdir -p data/import data/upload config
```

That's the minimum. The app also uses two docker-managed volumes (`libraries_data`, `databases_data`) that compose creates automatically. If you want your organised music and beets SQLite DB to live on a specific host path instead, see [`docs/existing-libraries.md`](docs/existing-libraries.md).

### 4. Build and start

```bash
docker compose build
docker compose up -d
```

First build takes a few minutes. Subsequent rebuilds are much faster thanks to layer caching.

Prefer prebuilt images? Every release is published to the GitHub Container Registry — skip the build by pointing compose at them:

```bash
IMAGE_PREFIX=ghcr.io/orthopoxvirus/beet-it IMAGE_TAG=latest docker compose up -d
```

(Or set `IMAGE_PREFIX`/`IMAGE_TAG` in `.env`. Pin `IMAGE_TAG` to a release tag like `v1.0.0` for reproducible deploys.)

### 5. Run database migrations

```bash
docker compose exec backend alembic upgrade head
```

This creates the app's Postgres schema (libraries, task events, user settings). You only need to run this once per fresh database.

### 6. Verify

```bash
docker compose ps          # all 6 services should be "healthy"
docker compose logs -f     # follow logs if anything is off
```

The one known-flaky healthcheck is `beet-it-dev-celery-beat` which reports *unhealthy* despite the scheduler running fine — it's `pgrep`-based and noisy in minimal images. Not a blocker for dev.

## Accessing the UI

**The compose stack publishes no host ports by default** (so it drops cleanly behind any reverse proxy). For a local run, use the override file:

```bash
cp docker-compose.override.yaml.example docker-compose.override.yaml
docker compose up -d --force-recreate frontend
```

The example override publishes the UI on `http://localhost:8080/` out of the box; it also documents optional blocks for direct API access, existing-library mounts, and Postgres access. The override file is gitignored — your customisations stay local.

API docs are exposed under the same origin: `/docs` (Swagger) and `/redoc`.

## Making changes

Neither the backend nor the frontend hot-reload in the compose setup — source is copied into the image at build time. After editing:

```bash
docker compose build backend celery-worker celery-beat     # if backend/ changed
docker compose build frontend                               # if frontend/ changed
docker compose up -d --force-recreate backend celery-worker celery-beat frontend
```

For faster iteration, see [`docs/development.md`](docs/development.md#faster-inner-loop).

## Running tests

```bash
# Backend (inside the container; dev deps aren't in the prod image)
docker compose exec backend pip install -r requirements-dev.txt
docker compose exec backend pytest

# Frontend (on your host)
cd frontend
npm install
npm run test:run
```

Full details in [`docs/testing.md`](docs/testing.md).

## Project layout

```
beet-it/
├── backend/                      # FastAPI app
│   ├── app/
│   │   ├── api/                  # HTTP routes
│   │   ├── models/               # SQLAlchemy models
│   │   ├── schemas/              # Pydantic schemas (wire types = camelCase)
│   │   ├── services/             # Business logic (beets integration, tag writing)
│   │   └── tasks/                # Celery tasks
│   ├── alembic/                  # DB migrations
│   ├── tests/                    # pytest suite (unit + integration)
│   ├── Dockerfile
│   ├── requirements.txt          # runtime deps
│   ├── requirements-dev.txt      # pytest, ruff, mypy, ...
│   ├── pyproject.toml
│   └── main.py                   # uvicorn entrypoint
├── frontend/                     # React + Vite app
│   ├── src/
│   │   ├── components/           # shadcn/ui-based components
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── api/                  # TanStack Query clients per resource
│   │   ├── types/                # TS types mirroring backend schemas (camelCase)
│   │   └── __tests__/setup.ts    # Vitest global setup (ResizeObserver, EventSource mocks)
│   ├── e2e/                      # Playwright specs
│   ├── Dockerfile                # Multi-stage: Vite build → nginx
│   └── package.json              # Node deps (uses npm, not pnpm)
├── config/                       # bind-mount: per-library beets *.yaml configs
├── data/
│   ├── import/                   # bind-mount: source files to import
│   └── upload/                   # bind-mount: web-uploaded files
├── docs/                         # architecture & dev docs — start here
│   ├── README.md
│   ├── architecture.md
│   ├── development.md
│   ├── testing.md
│   └── existing-libraries.md
├── docker-compose.yaml
└── README.md                     # this file
```

Read [`docs/architecture.md`](docs/architecture.md) for how the services talk to each other, the two-database split (Postgres for app metadata, SQLite per beets library), the API camelCase convention, and the beets-version-specific quirks you need to know about.

## Using it with an existing beets library

Yes, you can. The short version: add bind mounts in `docker-compose.yaml` for your existing music directory and `library.db`, create a library record with the matching container paths, and drop a beets YAML config under `./config/`. Full walkthrough in [`docs/existing-libraries.md`](docs/existing-libraries.md).

## Contributing

Open an issue or a pull request. Follow conventional-commit prefixes (`feat:`, `fix:`, `docs:`, …) for PR titles — squash-merge turns them into the master commit message.

Commit-message style: conventional commits. Skim `git log --oneline | head -30` for the local flavour.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| "My change isn't showing up." | Rebuilt the image but didn't `--force-recreate`. See [Making changes](#making-changes). |
| Backend 500s with a PyYAML error. | A `./config/*.yaml` is invalid. Fix via the UI or editor, restart backend. |
| `resizeObserver.observe is not a function` in vitest. | You tripped a `vi.restoreAllMocks()` and setup.ts's ResizeObserver lost its implementation. It's now a real class — don't change it back to a `vi.fn()`. |
| `Cannot destructure property 'data' of 'useFoo(...)'`. | A mocked React Query hook returned `undefined`. Stub with `{ data: ..., isLoading: false, error: null, isSuccess: true, isError: false }`. |
| `Compiler can't render element of type JSONB`. | You added a JSONB column but tests use SQLite. Use `JSON().with_variant(JSONB, "postgresql")`. |
| Pytest can't find `from main import app`. | Run pytest with `-w /app` so `sys.path` picks up `main.py`. |

More in [`docs/testing.md`](docs/testing.md) and [`docs/development.md`](docs/development.md).

## Acknowledgments

- [beets](https://beets.io/) — the music library manager this project is a UI for.
- [FastAPI](https://fastapi.tiangolo.com/), [React](https://react.dev/), [shadcn/ui](https://ui.shadcn.com/).

## Securing your instance

beet-it ships **without authentication by default** — it's built for trusted
home-LAN use. Decide how you expose it *before* anyone but you can reach it:

1. **Don't expose it at all** (simplest, recommended). The compose stack
   publishes no host ports by default; keep it that way and reach the UI over
   your LAN or a VPN such as WireGuard or Tailscale.
2. **Reverse proxy with SSO / forward auth** (recommended when it must be
   reachable from outside). Put the `frontend` service behind Traefik, Caddy
   or nginx with HTTPS, and gate it with your identity provider — e.g.
   [Authentik](https://goauthentik.io/) or [Authelia](https://www.authelia.com/)
   via forward auth, or oauth2-proxy. UI and API are same-origin (the
   frontend's nginx proxies `/api/` to the backend), so a single auth gate in
   front of the frontend covers everything.
3. **Built-in HTTP Basic Auth.** Set `BASIC_AUTH_USER` + `BASIC_AUTH_PASSWORD`
   in `.env`. This is enforced by the backend, so every API route — all data
   and actions — requires credentials; only the static UI shell itself loads
   without them. Fine as a quick gate or second layer, less polished than a
   proxy login.

Options 2 and 3 combine well: SSO at the proxy, Basic Auth as a backstop.
Never expose the stack over plain HTTP to the internet.

Other security notes:

- Cover-art downloads validate URLs against private/loopback address ranges
  (including every redirect hop) and enforce image magic bytes + a 10 MB cap.

## License

[MIT](LICENSE)
