# Race first commands on a fresh worktree

**When:** a change touches what opening a store does (migrations, bootstrap, daemon startup, the write lock) and racing first commands must all succeed.
**Instead of:** hand-building a scratch repository and N documents, spawning background commands with sleeps, and grepping stderr and `daemon.log` for tracebacks, once per build and mode.
**Status:** verified
**Last verified:** 2026-10-21

## Do
1. `bash docs/playbooks/scripts/race_first_open.sh 500 2 0.3` — the workspace build, `--no-daemon`, two `get` 0.3s apart.
2. Widen it as the change needs: `... 500 6 0` for six at once; `... 2000 4 0` for a bootstrap longer than the 5s busy timeout; `DAEMON=1 ...` for the daemon path.
3. To see the defect on the release users have: `DOCIR_BIN=~/.local/bin bash docs/playbooks/scripts/race_first_open.sh ...`.

## Verify
Last line `PASS: <K> first commands, <N> documents` and exit 0. Any non-zero command or an `...Error:` line from stderr or `daemon.log` prints `FAIL (<scratch dir>)` and exits 1; the scratch dir keeps each command's stderr.

## Pitfalls
- The window is the first command's bootstrap. With a handful of documents it is too short to race; 500 made 0.30.3 fail at every gap from 0.1s to 0.5s.
- Shorter gaps race the migration, longer ones the bootstrap, and the boundary moves between runs (0.30.3 lost either race at 0.3s). Run a few gaps, or `K` at `STEP 0`, before calling one path covered.
- Build times swing ±30% run to run on this machine (disk-bound), so compare a K-way race against a lone run several times, alternating, before calling anything a slowdown.
- Over the daemon a lost race never reaches the client: the second daemon dies at startup and the survivor answers both. Only `daemon.log` shows it, which is why the script greps it.
