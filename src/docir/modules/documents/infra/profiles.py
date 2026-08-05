"""The frozen domain-agnostic **core** schema and the bundled **profiles**.

The core is a tiny, domain-agnostic type set (just ``decision`` — ADRs exist in
every domain) plus the relation-kind registry and staleness cadences. Everything
domain-specific ships as a *profile* that layers additional types on top of the
core, so generalizing docir beyond software never mutates the base schema.

A ``docs-schema.yaml`` selects profiles with a top-level ``profiles: [..]`` key;
the loader merges ``core -> each profile -> the file's own inline overrides``.
"""

from __future__ import annotations

# The frozen core: the relation-kind registry + universal types + cadences.
#
# The list form is deliberate: what these six kinds *mean* (symmetric /
# dependency / successor) lives in `schema.CORE_RELATION_KINDS`, not here, so
# that an inline-only schema — one with no `profiles:` key, which never merges
# this file — still gets a symmetric `relates_to`. Declaring it in both places
# would be two definitions waiting to disagree.
CORE_SCHEMA_YAML = """\
relation_types:
  - relates_to      # generic association (the default when no kind is given)
  - supersedes      # this doc replaces the target
  - depends_on      # this doc relies on the target
  - implements      # this doc realizes the target (e.g. code impl of a decision)
  - contradicts     # this doc conflicts with the target
  - refines         # this doc narrows/details the target

types:
  decision:
    prefix: adr
    level: 3
    required: []
    default_status: proposed
    inactive_statuses: [rejected, superseded]
    review_days: 365
    statuses:
      proposed: [accepted, rejected]
      accepted: [superseded, rejected]
      rejected: []
      superseded: []
"""

# Profiles keyed by name. Each is a schema fragment (types, optionally more
# relation_types) merged on top of the core.
PROFILE_YAMLS: dict[str, str] = {
    "software": """\
types:
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
    review_days: 365
    statuses:
      draft: [active]
      active: [deprecated]
      deprecated: []

  release_note:
    prefix: rel
    level: 0
    required: []
    default_status: draft
    statuses:
      draft: [published]
      published: []
""",
    "qa": """\
types:
  test_plan:
    prefix: tp
    level: 3
    required: []
    default_status: draft
    inactive_statuses: [deprecated]
    review_days: 180
    statuses:
      draft: [active]
      active: [deprecated]
      deprecated: []

  test_case:
    prefix: tc
    level: 1
    required: []
    default_status: draft
    inactive_statuses: [obsolete]
    review_days: 180
    statuses:
      draft: [active]
      active: [obsolete]
      obsolete: []
""",
    "research": """\
types:
  hypothesis:
    prefix: hyp
    level: 2
    default_status: proposed
    inactive_statuses: [refuted]
    statuses:
      proposed: [testing]
      testing: [supported, refuted]
      supported: []
      refuted: []

  experiment:
    prefix: exp
    level: 1
    default_status: planned
    inactive_statuses: [abandoned]
    statuses:
      planned: [running]
      running: [complete, abandoned]
      complete: []
      abandoned: []

  finding:
    prefix: find
    level: 3
    default_status: draft
    inactive_statuses: [retracted]
    review_days: 180
    statuses:
      draft: [published]
      published: [retracted]
      retracted: []
""",
    "ops": """\
types:
  runbook:
    prefix: run
    level: 3
    default_status: draft
    inactive_statuses: [deprecated]
    review_days: 180
    statuses:
      draft: [active]
      active: [deprecated]
      deprecated: []

  incident:
    prefix: inc
    level: 1
    default_status: open
    inactive_statuses: [resolved]
    statuses:
      open: [mitigated]
      mitigated: [resolved]
      resolved: []

  postmortem:
    prefix: pm
    level: 2
    default_status: draft
    statuses:
      draft: [published]
      published: []
""",
    "legal": """\
types:
  policy:
    prefix: pol
    level: 4
    default_status: draft
    inactive_statuses: [superseded, retired]
    review_days: 365
    statuses:
      draft: [active]
      active: [superseded, retired]
      superseded: []
      retired: []

  contract:
    prefix: ctr
    level: 3
    default_status: draft
    inactive_statuses: [expired, terminated]
    review_days: 365
    statuses:
      draft: [executed]
      executed: [expired, terminated]
      expired: []
      terminated: []

  obligation:
    prefix: obl
    level: 1
    default_status: open
    inactive_statuses: [fulfilled]
    review_days: 90
    allowed_relations:
      relates_to: []
      implements: [policy, contract]
      depends_on: [obligation, policy, contract]
    statuses:
      open: [fulfilled, breached]
      fulfilled: []
      breached: []
""",
}

#: Names of the bundled profiles, for error messages and discovery.
PROFILE_NAMES: tuple[str, ...] = tuple(PROFILE_YAMLS)
