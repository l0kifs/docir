"""The site model — which documents appear, in what order, and with which edges.

Pure rules, tested without HTML. The point of keeping them out of the templates
is that a failure here says "the back-edge inversion is wrong", not "a regex did
not match a rendered page".
"""

from __future__ import annotations

from docir.modules.publishing.api import build_site

_A = {
    "id": "adr-0001",
    "title": "Old way",
    "description": "The previous decision.",
    "type": "decision",
    "status": "superseded",
    "created": "2026-01-01",
    "updated": "2026-01-02",
    "body": "## Context\n\nThe old approach.\n",
}
_B = {
    "id": "adr-0002",
    "title": "New way",
    "description": "The replacement.",
    "type": "decision",
    "status": "accepted",
    "created": "2026-02-01",
    "updated": "2026-02-01",
    "body": "## Context\n\nThe new approach.\n",
    "related": [{"target": "adr-0001", "kind": "supersedes"}],
}
_C = {
    "id": "arch-0001",
    "title": "Architecture",
    "description": "How it fits together.",
    "type": "architecture",
    "status": "active",
    "created": "2026-01-15",
    "updated": "2026-03-01",
    "body": "Body.",
    "tags": ["core"],
    "stale": True,
    "owner": "platform",
}


class TestEdges:
    def test_outgoing_edges_resolve_to_titles(self) -> None:
        site = build_site([_A, _B])
        new = next(d for d in site.documents if d.id == "adr-0002")
        assert [(e.target, e.kind, e.title) for e in new.outgoing] == [
            ("adr-0001", "supersedes", "Old way")
        ]

    def test_edges_are_inverted_onto_their_target(self) -> None:
        """The graph is stored one way and has to be read both.

        The `supersedes` edge lives on the *new* document's frontmatter, so
        without inversion a reader landing on the old decision has no way to
        learn it was replaced — the exact failure the typed graph exists to
        prevent.
        """
        site = build_site([_A, _B])
        old = next(d for d in site.documents if d.id == "adr-0001")
        assert [(e.target, e.kind, e.title) for e in old.incoming] == [
            ("adr-0002", "supersedes", "New way")
        ]

    def test_successors_are_separable_from_ordinary_backlinks(self) -> None:
        """ "Something replaced this" must not sit in an undifferentiated list."""
        linked = dict(_C, related=[{"target": "adr-0001", "kind": "relates_to"}])
        site = build_site([_A, _B, linked])
        old = next(d for d in site.documents if d.id == "adr-0001")
        assert len(old.incoming) == 2
        assert [e.target for e in old.successors] == ["adr-0002"]

    def test_a_dangling_edge_keeps_its_id_and_no_title(self) -> None:
        """The site shows the broken reference `check` reports, not a gap."""
        orphan = dict(_C, related=[{"target": "adr-9999", "kind": "relates_to"}])
        site = build_site([orphan])
        (document,) = site.documents
        assert document.outgoing[0].target == "adr-9999"
        assert document.outgoing[0].title is None

    def test_a_bare_id_is_a_relates_to_edge(self) -> None:
        """Pre-typed files store a bare id; they must still round-trip."""
        site = build_site([_A, dict(_B, related=["adr-0001"])])
        new = next(d for d in site.documents if d.id == "adr-0002")
        assert new.outgoing[0].kind == "relates_to"


class TestOrdering:
    def test_documents_group_by_type(self) -> None:
        site = build_site([_C, _A, _B])
        assert [name for name, _ in site.groups] == ["architecture", "decision"]

    def test_newest_first_inside_a_type(self) -> None:
        """A reader arriving at a section wants the current decisions first."""
        site = build_site([_A, _B])
        (_, decisions) = site.groups[0]
        assert [d.id for d in decisions] == ["adr-0002", "adr-0001"]

    def test_every_document_appears_exactly_once(self) -> None:
        site = build_site([_A, _B, _C])
        ids = [d.id for d in site.documents]
        assert sorted(ids) == ["adr-0001", "adr-0002", "arch-0001"]
        assert sum(len(docs) for _, docs in site.groups) == 3


class TestFieldMapping:
    def test_absent_keys_read_as_defaults(self) -> None:
        """Trimmed CLI JSON omits empty fields; a site must build from it.

        This is what lets `docir build` consume captured output rather than
        requiring an in-process call.
        """
        (document,) = build_site([_A]).documents
        assert document.tags == ()
        assert document.owner == ""
        assert document.verified is None
        assert document.stale is False

    def test_staleness_and_ownership_survive(self) -> None:
        (document,) = build_site([_C]).documents
        assert document.stale is True
        assert document.owner == "platform"
        assert build_site([_C]).stale_count == 1
