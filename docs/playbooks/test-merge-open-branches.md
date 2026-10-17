# Test-merge two open branches before either lands

**When:** two open PRs touch the same files and you need to know they merge, and pass, together before the first one lands.
**Instead of:** merging one, rebasing the other, and meeting the conflict or the broken combination in CI after the first is already on `main`.
**Status:** verified
**Last verified:** 2026-10-17

## Do
1. `git merge-tree --write-tree --name-only <branch-a> <branch-b>` — exit 0 merges clean; exit 1 lists the conflicted files under the tree id.
2. `git worktree add -q --detach /tmp/merge-check <branch-a>`, then `git -C /tmp/merge-check merge --no-edit <branch-b>`. Resolve any conflict there and commit; the commit is detached and thrown away with the worktree.
3. Run the suite on the merged tree with this repo's interpreter, from the worktree:
   `cd /tmp/merge-check && PATH=<repo>/.venv/bin:$PATH PYTHONPATH=/tmp/merge-check/src <repo>/.venv/bin/python -m pytest -q -p no:tach -p no:cacheprovider`
4. `git worktree remove --force /tmp/merge-check`, and write the resolution into the second PR's body so whoever merges it can repeat it.

## Verify
pytest exits 0 on the merged tree, and `git worktree list` afterwards shows only the main checkout.

## Pitfalls
- Leave `.venv/bin` off PATH and `tests/modules/release/test_adapters.py` fails with exit 127: it runs a bare `python`, which `uv run` would have put on PATH. That is the environment, not the merge.
- `uv run` inside the worktree builds a second venv for it; `PYTHONPATH` on the repo's interpreter outranks the editable install instead. Confirm with `python -c "import docir; print(docir.__file__)"`.
- Nothing here pushes. The merge commit exists only in the worktree, which is the point: neither branch changes until one of them lands.
