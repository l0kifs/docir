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
import yaml
from typer.testing import CliRunner

from docir.config.settings import Settings
from docir.entry_points.cli import app as cli_app
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
    store_description,
    unrecognised_keys,
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


def _declare(home: Path, *peers: Path, description: str = "") -> None:
    """Write a store's `stores.yaml`: the peers it reads, what it is, or both."""
    document: dict[str, object] = {}
    if peers:
        document["stores"] = [str(path) for path in peers]
    if description:
        document["description"] = description
    (home / PEER_FILE).write_text(yaml.safe_dump(document), encoding="utf-8")


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


class TestStoreDescriptions:
    """Every federated row says what corpus it came from, in that corpus's words.

    A store path answers "which repository" and nothing else, and the reader
    ranking a hit has to decide whether that corpus is the one that governs the
    thing it is doing. The description is written once, by the store that owns
    it, so N readers do not each maintain a sentence about someone else's
    repository — and so the reader's *own* rows are labelled too, which a
    reader-side annotation of its peers cannot do.
    """

    _PLATFORM = "Platform decisions binding every service: auth, transport, deploy."
    _SERVICE = "The checkout service's own issues and design notes."

    def test_a_peer_row_carries_the_peers_own_words(
        self, container: Container, peer: Container
    ) -> None:
        _declare(peer.settings.home, description=self._PLATFORM)
        _declare(container.settings.home, peer.settings.home)
        container.dispatcher.dispatch("add", _LOCAL_DOC)

        rows = container.dispatcher.dispatch("query", {"limit": 10})
        assert isinstance(rows, list)
        described = {row["title"]: row.get("store_description") for row in rows}
        assert described[_PEER_DOC["title"]] == self._PLATFORM

    def test_the_local_store_labels_its_own_rows_too(
        self, container: Container, peer: Container
    ) -> None:
        """Named per row, not counted: with one description in play a merge that
        stamped every row from the local file would pass a count and mislabel
        the peer's documents as this repository's."""
        _declare(peer.settings.home, description=self._PLATFORM)
        _declare(container.settings.home, peer.settings.home, description=self._SERVICE)
        container.dispatcher.dispatch("add", _LOCAL_DOC)

        rows = container.dispatcher.dispatch("query", {"limit": 10})
        assert isinstance(rows, list)
        described = {row["title"]: row.get("store_description") for row in rows}
        assert described == {
            _LOCAL_DOC["title"]: self._SERVICE,
            _PEER_DOC["title"]: self._PLATFORM,
        }

    def test_a_store_that_says_nothing_omits_the_field(
        self, container: Container, peer: Container
    ) -> None:
        """Absent, never empty: `""` reads as "this corpus is about nothing"
        rather than "nobody has written a description"."""
        _declare(container.settings.home, peer.settings.home)
        container.dispatcher.dispatch("add", _LOCAL_DOC)

        rows = container.dispatcher.dispatch("query", {"limit": 10})
        assert isinstance(rows, list)
        assert all("store" in row for row in rows), "federation is on"
        assert all("store_description" not in row for row in rows)

    def test_a_single_store_read_is_unchanged_by_describing_itself(
        self, container: Container
    ) -> None:
        """A description is for telling *another* reader what this corpus is. A
        store with no peers is talking to nobody, and the field would cost every
        row of every local read — the same argument that keeps `store` off
        them."""
        _declare(container.settings.home, description=self._SERVICE)
        container.dispatcher.dispatch("add", _LOCAL_DOC)

        rows = container.dispatcher.dispatch("query", {"limit": 10})
        assert isinstance(rows, list)
        assert all("store" not in row and "store_description" not in row for row in rows)

    def test_a_deep_read_of_a_peer_document_is_described(
        self, container: Container, peer: Container
    ) -> None:
        """`get` is where the reader decides whether to trust what it just read,
        so the corpus it came from has to survive the fetch."""
        added = peer.dispatcher.dispatch("add", {**_PEER_DOC, "title": "Rate limits"})
        assert isinstance(added, dict)
        _declare(peer.settings.home, description=self._PLATFORM)
        _declare(container.settings.home, peer.settings.home)

        view = container.dispatcher.dispatch("get", {"doc_id": added["id"]})
        assert isinstance(view, dict)
        assert view["store"] == str(peer.settings.home)
        assert view["store_description"] == self._PLATFORM

    def test_a_batch_read_describes_each_documents_own_store(
        self, container: Container, peer: Container
    ) -> None:
        local = container.dispatcher.dispatch("add", _LOCAL_DOC)
        remote = peer.dispatcher.dispatch("add", {**_PEER_DOC, "title": "Rate limits"})
        assert isinstance(local, dict) and isinstance(remote, dict)
        _declare(peer.settings.home, description=self._PLATFORM)
        _declare(container.settings.home, peer.settings.home, description=self._SERVICE)

        payload = container.dispatcher.dispatch("get", {"doc_ids": [local["id"], remote["id"]]})
        assert isinstance(payload, dict)
        described = {row["id"]: row.get("store_description") for row in payload["documents"]}
        assert described == {local["id"]: self._SERVICE, remote["id"]: self._PLATFORM}

    def test_a_peers_broken_file_costs_its_label_and_not_the_read(
        self, container: Container, peer: Container
    ) -> None:
        """The peer's `stores.yaml` is that repository's file to get wrong, and
        the established rule is that a peer's state never fails this reader's
        query — it only costs what it could not supply."""
        (peer.settings.home / PEER_FILE).write_text("description: [not, a, string]\n")
        _declare(container.settings.home, peer.settings.home, description=self._SERVICE)
        container.dispatcher.dispatch("add", _LOCAL_DOC)

        rows = container.dispatcher.dispatch("query", {"limit": 10})
        assert isinstance(rows, list)
        described = {row["title"]: row.get("store_description") for row in rows}
        assert described == {_LOCAL_DOC["title"]: self._SERVICE, _PEER_DOC["title"]: None}


class TestDescriptionFileShape:
    """This store's own `stores.yaml` is refused when it is wrong, not ignored.

    Every failure here is silent otherwise: the read still answers, from a set
    or a label the author believes they changed.
    """

    def test_a_file_that_only_describes_declares_no_peers(self, tmp_path: Path) -> None:
        """The common case: a corpus is worth describing to whoever points at
        it, whether or not it points anywhere itself."""
        home = tmp_path / ".docir"
        home.mkdir()
        _declare(home, description="Platform decisions.")
        assert peer_homes(home) == ()
        assert store_description(home) == "Platform decisions."

    def test_no_file_describes_nothing(self, tmp_path: Path) -> None:
        assert store_description(tmp_path) == ""

    def test_a_description_that_is_not_a_string_raises(self, tmp_path: Path) -> None:
        home = tmp_path / ".docir"
        home.mkdir()
        (home / PEER_FILE).write_text("description:\n  - platform\n  - decisions\n")
        with pytest.raises(DocirError, match="one string"):
            peer_homes(home)

    def test_a_misspelled_key_is_refused_and_named(self, tmp_path: Path) -> None:
        """`store:` for `stores:` used to be caught only because a file without
        a `stores` key was itself an error, and a description-only file is now
        legitimate — so the typo needs its own refusal or it reads as a store
        that declares no peers."""
        home = tmp_path / ".docir"
        home.mkdir()
        (home / PEER_FILE).write_text("store:\n  - ../platform/.docir\n")
        with pytest.raises(DocirError, match="did you mean 'stores'"):
            peer_homes(home)

    @pytest.mark.parametrize("typo", ["store", "stors", "descriptions", "desc"])
    def test_every_shape_of_slip_is_named(self, tmp_path: Path, typo: str) -> None:
        """A near match and an abbreviation are both mistakes this build can
        name; the parametrization is what keeps the predicate from being tuned
        to the one example it was written against."""
        home = tmp_path / ".docir"
        home.mkdir()
        (home / PEER_FILE).write_text(f"{typo}: something\n")
        with pytest.raises(DocirError, match="did you mean"):
            peer_homes(home)

    def test_a_file_declaring_nothing_at_all_raises(self, tmp_path: Path) -> None:
        home = tmp_path / ".docir"
        home.mkdir()
        (home / PEER_FILE).write_text("{}\n")
        with pytest.raises(DocirError, match="list of store paths"):
            peer_homes(home)


class TestOlderDocirCanStillReadTheseStores:
    """Every `stores.yaml` docir ships as an example keeps its `stores:` key.

    docir 0.20.0 and earlier parse that file with a check that requires it:
    `peer_homes` raises before the read, so a description-only file takes
    `context`, `query`, `search`, `get` and `doctor` down for everyone in that
    repository who has not upgraded — writes keep working, which is what makes
    it look like a corrupt store rather than a version skew. Verified against
    the published 0.20.0 (adr-84fb02d5061b).

    Nothing this build does can fix an older reader, so the shipped spelling is
    the whole mitigation, and the examples are what an adopter copies.
    """

    _SKILL = Path("src/docir/modules/agents/infra/templates/skill/reference/retrieval.md")
    _OWN_STORE = Path(".docir/stores.yaml")

    @staticmethod
    def _declares_stores(block: str) -> bool:
        """Whether an example that describes a store also declares its peers."""
        lines = [line.strip() for line in block.splitlines()]
        return "description:" in " ".join(lines) and any(
            line.startswith("stores:") for line in lines
        )

    def test_the_packaged_skill_example_declares_stores(self) -> None:
        """The skill is what an agent installs and copies from."""
        text = self._SKILL.read_text(encoding="utf-8")
        fences = [block.split("```")[0] for block in text.split("```yaml")[1:]]
        describing = [block for block in fences if "description:" in block]
        assert describing, "the skill no longer shows a stores.yaml example"
        assert all(self._declares_stores(block) for block in describing), describing

    def test_the_cli_docstring_example_declares_stores(self) -> None:
        """`docir context --help` is JSON when piped, so it is the example an
        agent parses rather than reads."""
        doc = cli_app.context.__doc__ or ""
        marker = "# .docir/stores.yaml"
        assert marker in doc, "the context docstring no longer shows the file"
        block = doc.split(marker, 1)[1].split("\n\n", 1)[0]
        assert self._declares_stores(block), block

    def test_this_repositorys_own_store_declares_stores(self) -> None:
        """docir's own file is the example anyone reading the repo sees first —
        and the one that would break a teammate still on 0.20.0."""
        declared = yaml.safe_load(self._OWN_STORE.read_text(encoding="utf-8"))
        assert "description" in declared, "docir's store no longer describes itself"
        assert "stores" in declared

    def test_the_check_would_notice_a_description_only_example(self) -> None:
        """The three above pass trivially if the predicate is too generous, so
        this injects the exact file that breaks 0.20.0."""
        assert not self._declares_stores("description: Platform decisions.\n")
        assert self._declares_stores("description: Platform decisions.\nstores: []\n")


class TestAMalformedPeerListReachesTheCli:
    """A broken `stores.yaml` is a message and an exit code, not a traceback.

    It is parsed client-side, before anything is dispatched, so it sits outside
    the boundary that maps a `DocirError` onto the process exit code — the same
    gap `execute` already closed twice (issue-06f48d8f239f). Every other reader
    of the file, `docir doctor` included, printed the message all along, which
    is what made the traceback look like a crash rather than a bad file.
    """

    def test_the_message_and_exit_code_survive(self, settings: Settings) -> None:
        (settings.home).mkdir(parents=True, exist_ok=True)
        (settings.home / PEER_FILE).write_text("store:\n  - ../platform/.docir\n")
        result = CliRunner().invoke(cli_app.app, ["--no-daemon", "query", "--limit", "1"])
        assert result.exit_code != 0
        assert "did you mean 'stores'" in result.output
        # The failure this pins: an unhandled DocirError leaves the exception on
        # the result and prints a stack trace instead of the sentence.
        assert result.exception is None or isinstance(result.exception, SystemExit)


class TestAKeyFromANewerDocir:
    """An unfamiliar key is kept and reported; only a slip of a known one raises.

    The asymmetry is the decision (adr-84fb02d5061b). Refusing a key this build
    has never heard of would make one repository's upgrade break every
    repository that had not upgraded yet — backwards from what the strictness
    protects, and the same call `_peer_schema_status` already made for a peer's
    index revision. A misspelling is the opposite case: it reads as a store that
    declared nothing, so it must not pass quietly.
    """

    _FUTURE = "stores:\n  - {peer}\ndescription: A corpus.\nstore_labels:\n  - platform\n"

    def _declare_future(self, home: Path, peer_home: Path) -> None:
        (home / PEER_FILE).write_text(self._FUTURE.format(peer=peer_home), encoding="utf-8")

    def test_the_read_still_federates(self, container: Container, peer: Container) -> None:
        self._declare_future(container.settings.home, peer.settings.home)
        container.dispatcher.dispatch("add", _LOCAL_DOC)

        rows = container.dispatcher.dispatch("query", {"limit": 10})
        assert isinstance(rows, list)
        # Named rather than counted: the peer's document is the half a refusal
        # would have taken away.
        assert {row["title"] for row in rows} == {_LOCAL_DOC["title"], _PEER_DOC["title"]}

    def test_the_ignored_key_is_reported(self, tmp_path: Path) -> None:
        home = tmp_path / ".docir"
        home.mkdir()
        self._declare_future(home, tmp_path / "platform" / ".docir")
        assert unrecognised_keys(home) == ("store_labels",)

    def test_a_misspelling_is_not_treated_as_a_future_key(self, tmp_path: Path) -> None:
        """The guard above passes trivially if everything is tolerated."""
        home = tmp_path / ".docir"
        home.mkdir()
        (home / PEER_FILE).write_text("description: A corpus.\nstore: ../platform/.docir\n")
        with pytest.raises(DocirError, match="did you mean 'stores'"):
            peer_homes(home)

    def test_the_cli_warns_and_answers_anyway(self, settings: Settings) -> None:
        """stderr, not an error: the read is correct, and the key is news about
        the file rather than a failure of the command."""
        settings.home.mkdir(parents=True, exist_ok=True)
        (settings.home / PEER_FILE).write_text("description: A corpus.\nstore_labels: []\n")
        result = CliRunner().invoke(cli_app.app, ["--no-daemon", "query", "--limit", "1"])
        assert result.exit_code == 0
        assert "store_labels" in result.output
