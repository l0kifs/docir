---
paths:
  - "tests/**"
---

# Testing

The suite is hermetic and the gate is 90%. The rule that actually catches things: a test that has never failed has not been shown to work.

Central `tests/` tree, organized to mirror the modules (**adr-909fc2a170d0** — tests are not yet co-located
inside `src/docir/modules/**`, a recorded deviation from §9):

```
tests/
├── conftest.py                 shared fixtures (see below)
├── modules/{documents,tags,indexing}/
├── platform/                   persistence · filesystem · embedding
├── config/
└── entry_points/               executor + the slow e2e CLI/daemon tests
```

- **Everything is hermetic via `conftest.py`.** The `settings` fixture points `DOCIR_HOME` at a
  `tmp_path`, forces `DOCIR_NO_DAEMON`, and clears `DOCIR_EMBEDDER`. `container`/`dispatcher` build
  the in-process object graph with a `FixedClock` (frozen date) and `background_embeddings=False` —
  so timestamps are deterministic and embeddings drain synchronously. `uow_factory` is the
  persistence-level seam; `seeded` gives you two tags + two related docs.
- Test through the seams the layer test-table prescribes: pure unit tests for `domain/`, the
  `dispatcher`/`container` fixtures for use cases and contract tests, real SQLite for `infra/`, and
  the `slow` subprocess tests for end-to-end. Prefer in-memory fakes over mocks for ports.
- Keep the regression-guard style: when a test pins a subtle bug, name the bug in a comment (e.g.
  `test_merge_safety.py` guards duplicate ids a branch merge produces).
- **Verify a new guard by injecting the bug it claims to catch.** Four defects here survived
  because a test asserted the existing behaviour was intended (`test_check_strict_gates_ci`
  pinned the unusable CI gate; `test_layering_violation` pinned the false positive), or because
  the test silently checked nothing — `test_agent_guide_matches_cli.py` reported 28 valid
  invocations while its regex, thrown off by ``` fences, was not extracting the one line it
  exists to catch. Each was found by running the tool as a user would, never by reading the
  suite. A test that has never failed has not been shown to work. Where a guard scans a
  corpus, also assert *which* items it found: a count cannot distinguish "nothing is wrong"
  from "nothing is checked".
- **`tests/entry_points/test_agent_guide_matches_cli.py` validates docir's own prose**
  against the Typer command tree, introspected from `cli.app` rather than shelled out. Seven
  sources: the packaged guide (every file of `modules/agents/infra/templates/skill/`, joined —
  a command moved into `reference/` has not stopped being documented) and `README.md`,
  which an *adopter* reads; `CLAUDE.md`, every file in `.claude/rules/**` (where three
  quarters of CLAUDE.md's prose now lives, loaded by `paths:` rather than at launch) and
  every file in `.docir/docs/**`, which an agent
  working in this repo reads; every docstring under `src/`, which 37 stale invocations
  survived in after the markdown side was clean; and the six `CONTRACT.md` files, which
  §8.6 forces to change whenever a module's public surface does — so they are the prose
  most likely to name a command on the day it moves. Any `docir ...` in a fenced block, an
  inline code span or an RST literal must resolve to a real command with real flags — so
  prose naming a command that does not exist must not be written in backticks. Three things are deliberate. A retired binary name
  gets its **own** check (`_RETIRED_BINARIES`), because a code span opening with the old name
  instead of `docir ` never reaches the extractor at all — that is how the architecture
  document reached 96 of them. (Naming one in prose here trips that check, which is why this
  sentence describes it instead of quoting it.) `_DELIBERATELY_UNREAL` exempts prose that names a verb *because it does
  not exist* (`docir import`, `docir repair`, `docir schema accept`), and every entry must
  still match something, so a shipped command cannot leave its exemption behind to shadow the
  real thing. And `--type`/`--status` **values** are checked against the core merged with
  *every* bundled profile (`TYPE_STATUSES`), not this store's resolved schema — whether
  `decision` has an `open` status is not a local choice, but which profiles are enabled is,
  so an example may name a `test_plan`. Resolving a command proves only its shape: a
  `--type decision --status open` filter parses, runs, and matches nothing forever.
- The coverage gate is **90%** (`--cov-fail-under=90`); `alembic/` and `fastembed.py` are omitted.
