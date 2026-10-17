---
created: '2026-10-17'
description: agent update, agent install and self upgrade no longer let an older docir
  replace agent files a newer build wrote; they keep them, warn, and write them only
  with --force.
id: rel-21abb0e54631
related:
- issue-af3f335688f4
- issue-f0b537bde01a
- adr-3a2d5ee7bc84
status: published
tags: []
title: 0.30.3 — an older docir keeps the agent files a newer one wrote
type: release_note
updated: '2026-10-17'
---

## 🎯 The release

**An older docir keeps the agent files a newer one wrote, instead of quietly replacing them.**

`docir agent update` regenerated every agent file from the running build's templates, whatever
the file's version stamp said. In a shared repository that meant a teammate one release behind
could replace the skill a newer build had written with older text — and `docir self upgrade`
did the same whenever its install step did not move the version. Both reported `updated` and
exited 0.

## 🐛 Bug fixes

- **A file a newer docir wrote is kept, not downgraded** (issue-af3f335688f4). Its row says
  `kept` and names the version that wrote it, a warning on stderr says what to do, and nothing
  in the skill directory is written or deleted. This applies to `docir agent install`,
  `docir agent update` and `docir self upgrade`. Upgrade docir and run the command again; only
  when the older text is what you want — a repository pinned to an older release on purpose —
  write it anyway:

  ```bash
  docir agent update --force
  ```

  An absent or unparseable stamp is written over as before, and versions are ordered as PEP 440,
  so `0.10.0` is newer than `0.9.0`.

## ⬆️ Upgrading

- The guard lives in the build that runs the command, so **releases before this one still
  overwrite**. Upgrade every machine that refreshes a shared repository's agent files, then run
  `docir agent update` so the installed skill explains a `kept` row.
- If an older build already downgraded your skill, `git log -p .claude/skills/` shows when;
  `docir agent update` from this release writes the current text back.
- A uv tool installed with an exact version pin is one `docir self upgrade` cannot move — it
  says so and quotes the installer. Reinstall it the way the installer's hint names, then run
  `docir self upgrade --no-package`.

## 🔗 Full changelog

See [CHANGELOG.md](https://github.com/l0kifs/docir/blob/v0.30.3/CHANGELOG.md)
