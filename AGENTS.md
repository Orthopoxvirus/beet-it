# AGENTS.md

Conventions and gotchas for AI agents (and humans) working on this repo.
Read this before opening a PR — it'll save a CI cycle or two.

## What this is

Beets Web Manager — FastAPI + Celery backend, React + Vite frontend,
Postgres + Redis. Multi-library beets UI. Full architecture in
[`docs/architecture.md`](docs/architecture.md); start there for code-level
questions.

## Test commands

The CI workflow runs all of these on PR. Match these locally before pushing.

**Backend** (run from `backend/`):

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

Tests use SQLite for unit + integration (no Postgres needed). Mocks for
Redis. Real Postgres is only required for end-to-end manual testing.

**Frontend** (run from `frontend/`):

```bash
npm ci
npm run type-check     # tsc --noEmit
npm run test:run       # vitest run
```

Skip `npm run lint` — see Known issues below.

## CI / release pipeline

`.gitea/workflows/ci.yml` runs CI on every PR (backend pytest + frontend
type-check + vitest, aggregated under a `test` job).

`.gitea/workflows/release.yml` runs on every merge to `master`:
1. Computes next CalVer tag (`YYYY.MM.DD` or `YYYY.MM.DD-N`).
2. Builds + pushes the backend and frontend images to the configured
   container registry (`:TAG` and `:latest`).
3. Creates and pushes the git tag, which triggers the deployment webhook.

Deployment specifics (hosts, registry, paths) live outside this repo.

## Branch + merge

- `master` is protected. PRs only, no direct push.
- Squash-merge only. The PR title becomes the master commit message —
  follow conventional commits (`fix:`, `feat:`, `ci:`, `chore:`, etc.).
- Branch from master with `agent/<topic>` for agent work.

## Known issues to expect

8 tests are intentionally `.skip`'d. Don't try to "fix" them by removing
the skip without addressing the underlying mock infra:

- **AudioPlayer ~6 tests** — jsdom has no `AudioContext`; the component
  takes the "Web Audio API not available" fallback path. Need a Web Audio
  API mock in `frontend/src/__tests__/setup.ts`. Tracked: issue #4.
- **useLibraryBatchTagUpdate ~4 tests** — SSE/streaming-callback mock shape
  doesn't drive the hook's `onStarted/onCompleted/onError` callbacks.
  Tracked: issue #5.

Frontend `npm run lint` works locally but the `eslint` config has been
fragile in the past. CI doesn't run lint; type-check is the gate.

## Deployment quirks

The production stack's `docker-compose.yaml` uses **bind mounts** for
databases:

```yaml
- ./databases:/data/databases
```

This is intentional — was a named volume originally, but a 2026-05-08
bug left containers mounted to a phantom path with empty data. Bind
mount to the real host path is what works. Don't change it back to a
named volume without good reason.

Other paths to know:

| Container path | Host path | What it is |
|---|---|---|
| `/data/databases` | `./databases` (bind) | beets SQLite DBs per library |
| `/data/libraries` | named volume | organized music output |
| `/data/import` | `./data/import` (bind) | drop-zone for new imports |
| `/data/upload` | `./data/upload` (bind) | web-uploaded files |
| `/config` | `./config` (bind) | per-library beets `*.yaml` |

Library content (the actual music files) is bind-mounted read-only per
library. Don't write into those from the app — the import pipeline
copies from `/data/import` outward.

## When working on this repo

- Read [`docs/architecture.md`](docs/architecture.md) first for the
  service layout and the camelCase wire convention.
- Read [`docs/testing.md`](docs/testing.md) for test-infra quirks that
  cost real time (ResizeObserver mocks, JSON-vs-JSONB, etc.).
- After edits to backend code, the production image rebuilds on next
  merge to master automatically — no manual rebuild needed.
- Don't merge a PR with red CI even if it "looks unrelated". Two skipped
  test classes are already the bar; new failures need fixing or
  explicit `.skip` with a tracked issue.
