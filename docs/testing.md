# Testing

As of the last full run: **909 frontend tests** and **843 backend tests** pass. This doc covers how to run them, how to add new ones, and the few quirks that have cost real debugging time.

## Backend (pytest)

### Installing dev deps

The production image doesn't ship pytest, ruff, or mypy — they're only needed for dev. Install them into the running backend container:

```bash
docker compose exec backend pip install -r requirements-dev.txt
```

That's idempotent; you can re-run it any time. For a permanent local venv (rare — see `docs/development.md`):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

### Running

```bash
# All tests
docker compose exec -w /app backend pytest

# One file
docker compose exec -w /app backend pytest tests/unit/test_beets_library_service.py

# One test
docker compose exec -w /app backend pytest tests/integration/test_library_items_api.py::TestGetLibraryItemsEndpoint::test_get_library_items_success

# With coverage
docker compose exec -w /app backend pytest --cov=app --cov-report=term-missing
```

`-w /app` matters: `pyproject.toml` sets the test root via `configfile: pyproject.toml`, and tests import `from main import app` which only resolves when `sys.path` contains `/app`.

### Test DB strategy

Integration tests that touch the database use **SQLite in-memory**, not the stack's Postgres. This is why:

- `user_settings.preferences` and `task_event.metadata` use `JSON().with_variant(JSONB, "postgresql")` — PostgreSQL gets native JSONB, SQLite gets plain JSON, so `Base.metadata.create_all()` works against either dialect. If you add a new JSONB column somewhere, do the same dance or SQLite tests will fail with `Compiler can't render element of type JSONB`.
- Beets-side tests use temporary SQLite DBs seeded with the relevant `albums`/`items` rows, not a real `beet import`. See `tests/unit/test_beets_library_service.py` for the pattern.

### Mocking beets submodules

`app.services.beets_autotag_service.analyze_album` imports `beets.autotag`, `beets.plugins`, and `beets.config` *inside the function*, deliberately, to keep startup fast. That means `@patch('app.services.beets_autotag_service.autotag')` will fail — the name doesn't exist at module scope. Instead:

```python
import beets
from beets import autotag as _, plugins as _p  # force-load so patch.object finds them

with patch.object(beets, 'autotag', mock_autotag), \
     patch.object(beets, 'plugins', mock_plugins), \
     patch.object(beets, 'config', mock_config):
    ...
```

See `tests/unit/test_beets_autotag_service.py::test_analyze_album_loads_plugins_with_config` for the worked example.

### Async + blocking I/O gotcha

Never call blocking I/O (e.g. `pubsub.get_message(timeout=1.0)`, `time.sleep(...)`, blocking HTTP) from inside an async function — one blocking call stalls uvicorn's single event loop for every other request. We already shipped this bug once: three open SSE connections blocked the loop ~91% of the time, and `/health` started taking 7-41s.

Rule: use `pubsub.get_message()` (non-blocking, returns `None` immediately) and rely on `await asyncio.sleep(0.1)` for pacing. If a blocking call is truly unavoidable, wrap it with `await asyncio.to_thread(...)`.

### Test-only quirks to know about

- `tests/integration/test_scan_tasks.py::test_execute_scan_success` needs `mock_redis_manager.get_activity_progress.return_value = None` — otherwise the default `Mock` makes `datetime - started_at` blow up inside `task_events.record_progress`.
- `tests/integration/test_library_items_api.py` tests use the `page_size` query alias. The API accepts both `per_page` (original) and `page_size` (newer alias); the response body carries both keys so old and new consumers both work.
- Album-level status (`AlbumUpdateStatus`: `pending|syncing|success|failed`) is a **different enum** from job-level status (`BatchUpdateStatusResponse.status`: `pending|running|completed|failed|partial`). Don't mix them in fixtures.

## Frontend (vitest)

### Installing

Only needed once per clone:

```bash
cd frontend
npm install
```

(The repo ships a `package-lock.json`; do **not** use pnpm or yarn — they'd generate conflicting lockfiles.)

### Running

Vitest config lives at `frontend/vitest.config.ts`, so **run commands from `frontend/`**:

```bash
cd frontend

# All tests, headless, single pass
npm run test:run

# Watch mode
npm test

# One file
npx vitest run src/components/library/__tests__/BatchEditTab.integration.test.tsx

# Coverage
npm run test:coverage

# Playwright e2e (browsers must be installed first: npx playwright install)
npm run test:e2e
```

### Test setup (`src/__tests__/setup.ts`)

Two details that cost us debugging time:

1. **ResizeObserver is a real class, not a `vi.fn()`.** If you make it a `vi.fn().mockImplementation(...)`, any test that calls `vi.restoreAllMocks()` in `afterEach` will strip the implementation and subsequent tests fail with `resizeObserver.observe is not a function` inside Radix's scroll-area.
2. **MockEventSource is a full class with `simulateMessage`, `simulateOpen`, `simulateError` helpers** — use it when testing SSE hooks rather than stubbing `fetch`.

### Picking selectors

The tracks table and the tag-field configurator both render the word "Title". A bare `screen.getByText('Title')` will throw `Found multiple elements`. Scope the query:

```ts
// Prefer this
screen.getByText('Title', { selector: 'label' })

// Or
screen.getByLabelText('Title')
```

When a mock returns `null`/`undefined` from a React Query hook and the component doesn't guard for it, you'll see `Cannot destructure property 'data' of 'useFoo(...)' as it is undefined`. Have the test stub the hook with an object whose shape matches a settled query, e.g. `{ data: ..., isLoading: false, error: null, isSuccess: true, isError: false }`.

### Common failure patterns

- **"Cannot find package `@/components/…`"** — you ran vitest from repo root. Run from `frontend/` so the right vitest config is picked up.
- **"Preview: 2 tracks will be modified" shown after Reset** — this was a real bug: the preview hook returned cached data even when `shouldFetch` was false. Fixed in `useTagPreview.ts` and `useLibraryItems.ts` by gating `previewMap`/`hasChanges` on `shouldFetch`. Don't re-introduce.
- **"An update was not wrapped in act(...)"** — usually benign in our test harness; if the assertion still passes, leave it. If it flakes, wrap the trigger in `act()`.

## Integration coverage notes

Two things the automated suite does *not* cover well and a human should eyeball occasionally:

- **Real beets import.** All beets interactions are mocked or exercised against synthetic SQLite DBs. The one true test is an actual `beet import` against a real folder.
- **UI in a browser.** Browser smoke tests aren't part of the automated suite. Expose the frontend locally (see the compose override example) and click through the main flows by hand, or point Playwright at that URL.

## CI

There's no CI pipeline wired up yet. If you add one:

```
# backend
docker build -t beet-backend-test ./backend
docker run --rm beet-backend-test sh -c "pip install -r requirements-dev.txt && pytest"

# frontend
cd frontend && npm ci && npm run type-check && npm run test:run
```
