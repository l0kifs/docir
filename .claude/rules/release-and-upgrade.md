---
paths:
  - "src/docir/modules/release/**"
  - "src/docir/entry_points/doctor.py"
---

# Release detection and `docir self upgrade`

This is the one place docir acts on its own process, so the ordering rules are the feature.

- **The index records which docir built it, and `docir self upgrade` is the command that
  acts on it (adr-31aa7aa60d11).** Migration `0006` adds the one-row `index_build` table,
  written by `reindex` and nothing else — the same single-writer rule the schema baseline
  follows, for the same reason. It is a *separate* table on purpose: the baseline payload is
  diffed line by line and printed, so a version key inside it would render every upgrade as a
  schema change, and the baseline cannot answer this question anyway — it compares schemas, so
  it is silent for a release that changes how documents are *read* (adr-927aa43d9635 rewrote
  every vector without touching a type or a cadence). `stale-index-build` fires on
  **inequality**, not "older than": a downgrade needs the same rebuild. Absent means unknown,
  so a store not rebuilt since the table arrived reports nothing. `self upgrade` runs
  reindex → `agent update` → check in that order (check last, so the findings describe the
  state it left) and **must not gain the package install**: this process is the code that
  would be replaced, so the rebuild after it would stamp the version on its way out. It is a
  `self` group because `docir update <id>` already means "edit a document", and it is not an
  MCP tool — the halves it orchestrates already are.

- **The package half of `self upgrade` re-execs, and refuses to guess (adr-a555ee6bc484).**
  The installer runs only where docir owns its environment — a `uv tool` receipt, pipx
  metadata, a `pyvenv.cfg` — and then `os.execv`s `python -m docir` with a hidden
  `--upgraded-from` (which is also the loop guard), because the process that ran the installer
  is the old build and the reindex after it must not be. A checkout or path install
  (PEP 610 `direct_url.json`), an ephemeral `uvx` env, or anything unrecognised gets no
  command and a reason; the store is still resynced. **The test suite is structurally safe
  because it runs from an editable checkout, which detects as `project`** —
  `test_installation.py` asserts exactly that, and it is the guard that keeps a test from
  replacing the environment it runs in. The release check is opt-in
  (`DOCIR_UPDATE_CHECK=1`), fetched by the daemon at most once a day and *only* read by the
  CLI, so no command ever blocks on the network; `latest` absent means nobody has checked,
  never "up to date"; ordering is `packaging`'s PEP 440, since a hand-rolled compare makes
  0.9.0 newer than 0.10.0.
