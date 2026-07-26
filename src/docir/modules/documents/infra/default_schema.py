"""The bundled default ``docs-schema.yaml``.

Written to the store's ``docs-schema.yaml`` on first use if the user has not
supplied their own. It selects the ``software`` profile over the frozen core, so
the default type set is exactly ``decision`` (core) + ``issue`` + ``architecture``
+ ``release_note`` (software). Swap or add profiles (``research``, ``ops``,
``qa``, ``legal``) to generalize docir to another domain without touching the
base schema; add an inline ``types:`` block to extend or override.

The file body is assembled from a header and a footer around a generated
``profiles:`` line (:func:`render_schema_yaml`) rather than by string-replacing
a sentinel, so ``docir init --profiles`` cannot silently write a different
profile set than it reports.
"""

from __future__ import annotations

from collections.abc import Sequence

#: Profiles used when the caller does not name any.
_FALLBACK_PROFILES: tuple[str, ...] = ("software",)

# Everything above the generated ``profiles:`` line.
_SCHEMA_HEADER = """\
# docir document schema.
#
# The frozen, domain-agnostic *core* (the `decision` type, the relation-kind
# registry, and staleness cadences) is always included. Layer domain-specific
# types by naming *profiles* below; bundled profiles are:
#   software  -> issue, architecture, release_note
#   research  -> hypothesis, experiment, finding
#   ops       -> runbook, incident, postmortem
#   qa        -> test_plan, test_case
#   legal     -> policy, contract, obligation
#
# You can enable several at once, and add your own inline `types:` /
# `relation_types:` here — they are merged last and win on name conflicts.
#
# Typed edges: a document's `related` entries carry a relation *kind*. Write a
# bare id for the default `relates_to`, or `<id>:<kind>` (CLI) / `{to, kind}`
# (frontmatter) for a typed edge.
#
# Staleness: give a type a `review_days` cadence; `docir check` flags documents
# whose last `verified` date (or last edit) is older than that. Set `owner` and
# stamp `docir update <id> --verified` to reset the clock.
#
# Run `docir schema show` to see the fully merged result, and
# `docir schema validate` to check this file before it reaches a write.

"""

# Everything below the generated ``profiles:`` line: a worked, commented-out
# example of the inline syntax. It lives here (rather than only in the agent
# skill) so the syntax is discoverable at the point of use — an agent editing
# this file learns the grammar from the file itself.
_SCHEMA_FOOTER = """
# --------------------------------------------------------------------------
# Adding your own types
# --------------------------------------------------------------------------
# Uncomment and adapt. Three keys are REQUIRED on every type:
#
#   prefix          str  - id prefix, e.g. `tp` mints `tp-0001`. Must be UNIQUE
#                          across the whole merged schema (core + every enabled
#                          profile + these inline types).
#   statuses        map  - `status: [statuses it may transition to]`. A MAPPING,
#                          not a list. A terminal status maps to [].
#   default_status  str  - the status a new document starts in. Must be one of
#                          the keys in `statuses`.
#
# Optional keys:
#
#   required            list - extra frontmatter fields this type must carry, on
#                              top of the always-required id/title/description/
#                              type/status/created/updated.
#   inactive_statuses   list - statuses treated as "closed" and hidden from the
#                              default read path (widen back in with
#                              `--include-inactive`).
#   level               int  - layering rank. A higher-level doc depending on a
#                              lower-level one is a Tier 1 `check` warning.
#   review_days         int  - staleness cadence in days; 0 (default) = never
#                              stale.
#   id_style            str  - `sequential` (default) mints human-friendly ids
#                              like tp-0007 from the index counter — safe only
#                              within one shared index. Use `random` if people
#                              author docs on concurrent branches; it mints
#                              collision-resistant ids like tp-3f9a2b1c7d4e.
#   allowed_relations   map  - `kind: [allowed target types]` whitelist ([] as
#                              the target list means "any type"). CAREFUL: an
#                              empty/absent mapping is permissive (any kind, any
#                              target), but as soon as you list ONE kind it
#                              becomes a strict whitelist — every kind you still
#                              want, including `relates_to`, must be listed.
#
# relation_types:
#   # Registers additional edge kinds on top of the core six (relates_to,
#   # supersedes, depends_on, implements, contradicts, refines). Using a kind
#   # that is not registered is a Tier 0 error.
#   - governs
#   - blocks
#
# types:
#   test_plan:
#     prefix: tp
#     default_status: draft
#     statuses:
#       draft: [active]
#       active: [deprecated]
#       deprecated: []
#     inactive_statuses: [deprecated]
#     level: 3
#     review_days: 180
#
#   runbook:
#     prefix: rb
#     default_status: draft
#     statuses:
#       draft: [active]
#       active: [deprecated]
#       deprecated: []
#     allowed_relations:
#       relates_to: []                  # [] = any target type
#       depends_on: [runbook, decision] # only these target types
"""


def render_schema_yaml(profiles: Sequence[str] = ()) -> str:
    """Build a ``docs-schema.yaml`` body selecting ``profiles``.

    Falls back to the default ``software`` profile when none are named. The
    ``profiles:`` line is generated, not substituted into a template, so the
    written file always matches the requested profile set.
    """
    names = tuple(profiles) or _FALLBACK_PROFILES
    return f"{_SCHEMA_HEADER}profiles: [{', '.join(names)}]\n{_SCHEMA_FOOTER}"


#: The bundled default schema body (the ``software`` profile over the core).
DEFAULT_SCHEMA_YAML = render_schema_yaml()
