"""The finding vocabulary every check tier shares.

Separate from the rules so that the rule modules and the registry that
composes them can both import it without a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Findings that mean the corpus is *broken* — a document is unreachable, or an
#: edge resolves to nothing. These are what a merge gate must stop.
#:
#: `empty-index` is the one that does not describe damage to the corpus, and it
#: earns the severity by a different argument: it means `check` *could not look*.
#: The graph half reads the index, so with none built every structural finding is
#: silent and `--strict` exits 0 — a merge gate that passes because it read
#: nothing, which is strictly worse than no gate (issue-87410666c867). The
#: warnings this file argues against promoting all red-build a *correct* setup;
#: this one red-builds a setup that was never checking anything, and names the
#: single command that fixes it.
ERROR_KINDS: frozenset[str] = frozenset({"duplicate-id", "dangling", "malformed", "empty-index"})

#: Every finding kind docir defines. A store's own check may not take one of
#: these names: a check called `dangling` would make `--strict`'s behaviour
#: depend on whose schema is loaded, and a store's rule must never be able to
#: change what a docir finding means. The loader refuses the collision.
RESERVED_FINDING_KINDS: frozenset[str] = frozenset(
    {
        "duplicate-id",
        "dangling",
        "malformed",
        "orphan",
        "cycle",
        "layering",
        "stale",
        "unblocked",
        "unmatched-code",
        "code-changed",
        "code-drifted",
        "verification-outdated",
        "tag-key-format",
        "unknown-type",
        "unknown-status",
        "unknown-tag",
        "unknown-relation-kind",
        "missing-required",
        "schema-drift",
        "store-format-undeclared",
        "stale-index-build",
        "empty-index",
        "unresolved-link",
    }
)

#: Everything else (`orphan`, `cycle`, `layering`, `stale`, `unknown-type`,
#: `unknown-status`, `unknown-tag`, `tag-key-format`, `unmatched-code`,
#: `code-changed`, `code-drifted`, `verification-outdated`, `missing-required`,
#: `unknown-relation-kind`, `schema-drift`, `store-format-undeclared`,
#: `stale-index-build`, `unblocked`)
#: describes shape or classification, not
#: damage. `orphan` in particular fires for any document with no relations — the
#: default state of a new one — so treating these as build failures made the gate
#: unusable on a healthy corpus.
#:
#: `unknown-relation-kind` joins them on the same grounds and one more: the edge
#: keeps working. `Schema.relation_kind` falls back to the core properties, so a
#: kind the registry has stopped listing is still cycle-checked and still read as
#: a dependency — the corpus is intact and only the registry has fallen behind it.
#:
#: `unknown-status`/`unknown-tag` are warnings for the same reason as
#: `unknown-type`: the document is still readable and every edge still resolves,
#: the schema simply no longer recognises how it is classified. Promoting them
#: would also fail CI for any repo that already carries a hand-edited tag —
#: the exact way the `--strict` gate became unusable before. `--strict-all`
#: covers anyone who does want hand-edits to block a merge.
#:
#: `code-drifted` is a warning on the argument that made `code-changed` one,
#: and it needs it more: it fires from the same comparison against the working
#: tree, on every governed document rather than only the reviewed ones, so an
#: error kind would fail the CI of every branch that edits code before its
#: documentation — which is every branch.
#:
#: `store-format-undeclared` is a warning because the store it describes is
#: intact: every read answers, every edge resolves, and the only thing missing is
#: a line saying which docir the file needs. The damage it predicts lands on a
#: *different* machine — a teammate on an older build — which is exactly the
#: reader an error here could not reach.
#:
#: `missing-required` is a warning on the same argument, sharpened: the schema
#: change that creates it arrives *from the package*, so a corpus that passed
#: yesterday can fail today with no commit to point at. An error there would
#: red-build every repo on the release that added the field, which is precisely
#: the failure the two rules above were written to avoid.
ERROR = "error"
WARNING = "warning"


def severity_for(kind: str) -> str:
    """Whether a finding kind blocks a merge (`error`) or informs (`warning`)."""
    return ERROR if kind in ERROR_KINDS else WARNING


@dataclass(frozen=True, slots=True)
class CheckIssue:
    """One structural finding: a kind, a message, the ids involved, a severity.

    ``severity`` is derived from ``kind`` unless given explicitly, so a new check
    cannot forget to classify itself — it just has to be added to
    :data:`ERROR_KINDS` if it means damage.
    """

    kind: str
    message: str
    doc_ids: tuple[str, ...]
    severity: str = ""

    def __post_init__(self) -> None:
        if not self.severity:
            object.__setattr__(self, "severity", severity_for(self.kind))
