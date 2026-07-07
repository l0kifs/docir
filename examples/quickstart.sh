#!/usr/bin/env bash
#
# quickstart.sh — a complete, self-contained walkthrough of the docir CLI.
#
# It reproduces the architecture's end-to-end agent flow: discover context,
# read a decision, record a new decision, resolve an issue, then query/verify.
# Everything runs against a throwaway workspace under examples/.workspace so it
# never touches your real ~/.docir, and in-process (no daemon) so it is fully
# deterministic.
#
# Run it from anywhere:  ./examples/quickstart.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

# Hermetic, inspectable workspace — reset on every run.
export DOCIR_HOME="$SCRIPT_DIR/.workspace"
export DOCIR_NO_DAEMON=1
rm -rf "$DOCIR_HOME"

# Thin wrapper so each command is echoed before it runs.
docir() { echo "+ docir $*"; uv run docir "$@"; echo; }

echo "==> 1. Register the tags documents are allowed to use"
docir tag add auth --description "Authentication, authorization, tokens, sessions."
docir tag add api  --description "Public/internal HTTP API surface and versioning."
docir tag list

echo "==> 2. Record an existing decision and a related open issue"
docir add --type decision \
  --title "Auth strategy" \
  --description "How the service authenticates API clients and refreshes tokens." \
  --tags auth,api \
  --body "The service authenticates clients with short-lived JWT access tokens."

docir add --type issue \
  --title "Token refresh bug" \
  --description "Refresh tokens are not rotated on renewal, so old tokens stay valid." \
  --tags auth \
  --related adr-0001 \
  --body "Reproduced on staging: the refresh endpoint returns the same token."

echo "==> 3. An agent discovers the relevant context for a new task"
# Hybrid (lexical + semantic) ranking, then one-hop relation traversal.
docir context "implement a new authentication endpoint" --limit 3

echo "==> 4. Read the full decision before writing code"
docir get adr-0001

echo "==> 5. Record a new decision that came out of the work"
docir add --type decision \
  --title "Refresh token rotation" \
  --description "When and how refresh tokens are rotated on renewal." \
  --tags auth,api \
  --related adr-0001 \
  --body "On each renewal we issue a new refresh token and revoke the previous one."

echo "==> 6. Resolve the issue (a status-only change; validated transition)"
docir update issue-0001 --status resolved

echo "==> 7. Structured query — resolved issues are hidden by default"
docir query --type decision
docir query --type issue                 # empty: issue-0001 is resolved
docir query --type issue --include-resolved

echo "==> 8. Full-text search and a Tier 1 graph health check"
docir search "refresh token rotation"
docir check

echo "==> 9. The generated markdown files (git is the source of truth)"
find "$DOCIR_HOME/docs" -name '*.md' | sort
echo
echo "----- docs/decisions/adr-0002-refresh-token-rotation.md -----"
cat "$DOCIR_HOME/docs/decisions/adr-0002-refresh-token-rotation.md"

echo
echo "Done. Inspect the workspace at: $DOCIR_HOME"
