"""Reading across several stores — the fan-out half of adr-fb938175f72a.

In a multi-repo organisation the decision governing the service you are editing
lives in the platform repo, so an agent reading `context` in the service repo
cannot see it and re-decides. This module lets a store declare peers it reads
alongside its own, without giving up the property that makes a store safe: there
is still exactly one home per invocation, and it is still the only one written
to.

Three rules hold the design up, and each is load-bearing:

* **Peers are opened read-only at the database.** A peer engine's URL carries
  ``mode=ro``, so SQLite refuses a write rather than docir promising not to
  attempt one. This is also why peers get their own construction path:
  ``build_container`` runs migrations and creates directories, both of which
  write to a repository that is not this reader's.
* **An unavailable peer is a warning, never an error and never silence.** A
  peer's index is derived and gitignored, so a fresh clone of it simply has
  none. The read proceeds without it and says so, naming the fix — failing the
  read would make one colleague's unbuilt index everyone else's outage, and
  answering an empty list would be indistinguishable from a store with nothing
  to say.
* **The merge sorts on ``similarity``, never on ``score``.** ``score`` is
  reciprocal-rank fusion: it records where a document placed *within its own
  store*, so comparing two stores' scores compares the sizes of their corpora.
  ``similarity`` is a raw cosine against the query and means the same thing
  everywhere.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml

from docir.platform.errors import DocirError

#: The committed file naming a store's peers, beside ``docs-schema.yaml``.
PEER_FILE = "stores.yaml"

#: The commands that read across stores. Asserted against the dispatcher's own
#: vocabulary in the suite, so a new command joins federation by a decision
#: rather than by being forgotten. Everything absent from this set — every
#: write, every maintenance command — runs against the local store alone:
#: a peer's dangling edges are not this repository's to report, and ``--fix``
#: would repair someone else's corpus.
FEDERATED_COMMANDS = frozenset({"get", "query", "search", "context"})

#: Payload key carrying ad-hoc peers for one request (``--store``). It rides in
#: the payload rather than in the daemon's construction because the daemon is
#: long-lived and shared: a peer named for one invocation must not persist into
#: the next caller's reads.
STORES_KEY = "stores"

#: Payload key opting one request out of federation entirely.
#:
#: An empty ``stores`` list cannot mean this — the MCP tools send one whenever
#: the argument is omitted, and a declared ``stores.yaml`` must still apply
#: there. So the opt-out is its own key, and it is what ``docir build`` sets:
#: a site is a projection of *one* repository's corpus. Publishing a peer's
#: documents into your site makes a copy that ages the moment that repo edits
#: it — the failure docir's staleness model exists to prevent — and that repo
#: publishes its own site anyway.
LOCAL_ONLY_KEY = "local_only"


class Reader(Protocol):
    """The read half of a dispatcher — all a peer is ever asked for."""

    @property
    def commands(self) -> frozenset[str]: ...

    def dispatch(self, command: str, payload: dict[str, object]) -> object: ...


class ReaderFactory(Protocol):
    """Opens a peer store for reading, or explains why it cannot be opened."""

    def __call__(self, home: Path) -> tuple[Reader | None, str]: ...


@dataclass(frozen=True, slots=True)
class Peer:
    """One resolved peer: a reader, or the reason there is none."""

    home: Path
    reader: Reader | None
    unavailable: str = ""


def peer_homes(home: Path, extra: Sequence[str | Path] = ()) -> tuple[Path, ...]:
    """The peers this store reads: the committed file, then any ``--store``.

    **The two sources have different bases, on purpose.** A relative entry in
    `stores.yaml` resolves against the store's home, so a file committed by one
    person works for everyone who clones the same layout. A ``--store`` path is
    something a person typed at a shell and expects to behave like every other
    path argument, so the CLI resolves it against the *working directory* before
    it gets here — which it must do client-side regardless, because with the
    daemon the process reading this list has a different working directory from
    the one that typed the path.

    ``~`` expands in both. The store's own home is never a peer of itself, and
    the order is declaration order with duplicates dropped — the merge uses it
    to break ties.
    """
    declared = _read_peer_file(home / PEER_FILE)
    resolved: list[Path] = []
    seen = {home.resolve()}
    for entry in (*declared, *extra):
        candidate = Path(os.path.expanduser(str(entry)))
        absolute = (candidate if candidate.is_absolute() else home / candidate).resolve()
        if absolute in seen:
            continue
        seen.add(absolute)
        resolved.append(absolute)
    return tuple(resolved)


def resolve_extra(entries: Sequence[str]) -> list[str]:
    """Turn caller-supplied peer paths into absolute ones, here and now.

    Every client does this before the paths travel: with the daemon, the process
    that reads them started in a different directory from the one that named
    them, so a relative path resolved on arrival would point somewhere the
    caller never meant. One implementation, because the CLI's ``--store`` and the
    MCP tools' ``stores`` are the same argument reaching the same fan-out.
    """
    return [str(Path(entry).expanduser().resolve()) for entry in entries]


def _read_peer_file(path: Path) -> tuple[str, ...]:
    """Parse ``stores.yaml``. A missing file means no peers, which is the norm.

    A malformed one raises rather than reading as empty: the file exists only
    because someone declared peers, so silently reading none would answer a
    federated question with a local answer and nothing would say so.
    """
    if not path.is_file():
        return ()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise DocirError(f"{path} is not valid YAML: {exc}") from exc
    if data is None:
        return ()
    if not isinstance(data, dict) or not isinstance(data.get("stores"), list):
        raise DocirError(f"{path} must map 'stores' to a list of store paths")
    return tuple(str(item) for item in data["stores"])


class FederatedDispatcher:
    """Wraps the local dispatcher, fanning the four read commands out to peers.

    It sits at the composition root rather than inside a module because it is
    wiring: every command still runs through the same local ``Dispatcher``, so
    the wire contract and the local contract cannot drift, and the CLI, the
    daemon and MCP all inherit federation from the one place they are built.
    """

    def __init__(self, base: Reader, home: Path, factory: ReaderFactory) -> None:
        self._base = base
        self._home = home
        self._factory = factory
        # Readers are cached by resolved home for the process's life: opening a
        # peer costs an engine and a schema load, and a daemon answers many
        # requests against the same set.
        self._cache: dict[Path, Peer] = {}
        #: Peers that could not be opened during the last dispatch, for the
        #: caller to report. Reset per request, because a peer reindexed
        #: between two calls is no longer worth warning about.
        self.unavailable: tuple[Peer, ...] = ()

    @property
    def commands(self) -> frozenset[str]:
        """The wrapper adds no vocabulary; it only routes the existing one."""
        return self._base.commands

    def dispatch(self, command: str, payload: dict[str, object]) -> object:
        extra = payload.get(STORES_KEY) or ()
        local_only = bool(payload.get(LOCAL_ONLY_KEY))
        rest = {
            key: value for key, value in payload.items() if key not in (STORES_KEY, LOCAL_ONLY_KEY)
        }
        if local_only or command not in FEDERATED_COMMANDS:
            return self._base.dispatch(command, rest)

        homes = peer_homes(self._home, tuple(str(item) for item in _as_sequence(extra)))
        if not homes:
            self.unavailable = ()
            return self._base.dispatch(command, rest)

        peers = [self._peer(peer_home) for peer_home in homes]
        self.unavailable = tuple(peer for peer in peers if peer.reader is None)
        readers = [peer for peer in peers if peer.reader is not None]
        if command == "get":
            if rest.get("doc_ids") is not None:
                return self._get_many(rest, readers)
            return self._get(rest, readers)
        return self._merge(command, rest, readers)

    # -- fan-out ------------------------------------------------------------

    def _get(self, payload: dict[str, object], peers: Sequence[Peer]) -> object:
        """Local first, then each peer in declaration order; first match wins.

        A miss everywhere must raise the local store's own not-found error, not
        a federated variant of it: the caller asked for a document, and "it is
        in none of these stores" is the same answer with a longer search.
        """
        try:
            return _stamp(self._base.dispatch("get", payload), self._home, always=bool(peers))
        except DocirError as local_miss:
            for peer in peers:
                assert peer.reader is not None
                try:
                    return _stamp(peer.reader.dispatch("get", payload), peer.home, always=True)
                except DocirError:
                    continue
            raise local_miss

    def _get_many(self, payload: dict[str, object], peers: Sequence[Peer]) -> object:
        """A batch deep read: ask locally, then ask each peer only what is left.

        Store priority is the single ``get``'s rule applied per reference —
        local first, then peers in declaration order, first match wins — so the
        two cannot disagree about which copy of an id you are handed. It costs
        one dispatch per store rather than one per reference: a peer is asked
        only for the addresses nothing nearer could answer, and is not asked at
        all once none are left.

        A reference that resolves nowhere keeps the *local* store's error, for
        the reason the single ``get`` re-raises ``local_miss``: "it is in none of
        these stores" is the local answer with a longer search, and reporting a
        peer's phrasing of it would name a repository the caller never asked
        about. The order within ``documents`` is therefore by store and then by
        request, not by request alone — a peer's answers arrive after the local
        ones because that is the order the stores were consulted in.
        """
        result = _as_mapping(self._base.dispatch("get", payload))
        found = [
            _stamp_row(row, self._home) if peers else row for row in _rows(result.get("documents"))
        ]
        missing = {entry["ref"]: entry for entry in _missing(result.get("missing"))}
        for peer in peers:
            if not missing:
                break
            assert peer.reader is not None
            try:
                answer = _as_mapping(
                    peer.reader.dispatch("get", {**payload, "doc_ids": list(missing)})
                )
            except DocirError:
                continue
            found.extend(_stamp_row(row, peer.home) for row in _rows(answer.get("documents")))
            unresolved = {entry["ref"] for entry in _missing(answer.get("missing"))}
            missing = {ref: entry for ref, entry in missing.items() if ref in unresolved}
        return {"documents": found, "missing": list(missing.values())}

    def _merge(self, command: str, payload: dict[str, object], peers: Sequence[Peer]) -> object:
        """Ask every store, then order the union by comparable relevance.

        Each store is asked for the full ``limit`` and the merge is truncated to
        it, so ``--limit 10`` still means ten documents rather than ten per
        store.
        """
        ranked: list[list[dict[str, object]]] = []
        for home, reader in ((self._home, self._base), *((p.home, p.reader) for p in peers)):
            assert reader is not None
            rows = _rows(reader.dispatch(command, payload))
            ranked.append([_stamp_row(row, home) for row in rows])
        merged = merge_ranked(ranked)
        limit = payload.get("limit")
        if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0:
            return merged[:limit]
        return merged

    def _peer(self, home: Path) -> Peer:
        cached = self._cache.get(home)
        if cached is not None:
            return cached
        reader, reason = self._factory(home)
        peer = Peer(home=home, reader=reader, unavailable=reason)
        self._cache[home] = peer
        return peer


def merge_ranked(ranked: Sequence[Sequence[dict[str, object]]]) -> list[dict[str, object]]:
    """Order the union: comparable relevance first, then round-robin.

    Rows carrying ``similarity`` sort on it descending — the one number that
    means the same thing in every store. Rows without one are appended
    round-robin across stores, each store keeping its own order, because absent
    means *not scored* rather than zero: a lexical-only or graph-reached hit
    sorted as 0.0 would rank below a genuinely irrelevant match, and dropped it
    would filter on embedding-queue state. Ties keep the local store first,
    which is the order ``ranked`` arrives in.

    Public because it is the decision: an integration test over two real stores
    cannot reliably separate ordering-by-similarity from ordering-by-score —
    they usually agree — so the case where they disagree has to be constructed
    directly.
    """
    scored: list[tuple[float, int, int, dict[str, object]]] = []
    unscored: list[list[dict[str, object]]] = []
    for store_index, rows in enumerate(ranked):
        rest: list[dict[str, object]] = []
        for row_index, row in enumerate(rows):
            similarity = row.get("similarity")
            if isinstance(similarity, int | float) and not isinstance(similarity, bool):
                scored.append((-float(similarity), store_index, row_index, row))
            else:
                rest.append(row)
        unscored.append(rest)
    scored.sort(key=lambda item: item[:3])
    merged = [row for *_, row in scored]
    for position in range(max((len(rows) for rows in unscored), default=0)):
        for rows in unscored:
            if position < len(rows):
                merged.append(rows[position])
    return merged


# -- store stamping ---------------------------------------------------------


def _stamp(payload: object, home: Path, *, always: bool) -> object:
    """Tag a single-document payload with the store it came from."""
    if not always or not isinstance(payload, dict):
        return payload
    return _stamp_row({str(key): value for key, value in payload.items()}, home)


def _stamp_row(row: dict[str, object], home: Path) -> dict[str, object]:
    """Every federated row names its store.

    Local reads carry no ``store``: it is one absolute path, identical for every
    row, and per-row it costs more than it is worth. That argument holds exactly
    while there is one store — with peers, the path is the only thing
    distinguishing two hits, so it is the difference between an answer and an
    ambiguous one. Ids stay the only identifier.
    """
    return {**row, "store": str(home)}


def _as_mapping(payload: object) -> dict[str, object]:
    """One response object, or an empty mapping if the payload was not one."""
    if not isinstance(payload, dict):
        return {}
    return {str(key): value for key, value in payload.items()}


def _missing(payload: object) -> list[dict[str, str]]:
    """The unresolved addresses of a batch reply, keyed by the ``ref`` field.

    Anything without a string ``ref`` is dropped rather than carried: the ref is
    what the retry is addressed with, so an entry lacking one cannot be asked
    for again and would only survive as an unremovable miss.
    """
    return [
        {str(key): str(value) for key, value in row.items()}
        for row in _rows(payload)
        if isinstance(row.get("ref"), str)
    ]


def _rows(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, list | tuple):
        return []
    return [
        {str(key): value for key, value in item.items()}
        for item in payload
        if isinstance(item, dict)
    ]


def _as_sequence(value: object) -> Iterable[object]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple):
        return value
    return ()
