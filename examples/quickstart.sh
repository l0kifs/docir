#!/usr/bin/env bash
#
# quickstart.sh — a complete, self-contained walkthrough of the docir CLI.
#
# It reproduces the architecture's end-to-end agent flow — discover context,
# read a decision, record a successor, supersede the old one, resolve an issue —
# and shows the capabilities layered on top: typed relation edges, the
# skeleton-first read contract, staleness stewardship, and the core+profiles
# schema. Everything runs against a throwaway workspace under examples/.workspace
# (never your real ~/.docir) and in-process (no daemon) so it is deterministic.
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

echo "==> 2. Record a decision (with an owner) and a related issue (a TYPED edge)"
docir add --type decision \
  --title "Auth strategy" \
  --description "How the service authenticates API clients and refreshes tokens." \
  --tags auth,api \
  --owner platform-team \
  --body "The service authenticates clients with short-lived JWT access tokens."

# The issue *depends on* the decision — a typed edge (<id>:<kind>), not a bare link.
docir add --type issue \
  --title "Token refresh bug" \
  --description "Refresh tokens are not rotated on renewal, so old tokens stay valid." \
  --tags auth \
  --related adr-0001:depends_on \
  --body "Reproduced on staging: the refresh endpoint returns the same token."

echo "==> 3. An agent discovers context — a SKELETON (title/description, no body)"
# context/query/search return body-less skeletons, so the agent scans cheaply
# and then fetches only the bodies it needs by id (step 4).
docir context "implement a new authentication endpoint" --limit 3

echo "==> 4. Read the full decision before writing code (get carries the body)"
docir get adr-0001

echo "==> 5. Accept the decision, then record a successor that SUPERSEDES it"
docir update adr-0001 --status accepted
docir add --type decision \
  --title "Refresh token rotation" \
  --description "When and how refresh tokens are rotated on renewal." \
  --tags auth,api \
  --owner platform-team \
  --related adr-0001:supersedes \
  --body "On each renewal we issue a new refresh token and revoke the previous one."

echo "==> 6. Retire the old decision and resolve the issue (validated transitions)"
docir update adr-0001 --status superseded
docir update issue-0001 --status resolved

echo "==> 7. Staleness is data — confirm a doc is still correct"
# Stamps today as the last-verified date; 'docir check' warns when a doc drifts
# past its type's review cadence (decisions: 365 days).
docir update adr-0002 --verified

echo "==> 8. Structured query — superseded/resolved docs are hidden by default"
docir query --type decision                 # only adr-0002 (adr-0001 is superseded)
docir query --type decision --include-resolved
docir search "refresh token rotation"

echo "==> 9. Tier 1 graph health check (cycles, orphans, dangling, stale, unknown type)"
docir check

echo "==> 10. The schema: a frozen core + the 'software' profile"
# Swap or add profiles (research / ops / legal) to generalize docir beyond
# software without touching the base types.
cat "$DOCIR_HOME/docs-schema.yaml"

echo
echo "==> 11. The generated markdown files (git is the source of truth)"
find "$DOCIR_HOME/docs" -name '*.md' | sort
echo
echo "----- docs/decisions/adr-0002-refresh-token-rotation.md -----"
# Note the typed edge (related: {to: adr-0001, kind: supersedes}) plus owner/verified.
cat "$DOCIR_HOME/docs/decisions/adr-0002-refresh-token-rotation.md"

echo
echo "Done. Inspect the workspace at: $DOCIR_HOME"
