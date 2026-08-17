---
code:
- src/docir/platform/filesystem/code_matcher.py
- src/docir/modules/documents/domain/services/graph_checks.py
- src/docir/modules/documents/application/services/document_service.py
- src/docir/modules/documents/domain/entities/document.py
created: '2026-08-16'
description: Why --verified fingerprints the globs a document governs, why the digests
  live in the file, and why the resulting check-changed finding stays a warning.
id: adr-d9e6d5ccd0b4
owner: maintainer
related:
- kind: refines
  to: adr-bd7c4f3c5764
- arch-ad342aae8293
- arch-0a3c2d6d54a6
status: accepted
tags:
- cli
- docs
- persistence
title: A verification records what the code looked like
type: decision
updated: '2026-08-16'
---

A verification now records what the code looked like, and `docir check` reports when it
stops looking like that. This is the layer adr-bd7c4f3c5764 named as future work and
deliberately did not build; what changed is that it turns out not to need a parser.

## The two halves of staleness

`verified` plus the type's `review_days` measures a **calendar**: a cadence elapses and the
document becomes suspect whether or not anything happened to what it describes. That fires
on documents nothing has touched, and stays silent on the one rewritten underneath yesterday.

`verified_code` measures **evidence**: the code this document governs is not the code
somebody read. The two are complementary and both stay — a document nobody has looked at in
a year is worth re-reading even when its code never moved.

## What is stored, and where

`update --verified` fingerprints each `code:` glob and writes the digests into the
document's frontmatter, keyed by pattern. Keyed rather than positional so reordering the
globs cannot re-point a digest at a different pattern.

In the file, not the index — unlike the schema baseline and the build stamp, which are
properties of a build. This is the document's own review state, and the index is gitignored:
a digest that lived only there would be a fact only the machine that stamped it could know.
A clone rebuilds it from the file like every other field.

## Why it hashes contents

The digest covers the bytes of every file the pattern reaches, with each path folded in
beside its hash so an added, removed or renamed file registers too. A pattern naming a
directory is expanded to the files under it, because that is already what such a pattern
means on the read path.

Not mtimes and not a commit id: a clone, a checkout and a rebase move both without changing
a line, and a finding that fires after `git clone` is one nobody reads twice. Hashing bytes
also means no history is required, so it works in a shallow clone.

Whitespace and formatting count. Normalising a syntax tree would ignore them, at the price
of a parser per language and no answer at all for a language nobody wrote one for. For a
warning, over-reporting a reformat beats under-reporting an edit. This is the first place to
look if the noise turns out to be real.

## Absent means unverified

Three absences all read as unknown, never as unchanged: no digest recorded for the pattern,
a pattern that resolves to nothing, and no matcher at all (a global store has no repository
to fingerprint). So a never-verified document reports nothing, and a pattern added after the
last verification reports nothing until someone verifies against it.

With no matcher the digests are dropped rather than carried forward. A digest from an older
review sitting under a fresh `verified` date is the one combination that misreports in the
dangerous direction.

## Why it stays a warning

Editing code before its documentation is the ordinary shape of a change, so an error kind
here would fail the CI of every correct commit — the argument that made the first `--strict`
gate unusable, applied to a check that fires on the normal workflow rather than on a healthy
corpus.

## Clearing it is a judgement, not a rewrite

Somebody has to read the document against the code as it now stands and decide it is still
true. `check --fix` therefore leaves it alone: a repair has nothing to read *with*, and the
same holds for anything else mechanical.

The rule is deliberately **not** "only a human may verify". docir's writer is an agent by
design — every write goes through the CLI precisely so an agent can make it — and a signal
only a human could emit is a signal nothing would ever emit. An agent that reads the diff
between what the code was and what it is, and judges the document against it, is doing the
work the finding asks for. This finding is a better fit for that than `stale` is: `stale`
offers nothing to examine, while `code-changed` hands the reader a concrete delta.

## What the rule does exclude

Verifying inside the task that moved the code. A writer that edits `src/auth.py` and stamps
`--verified` on the decision governing it, in the same session, is certifying its own change;
`verified` stops meaning "somebody read this" and starts meaning "the check is green".

That is the laundering adr-bd7c4f3c5764 forbids, arriving by a different door. There it was a
mechanical rewrite bumping `updated` and resetting the clock nobody had looked at; here it is
a writer clearing the evidence of its own edit. Both replace a reading with a side effect of
the work being reported on.

Nothing enforces this — it is a rule for whoever drives the CLI, stated in the packaged skill.
Enforcing it would need docir to know which files a session touched, which is the working
tree's business and not the store's.
