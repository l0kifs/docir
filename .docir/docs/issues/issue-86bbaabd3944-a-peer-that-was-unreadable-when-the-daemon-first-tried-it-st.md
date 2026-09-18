---
code:
- src/docir/entry_points/federation.py
- src/docir/entry_points/composition.py
code_baseline:
  src/docir/entry_points/composition.py: e59f157c6b81
  src/docir/entry_points/federation.py: d4450115acce
created: '2026-09-18'
description: The federated reader caches each opened peer per container, so a peer
  repaired after first contact keeps being skipped over the socket while --no-daemon
  reads it — and the comment beside the cache promises the opposite.
id: issue-86bbaabd3944
owner: maintainer
related:
- issue-c2e8ce341a00
- arch-1cfb1b212237
status: open
tags:
- daemon
- retrieval
title: A peer that was unreadable when the daemon first tried it stays skipped for
  the daemon's life
type: issue
updated: '2026-09-18'
---

## What is wrong

`FederatedDispatcher` caches every peer it opens, keyed by resolved home, and it
is built once per container — so the cache lives as long as the daemon. A failed
open is cached exactly like a successful one, verdict and all.

The peer *list* is not the problem: `peer_homes` re-reads `stores.yaml` on every
dispatch, so declaring or removing a peer takes effect immediately. What is
frozen is each peer's opened reader and the answer to "could it be opened".

The comment beside the field says the opposite of what the code does:

> Peers that could not be opened during the last dispatch, for the caller to
> report. Reset per request, because a peer reindexed between two calls is no
> longer worth warning about.

`unavailable` is indeed rebuilt every dispatch — out of cached `Peer` objects, so
a peer reindexed between two calls is reported as unavailable exactly as before.

## Measured

Two scratch stores, A declaring B as a peer, B's index deleted so it opens
read-only and fails:

```
1. first read, through a daemon on A      Local decision
2. B repaired (docir reindex in B)        Peer decision   # B is readable now
3. same daemon on A                       Local decision
4. --no-daemon on A, same moment          Local decision, Peer decision
```

Step 3 against step 4 is the defect: one process reads the peer and the other
does not, at the same instant, against the same two stores.

## Why it matters

The same shape as issue-c2e8ce341a00, and the same reason it is worth fixing
rather than documenting: a federated read that silently returns fewer documents
is indistinguishable from a peer that has nothing to say. Federation exists to
read across stores, and the failure mode is that it quietly stops.

The other direction is cached too. A peer that was healthy at first contact keeps
its reader after the store behind it is migrated or removed, so what a later
request gets is whatever that engine does against a file that has moved on.

## What would fix it

**Cache only what opened.** A failed open is cheap — no engine, no schema load —
and it is the case the cache was never paying for. Retrying it each dispatch is
what the neighbouring comment already promises, and it fixes the measured
direction with no new state.

That leaves a successful peer's *schema* frozen for the daemon's life, which is
the peer-side version of issue-c2e8ce341a00 and much smaller: peers are
read-only, so a stale schema changes how rows project rather than what any write
is validated against. Keying the cache on the peer's schema digest and index
build stamp would close it, at the cost of two file reads per peer per dispatch.

Verify by injection: the four steps above as a subprocess test, asserting the
peer document's **title** comes back after the repair. A count cannot tell a
skipped peer from an empty one, which is the whole failure.
