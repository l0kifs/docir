"""One command for every way docir can be subtly wrong (``docir doctor``).

Each condition here was already detectable somewhere, and that was the problem:
a stale daemon showed up in ``daemon status``, a leftover ``DOCIR_EMBEDDER`` in
``self status``, a skipped peer in a stderr line during a read, an index built
by another version as one finding among a hundred in ``check``. None of them was
*reportable together*, so the way you found out was an answer that looked
correct and was not — which is the failure mode all of them share.

Two rules shape the module.

**The environment is snapshotted before anything is dispatched.** Every command
runs :func:`~docir.entry_points.daemon.lifecycle.ensure_running`, which stops a
daemon serving other code and replaces it — so a doctor that dispatched first
would repair the very thing it exists to report and then say the daemon is fine.
:func:`snapshot` therefore touches only this process, this environment and the
filesystem, and it runs first. The same ordering covers the index: a missing
``index.db`` is created by the next container build, so whether it existed has
to be read before one happens.

**The store half is asked, not reimplemented.** The index's account of itself is
one dispatcher command (``store_status``), which is what makes it reachable over
MCP as well and keeps the version comparison and the drift diff implemented
once, in the module that owns them. What stays here is the half a daemon
literally cannot answer: which build *this* process loaded, what is in *this*
shell's environment, and which store *this* working directory resolved to.

Findings classify themselves by kind, the rule
:class:`~docir.modules.documents.domain.services.graph_checks.CheckIssue`
already follows: ``error`` means docir cannot do its job here, ``warning`` means
it will do it worse than you think.
"""

from __future__ import annotations

import importlib.util
import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from docir.config.settings import (
    NO_DAEMON_ENV,
    Settings,
    enclosing_project_home,
)
from docir.entry_points.composition import (
    EMBEDDER_ENV,
    active_embedder_id,
    build_embedder,
    peer_status,
)
from docir.entry_points.daemon import lifecycle
from docir.entry_points.federation import (
    PEER_FILE,
    peer_homes,
    store_description,
    unrecognised_keys,
)
from docir.modules.documents.api import index_is_empty, load_schema
from docir.modules.release.api import ReleaseStatus, build_release_service
from docir.platform.errors import DocirError

ERROR = "error"
WARNING = "warning"

#: Kinds meaning docir cannot work correctly here, as opposed to working less
#: well than the caller believes. Only these fail ``docir doctor --strict`` —
#: the same split ``check --strict`` makes, and for the same reason: a gate that
#: fires on "the index was built by the previous release" is a gate every repo
#: turns off the week it upgrades.
ERROR_KINDS = frozenset(
    {
        # `no-index` is deliberately absent, and was an error until opening a
        # store began rebuilding it (adr-e53c813d2f13). The finding describes a
        # condition this very process has already repaired — the `stale-daemon`
        # case, worded in the past tense for the same reason — and an error for
        # a store that is now fine is a gate red on a healthy repository.
        # An index holding nothing while the files hold documents is not that:
        # it is a store the bootstrap did not reach — one opened before its
        # files arrived, or by a build that predates it — so every read still
        # answers nothing and the severity stays. Its own kind rather than a
        # severity that varies inside `index-behind-files`, because severity
        # deriving from the kind is what stops a new finding forgetting to
        # classify itself.
        "empty-index",
        "schema-unreadable",
        "no-embedder",
        "store-unreachable",
        "model-probe-failed",
    }
)

#: What ``--probe`` embeds. Content is irrelevant — the question is whether the
#: model loads at all — but it is short, because a cold ONNX session is already
#: the slow part.
_PROBE_TEXT = "docir doctor probe"


def severity_for(kind: str) -> str:
    """Whether a finding kind blocks (`error`) or informs (`warning`)."""
    return ERROR if kind in ERROR_KINDS else WARNING


@dataclass(frozen=True, slots=True)
class DoctorFinding:
    """One thing that is wrong, what it means, and what closes it.

    ``fix`` is a command the caller can run, and it is not optional prose: the
    conditions collected here are ones people hit while something else is
    already going badly, and a report that names a problem without naming the
    move costs a second round of searching at exactly the wrong moment.
    """

    kind: str
    message: str
    fix: str = ""
    severity: str = ""

    def __post_init__(self) -> None:
        if not self.severity:
            object.__setattr__(self, "severity", severity_for(self.kind))


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """What ``--probe`` found when it actually embedded something."""

    ok: bool
    #: Wall-clock seconds, including a download on a cold cache. The number is
    #: the point: "it worked" and "it worked after fetching 67 MB" are different
    #: answers to "why is my first command slow".
    seconds: float
    dimensions: int = 0
    error: str = ""


@dataclass(frozen=True, slots=True)
class PeerReport:
    """One declared peer: where it is, whether it reads, and what it is.

    ``description`` is the peer's own words, from its ``stores.yaml`` — the same
    string a federated row carries. Reporting it here is how the person who
    wrote it finds out this store can actually see it, without staging a query
    that happens to hit that corpus.
    """

    home: Path
    unavailable: str = ""
    description: str = ""


@dataclass(frozen=True, slots=True)
class Environment:
    """Everything doctor can learn without asking the store anything.

    Assembled before the first dispatch, because dispatching changes three of
    these fields: it replaces a stale daemon, creates a missing index, and
    starts a daemon where none was running.
    """

    # -- installation
    version: str
    release: ReleaseStatus
    fastembed_installed: bool

    # -- store resolution
    home: Path
    home_origin: str
    unintended_global: bool
    shadowed_home: Path | None
    schema_path: Path
    schema_present: bool
    schema_error: str
    index_present: bool

    # -- embedding
    embed_model: str | None
    embedder_env: str
    embedder_id: str

    # -- daemon
    daemon: lifecycle.DaemonStatus
    daemon_env_disabled: bool
    watch: bool

    # -- federation
    #: What this store says it is, for the rows it answers while federating.
    #: Empty is the norm and never a finding: a store with no peers has nobody
    #: to introduce itself to.
    store_description: str = ""
    #: Keys in this store's `stores.yaml` this build ignores. Reported here
    #: because the CLI's warning goes to stderr, which the MCP path has no
    #: reader for — and a key that quietly narrows what a read covers is the
    #: kind of thing doctor exists to surface.
    unknown_peer_keys: tuple[str, ...] = ()
    peers: tuple[PeerReport, ...] = ()


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """The whole diagnosis: the facts, then what is wrong with them."""

    environment: Environment
    #: The ``store_status`` payload, or ``None`` when the store could not be
    #: reached at all — which is itself a finding, not an empty report.
    store: Mapping[str, object] | None
    probe: ProbeResult | None
    findings: tuple[DoctorFinding, ...] = ()

    @property
    def errors(self) -> tuple[DoctorFinding, ...]:
        return tuple(finding for finding in self.findings if finding.severity == ERROR)


def snapshot(settings: Settings, version: str) -> Environment:
    """Read this process, this environment and this filesystem — nothing else.

    Deliberately free of dispatching, and that is the whole ordering
    contract: ``ensure_running`` replaces a daemon serving other code, and
    ``build_container`` creates the index and its directories, so both
    ``daemon.stale_code`` and ``index_present`` are true-at-the-time facts that
    the next request would erase.

    The release status is read from the cache and never fetched: doctor is a
    command people run when something is wrong, and blocking it on the network
    would be the one moment that costs the most.
    """
    schema_present = settings.schema_path.is_file()
    schema_error = ""
    embed_model: str | None = None
    if schema_present:
        try:
            embed_model = load_schema(settings.schema_path).embed_model
        except DocirError as exc:
            schema_error = str(exc)
    return Environment(
        version=version,
        release=build_release_service(version, settings.release_cache_path).status(),
        fastembed_installed=importlib.util.find_spec("fastembed") is not None,
        home=settings.home,
        home_origin=settings.home_origin,
        unintended_global=settings.is_unintended_global_fallback(),
        shadowed_home=_shadowed_home(settings.home),
        schema_path=settings.schema_path,
        schema_present=schema_present,
        schema_error=schema_error,
        index_present=settings.db_path.is_file(),
        store_description=store_description(settings.home),
        unknown_peer_keys=unrecognised_keys(settings.home),
        embed_model=embed_model,
        embedder_env=os.environ.get(EMBEDDER_ENV, ""),
        embedder_id=active_embedder_id(embed_model),
        daemon=lifecycle.status(settings),
        daemon_env_disabled=bool(os.environ.get(NO_DAEMON_ENV, "")),
        watch=settings.watch,
        peers=_peers(settings),
    )


def _shadowed_home(home: Path) -> Path | None:
    """A project store this one hides, excluding the global default.

    ``enclosing_project_home`` answers "is there a ``.docir`` above this one",
    which is the right question for ``init`` and the wrong one here. The global
    ``~/.docir`` is above *every* store under the user's home directory, and
    being shadowed by a project store is what it is for — so reporting it makes
    the finding fire on the ordinary, correct setup, which is how a warning
    stops being read (the argument ``orphan`` already lost).

    What is left is the case that is genuinely an accident: a store created
    beneath another *project* store, capturing every command run under it while
    the outer corpus never sees those documents (issue-e10cde8c5085).
    """
    enclosing = enclosing_project_home(home)
    return None if enclosing == Path.home() / ".docir" else enclosing


def _peers(settings: Settings) -> tuple[PeerReport, ...]:
    """Each declared peer, why it cannot be read, and what it says it is.

    Through :func:`~docir.entry_points.composition.peer_status`, the same
    function the reader factory and the read-path warning use, so doctor cannot
    disagree with the command whose output sent somebody here. A malformed
    ``stores.yaml`` raises rather than reading as no peers, and that error is
    the caller's to report — it is a broken declaration, not an unreachable
    peer, and folding the two together would answer a federated question with a
    local answer.
    """
    return tuple(
        PeerReport(home, peer_status(home), store_description(home))
        for home in peer_homes(settings.home)
    )


def probe_embedder(model_name: str | None) -> ProbeResult:
    """Actually embed a string, and time it (``docir doctor --probe``).

    Opt-in because it is the one check that can *change* the machine: on a cold
    cache ``fastembed`` downloads the model, which is ~67 MB for the default.
    Everything else doctor reports is a read.

    It catches ``Exception`` rather than a typed error on purpose. The failures
    worth naming here come from inside ONNX and the HTTP fetch beneath it — a
    truncated download, a corrupt cache entry, no network on a first run — and
    none of them is in docir's taxonomy. A traceback in place of a report would
    make the diagnostic command the thing that needs diagnosing.
    """
    embedder = build_embedder(model_name)
    started = time.perf_counter()
    try:
        vector = embedder.embed(_PROBE_TEXT)
    except Exception as exc:  # a broken model is not in docir's taxonomy; see above
        return ProbeResult(
            ok=False,
            seconds=time.perf_counter() - started,
            error=f"{type(exc).__name__}: {exc}",
        )
    return ProbeResult(
        ok=True,
        seconds=time.perf_counter() - started,
        dimensions=vector.dimension,
    )


def diagnose(
    environment: Environment,
    store: Mapping[str, object] | None,
    *,
    store_error: str = "",
    probe: ProbeResult | None = None,
) -> DoctorReport:
    """Turn the facts into findings, worst first.

    ``store`` is the ``store_status`` payload and ``store_error`` the reason
    there is none. They are passed in rather than fetched here so the ordering
    rule :func:`snapshot` documents is visible at the call site, and so this
    function stays a pure mapping from facts to findings.
    """
    findings = [
        *_installation_findings(environment),
        *_store_findings(environment, store, store_error),
        *_embedding_findings(environment, store, probe),
        *_daemon_findings(environment),
        *_peer_findings(environment),
    ]
    findings.sort(key=lambda finding: 0 if finding.severity == ERROR else 1)
    return DoctorReport(
        environment=environment,
        store=store,
        probe=probe,
        findings=tuple(findings),
    )


def _installation_findings(environment: Environment) -> list[DoctorFinding]:
    """The package: is it whole, and is it current.

    An absent ``latest`` says nothing. It means nobody has checked or the check
    failed, and reporting that as "up to date" is the reading every other
    three-valued field in docir refuses.
    """
    findings: list[DoctorFinding] = []
    if not environment.fastembed_installed and not _hashing_requested(environment):
        findings.append(
            DoctorFinding(
                kind="no-embedder",
                message=(
                    "fastembed is not installed, so reads fall back to the hashing "
                    "embedder and match on shared words rather than meaning"
                ),
                fix="reinstall docir, or set DOCIR_EMBEDDER=deterministic to accept it",
            )
        )
    release = environment.release
    if release.update_available:
        findings.append(
            DoctorFinding(
                kind="update-available",
                message=f"docir {release.latest} is published, this is {release.installed}",
                fix="docir self upgrade",
            )
        )
    return findings


def _store_findings(
    environment: Environment,
    store: Mapping[str, object] | None,
    store_error: str,
) -> list[DoctorFinding]:
    """The store: does it exist, does it parse, and is its derived half current."""
    findings: list[DoctorFinding] = []
    if environment.schema_error:
        findings.append(
            DoctorFinding(
                kind="schema-unreadable",
                message=f"{environment.schema_path} will not load: {environment.schema_error}",
                fix="docir schema validate",
            )
        )
    if not environment.index_present:
        findings.append(
            DoctorFinding(
                kind="no-index",
                message=(
                    "there was no index at "
                    f"{environment.home / 'index.db'} when this started — it is derived "
                    "and gitignored, so a fresh clone has none. Opening the store creates "
                    "it and rebuilds whatever is on disk into it, vectors deferred, so the "
                    "store counts below are the ones that say where you now stand"
                ),
                fix="docir reindex  (to compute the vectors that rebuild defers)",
            )
        )
    if environment.unintended_global:
        findings.append(
            DoctorFinding(
                kind="global-fallback",
                message=(
                    f"writes land in the global store {environment.home} even though this "
                    "directory is inside a git repository — the documents will be ungitted "
                    "and invisible to everyone else"
                ),
                fix="docir init  (or set DOCIR_HOME if the global store is what you meant)",
            )
        )
    if environment.shadowed_home is not None:
        findings.append(
            DoctorFinding(
                kind="shadowed-store",
                message=(
                    f"this store shadows {environment.shadowed_home} for every command run "
                    "beneath it; documents written here are absent from that corpus"
                ),
                fix=f"declare it as a peer in {environment.home / 'stores.yaml'} to read both",
            )
        )
    if store is None:
        findings.append(
            DoctorFinding(
                kind="store-unreachable",
                message=store_error or "the store could not be opened",
                fix="docir schema validate, then docir reindex",
            )
        )
        return findings
    stale_build = store.get("stale_index_build")
    if stale_build:
        findings.append(
            DoctorFinding(
                kind="stale-index-build",
                message=(
                    f"the index was built by docir {stale_build}, this is {environment.version}"
                ),
                fix="docir self upgrade  (or docir reindex)",
            )
        )
    findings.extend(_projection_findings(store))
    drift = store.get("schema_drift")
    if isinstance(drift, Sequence) and not isinstance(drift, str) and drift:
        findings.append(
            DoctorFinding(
                kind="schema-drift",
                message=(
                    f"{len(drift)} difference(s) between the active schema and the one the "
                    "index was built against, the first being: " + str(drift[0])
                ),
                fix="docir check  to read them all, then docir reindex",
            )
        )
    return findings


def _projection_findings(store: Mapping[str, object]) -> list[DoctorFinding]:
    """The index against the files it projects — one comparison, two severities.

    The empty case is decided by ``index_is_empty``, shared with ``check`` —
    which reports the same condition as an ``empty-index`` error, because every
    structural check it runs read the same blank graph. Two copies of that
    comparison would let one command call a store usable that the other refuses.

    **Empty is not "behind".** Zero documents beside files on disk is the state
    a fresh clone is in, and every read answers nothing: the same condition
    ``no-index`` describes, one step later, after anything at all opened the
    store and created the file. `docir doctor` does that itself, so without this
    the second run of a fresh clone reported a healthy empty corpus — and a
    ``--strict`` gate that passes on the second attempt is worse than one that
    never fired.

    **A partial mismatch stays a warning**, and must. A single file that will
    not parse counts on disk and not in the index, permanently, so an error kind
    would red-build a repository for a condition `check` already reports as
    `malformed` — twice, for one file.
    """
    indexed = store.get("documents")
    on_disk = store.get("documents_on_disk")
    if not isinstance(indexed, int) or not isinstance(on_disk, int) or indexed == on_disk:
        return []
    if index_is_empty(documents=indexed, documents_on_disk=on_disk):
        return [
            DoctorFinding(
                kind="empty-index",
                message=(
                    f"the index holds nothing while docs/ holds {on_disk} file(s) — "
                    "every read answers nothing, which is what a fresh clone looks like "
                    "before its first rebuild"
                ),
                fix="docir reindex",
            )
        ]
    return [
        DoctorFinding(
            kind="index-behind-files",
            message=(
                f"{on_disk} file(s) under docs/ but {indexed} document(s) in the index — "
                "the files are canonical, so every read is answering from a projection "
                "that does not match them"
            ),
            fix="docir reindex  (docir check names any file that will not parse)",
        )
    ]


def _embedding_findings(
    environment: Environment,
    store: Mapping[str, object] | None,
    probe: ProbeResult | None,
) -> list[DoctorFinding]:
    """The half of docir that degrades silently rather than failing.

    A wrong embedder never raises: it embeds, ranks and answers, one measured
    step worse than the numbers docir publishes, with nothing in the output to
    say so. So both the configuration *and* its consequence are reported — a
    leftover ``DOCIR_EMBEDDER`` from a test run shows up twice, once as the
    variable and once as a corpus with no current vectors, and the second is
    what makes the first legible.
    """
    findings: list[DoctorFinding] = []
    if _hashing_requested(environment):
        findings.append(
            DoctorFinding(
                kind="hashing-embedder",
                message=(
                    f"{EMBEDDER_ENV}={environment.embedder_env} is set in this environment, so "
                    "reads score shared vocabulary rather than meaning — measurably worse than "
                    "plain full-text search on its own"
                ),
                fix=f"unset {EMBEDDER_ENV}, then docir embed --flush",
            )
        )
    pending = store.get("embeddings_pending") if store is not None else None
    if isinstance(pending, int) and pending > 0:
        findings.append(
            DoctorFinding(
                kind="embeddings-pending",
                message=(
                    f"{pending} document(s) have no current vector for "
                    f"{environment.embedder_id} — semantic ranking is blind to them until "
                    "the queue drains"
                ),
                fix="docir embed --flush",
            )
        )
    if probe is not None and not probe.ok:
        findings.append(
            DoctorFinding(
                kind="model-probe-failed",
                message=f"the embedding model would not load: {probe.error}",
                fix="clear the fastembed cache (~/.cache/fastembed) and retry with --probe",
            )
        )
    return findings


def _daemon_findings(environment: Environment) -> list[DoctorFinding]:
    """The daemon: stale code is a warning because the next command repairs it.

    ``ensure_running`` stops and replaces a daemon serving another build, so by
    the time the caller reads this the condition is already gone. It is still
    worth a line, and this is the only place that can produce one: it explains
    an answer they may have already acted on.
    """
    findings: list[DoctorFinding] = []
    daemon = environment.daemon
    if daemon.stale_code:
        findings.append(
            DoctorFinding(
                kind="stale-daemon",
                message=(
                    f"the daemon (pid {daemon.pid}) was {_served(daemon, environment.version)} — "
                    "answers from it described code this process is not running"
                ),
                fix="already replaced by this command; re-run anything you acted on",
            )
        )
    if environment.daemon_env_disabled:
        findings.append(
            DoctorFinding(
                kind="no-daemon-env",
                message=(
                    f"{NO_DAEMON_ENV} is set in this environment, so every command runs "
                    "in-process and pays the embedding model's cold start"
                ),
                fix=f"unset {NO_DAEMON_ENV}",
            )
        )
    return findings


def _served(daemon: lifecycle.DaemonStatus, version: str) -> str:
    """How the daemon's build differs from this one, in the terms that differ.

    A code stamp is the version *and* the newest source mtime, so two daemons
    can be stale in two different ways and only one of them is a version gap: a
    reinstall or an edit under ``src/`` moves the mtime while ``__version__``
    stands still. Reporting the version pair either way printed "serving 0.19.0
    while this process is 0.19.0", which reads as a bug in the check rather than
    the finding it is.
    """
    if daemon.version is None:
        return "serving an unknown build (its pid file predates the version check)"
    if daemon.version != version:
        return f"serving docir {daemon.version} while this process is {version}"
    return (
        f"serving docir {version} loaded from different sources than this process — "
        "an upgrade, or an edit under src/, since it started"
    )


def _peer_findings(environment: Environment) -> list[DoctorFinding]:
    """One finding per peer a read would silently drop, and per key it ignores.

    A warning and never an error: a peer's index is derived and gitignored, so a
    colleague's fresh clone is not this repository's outage (adr-fb938175f72a).
    The reason is carried verbatim because it is the fix — it already names the
    command and the store to run it in.
    """
    declared = environment.home / PEER_FILE
    return [
        DoctorFinding(
            kind="peer-unavailable",
            message=(
                f"peer store {peer.home} is skipped by every federated read: {peer.unavailable}"
            ),
            # The reason usually names the command already, and sometimes there
            # is none to name ("no such store"). One line that is true in both
            # cases beats one that promises a command the reason may not carry.
            fix=f"repair {peer.home}, or drop it from {declared}",
        )
        for peer in environment.peers
        if peer.unavailable
    ] + [
        DoctorFinding(
            kind="stores-file-unknown-key",
            message=(
                f"{declared} declares {key!r}, which this docir does not know — it is ignored"
            ),
            # Both directions, because both are ordinary: a typo nobody has
            # noticed, or a key written by a docir newer than this one.
            # Refusing it is what this deliberately does not do.
            fix="remove the key, or upgrade docir if a newer build writes it",
        )
        for key in environment.unknown_peer_keys
    ]


def _hashing_requested(environment: Environment) -> bool:
    """Whether the environment asks for the model-free embedder.

    The same two spellings :func:`~docir.entry_points.composition.build_embedder`
    accepts, read from the snapshot rather than from ``os.environ`` again, so
    the report cannot describe a different environment from the one it measured.
    """
    return environment.embedder_env.lower() in ("deterministic", "hash")
