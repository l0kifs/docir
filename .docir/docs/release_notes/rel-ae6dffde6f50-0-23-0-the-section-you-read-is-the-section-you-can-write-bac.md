---
created: '2026-08-31'
description: The read/write round trip on one section stopped duplicating its heading,
  and --remove-section became the exit for a body that already has one.
id: rel-ae6dffde6f50
related:
- issue-9d4db5cd5f29
- issue-d5f68b44b1d9
- issue-71555a89a73d
- arch-0368cc754c15
- adr-7d9fbbf976e8
status: published
tags:
- cli
- docs
title: 0.23.0 — the section you read is the section you can write back
type: release_note
updated: '2026-08-31'
---

Reading a section and writing it back is the round trip the section read path exists to
enable — `docir context` ranks a document on one of its sections, `docir get --section`
reads it, `docir update --replace-section` writes it back — and it corrupted the document.
The read returns the heading line; the write supplies its own. So the obvious sequence
spelled the heading twice, and from there nothing could take the second one out.

## Upgrade notes

- **`--replace-section` and `--append-section` now refuse text that opens with the heading
  they are writing under.** A script that pipes `docir get --section X` straight into
  `docir update <id> --replace-section X` will start failing, with an error naming what to
  pass instead: drop the heading line, the flag writes it. This is exactly the round trip
  that was producing duplicates silently, so a failure here means the script was corrupting
  documents.
- **`docir update <id> --remove-section "<heading>"` is new**, and takes no `--body` —
  passing one is refused rather than ignored.
- **Nothing else changes.** A body that does not repeat a heading writes exactly as before.

## 🐛 A section read could be written straight back as a duplicate heading

`docir get <id> --section "Decision"` returns the heading line and the text under it.
`docir update <id> --replace-section "Decision"` keeps the document's own heading line and
replaces only what is beneath it. The two agree on where a section ends and differ by that
one line — and nothing said so. The `docir get` help called it "the same span
`--replace-section` would overwrite".

So an agent that read a section, edited it and wrote it back produced two `## Decision`
lines, reported as success. The second attempt was worse: `--replace-section` matches the
*first* heading, so it wrote into the now-empty first section and left the real content
stranded under the phantom one. The text the caller meant to replace survived untouched.

Nothing caught it. `docir check` sees neither malformed frontmatter nor a graph problem, and
`docir lint --deep`'s `ambiguous-heading` advisory arrives after the fact and names no way
out. `--replace-section` keeps the heading line by contract and `--append-section` adds a
sibling, so the only exit was `docir update <id> --replace-body --force` — the riskiest edit
mode, the one with the divergence guard, the one the agent guide ranks last. The safest body
edit reached a state only the riskiest one could leave.

Both writing modes now refuse, at Tier 0, replacement text whose **first** line is a heading
repeating the one being written under. Deliberately narrow: a section may open with a
sub-heading of its own, prose may name the heading further down, and a fence may quote it —
all three stay legal and are pinned as tests. Stripping the line instead was rejected for
the reason the same shortcut was rejected once before: it guesses at an intent the caller
stated.

## 🎯 `docir update <id> --remove-section "<heading>"`

The repair path a duplicated heading never had. It deletes a heading and everything under
it, on the CLI and as `docir_update(remove_section=)` over MCP.

It is a body edit mode like the others: at most one per call, and resolved against the body
as it is on disk, so it composes with an out-of-band change and never needs the divergence
guard. It uses the same end boundary as `docir get --section` — a nested subsection goes
with its parent, a heading quoted in a fenced block is not one — and it carries no
`#`-marker guard, because a body that already spells `## ## Resolution` has to be nameable
to be repairable.

A repeated heading resolves to the first, here as everywhere, so removing the second of two
is the same command run twice:

```bash
docir lint --deep                              # names the documents that have one
docir update adr-3f9a2b1c7d4e --remove-section "Notes"
```

A `--body` passed alongside it is refused, not ignored: `--remove-section X --body "..."`
reads as "delete this text from X" and would delete the whole section while consuming
nothing. That check sits at the dispatcher, so one rule covers the CLI and MCP, and it fires
only when no writing mode would consume the text — naming two modes still answers "only one
body edit mode" rather than blaming the argument doing its job.

## 🔗 Full Changelog

See [CHANGELOG.md](https://github.com/l0kifs/docir/blob/v0.23.0/CHANGELOG.md)
