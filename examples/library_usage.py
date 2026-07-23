"""library_usage.py — drive docir programmatically instead of via the CLI.

The CLI is a thin client over an application object graph. You can build that
graph yourself with :func:`build_container` and issue the same commands through
its dispatcher — useful for embedding docir in another Python tool or test.

Run it:  uv run python examples/library_usage.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from docir.config.settings import Settings
from docir.entry_points.composition import build_container


def main() -> None:
    # A hermetic, throwaway home so the example never touches your ~/.docir.
    home = Path(tempfile.mkdtemp(prefix="docir-example-"))
    settings = Settings.resolve(home, use_daemon=False)

    # The composition root wires the whole stack (index + files + embedder).
    # background_embeddings=False uses the synchronous inline embedder, so
    # semantic search is ready the moment a write returns.
    container = build_container(settings, background_embeddings=False)
    try:
        docs = container.dispatcher

        # 1. Register a tag (referential integrity: docs may only use known tags).
        docs.dispatch("tag_add", {"key": "auth", "description": "Auth and tokens."})

        # 2. Create two documents linked by a TYPED edge. `dispatch` returns
        #    plain dicts. `owner` is stewardship metadata for staleness.
        decision = docs.dispatch(
            "add",
            {
                "type": "decision",
                "title": "Auth strategy",
                "description": "How the service authenticates API clients.",
                "tags": ["auth"],
                "owner": "platform-team",
                "body": "Short-lived JWT access tokens with refresh rotation.",
            },
        )
        # The issue *depends on* the decision — `<id>:<kind>` is the edge form.
        issue = docs.dispatch(
            "add",
            {
                "type": "issue",
                "title": "Token refresh bug",
                "description": "Refresh tokens are not rotated on renewal.",
                "tags": ["auth"],
                "related": [f"{decision['id']}:depends_on"],
            },
        )
        edge = issue["related"][0]
        print(
            f"created {decision['id']} and {issue['id']} "
            f"({issue['id']} --{edge['kind']}--> {edge['target']})"
        )

        # 3. Ask for the minimal relevant context for a task (hybrid ranking +
        #    one-hop relation traversal). Results are SKELETONS — no body — so a
        #    prompt stays cheap; fetch full bodies by id only when needed.
        print("\ncontext for 'implement auth endpoint':")
        context = docs.dispatch("context", {"task": "implement auth endpoint", "limit": 5})
        for view in context:
            marker = " (via graph)" if view["via_graph"] else ""
            print(f"  - {view['id']}: {view['title']}{marker}")
        print(
            f"  (skeleton carries a body? {'body' in context[0]}; "
            f"get carries a body? {'body' in docs.dispatch('get', {'doc_id': decision['id']})})"
        )

        # 4. Metadata writes: resolve the issue (validated transition) and record
        #    that the decision was re-verified today (resets its staleness clock).
        docs.dispatch("update", {"doc_id": issue["id"], "status": "resolved"})
        verified = docs.dispatch("update", {"doc_id": decision["id"], "mark_verified": True})
        resolved = docs.dispatch("get", {"doc_id": issue["id"]})
        print(f"\n{issue['id']} status is now: {resolved['status']}")
        print(f"{decision['id']} verified on: {verified['verified']} (owner: {verified['owner']})")
    finally:
        container.close()

    print(f"\nworkspace: {home}")


if __name__ == "__main__":
    main()
