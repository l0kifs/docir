---
code:
- scripts/cli_oracle.py
- tests/entry_points/test_agent_guide_matches_cli.py
code_baseline:
  scripts/cli_oracle.py: 5a45ddc6bd6e
  tests/entry_points/test_agent_guide_matches_cli.py: bef9c1ad70de
created: '2026-09-18'
description: cli_oracle had two extractors and they disagreed about fenced code, so
  a dead command name sat in an architecture note's worked example with every prose
  guard green.
id: issue-acff9cbd2b06
owner: maintainer
related:
- adr-354a4270ecd8
status: resolved
tags:
- docs
- testing
title: The retired-binary guard read inline spans and never a fenced block
type: issue
updated: '2026-09-18'
verified: '2026-09-18'
verified_code:
  scripts/cli_oracle.py: 5a45ddc6bd6e
  tests/entry_points/test_agent_guide_matches_cli.py: bef9c1ad70de
verified_content: fb85b5ddcaad
---

## What is wrong

`cli_oracle` extracts runnable lines from two places — fenced blocks and inline code
spans — and its two consumers disagreed about which. `invocations` read both.
`retired_binary_hits` had its own regex, `` `(docs) (word) ``, anchored on a literal
backtick, so it matched an inline span and never a fenced line.

A fenced block is the worst place to miss. An inline span is read inside a sentence; a
fenced block is copied wholesale.

## Measured

Found by reading [[arch-0368cc754c15]] against the code it governs, not by a guard. Its
worked example for `docir add` opened with `docs` instead — the name the CLI answered to
before the rename — inside a fenced block, continued across lines with a trailing
backslash. An agent copying it gets `command not found`.

The comment above `_RETIRED_BINARIES` records that the architecture documents once carried
96 of these and were swept. This was the survivor: the sweep and the guard both read spans,
and this one was in a fence. It is the only occurrence left in the corpus, which is why
nothing noticed it for months.

Every other surface was already clean. Widening the scan to fenced blocks across
`CLAUDE.md`, the `.claude/rules/` files, the project store, the packaged guide, every
`src/` docstring and the `CONTRACT.md` files produces **no** new findings — so the fix
costs nothing and the guard was simply not looking.

## What would fix it

One extractor. `command_lines(text)` yields every line the prose presents as runnable,
whatever program it names; `invocations` filters it to `docir`, `retired_binary_hits`
to a retired binary. Two scanners over the same surfaces is how one of them comes to
be reading less than the other with nothing saying so — the same argument
`index_is_empty` is shared by `check` and `doctor` for.

The second word still has to be a live subcommand, which is what keeps `docs/` and
`docs-schema.yaml` out (no space) and prose out too: "the docs query the index" is not
in a fence or a span.

## Resolution

FIXED 2026-09-18. `command_lines(text)` is the one extractor: every line the prose presents
as runnable, whatever program it names. `invocations` filters it to `docir`,
`retired_binary_hits` to a retired binary, and neither can come to be reading less than the
other with nothing saying so.

The scan widened and **found nothing new**. `CLAUDE.md`, the `.claude/rules/` files, the
project store, the packaged guide, every `src/` docstring and the `CONTRACT.md` files are
all clean — the one occurrence had already been corrected by the read that found it. So the
guard costs no exemptions and buys the next one.

Two injections, each proven to fail its guard: putting the dead line back into the fenced
example, and re-anchoring the regex on a literal backtick. The second fails the two unit
guards on the extractor itself rather than the corpus sweep, which is the point — a corpus
that happens to be clean cannot tell you whether the scanner is looking.

No exemption mechanism, deliberately. `DELIBERATELY_UNREAL` exists for a `docir` verb that
is rejected on purpose and still worth naming in prose; a retired binary has no such case,
because a line beginning with it resolves to nothing on any machine. This issue's own
evidence is written as a sentence rather than a fenced example for exactly that reason — the
guard caught the first draft, which is the cheapest possible confirmation that it works.
