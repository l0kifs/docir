"""The bundled default schema.

Written to ``~/.docir/docs-schema.yaml`` on first use if the user has not
supplied their own. Covers the three document types from the architecture doc.
The ``statuses`` mapping does double duty: its keys are the valid status enum
for the type, and each value is the list of statuses that status may transition
to (reverse transitions are intentionally omitted, requiring an override flag).
"""

from __future__ import annotations

DEFAULT_SCHEMA_YAML = """\
# docir document schema — per-type grammar.
# Add new types here without changing any CLI code.
#
# id_style (per type): 'sequential' (default) mints human-friendly ids like
# adr-0007 from the local index counter — safe only within a single shared
# index. If your team authors docs on multiple git branches concurrently, set
# id_style: random to mint collision-resistant ids like adr-3f9a2b1c7d4e, so
# two branches never allocate the same id and merges can't silently collide.
types:
  decision:
    prefix: adr
    level: 3
    id_style: sequential
    required: []
    default_status: proposed
    inactive_statuses: [rejected, superseded]
    statuses:
      proposed: [accepted, rejected]
      accepted: [superseded, rejected]
      rejected: []
      superseded: []

  issue:
    prefix: issue
    level: 1
    required: []
    default_status: open
    inactive_statuses: [resolved]
    statuses:
      open: [resolved]
      resolved: []

  architecture:
    prefix: arch
    level: 5
    required: []
    default_status: draft
    inactive_statuses: [deprecated]
    statuses:
      draft: [active]
      active: [deprecated]
      deprecated: []
"""
