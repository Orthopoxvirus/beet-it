# Using the app with an existing beets library

The default compose layout is designed for a fresh install — the app creates libraries in a named docker volume and organises music into it via `beet import`. If you already have a beets library on disk (a directory of organised music and a `library.db`), you can point this app at it, but you'll need to adjust the compose volume mounts and make sure path boundaries line up.

## What "an existing library" means for this app

Each library record in the app's Postgres stores three paths:

| Field | What it points to | Example |
|---|---|---|
| `database_path` | The beets SQLite DB | `/data/databases/music.db` |
| `import_path` | Where new files come in *for this library* | `/data/import/music` |
| `config_path` | The beets YAML config file | `/config/music.yaml` |

These are **container paths**, so they have to match what's mounted inside the backend and celery-worker containers.

`database_path` and the beets config's `directory:` key (the library's root music folder) can point anywhere inside `/data/` as long as the backend can see the path. You choose where.

## Before you start: a safety note

This app's Celery worker can run `beet import`, `beet update`, `beet modify`, and similar commands against the configured library. If you point it at a library you care about, do the usual backup dance first:

```bash
cp -a /path/to/library /path/to/library.backup
```

The app opens the SQLite DB **read-only** from Python for queries (via `sqlite3` URI mode), so reads can't corrupt it. Writes go through the `beet` CLI which respects the same locking beets always has — concurrent writes from this app and a separate `beet` process are still a bad idea though, so shut down other users of the library while this app is running.

## Step 1: expose your existing library to the stack

Add bind mounts to the `backend`, `celery-worker`, and `celery-beat` services in `docker-compose.yaml`. For example, say your existing library lives at `/srv/music/rock` on the host with `rock.db` alongside it:

```yaml
  backend:
    # ...existing config...
    volumes:
      - libraries_data:/data/libraries
      - ./data/import:/data/import
      - ./data/upload:/data/upload
      - databases_data:/data/databases
      - ./config:/config
      # --- Your existing library ---
      - /srv/music/rock:/data/libraries/rock:rw
      - /srv/music/rock.db:/data/databases/rock.db:rw
```

Apply the same three mounts to `celery-worker` and `celery-beat`. (They must be identical — the worker will miss files otherwise.)

Bring the stack back up:

```bash
docker compose up -d --force-recreate backend celery-worker celery-beat
```

Verify the backend sees the paths:

```bash
docker compose exec backend ls /data/libraries/rock /data/databases/rock.db
```

## Step 2: register the library with the app

There are two endpoints that create library records, and only one works for existing libraries:

| Endpoint | What it does | Use for |
|---|---|---|
| `POST /api/v1/libraries/` | *Provisions* a fresh library. Fails with 409 if any of the target paths already exist. Schema: `LibraryCreate` (`name`, optional `slug`, optional `description`). | Brand-new libraries only. |
| `POST /api/v1/libraries/adopt` | *Adopts* an existing library. Does not create files; validates the paths are inside the configured mounts; runs `beet config -p` as a best-effort check. Schema: `LibraryAdopt` (all four container paths required). | Migrations from an existing beets setup. |

For an existing library, call `/adopt`:

```bash
curl -X POST http://localhost:8080/api/v1/libraries/adopt \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Rock",
    "slug": "rock",
    "description": "Existing collection from /srv/music/rock",
    "database_path": "/data/databases/rock.db",
    "library_path": "/data/libraries/rock",
    "import_path": "/data/import/rock",
    "config_path": "/config/rock.yaml"
  }'
```

All four paths are **container paths** (what the backend sees), not host paths — they must match the mount destinations you set up in step 1.

The slug becomes part of URLs like `/libraries/rock/albums` and `/import/rock/prepare`, so keep it short and lowercase.

### Path boundary enforcement

The adopt endpoint rejects paths that fall outside `/data/libraries`, `/data/databases`, `/config`, or `/data/import` (the container mount points). If you need to adopt a library under a different path, extend the mounts in your `docker-compose.override.yaml` and the `LIBRARIES_PATH` / `DATABASES_PATH` / `CONFIG_PATH` / `IMPORT_PATH` env vars — don't try to route around the check.

## Step 3: write a matching beets config

Create `./config/rock.yaml` on the host (it bind-mounts to `/config/rock.yaml` inside the container):

```yaml
# IMPORTANT: these paths are the container paths.
directory: /data/libraries/rock
library: /data/databases/rock.db

plugins:
  - musicbrainz
  - fetchart
  - embedart
  - lastgenre

musicbrainz:
  search_limit: 10          # underscore — not "searchlimit"

import:
  write: yes
  copy: no
  move: yes
  resume: ask
```

The config editor in the UI will read and write this file too, so you don't have to YAML by hand.

## Step 4: point the app at the existing DB safely

Open **Libraries → Rock → Settings → General**. You should see:

- Library directory: `/data/libraries/rock`  ✓ *directory exists*
- Database file: `/data/databases/rock.db`  ✓ *database exists*

The green ticks come from the `/libraries/{id}/config/path-status` endpoint. If either one shows a warning, double-check your volume mounts from step 1 — the container can't see the path.

**Do not click the "Initialize" button** unless both paths are missing. Initialize calls `beet config -p` which creates an empty beets DB; running it against a populated directory with a missing DB file is fine (it just creates the DB), but running it against a live library with changes you care about is overkill. In any case, the Initialize flow checks path existence first and reuses the existing DB if present (see `backend/app/services/library_provisioning.py::initialize_library_resources`).

## Step 5: verify it worked

```bash
# App should list albums from the existing DB
curl http://localhost:8080/api/v1/libraries/rock/albums | head -c 500
```

Or in the UI: **Libraries → Rock → Albums**. You should see your album grid populated from the existing beets DB within a few seconds.

## What you can and can't do with an existing library

| Action | Supported? | Notes |
|---|---|---|
| Browse albums, artists, tracks | ✅ | Reads the beets SQLite DB directly. |
| Play track previews | ✅ | Streams the file from `directory:`. |
| Update cover art | ✅ | Writes to the file + the beets DB. |
| Batch edit tags on imported tracks | ✅ | Pick a folder (or the whole library) from the tree on the batch-edit page; rules apply across every album below that folder. Writes tags to the file, then runs `beet update -a '<album>'` per affected album to resync the DB. |
| Import new music | ✅ | Drop files under `./data/import/rock/` and use the Import page. |
| Full re-scan a directory you added manually | ⚠️ | Currently no UI button for a `beet import -A` (automatic re-tag). Easier: `docker compose exec backend python -m beets -c /config/rock.yaml import -A /data/libraries/rock/NewFolder`. |
| Rename directory / change `directory:` key | ⚠️ | Requires the usual beets `beet move` dance; the app doesn't automate it. |

## Multiple libraries

Repeat steps 1–4 per library. They're fully isolated — each has its own SQLite DB, config, and import folder. The left sidebar's library selector switches between them.

## Don't touch volumes

If you already have other beets containers running on the host (e.g. a separate `beets-music` container your family uses), leave their volumes alone — don't share the SQLite DB between this app and a separate `beet` daemon. If you *must* share, make sure only one is writing at a time (stop the daemon while this app is in use), and pin both to the same beets version to avoid schema drift.
