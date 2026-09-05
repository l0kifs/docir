---
created: '2026-09-05'
description: Why a content edit revokes a verification, why the cadence restarts from
  the revocation rather than from creation, and why only a standing verification can
  be revoked.
id: adr-f4e6ade4afd0
owner: maintainer
related:
- kind: refines
  to: adr-bd7c4f3c5764
- kind: refines
  to: adr-fad49eaa4648
- issue-b4813930bfca
- adr-d9e6d5ccd0b4
status: accepted
tags:
- integrity
- schema
- cli
title: A verification is withdrawn when the content it covered moves
type: decision
updated: '2026-09-05'
---

## Context

adr-bd7c4f3c5764 made staleness data: an optional `verified` date, a per-type `review_days`
cadence, and a pull-based review queue. adr-fad49eaa4648 fixed the clock it ages on — `verified`,
else `created`, never `updated`, because `updated` moves on every edit and the queue emptied
itself the moment somebody wrote in a document (issue-6726eabcf871).

Both left one gap. A verification, once stamped, was permanent. Nothing withdrew it — not a
mistake (issue-b4813930bfca), and not the edit that made it untrue. A document could be verified
on Monday, rewritten on Tuesday, and still read `verified: Monday` for the rest of its cadence.
The stamp says *somebody read this*; after a rewrite, what they read is not what is there.

## Decision

A verification is withdrawn when the content it covered moves, and a new frontmatter field
records when. `Document.revoked` is the date a **standing** verification stopped being true, and
`stale_reference_date()` reads `verified`, else `revoked`, else `created`.

A content edit performs the withdrawal — `--set-title`, `--set-description`, or any body mode:
exactly what `content_changed` already tracks for the embeddings, the text a reviewer reads.
`--verified` in the same call wins and clears `revoked`; it is the ordinary "I rewrote it and
re-read it". A status, type, tag, edge, `owner`, `isolated` or `code` change is not a content
edit and leaves the verification standing — none of them changes a word of what was reviewed,
and a status is the first thing that moves on a document somebody has just finished reviewing.

The cadence **restarts from the revocation** rather than falling back to `created`. A revoked
document is not one nobody ever vouched for: somebody did, and the edit is what made the claim
stale. Ageing it from `created` reports it overdue the instant the edit lands, on any corpus older
than its cadence — the failure adr-fad49eaa4648 measured on the other clock and rejected.

`docir update <id> --clear-verified` is the second way to withdraw one, and it is deliberately
**not** the same write. It erases the stamp and records no `revoked` at all, so the document
ages from `created` again, exactly where a never-verified one sits. The two say different
things: an edit says "this was true and the content moved", and earns a restarted cadence; a
withdrawal says "this was never true", and a claim nobody made earns nothing. Granting it a
window would mean that taking back a stamp which had nearly run out pushes the document's due
date *further away* than leaving the wrong stamp in place — the opposite of what
issue-b4813930bfca asks for.

Only a standing verification can be withdrawn, and this is the load-bearing half. A document
with no `verified` has nothing to take back: the automatic path leaves its clock alone, and
`--clear-verified` is **refused** rather than treated as idempotent, so neither can manufacture
review state. One verification buys one reset, and buying it costs a verification.

`verified_content` closes the gap the write path cannot see. `--verified` records a digest of
the title, description and body it covered — hashed from the document the write *produces*, so
verifying alongside a rewrite records the rewrite — and `docir check` reports
`verification-outdated` when the file no longer matches: a hand-edit, a merge resolved into the
body, or a teammate on a build that predates revocation. Three rules make it usable. The
predicate is the digest and **not** `verified < updated`, which was the obvious one and fires on
the ordinary life of a correct document, since a status or a tag moves `updated` without
touching a reviewed word. An empty digest is *unknown*, so every stamp older than the field is
silent and the finding does not arrive announcing that the corpus rotted overnight. And both
withdrawal paths clear it, because a digest under no claim is evidence of nothing. It is a
warning, cleared by re-reading and stamping again or by withdrawing the claim; `check --fix`
does neither, having nothing to read *with*.

The `verified_code` digests, by contrast, are **kept** across a revocation. They record what the
code looked like at the last real review, and `code-changed` asks a question the reset calendar
does not: whether the code has moved since somebody read the document. The combination
adr-d9e6d5ccd0b4 forbids is the opposite one — an old digest under a *fresh* `verified` date,
which claims a review covered code it never saw.

## Alternatives considered

**Erase `verified` and fall back to `created`.** No new field, no migration, no cross-version
surface, and semantically the plainest reading — after a revocation the document is exactly where
an unverified one sits. Rejected on the number adr-fad49eaa4648 measured: this store's documents
are younger than their cadences but older than a week, so the first content edit after a
verification would report the document overdue on the spot. A warning that fires on the product's
own workflow is issue-40d1792bc9f9's shape, and it makes verifying a document that is still being
written strictly worse than never verifying it.

**Keep the old due date and report the lost verification as its own finding.** The calendar never
moves; `check` grows a `verification-withdrawn` warning. Rejected as the same information twice:
`stale` already exists to say "nobody has vouched for this recently", and a second finding on the
same fact splits the review queue across two reports.

**Revoke on any edit, not only a content one.** Simpler to state and impossible to keep: a
document's status changes when it is reviewed, so the stamp would be withdrawn by the write that
records the review.

## Consequences

- A verified document that is edited leaves the queue for a fresh cadence. That is a grace
  window, and it is the deliberate cost of not reporting every edited document immediately.
  `--verified` alongside the edit is how a reviewer keeps the original claim.
- Withdrawing a stamp by hand grants no window, so the reporter's two documents return to the
  review queue the moment the claim is taken back, rather than a cadence later.
- The corpus is not rewritten retroactively. A stamp made before this release carries no
  digest, so `verification-outdated` is silent on it and it self-heals on the document's next
  content edit; anything known to be wrong is withdrawn by hand.
- `revoked:` and `verified_content:` are new committed fields. An older docir reads them as
  unknown keys and ignores them, but rewrites the file without them — so a teammate on 0.23.0
  editing such a document silently drops both, and the clock falls back to `created`. That
  direction is safe (the document becomes *more* suspect, never less), which is what makes this
  additive rather than a break by adr-ab4598c6f707's test. Measured: 0.23.0 reindexed a copy of
  this store carrying both fields with 203 documents and 0 skipped, and `check --strict` /
  `doctor --strict` exited 0.
- Two builds reading one store disagree about `stale` for a revoked document, silently — the
  same consequence adr-fad49eaa4648 recorded, by the same mechanism, and it resolves the same
  way: when everyone upgrades.
- `revoked` joins the `--expr` projection, so `docir query --expr "revoked"` is the audit of
  which verifications a corpus has lost and when. `verified_content` deliberately does not: it
  is bookkeeping for one check, as `verified_code` is, and neither belongs on a read view.
