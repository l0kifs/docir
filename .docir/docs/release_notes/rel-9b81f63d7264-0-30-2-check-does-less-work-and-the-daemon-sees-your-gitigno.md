---
created: '2026-10-17'
description: docir check does ~40% less work and every command starts ~0.1s sooner
  with identical output, and a .gitignore edit now reaches check through the daemon.
id: rel-9b81f63d7264
related:
- issue-9509f9fa3631
- issue-3a505835cd7e
- ref-71c621c5532f
- arch-0a3c2d6d54a6
status: published
tags: []
title: 0.30.2 — check does less work, and the daemon sees your .gitignore
type: release_note
updated: '2026-10-17'
---

## 🎯 The release

**`docir check` does ~40% less work, every command starts ~0.1s sooner, and the daemon sees a
`.gitignore` edit.**

A warm read was mostly the client starting Python, and `check` was the slowest command agents
run often. Both were measured before anything changed, every speed-up leaves the output
byte-identical, and the one behaviour change is a fix.

## ⚡ Faster

Measured on docir's own store (266 documents, 1,947 vectors, 124 governed globs), interleaved
against 0.30.1's source:

| | 0.30.1 | 0.30.2 |
|---|---|---|
| `docir version` (process start, p50) | 0.585s | 0.487s |
| warm `docir context`, daemon side | 95ms | 44ms |
| warm `docir check`, daemon side | 789ms | 477ms |
| `docir --no-daemon check`, whole process | 1.91s | 1.40s |

- **Every command starts sooner.** The client imported the docs watcher and the site builder
  for every command; they now load only in `docir daemon serve` and `docir build`. 704 modules
  at startup become 570.
- **`context` scores its vectors ~8x faster.** The cosine scan runs on `math.sumprod`: ~60ms
  becomes ~7ms over 1,947 vectors, and `docir lint --deep` drops from 2.09s to 1.12s. No new
  dependency.
- **`check` walks each code glob once and reads the corpus once.** A `**` glob used to walk a
  file once per directory level above it, and four file checks each parsed every document.
  A governed directory holding `node_modules` or `target/` is no longer walked file by file.

## 🐛 Bug fixes

- **An edit to `.gitignore` reaches `check` through the daemon.** Since 0.28.0 the daemon read
  the ignore files once, at start, so after an edit it kept fingerprinting `code:` globs under
  the old rules — no `code-drifted` where `docir --no-daemon check` reported one — until it was
  replaced. The rules are now read afresh for every command, at ~10ms of the speed-up above.

## 📏 Measured and rejected

- **numpy for the vector scan** — converting the decoded vectors costs more than `sumprod`'s
  whole scan.
- **One `.gitignore` index per pattern** — +205-251ms per `check`; one per command is ~10ms.

## ⬆️ Upgrading

- Nothing to run for the speed-ups, and the daemon is replaced on the first command after the
  upgrade. The packaged skill is unchanged; `docir agent update` only re-stamps its version.
- If you edited a `.gitignore` while a daemon on 0.28.0-0.30.1 was running, a `--verified`
  or a new `--code` glob written through it may hold a digest the current rules disagree
  with. `docir check` reports it as `code-changed` or `code-drifted`; read the document
  against the code, then `docir update adr-0001 --verified`.

## 🔗 Full changelog

See [CHANGELOG.md](https://github.com/l0kifs/docir/blob/v0.30.2/CHANGELOG.md)
