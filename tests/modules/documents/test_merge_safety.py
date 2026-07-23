"""Tests for the multi-branch merge-safety features.

#2 collision-resistant ids (id_style: random) and #3 the merge-guard checks
(duplicate ids from files, dangling relations from the graph).
"""

from __future__ import annotations

import re

from docir.config.settings import Settings
from docir.entry_points.composition import build_container
from docir.entry_points.dispatch import Dispatcher

RANDOM_SCHEMA = """\
types:
  decision:
    prefix: adr
    default_status: proposed
    id_style: random
    statuses:
      proposed: [accepted]
      accepted: []
"""

_DUP_FILE = (
    "---\n"
    "created: '2026-07-07'\n"
    "description: a colliding doc from another branch\n"
    "id: adr-0001\n"
    "related: []\n"
    "status: proposed\n"
    "tags: []\n"
    "title: Collision\n"
    "type: decision\n"
    "updated: '2026-07-07'\n"
    "---\n\nbody\n"
)


def test_random_ids_are_unique_and_collision_safe(settings: Settings) -> None:
    settings.ensure_directories()
    settings.schema_path.write_text(RANDOM_SCHEMA, encoding="utf-8")
    container = build_container(settings, background_embeddings=False)
    try:
        docs = container.dispatcher
        ids = [
            docs.dispatch("add", {"type": "decision", "title": f"T{i}", "description": "x"})["id"]
            for i in range(25)
        ]
        assert len(set(ids)) == 25  # no collisions
        assert all(re.fullmatch(r"adr-[0-9a-f]{12}", doc_id) for doc_id in ids)
    finally:
        container.close()


def test_check_detects_duplicate_id_from_merged_file(container, settings: Settings) -> None:
    docs = container.dispatcher
    docs.dispatch("add", {"type": "decision", "title": "Original", "description": "d"})
    # Simulate a merge bringing a second file that reused the same id.
    dup = settings.docs_root / "decisions" / "adr-0001-collision.md"
    dup.write_text(_DUP_FILE, encoding="utf-8")

    issues = docs.dispatch("check", {})
    assert any(i["kind"] == "duplicate-id" for i in issues)


def test_check_detects_dangling_reference(seeded: Dispatcher) -> None:
    # issue-0001 relates to adr-0001; force-deleting adr-0001 leaves the link
    # dangling (as a cross-branch delete would after a merge).
    seeded.dispatch("delete", {"doc_id": "adr-0001", "force": True})
    issues = seeded.dispatch("check", {})
    assert any(i["kind"] == "dangling" for i in issues)
