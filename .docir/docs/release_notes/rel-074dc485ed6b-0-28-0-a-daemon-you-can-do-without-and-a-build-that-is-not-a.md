---
created: '2026-09-18'
description: 'Three reported defects closed, all the same shape: docir answering about
  something it had not looked at — a daemon it could not start, a file git already
  ignored, a generated file written once.'
id: rel-074dc485ed6b
owner: maintainer
related:
- adr-1d1eddbb6fbd
- adr-78090be868ec
- adr-c7ff45803a31
- issue-c4c6349e06d4
- issue-712f5bd17908
- issue-ec3819b1f13c
- issue-b9800d8265f6
- issue-c5c089bcc1b2
- issue-86bbaabd3944
status: published
tags:
- cli
- daemon
- release
title: 0.28.0 — a daemon you can do without, and a build that is not a change
type: release_note
updated: '2026-09-18'
---

Three reported defects, and all three were the same shape: docir answering confidently about a
thing it had not actually looked at. A daemon it could not start. A file the repository had
already said to ignore. A store whose generated file it had written once and never read again.

The full text is in `CHANGELOG.md` and on the release page. What follows is what neither can
carry.

## What the release is made of

- [[adr-1d1eddbb6fbd]] — a `code:` glob hashes what the repository tracks (GitHub #20,
  [[issue-ec3819b1f13c]]).
- [[adr-78090be868ec]] — where a downloaded embedding model lives ([[issue-c5c089bcc1b2]]).
- [[adr-c7ff45803a31]] — a document is the current state; git is the history.
- [[issue-c4c6349e06d4]] — a daemon that cannot be started runs in process (GitHub #15), and
  [[issue-b9800d8265f6]], the half of it that `doctor` and `daemon status` still crashed on.
- [[issue-712f5bd17908]] — the store's `.gitignore` is topped up by `self upgrade` (GitHub #21).
- [[issue-86bbaabd3944]] — a cached peer reader expires when that peer moves.

## Built and thrown away

**`pathspec`.** The gitignore engine shipped first as a dependency, and the dependency came back
out. Not for weight: hand-rolling the grammar was only defensible once correctness came from
`git check-ignore` instead of from a reading of `gitignore(5)`, and doing that immediately
caught an error the library version had — a file under an excluded directory cannot be
re-included, because git never descends into the directory to read the `!` that would bring it
back. A per-file matcher says it can, and hashes a build artifact. That is the whole defect,
reached through the fix for it.

**A Tier 2 lint finding for dated headings.** Refused rather than forgotten. The predicate would
key on a date or a word like "follow-up" in a `##`, and this corpus says that fires on correct
usage: `Resolution` is a terminal state and appears on 82 documents. Same shape as
`unresolved-mention`. `scope-creep` already fires on the documents in question and could name
the cause without inventing a predicate — that door is the cheap one and stays open.

**Re-minting `code_baseline` on `reindex`.** It would have made this upgrade silent. It would
also have handed anybody a way to clear a standing drift by upgrading, which is the laundering
[[adr-49bb8cc48938]] refused through `--set-code`.

## The instrument that was wrong

The writing rule shipped with a measurement taken by counting raw bodies against a flat 8,000.
`scope-creep` reads the *type's* `max_body_chars`, and this store sets `reference: 0` for never
([[issue-5d6a5e854d11]]) — so the three biggest documents, the ones the count named as worst,
are exempt by design. Corrected in the same release: 15 documents are over their own ceiling,
and 8 carried a dated heading, which is the signal the rule is about.

## Upgrading

`docir self upgrade`, then expect **one** `code-drifted` per pattern whose match set shrank.
Read the document against the code and `docir update <id> --verified`. Where the defect was live
that is every governed document, and the re-baseline is the fix arriving — the drift reported
before was false. Until a teammate upgrades, `code-drifted` is a per-build opinion in the
direction where the older build over-reports; nothing refuses anything either way.

The embedding model is re-downloaded once, into `~/.docir/models`. It is the last one a temp
sweep can force. `self upgrade` also tops up the store's `.gitignore` with `release-check.json`
and `models/`, and names what it added.
