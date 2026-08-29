# Architecture

## The constraint that drove every decision

A Baja team loses roughly a third of its members every year. Whoever inherits
this in 2028 will not have met whoever set it up. So the question is not "what is
the best stack" but **"what still runs in three years when nobody remembers how
it works."**

That pushes hard toward:

- one language, not two
- one process, not a frontend server plus an API server
- one file to back up
- a fallback UI that needs no build at all, for the day the toolchain rots
- a dependency list short enough to read

## The stack

| Layer | Choice | Why |
|---|---|---|
| API | **FastAPI** (Python) | Auto-generates interactive docs at `/docs`, so the API explains itself to the next maintainer. Type hints double as validation. |
| ORM | **SQLAlchemy 2.0** | The declarative models *are* the schema documentation. Swapping SQLite for Postgres is a connection-string change. |
| Validation | **Pydantic v2** | Bad data is rejected at the boundary with a readable error, not 200 rows into a CSV export. |
| Database | **SQLite** now, **Postgres** later | Zero install, zero admin. Backup is copying one file. Handles a team of 30 without noticing. |
| Files | Local disk, content-addressed | No S3 account, no credentials to leak, no bill. Abstracted so R2/S3 is a 3-function swap. |
| Frontend | **React + Vite**, with a no-build fallback | Covered below — there are two, on purpose. |
| Hosting | One process on one box | `uvicorn app.main:app`. Serves the API *and* the UI on one port. |

### Two frontends, and why both are still here

The original build used **vanilla ES modules with no build step at all**, because
this machine had no Node, no npm and no Docker — only Python. For a team that
loses a third of its members a year, "clone it and hit refresh" is a real
advantage over a toolchain that can rot.

React + Vite was added later, deliberately, and the old UI was kept rather than
deleted:

| | `frontend/` (React 19 + TS + Vite) | `static/` (no build) |
|---|---|---|
| Served at | `/` once built | `/static/` always |
| Needs Node | yes | no |
| Tree guide lines + connection gutter | yes | no |

They have genuinely diverged — the connection gutter exists only in the React
app. `static/` is a fallback for a machine with no Node, not a maintained twin.
If nobody is using it in a year, delete it; nothing in `app/` depends on either.

The cost of the React side is worth naming: ~28 npm packages, a lockfile, and a
build that must run before deploy. That is the trade for components and types.
See [FRONTEND.md](FRONTEND.md).

## Layout

```
app/
  config.py       Settings, all with working defaults
  database.py     Engine + session; SQLite pragmas (foreign_keys ON matters)
  models.py       The schema. Start reading here.
  schemas.py      Pydantic request/response types = the validation boundary
  tree.py         ALL hierarchy mechanics. Nothing else writes Node.path.
  storage.py      Content-addressed blob store
  seed.py         Baja subsystem template + default tags + demo data
  routers/        projects, nodes, tags, attachments, members
frontend/         React + TypeScript + Vite (the primary UI)
  src/lib/filter.ts       The filtering algorithm — read this one
  src/lib/connections.ts  Non-hierarchical links drawn in the right gutter
  src/lib/tree.ts         Indexes + the DOS-style guide glyphs
  src/components/         TreeView, DetailPanel, FilterBar, ConnectionPicker
static/           The original no-build UI. Edit and refresh; no toolchain.
  js/filter.js    The same filtering algorithm, vanilla
tests/            26 tests over the parts that are easy to break
scripts/          backup.py (WAL-safe), gc_blobs.py (reclaim orphan files)
deploy/           serve.py + Task Scheduler XML for unattended hosting
docs/             SCHEMA, FRONTEND
```

**The one rule:** nothing outside `app/tree.py` may write `Node.path`, `Node.depth`
or `Node.position`. Route every structural change through those functions and the
denormalized path cache stays consistent.

## Design decisions worth knowing

### The whole tree ships in one response

`GET /api/projects/{id}/tree` returns every node flat, plus resolved tags and
attachment counts. A Baja BOM is a few thousand rows — well under a megabyte.

Consequences: filtering, searching and expand/collapse are instant and need zero
round trips. There is no "loading…" spinner when you open a branch, and no lazy
loading logic to get wrong. If a tree ever gets big enough that this hurts, the
server-side `/filter` endpoint already exists as the escape hatch.

### Filtering shows ancestors, always

A tree filter is not a list filter. If the only match is a bolt five levels down,
returning just that bolt gives the client no way to render it — the row has no
visible parent. So both the client and `/filter` return **matched** nodes plus the
**ancestor chain** needed to reach them, drawn dimmed as scaffolding.

Two modes, because they answer different questions:
- **Isolate** — prune to matches + scaffolding. "What do I still owe?"
- **Highlight** — keep the whole tree, dim the misses. "Where does the electrical
  work actually live in this car?"

### Money is integers

`cost_cents`, never floats. A cost report that is off by pennies because of binary
floating point is a cost report nobody trusts.

### Statuses are strings, not database enums

Validated as Pydantic `Literal`s at the API boundary. A team *will* invent a new
status mid-season; this makes that a one-line edit in `schemas.py` instead of a
migration.

## What this deliberately does not have yet

**Authentication.** Everything is open to whoever can reach the port. That is fine
on a laptop or behind a campus VPN, and *not* fine on the public internet.

Cheapest real fix, in order of effort:
1. Put it behind Cloudflare Access or your campus SSO and let that do authn.
2. Add `fastapi-users` or a single shared password + session cookie.
3. Full per-user auth with roles (lead can delete, member can edit).

The `members` table already exists as the assignee list, so step 3 mostly means
adding a password hash column and a dependency that resolves the current user.

**Migrations.** `Base.metadata.create_all()` at startup creates missing tables but
will not alter existing ones. The moment you have a season of real parts in there:

```bash
pip install alembic && alembic init migrations
# point migrations/env.py at app.models.Base.metadata
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```
Then delete the `create_all` line in `app/main.py`.

**Audit history.** You can see a part's current status, not who changed it from
`released` to `needs_rework` last Tuesday. If that matters, add a `node_events`
table written on every PATCH — it is append-only and does not complicate anything
else.

**Concurrent-edit protection.** Two people editing the same part will last-write-
wins. Add an `updated_at` check on PATCH if that bites.

## Deploying

Backups first, because this is the part teams skip. **Do not just copy
`pitbox.db`** — the database runs in WAL mode, so recent writes sit in
`pitbox.db-wal` until SQLite checkpoints. A plain copy taken while the app is
running can produce a file that opens fine and is missing nearly everything.
Use the script, which uses SQLite's online backup API and verifies the result:

```bash
python scripts/backup.py --keep 20
```

Hosting options:
- **Cloudflare Tunnel + Access** on a machine you control — recommended. Solves
  the missing login with SSO, opens no ports, teammates install nothing.
- **Tailscale**, if you would rather not buy a domain. Free, private, but every
  teammate installs a client.
- **A shop PC on the campus LAN.** Zero setup, zero auth — fine on a trusted
  network, but anyone who can reach it can delete a subsystem.
- **Fly.io / Railway / Render** only if no machine can stay on. Needs a
  persistent volume for `pitbox.db` *and* `storage/` — a container filesystem
  resets on redeploy, and that is the most common way teams lose a season.

Once more than a handful of people write concurrently, switch to Postgres:

```bash
PITBOX_DATABASE_URL=postgresql+psycopg://user:pass@host/pitbox
```
Nothing in the application code changes. The materialized-path queries and the
`LIKE` prefix scans work identically.
