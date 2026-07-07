"""library_usage.py — drive docir programmatically instead of via the CLI.

The CLI is a thin client over an application object graph. You can build that
graph yourself with :func:`build_container` and issue the same commands through
its dispatcher — useful for embedding docir in another Python tool or test.

Run it:  uv run python examples/library_usage.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from docir.infrastructure.config.settings import Settings
from docir.presentation.composition import build_container


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

        # 2. Create two related documents. `dispatch` returns plain dicts.
        decision = docs.dispatch(
            "add",
            {
                "type": "decision",
                "title": "Auth strategy",
                "description": "How the service authenticates API clients.",
                "tags": ["auth"],
                "body": "Short-lived JWT access tokens with refresh rotation.",
            },
        )
        docs.dispatch(
            "add",
            {
                "type": "issue",
                "title": "Token refresh bug",
                "description": "Refresh tokens are not rotated on renewal.",
                "tags": ["auth"],
                "related": [decision["id"]],
            },
        )
        print(f"created {decision['id']} and issue-0001")

        # 3. Ask for the minimal relevant context for a task (hybrid ranking +
        #    one-hop relation traversal). Great for feeding an LLM prompt.
        print("\ncontext for 'implement auth endpoint':")
        for view in docs.dispatch("context", {"task": "implement auth endpoint", "limit": 5}):
            marker = " (via graph)" if view["via_graph"] else ""
            print(f"  - {view['id']}: {view['title']}{marker}")

        # 4. A metadata write: resolve the issue (validated status transition).
        docs.dispatch("update", {"doc_id": "issue-0001", "status": "resolved"})
        resolved = docs.dispatch("get", {"doc_id": "issue-0001"})
        print(f"\nissue-0001 status is now: {resolved['status']}")
    finally:
        container.close()

    print(f"\nworkspace: {home}")


if __name__ == "__main__":
    main()
