---
created: '2026-08-28'
description: The release that labelled every federated hit with the corpus behind
  it, and found that a fully green change can still break every read for anyone a
  version behind.
id: rel-145686e1fb12
owner: maintainer
related:
- adr-84fb02d5061b
- adr-ab4598c6f707
- adr-fb938175f72a
- adr-7d9fbbf976e8
- issue-06f48d8f239f
- rel-5e5a01b07887
status: published
tags:
- cli
- release
- retrieval
title: 0.21.0 — say what corpus answered, and prove it against the build people have
type: release_note
updated: '2026-08-28'
---

## What this release is about

0.20.0 was the release where four gates were green because they were not looking. 0.21.0 is
that lesson one level out: every gate in this repository runs *this* build against itself, and
a docir store is a committed artifact read by whatever docir each person on the team installed.

The feature is small. A federated hit named the repository that answered it and nothing about
what that repository holds, so a store now describes itself once, in its own `stores.yaml`, and
that sentence rides on every row it answers (adr-84fb02d5061b). The finding is the release:
shipping it fully green still broke every read for anyone on 0.20.0, and only running the
published wheel against a store this build had written found it (adr-ab4598c6f707).

## What is worth following the edges for

- **adr-84fb02d5061b** — why the store describes *itself* rather than each reader annotating the
  peers it declares, why the field is absent rather than empty, and why an unfamiliar key in
  `stores.yaml` is reported while a misspelled one raises.
- **adr-ab4598c6f707** — the rule the release produced: what counts as a break against an older
  build (a refusal, never a field it cannot show), and why the remedy has to live in the examples
  an adopter copies rather than in the build doing the shipping.
- **adr-fb938175f72a** — the federation decision this refines. `store` on a row came from there,
  and the argument for a second field is the one that decision made for the first.

## Upgrade note

Keep `stores:` in `.docir/stores.yaml` — `[]` when the store reads no peers:

```yaml
description: Platform decisions every service must follow.
stores: []
```

docir 0.20.0 and earlier refuse a file without that key, so a description-only file takes
`context`, `query`, `search`, `get` and `doctor` down for every teammate who has not upgraded,
while writes keep working — which reads like a corrupt store rather than a version skew.

Nothing else changes without asking: a store that describes itself nowhere reads exactly as it
did, field for field.

## Fixed while working nearby

A malformed `stores.yaml` printed a stack trace (issue-06f48d8f239f); forty parameters across
fourteen commands showed a blank column in `--help`; three error paths named a failure without
the move that closes it; twelve slow steps ran with nothing on screen. `CHANGELOG.md` and the
release page carry the detail — this document carries the edges.
