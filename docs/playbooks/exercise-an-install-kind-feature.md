# Exercise a feature whose behaviour depends on the install kind

**When:** a change reads `Installation.method` and you must see it work against this repo's real store, which a checkout cannot show you.
**Instead of:** `uv tool install .`, which replaces the docir on the developer's PATH, or trusting the unit tests because the real command printed nothing.
**Status:** verified
**Last verified:** 2026-09-23

## Do
1. `uv venv "$SCRATCH/relenv" --python 3.12 && uv pip install --python "$SCRATCH/relenv/bin/python" .`
2. `touch "$SCRATCH/relenv/uv-receipt.toml"` — `detect()` checks the uv receipt **first**, so this
   classifies as `uv-tool` whatever else the environment looks like. For the other kinds: a
   `pipx_metadata.json` beside it is `pipx`, nothing plus a `pyvenv.cfg` is `pip`.
3. Confirm before testing anything else:
   `"$SCRATCH/relenv/bin/docir" --json self status` must print `"method":"uv-tool"`.
4. Run the real commands from the repo root, so the store is discovered normally:
   `"$SCRATCH/relenv/bin/docir" query --limit 1 >/dev/null 2>"$SCRATCH/err"`.
   Seed `.docir/release-check.json` with `{"latest":"99.0.0","checked_on":"<today>"}` to stand in
   for a published release; delete the file afterwards.

## Verify
`cat "$SCRATCH/err"` shows the notice for the venv build and is empty for `uv run docir` on the same
store, the same day, the same cached version. Both halves matter: only the pair shows the behaviour
is the install kind's and not the store's.

## Pitfalls
- The global option comes before the subcommand: `docir --json self status`, never `self status --json`.
- Announcing is a **write** — it records the version and day, so the second command of the day is
  silent by design. Bump `latest` in `release-check.json` between checks, or you will read a working
  throttle as a broken notice. Building the MCP server consumes that day's announcement too.
- `zsh` has MULTIOS, so `cmd 2>&1 >/dev/null | head` still shows stdout. Redirect stderr to a file.
- Delete `.docir/release-check.json` when finished; it is gitignored but it is also what the daemon
  reads next.
