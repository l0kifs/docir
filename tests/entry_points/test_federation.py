"""Reading across stores — adr-fb938175f72a.

Four properties carry the design, and each is asserted against two real stores
rather than a mock: peers are read but never written, an unavailable peer costs
a warning rather than the read, the merge orders on the one number comparable
across stores, and nothing but the four read commands fans out.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from docir.config.settings import Settings
from docir.entry_points.composition import (
    Container,
    build_container,
    build_peer_reader,
    peer_status,
)
from docir.entry_points.federation import (
    FEDERATED_COMMANDS,
    PEER_FILE,
    STORES_KEY,
    FederatedDispatcher,
    merge_ranked,
    peer_homes,
)
from docir.platform.clock import Clock
from docir.platform.errors import DocirError


class _FixedClock(Clock):
    def today(self) -> date:
        return date(2026, 7, 7)


_PEER_DOC = {
    "type": "decision",
    "title": "All services authenticate with mTLS",
    "description": "Platform-wide transport authentication rule.",
    "body": "## Decision\n\nEvery internal service presents a client certificate.\n",
}
_LOCAL_DOC = {
    "type": "issue",
    "title": "Login endpoint returns 500",
    "description": "The login route fails under load.",
    "body": "Details.\n",
}


@pytest.fixture
def peer(tmp_path: Path) -> Iterator[Container]:
    """A second, fully built store standing in for another repository."""
    built = build_container(
        Settings.resolve(tmp_path / "peer"), background_embeddings=False, clock=_FixedClock()
    )
    built.dispatcher.dispatch("add", _PEER_DOC)
    try:
        yield built
    finally:
        built.close()


def _declare(home: Path, *peers: Path) -> None:
    lines = "\n".join(f"  - {path}" for path in peers)
    (home / PEER_FILE).write_text(f"stores:\n{lines}\n", encoding="utf-8")


class _RecordingReader:
    """A store that answers `get` for the ids it knows, and remembers the asking.

    Only the batch shape: the fan-out under test never sends anything else.
    """

    def __init__(self, known: set[str], label: str = "local") -> None:
        self.calls: list[list[str]] = []
        self._known = known
        self._label = label

    @property
    def commands(self) -> frozenset[str]:
        return frozenset({"get"})

    def dispatch(self, command: str, payload: dict[str, object]) -> object:
        raw = payload.get("doc_ids")
        refs = [str(item) for item in raw] if isinstance(raw, list) else []
        self.calls.append(refs)
        return {
            "documents": [{"id": ref} for ref in refs if ref in self._known],
            "missing": [
                {"ref": ref, "error": f"{self._label}: no document with id {ref!r}"}
                for ref in refs
                if ref not in self._known
            ],
        }


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestPeerList:
    def test_no_file_means_no_peers(self, tmp_path: Path) -> None:
        assert peer_homes(tmp_path) == ()

    def test_relative_entries_resolve_against_the_store(self, tmp_path: Path) -> None:
        """A committed stores.yaml has to work for everyone who clones the same
        layout, so its paths are relative to the store rather than to whatever
        directory the command was run from."""
        home = tmp_path / "service" / ".docir"
        home.mkdir(parents=True)
        _declare(home, Path("../../platform/.docir"))
        assert peer_homes(home) == ((tmp_path / "platform" / ".docir").resolve(),)

    def test_a_store_is_never_its_own_peer(self, tmp_path: Path) -> None:
        home = tmp_path / ".docir"
        home.mkdir()
        _declare(home, home)
        assert peer_homes(home) == ()

    def test_duplicates_collapse_and_order_is_declaration_order(self, tmp_path: Path) -> None:
        home = tmp_path / ".docir"
        home.mkdir()
        first, second = tmp_path / "a" / ".docir", tmp_path / "b" / ".docir"
        _declare(home, first, second, first)
        assert peer_homes(home) == (first.resolve(), second.resolve())

    def test_extra_entries_are_appended(self, tmp_path: Path) -> None:
        home = tmp_path / ".docir"
        home.mkdir()
        _declare(home, tmp_path / "a" / ".docir")
        homes = peer_homes(home, [str(tmp_path / "b" / ".docir")])
        assert [path.parent.name for path in homes] == ["a", "b"]

    def test_a_malformed_file_raises_rather_than_reading_as_empty(self, tmp_path: Path) -> None:
        """Silently reading no peers would answer a federated question with a
        local answer, and nothing would say so."""
        home = tmp_path / ".docir"
        home.mkdir()
        (home / PEER_FILE).write_text("stores: not-a-list\n", encoding="utf-8")
        with pytest.raises(DocirError, match="list of store paths"):
            peer_homes(home)


class TestVocabulary:
    def test_every_federated_command_exists(self, dispatcher: FederatedDispatcher) -> None:
        """A typo here would silently stop fanning a command out."""
        assert dispatcher.commands >= FEDERATED_COMMANDS

    def test_writes_and_maintenance_never_federate(self, dispatcher: FederatedDispatcher) -> None:
        """Named, not counted: a count cannot tell "the write commands are
        excluded" from "the sets drifted together". `check --fix` against a peer
        would repair someone else's corpus."""
        assert dispatcher.commands - FEDERATED_COMMANDS == {
            "ping",
            "add",
            "update",
            "archive",
            "unarchive",
            "delete",
            "tag_add",
            "tag_list",
            "tag_rename",
            "tag_remove",
            "reindex",
            "check",
            "schema_drift",
            # `docir doctor`'s store half. Local by decision: it reports whether
            # *this* index is current, and a peer's build stamp is that
            # repository's business — doctor already names an unreadable peer
            # from `peer_status`, and merging peers' answers into this one would
            # report a corpus size nobody can act on.
            "store_status",
            "repair",
            "lint",
            # A fixture judges ids in *this* store, and the score is a property
            # of this store's read path. Fanning it out would mix a peer's
            # documents into results the judgments cannot speak for.
            "bench",
            "embed_flush",
        }


class TestMergeOrder:
    """The one place score and similarity can be made to disagree on purpose.

    Two real stores almost always agree, so an integration test cannot show
    that the merge reads the right field — which is exactly how a merge on
    `score` would ship unnoticed.
    """

    def test_similarity_wins_where_score_disagrees(self) -> None:
        local = [{"id": "a", "similarity": 0.2, "score": 0.9}]
        peer = [{"id": "b", "similarity": 0.8, "score": 0.1}]
        assert [row["id"] for row in merge_ranked([local, peer])] == ["b", "a"]

    def test_an_unscored_hit_is_not_treated_as_zero(self) -> None:
        """Absent means *no current vector*, not "no match": a lexical-only hit
        sorted as 0.0 would rank below a genuinely irrelevant document."""
        scored = [{"id": "irrelevant", "similarity": 0.0}]
        lexical = [{"id": "lexical"}]
        assert [row["id"] for row in merge_ranked([scored, lexical])] == [
            "irrelevant",
            "lexical",
        ]

    def test_unscored_hits_round_robin_across_stores(self) -> None:
        """`query` scores nothing, so this is its whole ordering: one store's
        long list must not bury every other store's first row."""
        first = [{"id": "a1"}, {"id": "a2"}, {"id": "a3"}]
        second = [{"id": "b1"}]
        assert [row["id"] for row in merge_ranked([first, second])] == ["a1", "b1", "a2", "a3"]

    def test_ties_keep_the_local_store_first(self) -> None:
        local = [{"id": "local", "similarity": 0.5}]
        peer = [{"id": "peer", "similarity": 0.5}]
        assert [row["id"] for row in merge_ranked([local, peer])] == ["local", "peer"]

    def test_a_boolean_is_not_a_similarity(self) -> None:
        """`True` is an int in Python; treated as 1.0 it would outrank every
        real cosine in the corpus."""
        assert [row["id"] for row in merge_ranked([[{"id": "bool", "similarity": True}]])] == [
            "bool"
        ]
        merged = merge_ranked(
            [[{"id": "bool", "similarity": True}], [{"id": "real", "similarity": 0.9}]]
        )
        assert [row["id"] for row in merged] == ["real", "bool"]


class TestFederatedReads:
    def test_context_returns_both_stores_ranked_by_similarity(
        self, container: Container, peer: Container
    ) -> None:
        """The peer's decision is about authentication and the local issue is
        not, so the peer's document must come first — which only works if the
        merge sorts on `similarity`. `score` is rank-within-own-store."""
        container.dispatcher.dispatch("add", _LOCAL_DOC)
        _declare(container.settings.home, peer.settings.home)

        rows = container.dispatcher.dispatch(
            "context", {"task": "how do services authenticate to each other", "limit": 5}
        )
        assert isinstance(rows, list)
        assert [row["title"] for row in rows] == [_PEER_DOC["title"], _LOCAL_DOC["title"]]
        assert rows[0]["similarity"] > rows[1]["similarity"]

    def test_every_federated_row_names_its_store(
        self, container: Container, peer: Container
    ) -> None:
        container.dispatcher.dispatch("add", _LOCAL_DOC)
        _declare(container.settings.home, peer.settings.home)

        rows = container.dispatcher.dispatch("query", {"limit": 10})
        assert isinstance(rows, list)
        assert {row["store"] for row in rows} == {
            str(container.settings.home),
            str(peer.settings.home),
        }

    def test_a_store_with_no_peers_carries_no_store_field(self, container: Container) -> None:
        """The single-store response is unchanged by federation existing — the
        field costs tokens on every row and answers nothing while there is one
        store."""
        container.dispatcher.dispatch("add", _LOCAL_DOC)
        rows = container.dispatcher.dispatch("query", {"limit": 10})
        assert isinstance(rows, list)
        assert all("store" not in row for row in rows)

    def test_limit_bounds_the_merge_not_each_store(
        self, container: Container, peer: Container
    ) -> None:
        container.dispatcher.dispatch("add", _LOCAL_DOC)
        _declare(container.settings.home, peer.settings.home)

        rows = container.dispatcher.dispatch("context", {"task": "authentication", "limit": 1})
        assert isinstance(rows, list)
        assert len(rows) == 1

    def test_get_reaches_a_peer_document(self, container: Container, peer: Container) -> None:
        """Without this, a federated hit is unreadable: the agent sees an id it
        cannot fetch."""
        added = peer.dispatcher.dispatch("add", {**_PEER_DOC, "title": "Rate limits"})
        assert isinstance(added, dict)
        _declare(container.settings.home, peer.settings.home)

        view = container.dispatcher.dispatch("get", {"doc_id": added["id"]})
        assert isinstance(view, dict)
        assert view["title"] == "Rate limits"
        assert view["store"] == str(peer.settings.home)

    def test_a_miss_everywhere_raises_the_local_error(
        self, container: Container, peer: Container
    ) -> None:
        _declare(container.settings.home, peer.settings.home)
        with pytest.raises(DocirError, match="no document with id"):
            container.dispatcher.dispatch("get", {"doc_id": "adr-nope"})

    def test_an_ad_hoc_store_needs_no_file(self, container: Container, peer: Container) -> None:
        rows = container.dispatcher.dispatch(
            "query", {"limit": 10, STORES_KEY: [str(peer.settings.home)]}
        )
        assert isinstance(rows, list)
        assert [row["title"] for row in rows] == [_PEER_DOC["title"]]


class TestFederatedBatchRead:
    """A batch `get` applies the single `get`'s store priority per reference.

    The two must not disagree about which copy of an id you are handed, and the
    fan-out must not degrade into one dispatch per reference per store.
    """

    def test_local_and_peer_documents_come_back_together(
        self, container: Container, peer: Container
    ) -> None:
        local = container.dispatcher.dispatch("add", _LOCAL_DOC)
        remote = peer.dispatcher.dispatch("add", {**_PEER_DOC, "title": "Rate limits"})
        assert isinstance(local, dict) and isinstance(remote, dict)
        _declare(container.settings.home, peer.settings.home)

        payload = container.dispatcher.dispatch("get", {"doc_ids": [local["id"], remote["id"]]})
        assert isinstance(payload, dict)
        assert {row["id"] for row in payload["documents"]} == {local["id"], remote["id"]}
        assert not payload["missing"]

    def test_each_document_names_the_store_that_answered(
        self, container: Container, peer: Container
    ) -> None:
        """The single `get` stamps the peer's home; the batch must too, or a
        federated hit becomes an id with no repository behind it."""
        local = container.dispatcher.dispatch("add", _LOCAL_DOC)
        remote = peer.dispatcher.dispatch("add", {**_PEER_DOC, "title": "Rate limits"})
        assert isinstance(local, dict) and isinstance(remote, dict)
        _declare(container.settings.home, peer.settings.home)

        payload = container.dispatcher.dispatch("get", {"doc_ids": [local["id"], remote["id"]]})
        assert isinstance(payload, dict)
        stores = {row["id"]: row["store"] for row in payload["documents"]}
        assert stores[local["id"]] == str(container.settings.home)
        assert stores[remote["id"]] == str(peer.settings.home)

    def test_a_section_address_resolves_in_a_peer(
        self, container: Container, peer: Container
    ) -> None:
        """The retry has to carry the heading, which means carrying the whole
        address — a peer asked for the bare id would answer the wrong span."""
        remote = peer.dispatcher.dispatch("add", {**_PEER_DOC, "title": "Rate limits"})
        assert isinstance(remote, dict)
        _declare(container.settings.home, peer.settings.home)

        payload = container.dispatcher.dispatch("get", {"doc_ids": [f"{remote['id']}#Decision"]})
        assert isinstance(payload, dict)
        (document,) = payload["documents"]
        assert document["section"] == "Decision"
        assert "client certificate" in document["body"]

    def test_a_miss_everywhere_keeps_the_local_error(
        self, container: Container, peer: Container
    ) -> None:
        """The same rule the single `get` follows by re-raising `local_miss`:
        the answer is this store's, given after a longer search."""
        _declare(container.settings.home, peer.settings.home)
        payload = container.dispatcher.dispatch("get", {"doc_ids": ["adr-nope"]})
        assert isinstance(payload, dict)
        assert not payload["documents"]
        (entry,) = payload["missing"]
        assert entry["ref"] == "adr-nope"
        assert "no document with id" in entry["error"]


class TestBatchFanOutCost:
    """One dispatch per store, and only for the addresses still unanswered.

    Constructed against recording readers rather than two real stores: the
    property is *which* requests were made, and a real peer answers a wasteful
    fan-out and a frugal one identically.
    """

    def _federated(
        self, tmp_path: Path, local: set[str], remote: set[str]
    ) -> tuple[FederatedDispatcher, _RecordingReader]:
        home, peer_home = tmp_path / "local", tmp_path / "peer"
        home.mkdir()
        peer_home.mkdir()
        _declare(home, peer_home)
        reader = _RecordingReader(remote, label="peer")
        return (
            FederatedDispatcher(_RecordingReader(local), home, lambda _home: (reader, "")),
            reader,
        )

    def test_a_peer_is_not_asked_when_the_local_store_answered_everything(
        self, tmp_path: Path
    ) -> None:
        dispatcher, peer = self._federated(tmp_path, {"a", "b"}, {"c"})
        dispatcher.dispatch("get", {"doc_ids": ["a", "b"]})
        assert peer.calls == []

    def test_a_peer_is_asked_only_for_what_is_still_missing(self, tmp_path: Path) -> None:
        """Re-asking for the whole batch would make every peer re-read documents
        the caller already holds — the cost the batch exists to remove."""
        dispatcher, peer = self._federated(tmp_path, {"a"}, {"b"})
        payload = dispatcher.dispatch("get", {"doc_ids": ["a", "b"]})
        assert peer.calls == [["b"]]
        assert isinstance(payload, dict)
        assert [row["id"] for row in payload["documents"]] == ["a", "b"]
        assert not payload["missing"]

    def test_an_address_nobody_answers_keeps_the_local_error(self, tmp_path: Path) -> None:
        dispatcher, peer = self._federated(tmp_path, set(), set())
        payload = dispatcher.dispatch("get", {"doc_ids": ["a"]})
        assert peer.calls == [["a"]]
        assert isinstance(payload, dict)
        assert payload["missing"] == [{"ref": "a", "error": "local: no document with id 'a'"}]


class TestPeersAreReadOnly:
    def test_a_federated_read_does_not_touch_the_peer_index(
        self, container: Container, peer: Container
    ) -> None:
        """The guarantee is SQLite's — the peer engine is opened `mode=ro` — so
        this pins the outcome that guarantee exists for."""
        _declare(container.settings.home, peer.settings.home)
        before = _digest(peer.settings.db_path)
        container.dispatcher.dispatch("context", {"task": "authentication", "limit": 5})
        assert _digest(peer.settings.db_path) == before

    def test_the_peer_connection_itself_refuses_a_write(self, peer: Container) -> None:
        """The mechanism, not just the outcome: the engine is opened `mode=ro`,
        so SQLite refuses rather than docir promising not to try. Reached
        directly, because nothing in the federated path would ever ask."""
        reader, reason = build_peer_reader(
            peer.settings.home, embedder=peer.embedder, clock=_FixedClock()
        )
        assert reason == "" and reader is not None
        with pytest.raises(Exception, match="readonly database"):
            reader.dispatch("add", dict(_LOCAL_DOC))

    def test_a_write_goes_only_to_the_local_store(
        self, container: Container, peer: Container
    ) -> None:
        _declare(container.settings.home, peer.settings.home)
        before = _digest(peer.settings.db_path)
        container.dispatcher.dispatch("add", _LOCAL_DOC)
        assert _digest(peer.settings.db_path) == before

        local = container.dispatcher.dispatch("query", {"limit": 10, STORES_KEY: []})
        assert isinstance(local, list)
        assert _LOCAL_DOC["title"] in {row["title"] for row in local}


class TestUnavailablePeers:
    def test_a_peer_with_no_index_is_skipped_not_fatal(
        self, container: Container, tmp_path: Path
    ) -> None:
        """A peer's index is derived and gitignored, so a colleague's fresh
        clone must not become everyone else's outage."""
        empty = tmp_path / "unbuilt" / ".docir"
        empty.mkdir(parents=True)
        container.dispatcher.dispatch("add", _LOCAL_DOC)
        _declare(container.settings.home, empty)

        rows = container.dispatcher.dispatch("query", {"limit": 10})
        assert isinstance(rows, list)
        assert [row["title"] for row in rows] == [_LOCAL_DOC["title"]]
        assert [peer.home for peer in container.dispatcher.unavailable] == [empty.resolve()]

    def test_the_reason_names_the_fix(self, tmp_path: Path) -> None:
        missing = tmp_path / "gone" / ".docir"
        assert peer_status(missing) == "no such store"
        missing.mkdir(parents=True)
        assert "docir reindex" in peer_status(missing)

    def test_a_built_store_is_available(self, peer: Container) -> None:
        """The negative assertions above are only worth anything if this passes:
        otherwise every peer reads as unavailable and nothing is being tested."""
        assert peer_status(peer.settings.home) == ""


class TestPeerIndexedByOlderDocir:
    """A peer whose index predates a migration is skipped, not read.

    Peers are opened read-only and never migrated — a peer is another repository
    (adr-fb938175f72a). So every table or column a migration adds is one some
    peer will not have, and a read that assumes it is present turns one
    un-reindexed repository into an outage for everyone pointing at it. It had
    already happened twice: `mentions` (0008) broke `context` and `get`,
    `document_code.digest` (0007) broke every hydrate and so `query` too.

    The rule is one revision comparison rather than a guard per column, because
    the guard has to be remembered and the comparison does not. The cost is that
    upgrading docir darkens every peer until it is reindexed — which is what the
    message tells the user to do.

    Injected the way it really arises: the schema is rolled back *and* stamped
    with the older revision, which is what an index built by that docir is.
    """

    @staticmethod
    def _roll_back_to_0007(home: Path) -> None:
        """Make the index look exactly like one built before migration 0008."""
        import sqlite3

        with sqlite3.connect(home / "index.db") as raw:
            raw.execute("DROP TABLE mentions")
            raw.execute("UPDATE alembic_version SET version_num = '0007'")

    def test_such_a_peer_is_skipped_with_an_actionable_reason(
        self, tmp_path: Path, peer: Container
    ) -> None:
        peer_home = tmp_path / "peer"
        peer.close()
        self._roll_back_to_0007(peer_home)

        reason = peer_status(peer_home)
        assert "0007" in reason and "0008" in reason
        assert "docir reindex" in reason

    def test_the_local_store_still_answers(
        self, tmp_path: Path, container: Container, peer: Container
    ) -> None:
        # The established behaviour for an unreadable peer: warn and carry on.
        # A peer that cannot be read must never fail the caller's own query.
        peer_home = tmp_path / "peer"
        peer.close()
        self._roll_back_to_0007(peer_home)

        _declare(container.settings.home, peer_home)
        container.dispatcher.dispatch("add", _LOCAL_DOC)
        titles = {row["title"] for row in container.dispatcher.dispatch("query", {"limit": 10})}
        assert _LOCAL_DOC["title"] in titles
        assert _PEER_DOC["title"] not in titles

    def test_a_peer_from_a_newer_docir_is_still_read(
        self, tmp_path: Path, container: Container, peer: Container
    ) -> None:
        # The asymmetry is the point. A revision this build does not know is
        # from a *newer* docir, and every query names its columns, so extra ones
        # read fine. Refusing it would make upgrading one repository break every
        # repository that had not upgraded yet — backwards from what this
        # protects against.
        import sqlite3

        peer_home = tmp_path / "peer"
        peer.close()
        with sqlite3.connect(peer_home / "index.db") as raw:
            raw.execute("UPDATE alembic_version SET version_num = '0099'")

        assert peer_status(peer_home) == ""
        _declare(container.settings.home, peer_home)
        titles = {row["title"] for row in container.dispatcher.dispatch("query", {"limit": 10})}
        assert _PEER_DOC["title"] in titles

    def test_an_index_with_no_recorded_revision_is_skipped(
        self, tmp_path: Path, peer: Container
    ) -> None:
        # Cannot say is not permission to proceed: this is either corruption or
        # a build old enough to predate Alembic, and both need a rebuild.
        import sqlite3

        peer_home = tmp_path / "peer"
        peer.close()
        with sqlite3.connect(peer_home / "index.db") as raw:
            raw.execute("DELETE FROM alembic_version")

        assert "docir reindex" in peer_status(peer_home)
