<!-- Mechanics are in CONTRIBUTING.md. This template is the short version. -->

## What this changes

<!-- One or two sentences. Link the issue if there is one. -->

## Why

<!--
The constraint or bug that made this necessary. If a decision in docir's own store is
relevant, name it by id (`adr-...`) — `docir context "<what you changed>"` finds it.
-->

## Checks

- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `uv run ty check`
- [ ] `uv run vulture`
- [ ] `uv run tach check` — exits 0 (the `[WARN] ... deprecated` lines are the baseline)
- [ ] `uv run python scripts/check_contract_sync.py`
- [ ] `uv run pytest --cov=docir --cov-fail-under=90`

## If it applies

- [ ] **Changed an `api.py`** — its `CONTRACT.md` changed in the same commit
- [ ] **Added a design deviation** — recorded as a decision (`docir add --type decision`),
      never as a hand-edited markdown file
- [ ] **Touched ranking, chunking or the embedder** — benchmark numbers before and after are
      quoted below. `benchmarks/run.py` for retrieval, `benchmarks/chunking.py` for a
      splitter change
- [ ] **Added a guard or a check** — verified by injecting the bug it claims to catch, and
      it asserts *which* items it found rather than how many
- [ ] **Changed a command or a flag** — the README, the packaged agent skill and the
      relevant `CONTRACT.md` name it correctly (the prose tests gate on this)

<!--
Not on this list and never acceptable: a new `platform -> module` edge, a new cross-module
edge, or a `tach-ignore`. Route through the module's api, move the shared thing into
platform, or say in the PR why neither works.
-->

## Benchmarks / output

<!-- Paste before-and-after numbers, or the command output that shows the fix. -->
