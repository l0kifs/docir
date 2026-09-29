#!/usr/bin/env bash
# Point the newest release and the workspace build at each other's stores (adr-ab4598c6f707).
#
#   bash docs/playbooks/scripts/release_compat.sh <released-version>
#
# Half 1: the released build reads THIS repo's store, which the workspace build indexed.
# Half 2: a scratch store the released build creates is written by the workspace build
#         (repeated list flags, a code glob), then reindexed and read back by the released one.
# A refusal is the break (a non-zero exit, a rejected file); a warning the older build cannot
# name is not, so findings are printed for reading and never fail the run.
set -u
REL=${1:?usage: release_compat.sh <released-version, e.g. 0.29.0>}
REPO=$(git rev-parse --show-toplevel) || exit 2
NEW="$REPO/.venv/bin/docir --no-daemon"          # the workspace build, after `uv sync`
OLD="uvx --from docir==$REL docir --no-daemon"   # the release adopters already have
SCRATCH=$(mktemp -d "${TMPDIR:-/tmp}/docir-compat.XXXXXX")
export DOCIR_UPDATE_CHECK=0                      # no PyPI call and no announcement write
fail=0
run() { # <label> <cmd...>: run, keep stdout for the caller, report a refusal
  local label=$1; shift
  if ! "$@" >"$SCRATCH/out" 2>"$SCRATCH/err"; then
    echo "REFUSED  $label: $(tail -1 "$SCRATCH/err")"; fail=1; return 1
  fi
  echo "ok       $label"
}
kinds() { python3 -c 'import json,sys; print("         findings:", sorted({f["kind"] for f in json.load(open(sys.argv[1]))}))' "$SCRATCH/out"; }

echo "== $REL reads this repository's store"
cd "$REPO" || exit 2
run "context" $OLD context "why is the index shared across modules" --limit 3
run "query"   $OLD query --type decision --limit 2
run "search"  $OLD search "daemon socket" --limit 2
id=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[0]["id"])' "$SCRATCH/out" 2>/dev/null)
run "get $id" $OLD get "$id"
run "doctor --strict" $OLD doctor --strict
run "check --strict"  $OLD check --strict && kinds

echo "== a store $REL creates, written by the workspace build, read back by $REL"
export DOCIR_EMBEDDER=deterministic              # the scratch store needs no model
store="$SCRATCH/store"; mkdir -p "$store/src" && echo x >"$store/src/a.py" && cd "$store" || exit 2
run "$REL init" $OLD init
printf '## Context\n\nOld build.\n' | run "$REL add" $OLD add --type decision --title "Old build" --description "by $REL" --code "src/**" --stdin
run "new reindex" $NEW reindex
run "new tag add" $NEW tag add x --description x && run "new tag add" $NEW tag add y --description y
printf '## Context\n\nNew build.\n' | run "new add" $NEW add --type decision --title "New build" --description "by the workspace" --tags x --tags y --code "src/**" --code "lib/**" --stdin
new_id=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "$SCRATCH/out" 2>/dev/null)
run "new check" $NEW check && kinds
run "$REL reindex" $OLD reindex
run "$REL check --strict" $OLD check --strict && kinds
run "$REL get $new_id" $OLD get "$new_id"
run "$REL context" $OLD context "new build" --limit 2

rm -rf "$SCRATCH"
[ $fail -eq 0 ] && echo "PASS: no refusal in either direction" || echo "FAIL: a build refused the other's store"
exit $fail
