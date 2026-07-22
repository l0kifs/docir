# ADR-0004: Persistence stack — Dapper.AOT over Microsoft.Data.Sqlite
Status: accepted
Date: 2026-07-21

## Context

The .NET 10 rework (see [../dotnet-solution-layout.md](../dotnet-solution-layout.md))
needs a data-access approach for the derived SQLite index. The choice is between
EF Core 10 and a Dapper/ADO.NET stack, and it is load-bearing: it ripples through
every module's `infra/` layer and constrains the distribution options.

Forces at play:

- **The schema is small and stable.** Six tables (`documents`, `relations`,
  `document_tags`, `id_sequences`, `tags`, `embeddings`) plus the `documents_fts`
  virtual table. Edge-list relations, no navigation-property graphs, no ad-hoc
  LINQ querying, and every write is an explicit upsert — so EF Core's core value
  (change tracking, relational navigation, LINQ-to-SQL) is largely unused here.
- **Raw SQL is already unavoidable.** FTS5 (`documents_fts`, `bm25()`) and the
  little-endian float32 embedding BLOBs must be raw SQL under *any* ORM. With EF
  Core the codebase would carry two data-access models (mapped entities +
  `FromSqlRaw`); the schema is small enough that one raw-SQL model is simpler.
- **Reliability is the reason for the whole port.** A runtime query-translation
  layer is surface area for failures that surface at run time rather than build
  time. Explicit SQL keeps the behavior legible and diff-reviewable.
- **Modular DDD ownership (ARCHITECTURE_RULES §5.3).** Each module owns its own
  tables *and migrations* in a single shared `index.db`. Multiple EF `DbContext`s
  over one SQLite file means juggling separate migration histories and model
  snapshots; a small hand-written per-module migration runner is cleaner under
  this constraint.
- **Distribution optionality.** EF Core still has significant NativeAOT/trimming
  limitations. Classic Dapper uses reflection (also an AOT concern), but
  `Dapper.AOT` is a compile-time source generator: AOT-safe, reflection-free, and
  usable in non-AOT builds too. Choosing it keeps the single-native-binary
  distribution path open without committing to AOT now; choosing EF Core would
  foreclose it.

## Decision

Use **`Dapper.AOT` over `Microsoft.Data.Sqlite`** for all index data access, with
a **small hand-written migration runner** in `platform/persistence`.

- `platform/persistence` provides the `Microsoft.Data.Sqlite` connection factory,
  a `UnitOfWork` base, and a migration runner that applies each module's ordered,
  embedded SQL scripts inside a transaction and records applied scripts in a
  `schema_migrations` table.
- Each module's `infra/` owns its own table definitions, migration scripts, and
  `Dapper.AOT` repositories, and scopes its unit of work to its own tables. No
  cross-module transaction and no shared `DbContext`.
- FTS5 and embedding-BLOB access are hand-written parameterized SQL, consistent
  with the rest of the data layer.
- Do **not** take a dependency on EF Core.

## Consequences

**Easier**
- One consistent, explicit data-access model; the SQL is visible and reviewable,
  with no ORM translation to reason about at run time.
- NativeAOT stays viable (and the single-binary distribution win from the earlier
  analysis stays reachable) without committing to AOT today.
- Faster CLI cold start (no EF model-building) — relevant for agent-driven use.
- Per-module table + migration ownership maps cleanly onto the store, satisfying
  §5.3 without EF multi-context contortions.

**Harder**
- SQL is written by hand and must be parameterized deliberately (SQL-injection
  discipline is on the authors). Mitigated: `Dapper.AOT` lint-checks SQL at
  compile time, and the queries are already specified in the existing SQLAlchemy
  repositories.
- No change tracking or LINQ. Acceptable: docir uses explicit upserts and simple
  filters, so neither is needed.
- Migrations are hand-authored rather than scaffolded by `dotnet ef`. Accepted as
  a benefit — hand-written SQL migrations are the "schema owned by migrations"
  discipline docir already values, with no surprising generated diffs.

**Now forbidden**
- Adding `Microsoft.EntityFrameworkCore.*` to any project.
- A single shared `DbContext` or connection that spans more than one module's
  tables (would fuse data ownership, §5.3).
- Reflection-based row mapping (defeats the AOT guarantee); use `Dapper.AOT`
  source generation or explicit readers only.

Reconsider this decision if the index schema grows into a rich, frequently
changing relational model with substantial ad-hoc querying **and** NativeAOT has
been firmly ruled out — neither of which holds today.
