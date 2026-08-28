---
paths:
  - "src/docir/entry_points/federation.py"
---

# Federated reads across peer stores

Reads federate; writes never do. A peer is another repository, opened read-only, and everything below follows from that.

- **Reads federate; writes never do (adr-fb938175f72a).** `.docir/stores.yaml` declares peer
  stores, and `FEDERATED_COMMANDS` (`entry_points/federation.py`) is exactly
  `get`/`query`/`search`/`context` — asserted against `Dispatcher.commands` in the suite, so a
  new command joins by decision rather than by omission. Three details are load-bearing. Peers
  are opened `mode=ro`, which is why they get their own construction path: `build_container`
  runs migrations and creates directories, and a peer is another repository. An unreadable peer
  is skipped with a stderr warning (`peer_status`, called by both the CLI and the fan-out, so
  the two cannot disagree) — a peer's index is gitignored, so a fresh clone of it has none, and
  failing the read would make that everyone's outage. And `merge_ranked` sorts on `similarity`,
  never `score`: RRF ranks *within one store*, so cross-store scores compare corpus sizes rather
  than relevance. Rows carry `store` only while federating — the field is pure cost with one
  store, which is why the read paths never carried it before.

- **Every federated row says which store answered *and what that store is*.**
  `store` is a path: it disambiguates two hits and says nothing about the corpus behind
  them, which is the judgement the reader actually has to make about a hit from another
  repository. So `stores.yaml` takes a `description:` beside `stores:`, and
  `store_description` rides on every row that store answers (`_stamp_row`). Four properties
  are load-bearing. **A store describes itself**, in its own file — the alternative, each
  reader annotating the peers it declares, writes the same sentence once per repository
  pointing at it, drifts as that corpus changes, and cannot label the reader's *own* rows,
  which are stamped too. It is **read per request**, like the peer list, so a daemon does
  not serve a description its owner has rewritten. A **peer's broken file costs its label,
  never the read** (`store_description` swallows the error) while this store's own file
  still raises through `peer_homes` — the same asymmetry an unavailable peer already has.
  And the field is **absent, never empty**: `""` reads as "this corpus is about nothing".
  A single-store read still carries neither field — describing yourself is for telling
  another reader what this is, and a store with no peers is talking to nobody.
  **Every example docir ships writes `stores:` alongside `description:`, `[]` when there
  are none** — verified against the published 0.20.0, whose `_read_peer_file` raises on a
  file with no `stores:` key, taking down `context`/`query`/`search`/`get` (and `doctor`)
  for everyone in that repo still on it. A test pins the spelling in the shipped example.

- **A peer whose index is older than this build is skipped, not read.** Peers are opened
  read-only and never migrated by us (adr-fb938175f72a), so every table or column a migration
  adds is one some peer will not have — and it had already broken twice: `mentions` (`0008`)
  took down `context`/`get` with `no such table`, and `document_code.digest` (`0007`) took down
  every hydrate, which is `query` too. Through the daemon that surfaced as "daemon closed the
  connection without responding". `peer_status` now compares the peer's `alembic_version`
  against `head_revision()` (`_peer_schema_status`), so **one rule covers every past and future
  migration** — a guard per column worked and had to be remembered, which is the failure mode
  itself. Three properties are load-bearing: an **unknown** revision is from a *newer* docir and
  is **allowed**, because every query names its columns and refusing it would make upgrading one
  repo break every repo that had not (backwards from what this protects); **no** recorded
  revision is skipped, since "cannot say" is not permission; and the skip reuses the existing
  warn-and-carry-on path, so an unreadable peer never fails the caller's own query. The cost is
  deliberate and stated in the message: upgrading docir darkens every peer until each is
  reindexed.
