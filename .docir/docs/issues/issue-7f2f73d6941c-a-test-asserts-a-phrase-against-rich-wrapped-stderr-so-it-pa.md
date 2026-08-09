---
code:
- tests/entry_points/test_e2e_build.py
- tests/conftest.py
created: '2026-08-09'
description: test_an_empty_store_says_so holds or fails on where rich broke the line,
  which depends on the tmp path inside the message.
id: issue-7f2f73d6941c
owner: maintainer
related:
- adr-b2cfed9d5888
status: resolved
tags:
- testing
- cli
title: A test asserts a phrase against rich-wrapped stderr, so it passes on path length
type: issue
updated: '2026-08-09'
---

`tests/entry_points/test_e2e_build.py::test_an_empty_store_says_so` asserts a
phrase against stderr that rich rendered:

    assert "docir reindex" in str(result.stderr), "the fix was not named"

Under `CliRunner` the output is not a terminal, so rich takes its width from
`COLUMNS` and otherwise falls back to 80. The warning embeds the store path, so
the wrap lands wherever that path length puts it:

    warning: no documents found in
    /tmp/pytest-of-serj/pytest-1/test_an_empty_store_says_so0/docir — the site will
    be empty. The index is derived and gitignored, so a fresh clone needs `docir
    reindex` first.

The phrase is there and a newline sits inside it. The same test passes at
`COLUMNS=200` and fails at 80.

## Why it stayed hidden

Nothing about the message or the command changed. The break position is a
function of the temp directory pytest happened to name, so whether the assertion
holds depends on the length of a path — CI has been green since the test landed,
which is luck rather than evidence. A runner path a few characters longer or
shorter moves the break onto a different word.

This is the failure mode the project's own testing note describes: a test that
has never failed has not been shown to work. Here it is the inverse — a test
that failed locally while proving nothing about the code.

## The same class, elsewhere

- `tests/entry_points/test_e2e_cli.py:491` — `"prefix 'adr' -> 'dec'"`, four
  tokens, breakable the same way.
- `tests/entry_points/test_e2e_schema.py:121` — `"nonsense"`, a single token, so
  it can only break if it exceeds the whole width.

## Fix

Pinning `COLUMNS` from a fixture does **not** work: rich reads that variable in
`Console.__init__`, and `entry_points/cli/rendering.py` constructs its two
consoles at import time — long before any fixture runs. The width has to be set
on the console objects themselves, where `monkeypatch.setattr` also restores it
afterwards.

Wide is not the same as *wider*, either. A larger width only moves the break:
rendered at every width from 50 to 205, this message splits `docir reindex` at 19
of them, including 79-81 and 187-195. The pin is 500 — past the length of any
notice docir prints, so they do not wrap at all.
