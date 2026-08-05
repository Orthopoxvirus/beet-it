# Architecture

This document is the ground-truth description of how the pieces fit together. If something here disagrees with the code, the code wins — please fix the doc.

## 10,000-foot view

```
┌──────────────┐  HTTP  ┌──────────────┐  SQL   ┌────────────┐
│   frontend   │◄──────►│   backend    │◄──────►│ postgres   │
│ React + Vite │        │  FastAPI     │        │ (app data) │
│  (nginx)     │        └───┬──────┬───┘        └────────────┘
└──────────────┘            │      │
                     AMQP   │      │  SQLite  ┌────────────┐
                     via    │      └─────────►│ beets DB   │
                     Redis  │                 │(per libr.) │
                            ▼                 └────────────┘
                  ┌──────────────────┐
                  │  celery-worker   │  ← long-running beets ops
                  │  celery-beat     │  ← periodic scheduler
                  └──────┬───────────┘
                         │ pub/sub
                         ▼
                  ┌──────────────┐
                  │    redis     │  ← cache, task queue, SSE events
                  └──────────────┘
```

### Service responsibilities

| Service | Container name | Role |
|---|---|---|
| `frontend` | `beet-it-dev-frontend` | Static React build served by nginx on port 80. All API traffic goes to `/api/...` which nginx proxies to the backend. |
| `backend` | `beet-it-dev-backend` | FastAPI app. Synchronous request/response, plus SSE endpoints for progress streams. |
| `celery-worker` | `beet-it-dev-celery-worker` | Runs the actual heavy lifting — imports, scans, beets autotag, batch `beet update`. |
| `celery-beat` | `beet-it-dev-celery-beat` | Periodic scheduler (import-folder watcher health, etc.). Runs one instance. |
| `postgres` | `beet-it-dev-postgres` | Application data: libraries, task events, user settings. **Not** the beets library DB. |
| `redis` | `beet-it-dev-redis` | Celery broker & result backend, plus app-level cache, SSE pub/sub, activity index. |

There are two databases in play and they are not the same thing:

- **Postgres** stores application metadata — list of libraries, task event log, user settings, import scans.
- **SQLite (one per library)** *is* the beets database, living at `{library.database_path}` inside the stack (typically `/data/databases/{slug}.db`). The app opens this **read-only** from Python using `sqlite3` URI mode for anything that could race with a running `beet` process; writes go through the CLI (`python -m beets -c <cfg> update -a <album>`).

### Network layout

- One docker network: `internal` — private bridge; only the stack's services see each other via container DNS (`postgres`, `redis`, `backend`, etc.).
- **No host ports are published** by the compose stack by default — attach the frontend to your reverse-proxy network or add a `ports:` mapping in an override file.
- The frontend's nginx reverse-proxies `/api/` to `backend:8000` on the `internal` network, so clients only ever need to talk to the frontend.

## API conventions

Pydantic response models use `alias_generator=to_camel` with `populate_by_name=True`. That means:

- Python code sets fields in snake_case (`album_path`, `is_album`, `job_id`).
- JSON over the wire is camelCase (`albumPath`, `isAlbum`, `jobId`).
- TypeScript types in `frontend/src/types/` must match the wire format — camelCase. **Do not add a snake_case→camelCase transform layer in API clients**; the backend already returns camelCase.

Endpoints are namespaced under `/api/v1/` for the core resources. A handful of older endpoints (`/libraries`, `/api/libraries`) predate the v1 prefix; new work should land under `/api/v1/`.

Interactive API docs:
- Swagger: `/docs`
- ReDoc: `/redoc`

## Beets integration (beets 2.6.2)

These are the non-obvious rules — they have cost debugging time in the past.

1. **`plugins.load_plugins()` takes no arguments.** It reads `beets.config["plugins"]` itself. Calling `plugins.load_plugins(["musicbrainz"])` is wrong for 2.6.x.
2. **Set config before loading plugins.** The sequence is:
   ```python
   beets_config.clear()
   beets_config.set_file(config_path)
   beets_config.read()           # read AFTER set_file
   plugins.load_plugins()        # then load plugins
   ```
3. **MusicBrainz search limit key is `search_limit`** (with underscore). `searchlimit` is silently ignored.
4. **`beets.config` is a process-global singleton.** `backend/app/services/beets_autotag_service.py` serialises access with `_beets_config_lock` so concurrent analyses don't fight over it.
5. **Invoke the CLI as `python -m beets ...`, not `beet ...`.** The `beet` launcher isn't guaranteed to be on `$PATH` inside the container image; `python -m beets` always works.
6. **Inline imports are deliberate.** `from beets import autotag, plugins` lives inside `analyze_album()`, not at module top-level, so importing `beets_autotag_service` doesn't pay the beets startup cost on app boot. This affects how you mock them in tests (see `docs/testing.md`).

## Beets plugin dependencies

`beets>=2.6` ships the *code* for most plugins in the `beetsplug` package, but not their Python dependencies. A user who adds a plugin to their YAML and restarts the backend will get `ModuleNotFoundError` on startup unless the extras are installed.

| Plugin | Extra Python package | System package | Status |
|---|---|---|---|
| `musicbrainz` | (none) | (none) | ✅ works out of the box |
| `fetchart` | (none) | (none) | ✅ |
| `embedart` | (none) | (none) | ✅ |
| `embyupdate` | (none) | (none) | ✅ |
| `permissions` | (none) | (none) | ✅ |
| `scrub` | (none) | (none) | ✅ |
| `replaygain` | (none) | `ffmpeg` (in image) | ✅ |
| `convert` | (none) | `ffmpeg` (in image) | ✅ |
| `spotify` | (none) | (none) | ✅ |
| `deezer` | (none) | (none) | ✅ |
| `autobpm` | `librosa` | (none) | ✅ baked into the image |
| `lastgenre` | **`pylast`** | (none) | ❌ not installed by default |
| `discogs` | **`python3-discogs-client`** | (none) | ❌ |
| `chroma` | **`pyacoustid`** | **`chromaprint`** (for the `fpcalc` binary) | ❌ both missing |

To add the common extras, install `requirements-beets-plugins.txt` into the running containers:

```bash
docker compose exec backend pip install -r requirements-beets-plugins.txt
docker compose exec celery-worker pip install -r requirements-beets-plugins.txt
docker compose restart backend celery-worker
```

For `chroma`, also add `chromaprint-tools` (or `chromaprint`) to the backend Dockerfile's `apt-get install` list:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev ffmpeg libffi-dev \
    chromaprint-tools \
    && rm -rf /var/lib/apt/lists/*
```

Why we don't ship these by default: each extra adds ~10-40 MB to the image for users who may not use that plugin, and the plugin ecosystem is large and shifting — better to keep the base image lean and let users opt in.

### autobpm (BPM analysis)

`autobpm` is the exception to the lean-image rule: `librosa` is baked into the image as its own Dockerfile layer. It pulls in ~490 MB of site-packages (llvmlite 173 MB, scipy 107 MB, scikit-learn 47 MB, numpy 41 MB), growing the image from ~1.5 GB to ~2 GB — accepted deliberately so BPM analysis works out of the box, with no runtime-install mechanism.

Enable it per library in `<slug>.yaml`:

```yaml
plugins: ... autobpm

autobpm:
    auto: yes        # analyse new imports automatically
    overwrite: no    # never clobber existing bpm tags (keep this)
```

Notes:

- New imports get `bpm` computed automatically (`auto: yes`); existing tags are left alone (`overwrite: no`).
- Backfill for existing tracks runs from the library **Maintenance** page ("Analyze missing BPM") — chunked Celery task, progress in the activity stream, cancellable.
- librosa's import is expensive (seconds); the beets CLI subprocess pays that cost per invocation, the backend itself never imports it.
- **Octave errors** are inherent to beat detection: 150 BPM tracks are regularly detected as 75 (and vice versa). The BPM-range download in the Download Center offers an "include half/double tempo" toggle for exactly this reason.

## Secrets in library configs

The config editor writes plugin credentials (Discogs user tokens, Emby API keys, Spotify client IDs/secrets, etc.) straight to `/config/<slug>.yaml` in plaintext. That file is bind-mounted to the host `./config/` directory, so tokens end up on disk wherever your host stores them — the repo's `.gitignore` now excludes `config/*` except for `example.yaml` to prevent accidental commits, but that's the only guard.

**Known limitations** (no mitigation shipped yet):

- No secret-store integration (HashiCorp Vault, Docker secrets, AWS Secrets Manager).
- No environment-variable interpolation in YAML (`${DISCOGS_TOKEN}` is written verbatim, not expanded).
- No redaction in the API response — the `GET /libraries/{slug}/config` endpoint returns the full YAML, token values included. A client that logs the response body will leak them.

**What you can do today**:

- Keep your `./config/` directory out of public repos and backups that aren't separately encrypted.
- Prefer plugins whose auth can be scoped to a read-only or library-specific token (Discogs user tokens, Emby read-only API keys).
- If you're running on a shared host, consider moving `./config/` to a per-user encrypted volume and mounting it in via `docker-compose.override.yaml`.

**On the roadmap** (not implemented):

- `${VAR}` interpolation at config read/write time, with the env vars sourced from `.env`.
- Field-level redaction in `GET /libraries/{slug}/config` so tokens can't leak through the API even if the underlying file has them.

## Data flow: an album analyse

```
1. User clicks "Analyze" in BeetsImportPanel
   frontend/src/components/beets-import/BeetsImportPanel.tsx
        │
        │  POST /api/v1/libraries/{slug}/analyze  { albumPath, force }
        ▼
2. backend/app/api/routes/beets_autotag.py
        │  Check Redis cache: beets:album:{library_id}:{md5(album_path)}
        │  Hit  → return synthetic completed job immediately.
        │  Miss → enqueue a Celery task and return job id.
        ▼
3. celery-worker picks up the task
   backend/app/tasks/beets_tasks.py
        │  BeetsAutotagService.analyze_album(...)
        │  - walks the folder, reads tags via mutagen (single pass per file)
        │  - runs beets autotag.tag_album() (queries MusicBrainz)
        │  - publishes progress events on redis pub/sub
        ▼
4. Frontend polls GET /analyze/{job_id}/status (or SSE) until done
        │  Frontend caches the result in its TanStack query cache
        │  AND backend caches under beets:album:{library_id}:{hash}  (7-day TTL)
        ▼
5. Re-selecting that album later hits both caches — no MusicBrainz round-trip.
```

Force-reanalyse (`{force: true}`) bypasses the backend cache.

## Data flow: a batch tag edit

This one is harder to reason about because the tags live in two places at once — the audio file's ID3/Vorbis tags **and** the beets SQLite DB's mirror — and those must stay in sync.

0. User picks a folder (or the whole library) in `LibraryFolderTree`. The tree is built by `GET /api/v1/libraries/{slug}/library-tree` from the `items.path` column of the beets SQLite DB, so the folder hierarchy reflects exactly what beets wrote to disk. Each node carries the union of `albumIds` at or below it.
1. Frontend loads tracks: `GET /api/v1/libraries/{slug}/library-items?album_id=1&album_id=2&...` (repeated for every album id in the selected folder).
2. User configures rules (fixed/regex/sequence) in `BatchTagEditorForm`.
3. Rules are POSTed to `/library-items/preview` (no writes, just a diff).
4. On Apply, frontend opens an SSE stream to `/library-items/batch-update`:
   - Backend captures the **original album tag** per track before touching anything (so the `beet update -a '<original>'` command can still match the album in the beets DB even if the user renames the album in the same edit).
   - Writes tag changes to the audio files using `app.services.tag_writer`.
   - Emits `item_completed` events per track.
   - On `batch_completed`, hands off a `beets_update_albums` Celery task with the list of unique original album tags.
5. `beets_update_albums` runs `python -m beets -c <cfg> update -a '<album>'` per affected album, which re-reads the on-disk tags and updates the beets DB.
6. Progress of step 5 is available at `GET /batch-update-status/{job_id}`.

See `backend/app/api/routes/library_items.py` and `backend/app/tasks/beets_tasks.py:beets_update_albums` for the code.

## Caches

| Key pattern | Where set | Where invalidated | TTL | Purpose |
|---|---|---|---|---|
| `import:tree:{library_id}` | `api/libraries.py:get_import_tree` | `tasks/scan_tasks.py` after each scan | 5 min | Avoid the ~19s filesystem walk on every page load; cache-hit gets the page to <200ms. |
| `beets:album:{library_id}:{md5(album_path)}` | `tasks/beets_tasks.py` on analyze success | `force=true` re-analyse, library deletion | 7 days | Avoid re-querying MusicBrainz for an album that's already been analysed. |
| `beets:cache_status:{library_id}` | `api/routes/beets_autotag.py:get_cache_status` | Invalidated whenever an analyze or cache-clear happens | 5 min | Quick bulk check of which albums have cached analysis results. |

Frontend also uses TanStack Query's in-memory cache — that's orthogonal.

## Filesystem layout inside containers

| Host path | Container path | Purpose |
|---|---|---|
| `./config/` | `/config/` | Per-library `*.yaml` beets config files. Bind-mounted so you can edit them from the host. |
| `./data/import/` | `/data/import/` | Where new music is dropped for import. Bind-mounted. |
| `./data/upload/` | `/data/upload/` | Where files uploaded through the web UI land. Bind-mounted. |
| docker volume `libraries_data` | `/data/libraries/` | Where beets **moves** your music after import. Not bind-mounted by default — see `docs/existing-libraries.md` if you want to point this at an existing library on disk. |
| docker volume `databases_data` | `/data/databases/` | SQLite beets DBs. Not bind-mounted by default. |
| docker volume `postgres_data` | `/var/lib/postgresql/data` | Postgres data directory. |

**Heads-up:** the repo root is a FUSE mount on some dev environments. Files you create inside the backend container at `/config/foo.yaml` may take a moment (or may not ever) appear at `./config/foo.yaml` on the host. If you need to read the authoritative state, `docker exec` into the container.

## Reload semantics

The backend and frontend do **not** have hot reload:

- Backend is started with `uvicorn main:app` (no `--reload`); source is **copied** into the image at build time.
- Frontend is a static Vite build baked into the nginx image.
- Celery worker/beat re-use the backend image.

So changes to Python or TypeScript require:

```
docker compose build backend celery-worker celery-beat frontend
docker compose up -d --force-recreate backend celery-worker celery-beat frontend
```

See `docs/development.md` for the full dev loop.
