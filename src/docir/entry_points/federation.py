"""Reading across several stores — the fan-out half of adr-fb938175f72a.

In a multi-repo organisation the decision governing the service you are editing
lives in the platform repo, so an agent reading `context` in the service repo
cannot see it and re-decides. This module lets a store declare peers it reads
alongside its own, without giving up the property that makes a store safe: there
is still exactly one home per invocation, and it is still the only one written
to.

Four rules hold the design up, and each is load-bearing:

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
* **Every federated row says which store answered and what that store is.** A
  path answers "which repository" and nothing else, and a reader ranking a hit
  has to know whether that corpus is the one that decides this. So a store
  describes itself once, in its own ``stores.yaml``, and the sentence travels
  with every row it answers.
"""

from __future__ import annotations

import difflib
import os
from collections.abc import Iterable, Mapping, Sequence
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

#: What a store says it is, for the rows it answers with. See
#: :func:`store_description`.
DESCRIPTION_FIELD = "store_description"

#: Every key ``stores.yaml`` recognises. Anything else is either a slip of one
#: of these — refused — or a key a newer docir writes, which is kept and
#: reported; :func:`_read_peer_file` is where that asymmetry lives.
KNOWN_KEYS = ("stores", "description")

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


@dataclass(frozen=True, slots=True)
class StoreFile:
    """``stores.yaml`` parsed: the peers a store reads, and what it is.

    The two keys are independent. A store that only reads peers says nothing
    about itself; a store that only describes itself declares no peers — which
    is the common case, since a corpus is worth describing to every reader that
    points at it, whether or not it points anywhere.
    """

    stores: tuple[str, ...] = ()
    description: str = ""
    #: Keys this build does not know, kept rather than refused.
    unknown: tuple[str, ...] = ()


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
    declared = _read_peer_file(home / PEER_FILE).stores
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


def store_description(home: Path) -> str:
    """What a store says it is, in its own words — or ``""`` if it says nothing.

    **A store describes itself.** The description lives in that store's own
    ``stores.yaml`` beside the peers it reads, so it is written once by the
    people who know the corpus and travels with it to every reader. The
    alternative — each reader annotating the peers it declares — writes the same
    sentence once per repository pointing at it, drifts as the corpus changes,
    and cannot label the reader's *own* rows at all, which are stamped too.

    Read per request, for the reason the peer list is: it is one small file, and
    a daemon that had cached it would label rows with a description its owner
    has already rewritten.

    A peer whose file is missing or malformed simply has no description. Only
    that store's own commands owe an error for it — a peer is someone else's
    repository, and the established rule is that its state never fails this
    reader's query. The local file gets no such tolerance: :func:`peer_homes`
    parses it on the same request and raises.
    """
    try:
        return _read_peer_file(home / PEER_FILE).description
    except DocirError:
        return ""


def unrecognised_keys(home: Path) -> tuple[str, ...]:
    """Keys in this store's ``stores.yaml`` this build does not know.

    Kept rather than refused, and this is the asymmetry that matters: a key
    nothing here has heard of is most likely one a *newer* docir writes, and
    refusing it would make one repository's upgrade break every repository that
    had not upgraded yet — backwards from what the strictness protects, and the
    same call :func:`~docir.entry_points.composition._peer_schema_status`
    already made for a peer's index revision. A key that misspells one this
    build *does* know is the opposite case and still raises.

    Kept is not silent: the CLI warns and ``docir doctor`` carries a finding, so
    an ignored key is visible on a transport an agent reads rather than only on
    a stderr line nobody is watching.
    """
    try:
        return _read_peer_file(home / PEER_FILE).unknown
    except DocirError:
        return ()


def resolve_extra(entries: Sequence[str]) -> list[str]:
    """Turn caller-supplied peer paths into absolute ones, here and now.

    Every client does this before the paths travel: with the daemon, the process
    that reads them started in a different directory from the one that named
    them, so a relative path resolved on arrival would point somewhere the
    caller never meant. One implementation, because the CLI's ``--store`` and the
    MCP tools' ``stores`` are the same argument reaching the same fan-out.
    """
    return [str(Path(entry).expanduser().resolve()) for entry in entries]


def _read_peer_file(path: Path) -> StoreFile:
    """Parse ``stores.yaml``. A missing file means no peers, which is the norm.

    A malformed one raises rather than reading as empty: the file exists only
    because someone declared something, so silently reading nothing would answer
    a federated question with a local answer and nothing would say so.

    An unrecognised key splits in two, and the halves get opposite answers.
    ``store:`` for ``stores:`` **raises**: it reads as a store with no peers,
    which is a federated question answered locally, and it used to be caught for
    free because a file with no ``stores`` key was itself an error — a
    description-only file is legitimate now, so the typo needs its own refusal.
    A key that resembles nothing here is kept and reported instead, because it is
    most likely one a newer docir writes; see :func:`unrecognised_keys`.
    """
    if not path.is_file():
        return StoreFile()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise DocirError(f"{path} is not valid YAML: {exc}") from exc
    if data is None:
        return StoreFile()
    shape = (
        f"{path} must map 'stores' to a list of store paths, 'description' to one string, or both"
    )
    if not isinstance(data, dict) or not data:
        raise DocirError(shape)
    # Judged before the shape is, so `store:` for `stores:` is reported as the
    # typo it is rather than as a file that declares nothing.
    unknown = tuple(sorted(str(key) for key in set(data) - set(KNOWN_KEYS)))
    for key in unknown:
        intended = _misspelling_of(key)
        if intended:
            raise DocirError(
                f"{path} declares {key!r}, which is not a key here — did you mean "
                f"{intended!r}? A misspelled key reads as a store that declared "
                "nothing, and the read would answer locally without saying so"
            )
    stores = data.get("stores", [])
    if not isinstance(stores, list):
        raise DocirError(f"{path} must map 'stores' to a list of store paths")
    description = data.get("description", "")
    if not isinstance(description, str):
        raise DocirError(f"{path} must map 'description' to one string")
    return StoreFile(tuple(str(item) for item in stores), description.strip(), unknown)


def _misspelling_of(key: str) -> str:
    """The recognised key this one was meant to be, or ``""`` if it is new.

    Two shapes, both slips of a name that already exists: a near match
    (``store``, ``stors``, ``descriptions``) and an abbreviation of one
    (``desc``). A name that is merely *unfamiliar* — ``store_labels``,
    ``peer_timeout`` — matches neither, which is the whole point: the first is a
    mistake this build can name, the second is a build this one has not met.
    """
    close = difflib.get_close_matches(key, KNOWN_KEYS, n=1, cutoff=0.8)
    if close:
        return close[0]
    return next((known for known in KNOWN_KEYS if len(key) >= 3 and known.startswith(key)), "")


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
        labels = _labels(self._home, [peer.home for peer in readers])
        if command == "get":
            if rest.get("doc_ids") is not None:
                return self._get_many(rest, readers, labels)
            return self._get(rest, readers, labels)
        return self._merge(command, rest, readers, labels)

    # -- fan-out ------------------------------------------------------------

    def _get(
        self, payload: dict[str, object], peers: Sequence[Peer], labels: Mapping[Path, str]
    ) -> object:
        """Local first, then each peer in declaration order; first match wins.

        A miss everywhere must raise the local store's own not-found error, not
        a federated variant of it: the caller asked for a document, and "it is
        in none of these stores" is the same answer with a longer search.
        """
        try:
            return _stamp(
                self._base.dispatch("get", payload), self._home, labels, always=bool(peers)
            )
        except DocirError as local_miss:
            for peer in peers:
                assert peer.reader is not None
                try:
                    return _stamp(
                        peer.reader.dispatch("get", payload), peer.home, labels, always=True
                    )
                except DocirError:
                    continue
            raise local_miss

    def _get_many(
        self, payload: dict[str, object], peers: Sequence[Peer], labels: Mapping[Path, str]
    ) -> object:
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
            _stamp_row(row, self._home, labels) if peers else row
            for row in _rows(result.get("documents"))
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
            found.extend(
                _stamp_row(row, peer.home, labels) for row in _rows(answer.get("documents"))
            )
            unresolved = {entry["ref"] for entry in _missing(answer.get("missing"))}
            missing = {ref: entry for ref, entry in missing.items() if ref in unresolved}
        return {"documents": found, "missing": list(missing.values())}

    def _merge(
        self,
        command: str,
        payload: dict[str, object],
        peers: Sequence[Peer],
        labels: Mapping[Path, str],
    ) -> object:
        """Ask every store, then order the union by comparable relevance.

        Each store is asked for the full ``limit`` and the merge is truncated to
        it, so ``--limit 10`` still means ten documents rather than ten per
        store.
        """
        ranked: list[list[dict[str, object]]] = []
        for home, reader in ((self._home, self._base), *((p.home, p.reader) for p in peers)):
            assert reader is not None
            rows = _rows(reader.dispatch(command, payload))
            ranked.append([_stamp_row(row, home, labels) for row in rows])
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


def _labels(home: Path, peers: Sequence[Path]) -> dict[Path, str]:
    """What each store answering this request says it is, keyed by home.

    Only the stores that can answer: an unavailable peer contributes no rows,
    so reading its description would be a file read for a label nothing wears.
    """
    return {store: store_description(store) for store in (home, *peers)}


def _stamp(payload: object, home: Path, labels: Mapping[Path, str], *, always: bool) -> object:
    """Tag a single-document payload with the store it came from."""
    if not always or not isinstance(payload, dict):
        return payload
    return _stamp_row({str(key): value for key, value in payload.items()}, home, labels)


def _stamp_row(row: dict[str, object], home: Path, labels: Mapping[Path, str]) -> dict[str, object]:
    """Every federated row names its store, and says what that store is.

    Local reads carry no ``store``: it is one absolute path, identical for every
    row, and per-row it costs more than it is worth. That argument holds exactly
    while there is one store — with peers, the path is the only thing
    distinguishing two hits, so it is the difference between an answer and an
    ambiguous one. Ids stay the only identifier.

    ``store_description`` rides along for the same reason one step further: a
    path says *which* repository answered and nothing about what is in it, and
    "is this corpus the one that decides this?" is the judgement the reader has
    to make about every federated hit. It is omitted, never empty, when the
    store publishes none — an empty string reads as "this corpus is about
    nothing" rather than "nobody wrote a description".
    """
    described = labels.get(home, "")
    stamped: dict[str, object] = {**row, "store": str(home)}
    if described:
        stamped[DESCRIPTION_FIELD] = described
    return stamped


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
