"""The bundled default ``docs-schema.yaml``.

Written to ``~/.docir/docs-schema.yaml`` on first use if the user has not
supplied their own. It selects the ``software`` profile over the frozen core, so
the default type set is exactly ``decision`` (core) + ``issue`` + ``architecture``
(software) — the three types from the architecture doc. Swap or add profiles
(``research``, ``ops``, ``legal``) to generalize docir to another domain without
touching the base schema; add an inline ``types:`` block to extend or override.
"""

from __future__ import annotations

DEFAULT_SCHEMA_YAML = """\
# docir document schema.
#
# The frozen, domain-agnostic *core* (the `decision` type, the relation-kind
# registry, and staleness cadences) is always included. Layer domain-specific
# types by naming *profiles* below; bundled profiles are:
#   software  -> issue, architecture
#   research  -> hypothesis, experiment, finding
#   ops       -> runbook, incident, postmortem
#   legal     -> policy, contract, obligation
#
# You can enable several at once, and add your own inline `types:` /
# `relation_types:` here — they are merged last and win on name conflicts.
#
# id_style (per type): 'sequential' (default) mints human-friendly ids like
# adr-0007 from the local index counter — safe only within a single shared
# index. If your team authors docs on multiple git branches concurrently, set
# id_style: random per type to mint collision-resistant ids like
# adr-3f9a2b1c7d4e, so two branches never allocate the same id.
#
# Typed edges: a document's `related` entries carry a relation *kind*. Write a
# bare id for the default `relates_to`, or `<id>:<kind>` (CLI) / `{to, kind}`
# (frontmatter) for a typed edge. A type may constrain its edges with
# `allowed_relations: {kind: [allowed target types]}` ([] means any type).
#
# Staleness: give a type a `review_days` cadence; `docir check` flags documents
# whose last `verified` date (or last edit) is older than that. Set `owner` and
# stamp `docir update <id> --verified` to reset the clock.

profiles: [software]
"""
