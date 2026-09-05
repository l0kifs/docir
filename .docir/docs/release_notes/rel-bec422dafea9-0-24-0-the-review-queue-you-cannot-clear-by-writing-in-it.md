---
created: '2026-09-05'
description: 'What shipped in 0.24.0: a verification that is withdrawn when its content
  moves, a way to take a stamp back, and the two queues that emptied themselves.'
id: rel-bec422dafea9
owner: maintainer
related:
- adr-f4e6ade4afd0
- adr-fad49eaa4648
- adr-e98749aa457d
- issue-b4813930bfca
- issue-6726eabcf871
- issue-77a09761e1d4
- issue-38a4f13b1e61
- adr-ab4598c6f707
status: published
tags:
- integrity
- staleness
- cli
title: 0.24.0 — the review queue you cannot clear by writing in it
type: release_note
updated: '2026-09-05'
---

The review queue only works if the clock is honest, and three ways of lying to it turned up in
one week. Writing into a document took it off the queue. A judgement about an orphan cleared the
orphan. And a verification, once stamped, outlived the document it vouched for — nothing
withdrew it, not the edit that made it untrue and not the person who stamped it by mistake.

## Upgrade notes

- **Editing a verified document withdraws the verification.** Change its title, description or
  body and `verified` is erased, `revoked` is stamped, and the review cadence restarts from that
  day. Pass `--verified` with the edit when you rewrote it *and* re-read it. A status, tag,
  type, edge, `owner`, `isolated` or `code` change is not a content edit and keeps the stamp.
- **The staleness clock no longer reads `updated`.** It runs from `verified`, else `revoked`,
  else `created`. On a corpus whose documents are edited more often than their cadence this
  reports more documents than 0.23.0 did — correctly: those are the ones nobody has confirmed.
- **`orphan` no longer reads prose.** A document whose id is only *mentioned* in another body
  reports as an orphan again. Give it an edge, or record why it stands alone.
- **Two new frontmatter keys**, `revoked:` and `verified_content:`, plus `isolated:`. An older
  docir reads a store carrying them without refusing, but drops the keys when it writes.
- **Run `docir reindex` after upgrading**, or `docir self upgrade`, which does it for you.

## Taking a verification back

A `verified:` line could be set and never unset, so correcting one meant the hand-edit the CLI
exists to prevent — which `docir check` then reported as a hand-edit.

```
docir update <id> --clear-verified
```

It erases the stamp and records no revocation, so the document ages from `created` again: a
claim nobody made earns no review window, and a bad stamp that had nearly run out returns to the
queue instead of buying a fresh cadence. Refused when no verification is standing, and refused
alongside `--verified`.

## A verification does not outlive what it covered

An edit to the title, description or body of a verified document withdraws the verification and
stamps `revoked`, and the cadence restarts there — the text somebody read is not the text that
is there now. Only a *standing* verification can be revoked, so writing into a document nobody
vouched for still moves nothing: one verification buys one reset, and buying it costs a
verification.

```
docir update <id> --replace-section "Context" --body "..." --verified
docir query --expr "revoked"
```

`--verified` also digests the text it covered, and `docir check` reports `verification-outdated`
for a stamp left standing over text the CLI never saw move — a hand-edit, a merge resolved into
the body, or a teammate on a build that predates revocation. Keyed on that digest and never on
`updated`, which a status or a tag moves without touching a reviewed word.

## The two queues that emptied themselves

`docir query --stale` fell back to `updated` for a document with no `verified`, and every edit
moves `updated` — so the body an overdue document most reliably gets, the re-check saying it is
*still* unanswered, was what ended the report of it.

`orphan` read the derived mention graph as well as `related:`, so an id named anywhere in any
body cleared it. An orphan triage is a list of orphan ids, so writing one closed every orphan in
it. Reported on a 418-document corpus where 12 orphans became 0 and 4 were genuinely unwired.
The judgement a mention was standing in for is now recorded instead:

```
docir update <id> --set-isolated "scope deferred; nothing depends on it yet"
docir query --expr "isolated"
```

## Also

- `docir doctor` reports `index-from-newer-build` as its own error finding, naming both real
  answers — run the newer docir, or delete the index and reindex.
- An index built by a newer docir is refused by name (exit 8) instead of a raw Alembic
  traceback out of every command.

## Measured and rejected

- **Ageing staleness from `verified` alone**, treating an absent stamp as infinitely stale. It
  reports 83 of this store's 84 cadence-bearing documents, ones written the day before included.
- **Falling back to `created` after a revocation.** No new field, but it reports a document
  overdue the instant an edit lands, which makes verifying a document that is still being
  written strictly worse than never verifying it.
- **Keying the new finding on `verified < updated`.** A status or a tag moves `updated` without
  touching a reviewed word, so it fires on the ordinary life of a correctly verified document.

## Full changelog

See [CHANGELOG.md](https://github.com/l0kifs/docir/blob/v0.24.0/CHANGELOG.md).
