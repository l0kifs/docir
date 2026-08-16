---
code:
- src/docir/modules/documents/application/services/schema_conformance.py
- src/docir/modules/documents/domain/services/graph_checks.py
- src/docir/entry_points/composition.py
created: '2026-08-16'
description: Why the command run after a schema edit reports what that schema costs
  the corpus, reads files rather than the index, and never changes the exit code.
id: adr-dbe6633405ca
owner: maintainer
related:
- issue-3678c897295f
- kind: refines
  to: adr-f8cce745d0d5
- kind: refines
  to: arch-1cfb1b212237
status: accepted
tags:
- schema
- cli
title: schema validate measures the corpus, not just the file
type: decision
updated: '2026-08-16'
---

## Context

`docir schema validate` answered one question — does this file load? — and
answered it about the file alone. So the command a person runs immediately after
editing `docs-schema.yaml` reported `valid: true` at the exact moment a corpus
could have left the type system (issue-3678c897295f).

The information already existed. `docir check` reports `unknown-type`,
`unknown-status`, `missing-required` and `unknown-relation-kind`. What was
missing was not a rule but a *moment*: nobody runs `check` while editing the
schema, and by the time they do, the edit is in history.

## Decision

`schema validate` also measures the documents against the schema it just loaded,
and reports the size of the mismatch: how many documents are affected, broken
down by finding kind, with a bounded sample of ids.

**It is not a new rule.** `GraphChecker.check_schema_conformance` is the four
findings a *schema* edit can cause, extracted from `check` and called by both.
Two lists of check names in two commands is the failure `is_absent` already
guards against on the Tier 0 / Tier 1 seam: one command calling a document
conforming that the other refuses.

## The properties that make it usable

**It reads the files, not the index.** A schema edit is a hand edit, and a hand
edit is exactly when the index is behind. A fresh clone has no index at all —
it is gitignored — and that is a common moment to change the schema.

**It opens no database.** `schema validate` already bypassed the container,
because building one loads the schema and a file too broken to start the store
would make the command meant to diagnose it unreachable. Adding an engine here
would give that property away for nothing.

**The exit code does not move.** The schema is valid; the documents are what
changed. A gate here would fail during a *correct* migration, which necessarily
passes through the stranded state — the argument that keeps `orphan` out of
`check --strict`, applied one command over.

**Graph findings are excluded.** `orphan` fires for every document with no
relations, so including the rest of `check` would bury the answer under the
default state of a healthy corpus.

## What this does not do

It does not answer "what changed since the last commit". That is the other half
of issue-3678c897295f, and it stays unbuilt for the reason filed there: it needs
to read git objects, which docir has never done and should not start doing for
one command. This half needs no history — the schema in the file and the
documents on disk are both present.

## Consequences

- A schema edit is reviewable before it is committed, which `git diff` cannot do
  on its own: the core and the profiles merge in at load, so the file's text is
  not its meaning.
- `schema validate` now costs a scan of the docs root. It is run by a person
  after an edit, and by CI once, so the cost lands nowhere hot.
- `documents` and `unreadable` are reported even when nothing is wrong: "0
  findings" over a corpus that failed to parse is otherwise indistinguishable
  from a clean one.
