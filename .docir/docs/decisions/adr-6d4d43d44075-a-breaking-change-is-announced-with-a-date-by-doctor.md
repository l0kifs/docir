---
code:
- src/docir/entry_points/doctor.py
code_baseline:
  src/docir/entry_points/doctor.py: ce032a47b5e6
created: '2026-09-16'
description: Why deprecations carry a sunset date, why docir doctor is the channel
  rather than a release note, and why --strict stays green until the date passes.
id: adr-6d4d43d44075
owner: maintainer
related:
- kind: refines
  to: adr-909734bced92
- adr-36d6156ffab9
- adr-bd7c4f3c5764
- issue-c30895cc62a3
status: accepted
tags:
- cli
- integrity
- docs
title: A breaking change is announced with a date, by doctor
type: decision
updated: '2026-09-22'
verified: '2026-09-22'
verified_code:
  src/docir/entry_points/doctor.py: ce032a47b5e6
verified_content: 95b45e81d509
---

A floor stops a break; it does not give anybody time. The reader who needs the warning is an
agent holding only the installed package, so the announcement has to arrive on a surface it
already runs, carrying a date it can act on.

## The reader will not open a changelog

docir's user is an agent, by design — every write goes through the CLI precisely so one can
make it. It does not browse release notes, and a notice that only exists in a release note
reaches whoever upgraded, once, and nobody else on the team.

What it does run is `docir doctor` and `docir check`, because CI runs them in that order
after `reindex`. That is the channel: not a new one, the one that is already there.

## A warning with no date cannot be planned around

This is settled practice outside docir. RFC 9745 pairs a `Deprecation` date with RFC 8594's
`Sunset` — when it stops working — and RFC 8288's link to the migration, with the sunset
never earlier than the deprecation. Clients warn on it outside production.

An agent asked "is this urgent" needs the same three facts: what is going away, what replaces
it, and when. "Deprecated" alone is a mood.

## What `doctor` reports

A `compat` section, beside the findings it already has:

- The store format: the floor this file declares, the one its contents need, and the highest
  this build reads — three integers, `declared`/`required`/`supported` — so "can my teammate
  read this store" is `required` against their build's `supported`, a fact rather than an
  experiment. A number rather than the release that introduced a feature, because the version
  is bumped at release and a floor named by release would not exist while the change is being
  written (adr-36d6156ffab9).
- Per deprecated thing, what replaces it and the date it stops working.

Same shape as `schema-drift` and `stale-index-build`: a report about how this store and this
build relate, computed on demand.

## Why `--strict` stays green until the date

An announcement whose date is still ahead is **data, not a finding**: it rides in the report's
`compat` section on every run, the way RFC 9745 carries a deprecation on every response rather
than as an error.

Making it a warning was the first draft and is the same defect one notch quieter. A warning
that fires for a change which has not happened yet never clears, so the findings list is the
same length every run — and a list that never changes is one the reader stops reading, which
is the failure [[adr-1cccd77cb023]] guards the report against.

Past the date it changes kind. The surface was supposed to be gone, so an entry still
answering is a removal docir promised and did not make: `deprecation-overdue`, an error, read
first by `doctor --strict` in docir's own CI. The register polices the schedule it named
instead of relying on somebody to remember it.

## Pull, not push

No notifier, no phoning home. [[adr-bd7c4f3c5764]] settled that for staleness — the review
queue is a query — and the argument transfers unchanged: the state lives in the store and the
build, both already in front of the caller.

## The limit it shares with the floor

A build that does not ship this cannot report it, so the first release carrying it announces
nothing about itself to anyone older. It is worth building anyway for the same reason the
floor is: every break after it is dated, and the two together are what [[adr-36d6156ffab9]]
calls a promise to future readers.
