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
| Auth | **Sessions + scrypt**, stdlib only | No new dependency. Sessions live in the database so they can actually be revoked. |
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

### Login is deliberately boring

Passwords are hashed with `hashlib.scrypt` — a memory-hard KDF that ships with
Python. No bcrypt, no passlib, no argon2 package: that is three more things to
keep alive for a team that hands this over every year, and passlib in particular
has broken against new bcrypt releases before. The cost parameters are stored
with each hash, so they can be raised later without invalidating anyone.

Sessions are rows in the database, not signed stateless cookies. The lookup
costs a query; what it buys is revocation — logging out, resetting a password,
or deactivating a member ends access on the very next request rather than
whenever a token happens to expire. For a team that graduates a third of its
members every year, being able to cut access immediately is worth more than
saving a query.

Accounts live on the existing `members` table rather than a separate `users`
table, so a graduating senior is deactivated in one place instead of two, and
their name stays on the parts they designed. A member with no password simply
cannot sign in, which is exactly right for people you assign work to but who
never log in.

The guard is applied where the routers are mounted, not endpoint by endpoint, so
a new route is protected by default — you have to go out of your way to expose
something rather than remembering to lock it down.

### Money is integers

`cost_cents`, never floats. A cost report that is off by pennies because of binary
floating point is a cost report nobody trusts.

### Statuses are strings, not database enums

Validated as Pydantic `Literal`s at the API boundary. A team *will* invent a new
status mid-season; this makes that a one-line edit in `schemas.py` instead of a
migration.
