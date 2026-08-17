---
created: '2026-08-15'
description: The three tiers deciding what blocks a write, what a check reports and
  what stays advisory, plus how a schema change is detected against the index build.
id: arch-ad342aae8293
related:
- kind: refines
  to: arch-1cfb1b212237
status: active
tags:
- architecture
title: Doc-Index CLI — validation strictness tiers
type: architecture
updated: '2026-08-17'
---

## Validation strictness tiers

The system borrows the "programming language" metaphor (schema = grammar, typed
`related` links = imports, validation = compiler, graph checks = linter) but only
where it holds: document metadata and the relation graph are formally checkable,
document *body text* is natural language and is not — so checks are split into
three tiers, not one uniform gate. Mixing these levels (hard-failing on a
text-similarity heuristic, say) is the main overengineering risk and is
deliberately avoided.

## Tier 0 — hard errors (synchronous, blocks the write)

Runs inline inside every `docir add` / `docir update` call, like a compiler. Only
checks that are cheap and essentially free of false positives:

- Missing required frontmatter field for the document's type
- Invalid `status` value (not in the type's enum)
- Invalid status transition (`--override` forces one and warns, naming the rule
  it broke; it cannot set a status the type does not declare)
- A `related` id that does not exist in the index
- A relation `kind` not in the `relation_types` registry, or one the source
  type's `allowed_relations` whitelist forbids for that target type
- A `tags` key not in the tag registry
- A `code` glob that can never match — absolute, containing `..`, backslash
  separated, or empty. A pattern that matches *nothing today* is accepted: a
  decision is routinely written before the code it decides
- Malformed frontmatter (not valid YAML, wrong types)

## Tier 1 — structural findings (non-blocking, via `docir check`)

Graph-level issues, run on demand or in CI, never inline in an agent's write
call — an agent mid-task should not be blocked by a "possible problem".

**Findings carry a severity, and this is the load-bearing part.** `ERROR_KINDS`
is `duplicate-id` / `dangling` / `malformed`: the corpus is *broken*. Everything
else is a `warning` about shape or age. `docir check --strict` exits 1 on errors
only and is the pre-merge gate; `--strict-all` makes every finding fatal for
anyone who wants that.

The distinction is not cosmetic. `orphan` used to fire for every document with
no `related:` edges — the default state of a new one, and of any document linked
only by someone writing its id in a sentence — so a fail-on-any-finding gate went
red on a healthy corpus, and the only way to keep CI green was to drop the gate,
which also dropped the duplicate-id detection that was its actual purpose. It now
reads the derived mention graph too (adr-e86c5040d626), which removes most of
that noise; the severity split stays, because the finding is still about shape.
`CheckIssue` derives `severity` from `kind`, so a new check classifies itself by
being added to `ERROR_KINDS` or not.

| kind | severity | means |
|---|---|---|
| `duplicate-id` | error | two files claim one id; the index dedupes, so one document is invisible. Found by scanning the *files*, not the index |
| `dangling` | error | a `related` edge points at nothing |
| `malformed` | error | a file the loader cannot parse — absent from every read path |
| `orphan` | warning | nothing connects to it — no `related` edge either way, and no other document names its id in prose |
| `cycle` | warning | a loop in the graph |
| `layering` | warning | a higher-level type *depends on* a lower one |
| `stale` | warning | past the type's `review_days`, measured from `verified` else `updated` |
| `code-changed` | warning | the code a document governs differs from what it was when somebody last verified it |
| `unmatched-code` | warning | a `code` glob that no longer names anything (only when the store sits in a repository) |
| `unknown-type` / `unknown-status` / `unknown-tag` / `unknown-relation-kind` | warning | the file was written outside the CLI, or a profile was disabled under it |
| `missing-required` | warning | the *rule* moved under a document that was valid when written |
| `schema-drift` | warning | the resolved schema differs from the one the index was built against |
| `stale-index-build` | warning | a different docir built this index |
| `tag-key-format` | warning | a registry key that is not a usable tag |

The last group must not be promoted to errors: the schema they measure against
ships in the *package*, so a corpus that passed yesterday can fail today with no
commit to point at, and nothing about the documents changed.

**`stale` and `code-changed` are the two halves of one question** and neither
replaces the other. `stale` is the calendar — how long since a human read this —
and fires on documents nothing has touched. `code-changed` is the evidence — the
code moved since they read it — and fires the day it moves. `code-changed` must
stay a warning for a reason of its own: editing code before its documentation is
the ordinary shape of a change, so an error kind would fail the CI of every
correct commit. Clearing it is a judgement — read the document against the code
and stamp `--verified` — and the one thing the rule forbids is making that
judgement inside the task that moved the code, which certifies its own change.
See adr-d9e6d5ccd0b4.

**Layering is opt-in per relation kind.** The check reads only edges the schema
marks `dependency: true` — `depends_on` and `refines` among the core six. It is
not a list of exempt kinds: `relates_to`, `implements` and `supersedes` are
simply not dependencies, so linking a decision to the issue that motivated it is
normal and silent. Treating every edge as a dependency made the most natural
pairing in the quickstart a permanent warning.

**`docir check --fix` repairs what needs no guess**: duplicate ids are re-issued
(the *oldest* file keeps the id, because existing edges were written against it
and an edge cannot say which document it meant) and dangling edges are dropped.
It reindexes first, and does **not** advance `updated` — a mechanical repair is
not a re-verification. `malformed`, `unknown-type`, `unmatched-code` and
`code-changed` are deliberately left alone and returned unrepaired: each needs
somebody to *read* something and decide what the file, the schema, the pattern or
the document should say, and a repair has nothing to read with.

## Tier 2 — advisory/style (opt-in only, via `docir lint --deep`)

Heuristic, never CI-blocking, run only when a human chooses to:

- Content similarity across documents (DRY at the idea level), using the
  *document* vectors already computed for `docir context` — surfaced as a
  suggestion, never an error. Chunk vectors are deliberately not used here: they
  would answer "do these share a section", not "are these the same document"
- Document size / scope creep (one document covering several unrelated decisions)

## Why this split

Tier 0 can be as strict as a real compiler because it is fully deterministic and
cheap to verify. Tiers 1–2 deal with things that are inherently uncertain (graph
shape, natural-language meaning), so they are surfaced as information, not
failures — keeping the CLI usable in an agent's task flow while still giving
humans and CI a way to keep the graph healthy. Never promote a heuristic to a
hard error.

## Schema drift and the index build stamp

The schema is not only `docs-schema.yaml`. The frozen core and the bundled
profiles are compiled into the package and re-merged on *every* command, so
upgrading docir can add a type, make a field `required:`, or change a prefix in
a store whose schema file nobody touched — with nothing in `git diff` to review.

The index therefore records two facts about how it was last built, each in its
own one-row table, and `docir reindex` is the only writer of both:

| Table | Records | Reported by `check` as |
|---|---|---|
| `schema_baseline` | the resolved schema the index was built against | `schema-drift`, one finding per change (`+type test_plan`, `type decision: required [] -> ['owner']`) |
| `index_build` | the docir version that built the index | `stale-index-build` |

They are separate on purpose. The baseline payload is diffed line by line and
printed, so a version key inside it would render every upgrade as a schema
change — and the baseline cannot answer the version question anyway, since it
compares schemas and stays silent for a release that changes how documents are
*read* rather than what they may say.

Three rules hold this up:

### Absent means unknown, not unchanged.

A store with no baseline reports
nothing, rather than reporting its entire schema as new; an unparseable one
reads the same way, since `reindex` overwrites it. `stale-index-build`
likewise fires on **inequality**, not "older than" — a downgrade needs the
same rebuild.

### reindex is the only writer.

It is already the "make derived state agree
with the sources" verb. A separate `accept` command would be a ritual whose
only effect is silencing a report.

### One renderer.

The drift check lives in `application`, which may not import
`infra`, so both sides go through `domain/services/schema_shape.describe`. A
second renderer would mean a baseline written in one shape and compared in
another.

`DOCIR_SCHEMA_NOTICE=1` prints the drift on stderr after every command. It is
emitted **client-side**, through the same request boundary, because with the
daemon running the process that first loads a changed schema is the daemon —
whose stderr is a log nobody reads. `docir self upgrade` is the command that
acts on `stale-index-build`: reindex → `agent update` → `check`, in that order.
