---
created: '2026-08-31'
description: The read/write round trip on one section duplicates its heading, and
  no edit mode but --replace-body --force can undo it.
id: issue-9d4db5cd5f29
related:
- arch-3e305bc76ff0
- issue-d5f68b44b1d9
status: resolved
tags:
- cli
- material
title: get --section returns the heading, --replace-section writes it again — and
  nothing can remove the duplicate
type: issue
updated: '2026-08-31'
---

**Class:** missing · **Severity:** material
**Flow:** arch-3e305bc76ff0 · **Step:** `docir get <id> --section` → `docir update <id> --replace-section`

## Finding

`get --section` returns the heading line *and* the text under it. `--replace-section`
keeps the document's own heading line and writes what it is given *under* it. So the
obvious round trip — read a section, edit it, write it back — writes the heading twice,
and nothing validates the replacement text.

The CLI docstring invites exactly that round trip: "--section takes a heading and returns
that heading plus the text under it — the same span --replace-section would overwrite."
The span is the same for *locating*; it is off by the heading line for *writing*, and
nothing said so. `--append-section` has the identical hole in its content argument.

## What happens today

REPRODUCED end to end on a scratch store, seeded `## Notes` / `## Other`:

```
docir get <id> --section Notes
  body -> '## Notes\n\noriginal text\n'

docir update <id> --replace-section Notes --body-file <that text, edited>
  body -> '## Notes\n\n## Notes\n\nedited text\n\n## Other\n\ntail\n'
```

The duplicate cannot then be removed. `_locate_section` matches the *first* heading and
`replace_section` keeps that line by contract; `--append-section` adds a sibling (a third
run gave three `## Notes`). Only `--replace-body --force` — the riskiest edit mode, the
one with the divergence guard, the one the agent guide ranks last — can leave the state.
This is the shape of issue-d5f68b44b1d9 one level out: the safest body edit reaches a
state only the riskiest one can leave.

It gets worse on the second attempt. `--replace-section Notes` now writes into the
*first*, empty section and the real content stays stranded under the phantom heading:

```
docir update <id> --replace-section Notes --body "clean"
  body -> '## Notes\n\nclean\n\n## Notes\n\nedited text\n\n## Other\n\ntail\n'
```

The agent asked to replace `Notes` and the text it meant to replace survives untouched,
reported as success.

## Impact

Silent body corruption on the round trip the read path exists to enable — `context` ranks
a section, `get --section` reads it, `--replace-section` writes it back. Agents are the
likely victims: they compose the replacement from the span they just read, where it
carries its heading.

`docir check` sees nothing — a repeated heading is neither malformed frontmatter nor a
graph problem. `docir lint --deep` reports `ambiguous-heading` (issue-71555a89a73d), but
Tier 2 is advisory and after the fact, and it names no way out.

## Proposed direction

Two halves, because the second is what issue-d5f68b44b1d9 left out.

Refuse at Tier 0, on both write modes, when the replacement text *opens* with a heading
whose text repeats the one being written under, and let the error say to drop that line.
Narrow deliberately: text that merely mentions the heading later, or quotes it in a
fence, is legitimate. Stripping the line instead was rejected for the same reason
issue-d5f68b44b1d9 rejected it — it guesses at an intent the caller stated.

And add `docir update <id> --remove-section "<heading>"`, so a body that already carries a
duplicate has an exit that is not `--replace-body --force`. Repair was out of scope in
issue-d5f68b44b1d9 because one document was affected and `check --fix` repairs only what
needs no guess; that reasoning holds for automatic repair and not for giving the caller a
verb. Removal matches like every other section operation — first heading whose text
matches — so removing the second of two means running it twice.

## Resolution

FIXED, in both halves the filing asked for.

`append_section` and `replace_section` now refuse replacement text whose *first*
line is a heading repeating the one being written under, at Tier 0, and the error
names the flag and what to pass instead. Narrow on purpose: a section may open
with a sub-heading of its own, prose may name the heading further down, and a
fence may quote it — `scan_headings` already tells those apart, and all three
are pinned as tests. Stripping the line instead was rejected for the reason
issue-d5f68b44b1d9 gave: it guesses at an intent the caller stated.

`docir update <id> --remove-section "<heading>"` deletes a heading and everything
under it, on the CLI and as `docir_update(remove_section=)` over MCP. It is a
body edit mode like the others — at most one per call, resolved against the body
as it is on disk, so it composes with an out-of-band change and never needs the
divergence guard. It uses the same end boundary as `get --section`, and carries
no `#`-marker guard: `extract_section`'s reason turned around, a body that
already spells `## ## Resolution` has to be nameable to be repairable.

Removal resolves a repeated heading to the first, like every other section
operation, so taking out the second of two is the same command twice. Addressing
the later one would delete a span `get --section` never showed, which is the
divergence this module exists to prevent.

It takes no text, and a `--body` passed alongside it is **refused rather than
ignored**: `--remove-section X --body "..."` reads as "delete this text from X"
and would delete the whole section, consuming nothing. The check sits in the
`Dispatcher`, beside the one `_get` makes, because both transports fold `body`
into a mode and neither can be where a wire rule is decided — one check covers
the CLI and MCP. It fires only when nothing else would consume the text: naming
a writing mode as well is a different mistake with its own error, and answering
it with this one would blame the argument that is doing its job.

The `get --section` docstring no longer claims the read and the write are the
same span without qualification — they agree on where the section ends and
differ by the heading line, and that one line was the whole defect.

Verified by injection: disabling the round-trip guard fails four tests and leaves
the three "this is ordinary content" tests green; disabling the stray-body check
fails the CLI and MCP tests for it while the mode-conflict test stays green;
dropping `remove_section` from the MCP payload fails the MCP test, and dropping
it from the mode list fails the mutual-exclusion test.
