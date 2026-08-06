---
code:
- tach.toml
- scripts/check_contract_sync.py
created: '2026-07-30'
description: The MUST/SHOULD module rules this codebase is held to, and how CI proves
  them.
id: arch-322e5f992ad2
owner: maintainer
related: []
status: active
tags:
- architecture
- testing
title: Architecture Rules — Modular DDD
type: architecture
updated: '2026-08-06'
---

Audience: AI coding agent creating and maintaining this project.
Scope: language-independent. Substitute your ecosystem's equivalents for
"package", "module", "import", "linter", "CI".

Purpose: keep the codebase legible at any size. The target property is
**bounded blast radius** — adding or changing a feature touches one module plus
one line of wiring, and the tooling can prove it.

Rules are marked **MUST** (violation fails CI or review) or **SHOULD**
(deviation requires a recorded reason).

---

## 1. Core principles

1. **A module is a box.** Declared purpose, declared inputs, declared outputs,
   private everything else.
2. **Boundaries that are not enforced do not exist.** Every rule here that can be
   machine-checked MUST be machine-checked. Conventions decay within weeks.
3. **Vertical before horizontal.** Slice by business capability first, by
   technical layer second. Layers live *inside* a module, never above it.
4. **Cross-cutting concerns are implemented once, at a boundary.** If a concern
   requires editing many features, the design is wrong.
5. **Coupling is paid at the boundary, not in the middle.** Duplication across
   modules is cheaper than a shared type that fuses them.
6. **Legibility is a deliverable.** A reader (human or agent) MUST be able to
   understand a module's business purpose without reading its implementation.

---

## 2. Project structure

```
<root>/
├── config/            # configuration and settings only
├── platform/          # shared technical capability; LEAF — depends on nothing internal
│   ├── persistence/   # connection/session/unit-of-work primitives, migration runner
│   ├── transport/     # base HTTP/queue clients, retry and timeout policy
│   ├── observability/ # logging, metrics, tracing setup
│   ├── authn/         # identity: who is the caller
│   ├── authz/         # authorization: permission registry + enforcement
│   └── errors/        # base error taxonomy
├── modules/           # one directory per bounded context
│   └── <module>/
│       ├── api.*      # THE public surface — the only externally importable file
│       ├── CONTRACT.md
│       ├── domain/       # entities, value objects, invariants, domain services
│       ├── application/  # use-case handlers, ports (interfaces), orchestration
│       └── infra/        # repositories, storage schema, external clients, adapters
└── entry_points/      # thin wiring: HTTP server, CLI, workers, schedulers, RPC
```

**MUST** — no technical-layer directory at the project root other than
`platform/`, `config/`, and `entry_points/`. A top-level `services/`,
`models/`, `utils/`, or `helpers/` is forbidden; those are module-internal
concerns.

**MUST** — if a directory under `platform/` is named after a business concept, it
is misplaced. Move it into the owning module. This is the single most reliable
smell for detecting fan-out.

**MUST** — `entry_points/` contains no business logic, no validation beyond
transport parsing, and no handler bodies. It imports module APIs and registers
them.

---

## 3. Module rules

### 3.1 What qualifies as a module

A module **MUST** correspond to a bounded context: a set of concepts that change
together and have a single owner concept of correctness.

Not modules:
- a delivery channel (email digest, Slack report, a specific dashboard) — that is
  a renderer or transport inside a module, or wiring in `entry_points/`
- a technical capability shared by many contexts (caching, retries, templating) —
  that belongs in `platform/`
- a single entity with no behaviour — fold it into the context that owns it

### 3.2 Public surface

**MUST** — every module exposes exactly one public file, `api.*`. Everything else
in the module is private.

`api.*` **MUST** export only:
- **commands** — operations that change state; take a command object, return an
  identifier or a result DTO
- **queries** — read operations; take a query object, return DTOs
- **DTOs** — data structures owned by this module, containing only primitives and
  other DTOs
- **events** — the classes this module publishes
- **surface descriptors** — router/handler/tool/job registrations for
  `entry_points/` to mount

`api.*` **MUST NOT** export:
- domain entities, aggregates, or value objects
- persistence models, schema classes, or query builders
- database connections, sessions, transactions, or unit-of-work handles
- repositories, ports, or any interface intended for internal substitution
- another module's types (re-export is forbidden; the caller imports directly)

### 3.3 Size and splitting

- **SHOULD** — a module whose `api.*` exports more than ~15 operations is
  probably two modules. Split along the seam where the two halves stop sharing
  invariants.
- **MUST** — if module A and module B need each other's internals, they are one
  module. Merge them. Do **not** widen either `api.*` to resolve the coupling.
- **SHOULD** — a module with no `domain/` content (pure pass-through to an
  external system) is an adapter, not a module. Move it under `platform/` or into
  the module that consumes it.

---

## 4. Dependency rules

| From | May depend on |
|---|---|
| `entry_points/**` | `modules/*/api`, `platform/**`, `config` |
| `modules/X/**` | own module internals, `modules/Y/api` (Y≠X), `platform/**`, `config` |
| `platform/**` | `config`, third-party only |
| `config/**` | third-party only |

Inside a module:

| From | May depend on |
|---|---|
| `api` | `application`, module DTOs |
| `application` | `domain`, own ports; NOT `infra` |
| `domain` | nothing internal — no `application`, no `infra`, no `platform` beyond pure primitives |
| `infra` | `domain`, `application` ports, `platform` |

**MUST** — `domain/` has zero dependencies on frameworks, ORMs, HTTP libraries,
or `platform/` services. If domain code cannot be tested with no I/O and no
mocks, it is not domain code.

**MUST** — dependencies flow inward. `application` defines ports (interfaces);
`infra` implements them. `application` never imports a concrete adapter.

**MUST** — no cycles at any level: between modules, between layers, between
files. A cycle is a CI failure, not a review comment.

---

## 5. Cross-module communication

Only two mechanisms are permitted.

### 5.1 Direct call through `api`

Use when the caller needs the result synchronously.

- **MUST** pass and return DTOs only.
- **MUST NOT** pass entities, persistence objects, or transaction handles.
- **MUST NOT** share a transaction across modules. Each module commits its own
  work; multi-module consistency is handled by events plus idempotency, not by a
  distributed transaction.

### 5.2 Domain event

Use when the publisher must not know its consumers.

- **MUST** — the event class is declared in the publisher's `api.*` and contains
  only primitives and DTOs.
- **MUST** — the publisher is unaware of subscriber identity or count. Adding a
  subscriber never modifies the publisher.
- **MUST** — handlers are idempotent. Assume at-least-once delivery.
- **SHOULD** — name events as past-tense facts (`OrderPlaced`), never as commands
  (`PlaceOrder`) and never as notifications about the consumer's job
  (`SendEmail`).

### 5.3 Data ownership

- **MUST** — each persisted table/collection/stream has exactly one owning
  module. Only that module reads or writes it.
- **MUST NOT** — cross-module joins at the storage layer. If module A needs
  module B's data, it calls B's query API or maintains its own projection built
  from B's events.
- **SHOULD** — accept read-model duplication. A denormalized copy owned by the
  reader is cheaper than a shared table owned by nobody.

### 5.4 Duplication policy

**MUST** — when two modules need a structurally identical DTO, each defines its
own. A shared DTO package is forbidden; it becomes an unbounded coupling surface
within months. Shared code is permitted only in `platform/`, and only when it is
free of business meaning.

---

## 6. Cross-cutting concerns

This is the rule set that prevents the most common failure: a concern (auth,
audit, tenancy, feature flags, rate limits, localization, soft delete) being
retrofitted by editing every feature and producing bugs everywhere.

**MUST** — every cross-cutting concern has:

1. **One declaration point.** A registry or annotation stating, per operation,
   what the concern requires. Readable as a single artifact answering "what is
   the policy across the whole system".
2. **One enforcement point per entry-point kind.** A middleware, decorator, or
   dependency applied uniformly — not per handler, not per feature.
3. **One CI gate.** A check that every public operation is covered by the
   declaration, failing the build otherwise.

**MUST NOT** — business modules contain conditional logic keyed on the concern.
No role checks in domain code, no tenant filtering scattered in services, no
feature-flag branches inside entities.

**SHOULD** — where a concern must influence data access (row-level filtering by
tenant, ownership, or permission), express it as a *scope object* built once at
the boundary and applied at the repository layer. Never as branching in
application services.

**Test for correctness of the design:** adding one new operation should require
adding one line to the declaration and nothing else. If it requires touching the
enforcement logic, the enforcement is not generic enough.

### 6.1 Authorization specifically

- Declaration: `operation → required permission`, registered where the operation
  is declared in `api.*`.
- Enforcement: one check per entry-point kind, resolving
  `(actor, permission, resource)` before the handler runs.
- Role→permission mapping lives only in `platform/authz`. Modules know
  permissions; they never know roles.
- CI gate: every operation exported by any `api.*` appears in the registry; every
  registered surface has the enforcement attached; every referenced permission is
  defined.
- Tests: every operation has an authorized case and a denied case, in the owning
  module's test suite.

---

## 7. Contract documentation

**MUST** — every module has `CONTRACT.md` next to `api.*`, under 40 lines:

```markdown
# <module>

## Purpose
Two sentences, in business language. No technical terms.

## Public operations
- `<name>(<input>) -> <output>` — one-line description

## Events published
- `<EventName>` — when it fires

## Events consumed
- `<EventName>` (from <module>)

## Owns
- storage: <tables/collections owned exclusively>

## Depends on
- modules: <list>
- platform: <list>

## Policy
- permissions: <list>
- other cross-cutting requirements
```

**MUST** — a change to `api.*` and the corresponding change to `CONTRACT.md`
occur in the same commit. A diff touching one without the other is rejected.

**SHOULD** — `CONTRACT.md` is the context an agent loads to work on or against a
module. Keep it accurate and short enough that loading all of them at once is
cheap. It replaces reading the module's source for callers.

**MUST** — the root README lists every module with its one-line purpose, and
nothing else about internals.

---

## 8. Enforcement

Convention without tooling is not a rule. Each item below **MUST** run in CI and
fail the build.

1. **Boundary check.** A module-dependency linter encoding §4. Configuration is
   version-controlled and only ever tightens — see §8.1.
2. **Public-surface check.** No import path from outside `modules/X/` resolves to
   anything under `modules/X/` other than `api.*`.
3. **Layer check.** `domain/` imports no framework, no `infra`, no `platform`
   services. `application/` imports no `infra`.
4. **Cycle check.** No import cycles.
5. **Cross-cutting coverage checks.** One per concern, per §6.
6. **Contract sync check.** `api.*` modified without `CONTRACT.md` modified in
   the same commit → fail.
7. **Dead-code check.** Unreferenced exports are removed, not retained "just in
   case". A stale export is a boundary that still has to be reasoned about.

### 8.1 The ratchet

- **MUST** — when introducing enforcement to an existing codebase, snapshot the
  current graph as a baseline of known violations and fail on anything new.
- **MUST** — the baseline only shrinks. Adding an entry to it is forbidden;
  removing entries is ordinary work.
- **MUST NOT** — resolve a boundary failure by adding an exception, widening
  `api.*`, or relaxing the linter. The correct responses are: route through the
  proper API, merge the two modules, or move the shared thing to `platform/`.

---

## 9. Testing

| Layer | Test kind | Dependencies |
|---|---|---|
| `domain/` | pure unit | none — no I/O, no mocks |
| `application/` | use-case tests | ports replaced by in-memory fakes |
| `infra/` | integration | real storage/external system, containerized |
| `api.*` | contract tests | module wired, dependencies faked at the boundary |
| `entry_points/` | end-to-end | full stack, thin coverage of happy paths |

**MUST** — tests live inside the module they cover, mirroring its structure. A
central test tree recreates the fan-out problem the module layout removes.

**MUST** — every operation in `api.*` has a contract test. This suite is the
executable form of `CONTRACT.md`; breaking a consumer's expectation breaks a test
in the *provider's* suite, where the fix belongs.

**SHOULD** — prefer in-memory fakes over mocks for ports. Mocks encode the
implementation; fakes encode the contract.

---

## 10. Workflow: adding a feature

**MUST** follow in order. Stop and report if a step cannot be completed as
written — that is a signal about the design, not an obstacle to work around.

1. Identify the owning module. If none fits, justify a new module against §3.1
   before writing code.
2. Write or update `CONTRACT.md` first: the operation, its inputs, outputs,
   events, and policy.
3. Add the operation to `api.*` with its cross-cutting declarations.
4. Implement inward: `domain` → `application` → `infra`.
5. Wire it in `entry_points/` — one registration line, no logic.
6. Add contract tests including the denied/negative cross-cutting case.
7. Run the full enforcement suite (§8).

**MUST** — the resulting diff touches exactly one module directory plus
`entry_points/` wiring. A diff spanning multiple modules is a design defect;
report it rather than proceeding.

---

## 11. Workflow: changing an existing feature

- **MUST** — determine whether the change is internal (no `api.*` diff) or
  contractual. Internal changes need no coordination. Contractual changes require
  updating `CONTRACT.md`, contract tests, and every consumer in the same change.
- **MUST** — when a change would require reading another module's internals to
  understand its effect, stop: the boundary is already broken. Fix the boundary
  first, in a separate change.
- **SHOULD** — evolve a contract additively: add the new operation, migrate
  consumers, remove the old one. Three commits, not one.

---

## 12. Refactoring an existing codebase into this shape

Order matters. Do not reorder.

1. **Enforce before restructuring.** Introduce the boundary linter with a
   permissive baseline (§8.1). Without it, the refactor decays as fast as it
   lands.
2. **Pilot one module.** Choose the most independent business context. Give it
   `api.*`, `CONTRACT.md`, and pull its scattered infrastructure inward. Tighten
   the linter for that module only.
3. **Repeat, one module per change.** Order by independence: fewest inbound
   dependencies first.
4. **Dissolve the shared technical bucket.** Whatever remains after modules
   reclaim their own code is the real `platform/`. Rename it — the name of a
   shared directory determines what people put in it.
5. **Collapse near-duplicate modules.** Contexts that differ only by output
   format or delivery channel become one module with pluggable renderers.
6. **Thin the entry points.** Move handler bodies into modules; leave
   registration.
7. **Rework cross-cutting concerns last**, per §6, once boundaries are stable.

---

## 13. Anti-patterns — reject on sight

| Pattern | Why it fails | Correct form |
|---|---|---|
| Shared `common`/`utils`/`shared` package with business meaning | Becomes an unbounded coupling surface | Duplicate per module, or move to `platform/` if meaning-free |
| Shared DTO or "contracts" package across modules | Every module now changes when any changes | Each module owns its DTOs |
| Technical layers at project root | Guarantees feature fan-out | Layers inside modules |
| Infrastructure directory named after a business concept | The feature already spans two trees | Move into the owning module |
| Business logic in entry points | Untestable, duplicated per transport | Move to `application/` |
| Cross-module database join | Silent coupling the linter cannot see | Query API or event-built projection |
| Role or tenant checks inside domain code | Retrofit touches every feature | Single enforcement point (§6) |
| Anemic module: entities with only getters, all logic in services | Invariants unprotected, drift across callers | Move behaviour onto the entity |
| Widening `api.*` to satisfy an import error | Boundary erosion disguised as progress | Route properly, or merge the modules |
| Adding an exception to the boundary linter | The ratchet is the whole mechanism | Fix the dependency |
| "Temporary" direct import of another module's internals | It is not temporary | Not permitted |

---

## 14. Decision records

**MUST** — record a decision whenever: a new module is created, two modules are
merged or split, a `platform/` capability is added, a cross-cutting concern is
introduced, or a **SHOULD** rule is deliberately violated.

Format — one file per decision, append-only, never edited after acceptance:

```markdown
# ADR-<n>: <title>
Status: proposed | accepted | superseded by ADR-<m>
Date: <date>

## Context
The forces at play. What made this a decision rather than a default.

## Decision
What was chosen, stated in the imperative.

## Consequences
What becomes easier. What becomes harder. What is now forbidden.
```

**SHOULD** — when a rule in this document is superseded, amend this document in
the same change as the ADR that supersedes it. This file is the current state;
ADRs are the history.

---

## 15. Definition of a healthy codebase

Verify periodically. Each item is objective.

- [ ] Adding a feature touches one module directory plus wiring
- [ ] Every module has `api.*` and an accurate `CONTRACT.md`
- [ ] Reading all `CONTRACT.md` files explains the whole system's behaviour
- [ ] No import from outside a module resolves to anything but its `api.*`
- [ ] `domain/` is framework-free and testable with no I/O
- [ ] `platform/` depends on nothing in `modules/`
- [ ] No import cycles anywhere
- [ ] Each stored dataset has exactly one owning module
- [ ] Each cross-cutting concern has one declaration, one enforcement, one gate
- [ ] The linter baseline is empty, or strictly smaller than last quarter
- [ ] Every `api.*` operation has a contract test, including a negative policy case
- [ ] No shared package with business meaning exists

Any unchecked item is a work item, not an accepted state.
