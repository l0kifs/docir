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

from docir.modules.documents.domain.schema import DEFAULT_ID_STYLE, ID_STYLES
from docir.platform.errors import SchemaError

# Re-exported so the module's public ``api`` can surface them without reaching
# into ``domain`` itself (the layering rule this module's infra is allowed to
# cross, and its api is not).
__all__ = ["DEFAULT_ID_STYLE", "DEFAULT_SCHEMA_YAML", "ID_STYLES", "render_schema_yaml"]

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
# Merging only adds. To drop a type the core or a profile contributed — because
# this corpus calls it something else, and leaving the old name addable would
# split the corpus across two — list it under `disable_types:`:
#
#   disable_types: [decision]
#
# That also frees its `prefix`, so your own type can claim `adr` and keep the
# ids you already have. Retype the documents with `docir update <id> --type`.
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
#   required            list - fields this type must carry, on top of the
#                              always-required id/title/description/type/status/
#                              created/updated. Names an existing document field
#                              -- `owner`, `verified`, `tags`, `related`, `body`,
#                              `code` -- not an arbitrary frontmatter key: a name
#                              no document can carry is refused when the schema
#                              loads. An empty list or empty string counts as
#                              missing, so `required: [tags]` means "at least one
#                              tag".
#   inactive_statuses   list - statuses treated as "closed" and hidden from the
#                              default read path (widen back in with
#                              `--include-inactive`).
#   level               int  - layering rank. A higher-level doc depending on a
#                              lower-level one is a Tier 1 `check` warning.
#   review_days         int  - staleness cadence in days; 0 (default) = never
#                              stale.
#   max_body_chars      int  - body size past which `lint --deep` suggests
#                              splitting the document. Absent inherits the
#                              default (8000); 0 means never — the right answer
#                              for a type that exists to hold a register, since
#                              a glossary split in half is two half-glossaries.
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
# embed_model:
#   # Top-level, like id_style. The model `docir context` vectorises this
#   # corpus with. Absent means BAAI/bge-small-en-v1.5 -- English-only, so a
#   # corpus written in another language should name another. Measured:
#   #   sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2  (384d, 220MB)
#   #   sentence-transformers/paraphrase-multilingual-mpnet-base-v2  (768d, 1.0GB)
#   # Any other model fastembed supports is accepted, with one warning: docir
#   # embeds queries and documents through the same call, so a model trained on
#   # asymmetric query/passage prefixes will rank below its published numbers.
#   # Benchmark yours before trusting it.
#   # It lives here rather than in an environment variable because the index is
#   # gitignored: two clones holding different models would each re-embed the
#   # whole corpus behind the other. Changing it re-embeds on the next write or
#   # `docir embed --flush` -- vectors record which model made them, so nothing
#   # compares across models.
#
# relation_types:
#   # Registers additional edge kinds on top of the core six (relates_to,
#   # supersedes, depends_on, implements, contradicts, refines). Using a kind
#   # that is not registered is a Tier 0 error.
#   #
#   # A plain list registers kinds with default meaning: directed (so a loop of
#   # them is a `cycle` finding), not a dependency, not a successor.
#   - governs
#   - blocks
#   #
#   # The mapping form declares what a kind *means*. Every property is optional
#   # and defaults as above; naming a core kind to set one leaves the rest alone.
#   #   symmetric   the edge says the same thing both ways, so a pair of
#   #               documents referencing each other is not a `cycle`
#   #               (`relates_to` and `contradicts` are symmetric by default)
#   #   dependency  the source *relies on* the target, which is the only claim
#   #               the `layering` check reads (`depends_on`, `refines`)
#   #   successor   the *incoming* direction answers "is this still current?",
#   #               so `docir context` follows it backwards (`supersedes`,
#   #               `contradicts`)
#   #
#   # governs:   {dependency: true}
#   # blocks:    {}                    # registered, all defaults
#   # duplicates: {symmetric: true}
#   # replaced_by: {successor: true}
#
#   # Run `docir schema show` to see the resolved properties of every kind —
#   # a core kind carries its meaning without being named here.
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


_ID_STYLE_NOTE = {
    "random": (
        "# Ids are collision-resistant hex tokens (adr-3f9a2b1c7d4e), so people\n"
        "# authoring docs on concurrent branches never mint the same id. Switch to\n"
        "# `sequential` for human-friendly numbers (adr-0007) if this repo has a\n"
        "# single doc author. Per-type `id_style:` overrides this.\n"
    ),
    "sequential": (
        "# Ids are human-friendly numbers (adr-0007) drawn from the index counter.\n"
        "# They are unique within this store, but two git branches can each mint the\n"
        "# same number -- `docir check` reports that as `duplicate-id` after a merge.\n"
        "# Use `random` if several people author docs on concurrent branches.\n"
        "# Per-type `id_style:` overrides this.\n"
    ),
}


def render_schema_yaml(profiles: Sequence[str] = (), id_style: str = DEFAULT_ID_STYLE) -> str:
    """Build a ``docs-schema.yaml`` body selecting ``profiles`` and ``id_style``.

    Falls back to the default ``software`` profile when none are named. Both
    generated lines are assembled here rather than substituted into a template,
    so ``docir init`` cannot write a different profile set or id style than it
    reports.
    """
    if id_style not in ID_STYLES:
        raise SchemaError(f"unknown id_style {id_style!r}; available: {', '.join(ID_STYLES)}")
    names = tuple(profiles) or _FALLBACK_PROFILES
    return (
        f"{_SCHEMA_HEADER}"
        f"profiles: [{', '.join(names)}]\n\n"
        f"{_ID_STYLE_NOTE[id_style]}"
        f"id_style: {id_style}\n"
        f"{_SCHEMA_FOOTER}"
    )


#: The bundled default schema body, written when a store has no schema file of
#: its own. Deliberately ``sequential``: this is the implicit fallback an
#: existing or un-``init``-ed store lands on, and changing what it mints would
#: alter the ids of a store that never asked for it. ``docir init`` defaults to
#: ``random`` instead -- see its ``--id-style`` flag.
DEFAULT_SCHEMA_YAML = render_schema_yaml()
