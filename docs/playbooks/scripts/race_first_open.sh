#!/usr/bin/env bash
# Start K first commands at once in a fresh `git worktree` of an N-document store (GitHub #42).
#
#   bash docs/playbooks/scripts/race_first_open.sh [N] [K] [STEP]
#
# N     documents in the scratch store (500: the bootstrap takes ~2s, wide enough to race)
# K     commands started in the one worktree, STEP seconds apart (0 = all at once)
# Env:  DOCIR_BIN=<dir holding a docir> runs another build, e.g. ~/.local/bin for the release;
#       DAEMON=1 drops `--no-daemon`, so the race moves into daemon startup and its log.
# Exits 1 when any command exits non-zero or any traceback reaches stderr or daemon.log.
set -u
N=${1:-500}; K=${2:-2}; STEP=${3:-0.3}
REPO=$(git rev-parse --show-toplevel) || exit 2
export PATH="${DOCIR_BIN:-$REPO/.venv/bin}:$PATH"
unset DOCIR_HOME DOCIR_NO_DAEMON
export DOCIR_EMBEDDER=deterministic DOCIR_UPDATE_CHECK=0  # the race needs no model and no network
FLAG="--no-daemon"; [ "${DAEMON:-0}" = 1 ] && FLAG=""
ROOT=$(mktemp -d "${TMPDIR:-/tmp}/docir-race.XXXXXX")
git init -q -b main "$ROOT/main" && cd "$ROOT/main" || exit 2
git config user.email race@example.invalid && git config user.name race
docir --no-daemon init >/dev/null
for t in alpha beta gamma; do docir --no-daemon tag add "$t" --description "Tag $t." >/dev/null; done
python3 - "$ROOT/main/.docir/docs/decisions" "$N" <<'PY'
import os, random, sys
out, n, rnd = sys.argv[1], int(sys.argv[2]), random.Random(7)
words = "alpha beta gamma delta river stone cloud field".split()
os.makedirs(out, exist_ok=True)
for i in range(n):
    did = "adr-%012x" % rnd.getrandbits(48)
    tags = "".join(f"- {t}\n" for t in sorted(rnd.sample(["alpha", "beta", "gamma"], 2)))
    body = "\n\n".join(f"## Part {k}\n\n" + " ".join(rnd.choice(words) for _ in range(250)) for k in (1, 2, 3))
    with open(f"{out}/{did}-doc-{i}.md", "w") as f:
        f.write(f"---\ncreated: '2026-10-20'\ndescription: Document {i}.\nid: {did}\nrelated: []\n"
                f"status: proposed\ntags:\n{tags}title: Document {i}\ntype: decision\nupdated: '2026-10-20'\n---\n\n{body}\n")
PY
git add -A && git commit -qm docs
ID=$(ls .docir/docs/decisions | head -1 | cut -c1-16)
git worktree add -q "$ROOT/wt" -b wt && cd "$ROOT/wt" || exit 2
for k in $(seq 1 "$K"); do
  ( sleep "$(echo "($k - 1) * $STEP" | bc)"; docir $FLAG get "$ID" >/dev/null 2>"$ROOT/err-$k"
    echo "command $k: exit $?" >"$ROOT/rc-$k" ) &
done
wait
[ -n "$FLAG" ] || docir daemon stop >/dev/null 2>&1
cat "$ROOT"/rc-*
errors=$(cat "$ROOT"/err-* .docir/daemon.log 2>/dev/null | grep -E '^[A-Za-z_.]+(Error|Exception): ' | sort | uniq -c)
[ -n "$errors" ] && echo "$errors"
if grep -qv 'exit 0' "$ROOT"/rc-* || [ -n "$errors" ]; then echo "FAIL ($ROOT)"; exit 1; fi
echo "PASS: $K first commands, $N documents"
