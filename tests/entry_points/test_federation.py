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
            "repair",
            "lint",
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
    """A peer whose index predates a migration must still be readable.

    Peers are opened read-only and deliberately *not* migrated — a peer is
    another repository, and docir does not rewrite one it was merely pointed at
    (adr-fb938175f72a). So every derived table added by a migration is a table
    some peer will not have, and a read that assumes it is present turns one
    un-reindexed repository into an outage for everyone pointing at it.

    Injected the way it actually arises: the table is dropped, which is what a
    peer last built before migration 0008 looks like.
    """

    def test_a_missing_mentions_table_does_not_break_a_federated_read(
        self, tmp_path: Path, container: Container, peer: Container
    ) -> None:
        import sqlite3

        peer_home = tmp_path / "peer"
        peer.close()
        with sqlite3.connect(peer_home / "index.db") as raw:
            raw.execute("DROP TABLE mentions")

        _declare(container.settings.home, peer_home)
        rows = container.dispatcher.dispatch(
            "context", {"task": "mutual tls between services", "limit": 5}
        )
        titles = {row["title"] for row in rows}
        assert _PEER_DOC["title"] in titles, "the peer's documents became unreachable"

    def test_a_missing_code_digest_column_does_not_break_a_federated_read(
        self, tmp_path: Path, container: Container, peer: Container
    ) -> None:
        # The same defect one migration earlier: `document_code.digest` arrived
        # in 0007, and every hydrate selects it — so a peer built before that
        # broke `query` and `get`, not just expansion. Rebuilt the way SQLite
        # forces a column drop, which is what the older schema literally was.
        import sqlite3

        peer_home = tmp_path / "peer"
        peer.close()
        with sqlite3.connect(peer_home / "index.db") as raw:
            raw.execute("ALTER TABLE document_code RENAME TO document_code_old")
            raw.execute(
                "CREATE TABLE document_code (doc_id TEXT NOT NULL "
                "REFERENCES documents(id) ON DELETE CASCADE, pattern TEXT NOT NULL, "
                "PRIMARY KEY (doc_id, pattern))"
            )
            raw.execute("INSERT INTO document_code SELECT doc_id, pattern FROM document_code_old")
            raw.execute("DROP TABLE document_code_old")

        _declare(container.settings.home, peer_home)
        titles = {row["title"] for row in container.dispatcher.dispatch("query", {"limit": 10})}
        assert _PEER_DOC["title"] in titles, "the peer's documents became unreachable"

    def test_get_against_such_a_peer_reports_no_mentions_rather_than_failing(
        self, tmp_path: Path, container: Container, peer: Container
    ) -> None:
        # Absent means unknown, the rule the whole index follows: no table is
        # the same answer as an empty one, not an error.
        import sqlite3

        peer_home = tmp_path / "peer"
        doc_id = peer.dispatcher.dispatch("query", {"limit": 1})[0]["id"]
        peer.close()
        with sqlite3.connect(peer_home / "index.db") as raw:
            raw.execute("DROP TABLE mentions")

        _declare(container.settings.home, peer_home)
        view = container.dispatcher.dispatch("get", {"doc_id": doc_id})
        assert view["title"] == _PEER_DOC["title"]
        assert view.get("mentions", ()) == ()
