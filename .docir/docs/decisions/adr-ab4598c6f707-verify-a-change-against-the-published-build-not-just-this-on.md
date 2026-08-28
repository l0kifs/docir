---
created: '2026-08-28'
description: Why every change touching a committed file, the on-disk contract or the
  index schema is run against the docir release on PyPI, in both directions, before
  it ships.
id: adr-ab4598c6f707
owner: maintainer
related:
- kind: refines
  to: adr-7d9fbbf976e8
- adr-84fb02d5061b
- adr-f14682e3f4d6
status: accepted
tags:
- architecture
- cli
- release
title: Verify a change against the published build, not just this one
type: decision
updated: '2026-08-28'
---

## Context

Every gate in this repository runs one build against itself. That is enough for
a program nobody else holds a copy of, and docir is not one: a store is a
*committed* artifact. The same `.docir/` is read by whatever docir each person
on the team installed, and by every repository that declares it a peer. So a
change to a committed file's shape, to the CLI's on-disk contract or to the
index schema is an interface change against builds already in the wild — and
nothing in CI is holding one of those.

adr-84fb02d5061b is the evidence. It shipped with every gate green — lint,
types, tach, vulture, 3,299 tests, `doctor --strict` and `check --strict` on
the real corpus, exercised through the daemon and MCP — and it still took every
read down for anyone still on the released build, the moment a store wrote the
new key without the old one. Reading the diff did not find it. Running the
published wheel did, in about a minute.

## Decision

Before shipping a change that touches a committed file's shape, the on-disk
contract or the index schema, run the **published** build and this one against
each other's stores:

```bash
uvx --from docir==<the release `docir self status` names> docir --no-daemon \
  context "..." --limit 3      # also query, search, get, doctor, check
```

Both directions, and each on a store the *other* build created — an index built
by the released build read by this one, and a file written by this one read by
the released build. The published wheel, not a git checkout of the tag: what
adopters run is what has to be tested.

## What counts as a break

A refusal: a read that errors, an index skipped, a file rejected. Those turn one
person's upgrade into everyone else's outage, which is the failure the peer
schema check already exists to prevent.

A *missing* feature is not a break. An older build cannot show a field it has
never heard of, and demanding otherwise would freeze the format.

## The remedy is the shipped spelling

Nothing this build does can change one already installed, so a fix has to live
in what an adopter copies: the packaged skill, the CLI docstring, this store's
own files. That makes it prose, and prose regresses silently — so whatever
spelling keeps the older build working is pinned by a test, the way
adr-84fb02d5061b pins `stores:` beside `description:`.

## Consequences

- The check needs the network on a cold `uvx` cache, so it stays a step in
  shipping a change rather than a CI gate. CI proves this build correct; this
  proves it compatible.
- It is adr-f14682e3f4d6 one level out: that rule says a scratch store cannot
  stand in for the real corpus, this one says the current build cannot stand in
  for the one people have.
- A deliberate break is still allowed — it is recorded as a decision, with the
  version it starts at, rather than discovered by whoever had not upgraded.
