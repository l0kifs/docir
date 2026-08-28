"""`docir doctor` end to end — the ways docir can be subtly wrong, in one report.

Each condition here was already detectable somewhere else, so what these tests
pin is not the detection but the three properties that make one report out of
five scattered ones:

* the environment is read **before** anything is dispatched, because dispatching
  repairs two of the conditions (a stale daemon is replaced, a missing index is
  created) and would leave doctor reporting the state it caused;
* a store too broken to open still produces a report, because "the store will
  not open" is the finding — exiting there prints nothing at the moment somebody
  needs it most;
* `--strict` gates on errors only, so the ordinary state of a repo between an
  upgrade and its next reindex does not fail a setup script.

Guards are verified by injecting the condition, never by asserting the current
output: every assertion below is preceded by a step that breaks something.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from docir import __version__
from docir.config.settings import Settings
from docir.entry_points import doctor
from docir.entry_points.cli.app import app
from docir.entry_points.daemon.lifecycle import DaemonStatus
from docir.modules.documents.api import describe_schema, load_schema
from docir.modules.release.api import ReleaseStatus

runner = CliRunner()


def _doctor(*args: str) -> tuple[int, dict]:
    result = runner.invoke(app, ["--no-daemon", "doctor", *args])
    return result.exit_code, json.loads(result.stdout)


#: What the hermetic fixtures themselves put in the environment: they export
#: DOCIR_EMBEDDER and DOCIR_NO_DAEMON to keep the suite model-free and
#: in-process, and doctor's job is to report exactly that. Subtracted rather
#: than tolerated, so a test asserting "nothing else is wrong" still fails the
#: day a third finding appears.
FIXTURE_KINDS = {"hashing-embedder", "no-daemon-env"}


def _kinds(report: dict) -> set[str]:
    return {finding["kind"] for finding in report.get("findings", [])} - FIXTURE_KINDS


def _all_kinds(report: dict) -> set[str]:
    return {finding["kind"] for finding in report.get("findings", [])}


def _add(title: str = "A") -> None:
    result = runner.invoke(
        app,
        ["--no-daemon", "add", "--type", "decision", "--title", title, "--description", "d"],
    )
    assert result.exit_code == 0, result.output


# -- the healthy baseline ---------------------------------------------------


def test_a_healthy_store_reports_nothing(settings: Settings) -> None:
    """The floor every other test is a deviation from.

    Without it a report full of findings proves nothing: a check that fires on
    a correct store is indistinguishable from one that fires on a broken one.
    """
    _add()
    code, report = _doctor()
    assert code == 0
    assert _kinds(report) == set()
    assert _all_kinds(report) == FIXTURE_KINDS, "the suite's own environment, and nothing else"
    assert report["ok"] is True
    assert report["installation"]["version"] == __version__


def test_the_facts_are_reported_even_when_nothing_is_wrong(settings: Settings) -> None:
    """Half of what doctor reports is only legible beside the state that
    produced it, so the sections are not conditional on a finding."""
    _add()
    _, report = _doctor()
    assert report["store"]["documents"] == 1
    assert report["store"]["documents_on_disk"] == 1
    assert report["embedding"]["model"].startswith("deterministic")
    assert report["daemon"]["disabled_by_env"] is True


# -- the store half ---------------------------------------------------------


def test_a_store_that_will_not_open_still_produces_a_report(settings: Settings) -> None:
    """The finding *is* that the store is unusable, so exiting on it would
    print nothing at the one moment somebody needs the environment half."""
    _add()
    settings.schema_path.write_text("types:\n  - {{{ broken\n", encoding="utf-8")
    code, report = _doctor()
    assert code == 0, "no --strict: a diagnosis does not fail by default"
    assert {"schema-unreadable", "store-unreachable"} <= _kinds(report)
    # The half that needs no store is still there.
    assert report["installation"]["version"] == __version__
    assert report["daemon"]["running"] is False


def test_a_missing_index_is_read_before_the_dispatch_that_creates_one(
    settings: Settings,
) -> None:
    """`build_container` creates the index, so `index_present` has to be a
    snapshot: read it after dispatching and this finding can never fire."""
    _add()
    settings.db_path.unlink()
    _, report = _doctor()
    assert "no-index" in _kinds(report)


def test_an_empty_index_beside_files_is_an_error_on_the_second_run_too(
    settings: Settings,
) -> None:
    """The hole `no-index` alone leaves, and why it is an *error*.

    Doctor's own dispatch creates the index, so on a fresh clone the second run
    finds a file where the first found none. Reported as a mere warning, that run
    passed `--strict` — a gate that goes green on the second attempt is worse
    than one that never fired, and the corpus is in exactly the same state both
    times: every read answers nothing.
    """
    _add()
    _add("B")
    settings.db_path.unlink()
    code, first = _doctor("--strict")
    assert (code, "no-index" in _kinds(first)) == (1, True)

    code, report = _doctor("--strict")  # the index now exists, and is empty
    assert "no-index" not in _kinds(report), "the first run created one"
    assert "empty-index" in _kinds(report)
    assert code == 1, "same corpus, same answer: --strict must not go green here"
    assert (report["store"]["documents"], report["store"]["documents_on_disk"]) == (0, 2)


def test_an_index_merely_behind_its_files_stays_a_warning(settings: Settings) -> None:
    """A file that will not parse counts on disk and not in the index, for as
    long as it exists — so an error kind would red-build a repository for a
    condition `check` already reports as `malformed`, twice, for one file."""
    _add()
    (settings.docs_root / "decisions" / "broken.md").write_text(
        "---\nid: adr-9999\ntitle: B\ndescription: d\ntype: decision\n"
        "status: proposed\ncreated: not-a-date\nupdated: not-a-date\n"
        "tags: []\nrelated: []\n---\n\nbody\n",
        encoding="utf-8",
    )
    code, report = _doctor("--strict")
    assert "index-behind-files" in _kinds(report)
    assert "empty-index" not in _kinds(report)
    assert code == 0, "one unparseable file must not fail a gate twice"


def test_doctor_and_check_agree_that_a_store_is_unreadable(settings: Settings) -> None:
    """One store, one condition, two commands — and they must not disagree.

    `check` reports `empty-index` because its structural checks read that blank
    graph (adr-1cccd77cb023); `doctor` reports it because every read does. Both
    go through `index_is_empty`, and this is the assertion that the sharing
    survives from the CLI side: a caller told by one command that a store is
    unusable must not be told by the other that it is fine.

    Both are errors, so both gate. That pairing is the whole point — a warning on
    either side leaves a green gate over a corpus nobody read.
    """
    _add()
    _add("B")
    settings.db_path.unlink()
    _doctor()  # doctor's own dispatch leaves an index that exists and is empty

    code, report = _doctor("--strict")
    assert "empty-index" in _kinds(report)
    assert code == 1

    result = runner.invoke(app, ["--no-daemon", "check", "--strict"])
    findings = json.loads(result.stdout)
    kinds = {finding["kind"] for finding in findings}
    assert "empty-index" in kinds, "check must not call this store readable"
    assert result.exit_code == 1, "and must not pass a gate over a graph it never read"


def test_neither_reports_it_for_a_store_with_no_documents(settings: Settings) -> None:
    """A freshly initialised store has no files either, so the counts agree at
    zero. Firing here would greet every new store with an error from both."""
    settings.ensure_directories()
    _, report = _doctor()
    assert "empty-index" not in _kinds(report)

    findings = json.loads(runner.invoke(app, ["--no-daemon", "check"]).stdout)
    assert "empty-index" not in {finding["kind"] for finding in findings}


def test_an_index_built_by_another_version_is_reported(settings: Settings, uow_factory) -> None:
    _add()
    with uow_factory() as uow:
        uow.index_build.set("0.0.1-other")
        uow.commit()
    _, report = _doctor()
    assert "stale-index-build" in _kinds(report)
    assert "0.0.1-other" in _message(report, "stale-index-build")


def test_schema_drift_is_reported_with_the_first_change_named(
    settings: Settings, uow_factory
) -> None:
    """One difference in the message, not a count: the change arrived with no
    diff to read, and a bare number is not the diff either."""
    _add()
    # Injected as a *baseline* rather than as a schema edit: drift is the gap
    # between the schema the index was built against and the active one, and the
    # condition it exists for is the one no file edit produces — a type the
    # installed package added under a `docs-schema.yaml` nobody touched. The
    # baseline is the real description with one type taken out, so the diff is
    # exactly one line and the assertion can name it; an empty baseline would
    # produce ten and prove only that something differs.
    baseline = describe_schema(load_schema(settings.schema_path))
    types = [shape for shape in baseline["types"] if shape["name"] != "issue"]
    with uow_factory() as uow:
        uow.schema_baseline.set({**baseline, "types": types})
        uow.commit()
    _, report = _doctor()
    assert "schema-drift" in _kinds(report)
    assert _message(report, "schema-drift").endswith("+type issue")


# -- the embedding half -----------------------------------------------------


def test_a_leftover_embedder_variable_is_reported_twice(settings: Settings) -> None:
    """Once as the variable and once as its consequence.

    The consequence is what makes the variable legible: a vector made by another
    model reads as dirty, so a corpus with no current vectors is what a leftover
    DOCIR_EMBEDDER actually looks like from the index's side. The fixture sets
    the variable, so this is the suite's own environment reporting itself.
    """
    _add()
    settings.db_path.unlink()  # drop the vectors the add wrote
    _doctor()
    _, report = _doctor()
    assert "hashing-embedder" in _all_kinds(report)
    assert report["embedding"]["env"] == "deterministic"


def test_a_pending_embedding_queue_is_reported(settings: Settings, uow_factory) -> None:
    _add()
    with uow_factory() as uow:
        uow.embeddings.mark_dirty("adr-0001")
        uow.commit()
    _, report = _doctor()
    assert "embeddings-pending" in _kinds(report)


def test_the_model_is_not_loaded_without_probe(settings: Settings, monkeypatch) -> None:
    """The one check that can change the machine (a ~67MB download) is opt-in,
    so the default path must not reach the embedder at all."""
    loaded: list[str] = []
    monkeypatch.setattr(
        doctor,
        "build_embedder",
        lambda name=None: loaded.append(str(name)) or _never_embed(),
    )
    _add()
    _doctor()
    assert loaded == [], "doctor loaded a model without --probe"


def test_probe_reports_a_model_that_will_not_load(settings: Settings, monkeypatch) -> None:
    """A broken model raises from inside ONNX, which is not in docir's error
    taxonomy — a traceback here would make the diagnostic command the thing
    needing diagnosis."""
    monkeypatch.setattr(doctor, "build_embedder", lambda name=None: _never_embed())
    _add()
    code, report = _doctor("--probe")
    assert code == 0
    assert "model-probe-failed" in _kinds(report)
    assert report["probe"]["ok"] is False
    code, _ = _doctor("--probe", "--strict")
    assert code == 1, "a model that will not load is an error, not a warning"


# -- the process half -------------------------------------------------------


def test_a_shadowed_project_store_is_reported(tmp_path, monkeypatch) -> None:
    """The accident issue-e10cde8c5085 describes: a store beneath another one
    captures every command run under it while the outer corpus never sees them."""
    outer = tmp_path / "repo" / ".docir"
    inner = tmp_path / "repo" / "sub" / ".docir"
    outer.mkdir(parents=True)
    inner.mkdir(parents=True)
    monkeypatch.setenv("DOCIR_HOME", str(inner))
    _, report = _doctor()
    assert "shadowed-store" in _kinds(report)
    assert str(outer) in _message(report, "shadowed-store")


def test_the_global_store_is_not_reported_as_shadowing(tmp_path, monkeypatch) -> None:
    """`~/.docir` sits above every store under the user's home directory and
    being shadowed by a project store is what it is for. Reporting it would fire
    the finding on the ordinary correct setup, which is how a warning stops
    being read."""
    home = tmp_path / "user"
    (home / ".docir").mkdir(parents=True)
    project = home / "repo" / ".docir"
    project.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("DOCIR_HOME", str(project))
    _, report = _doctor()
    assert "shadowed-store" not in _kinds(report)


def test_an_unreadable_peer_is_named(settings: Settings, tmp_path) -> None:
    """Every federated read silently drops it, and a stderr line during that
    read is the only place it was ever said."""
    settings.ensure_directories()
    (settings.home / "stores.yaml").write_text(
        yaml.safe_dump({"stores": [str(tmp_path / "gone")]}), encoding="utf-8"
    )
    _add()
    _, report = _doctor()
    assert "peer-unavailable" in _kinds(report)
    assert report["peers"][0]["unavailable"] == "no such store"


def test_a_peer_is_reported_with_what_it_says_it_is(settings: Settings, tmp_path) -> None:
    """The description a federated row carries is the peer's own, so this is
    where the person who wrote it finds out whether this store can see it —
    without staging a query that happens to hit that corpus."""
    settings.ensure_directories()
    unbuilt = tmp_path / "platform" / ".docir"
    unbuilt.mkdir(parents=True)
    (unbuilt / "stores.yaml").write_text(
        yaml.safe_dump({"description": "Platform decisions binding every service."}),
        encoding="utf-8",
    )
    (settings.home / "stores.yaml").write_text(
        yaml.safe_dump({"stores": [str(unbuilt)], "description": "This service's own notes."}),
        encoding="utf-8",
    )
    _add()
    _, report = _doctor()
    (peer,) = report["peers"]
    # Both halves: an unreadable peer is still the peer it says it is, and the
    # reason it is skipped is the actionable half.
    assert peer["description"] == "Platform decisions binding every service."
    assert "docir reindex" in peer["unavailable"]
    assert report["store"]["description"] == "This service's own notes."


def test_a_store_that_describes_nothing_reports_no_description(settings: Settings) -> None:
    """The overwhelmingly common case, and never a finding: a store with no
    peers has nobody to introduce itself to. Absent rather than empty, which is
    what the trimmed payload does with every field nobody filled in."""
    _add()
    _, report = _doctor()
    assert "description" not in report["store"]


def test_no_daemon_env_is_reported_separately_from_the_flag(settings: Settings) -> None:
    """A leftover variable and a deliberate `--no-daemon` are the same setting
    and different facts; only the variable outlives the command."""
    _add()
    _, report = _doctor()
    assert "no-daemon-env" in _all_kinds(report), "the fixture exports DOCIR_NO_DAEMON"


# -- severity ---------------------------------------------------------------


def test_strict_gates_on_errors_only(settings: Settings, uow_factory) -> None:
    """A store between an upgrade and its next reindex is the ordinary state of
    every repo the week it upgrades; failing a setup script on it is how a gate
    gets turned off."""
    _add()
    with uow_factory() as uow:
        uow.index_build.set("0.0.1-other")
        uow.commit()
    code, report = _doctor("--strict")
    assert "stale-index-build" in _kinds(report)
    assert code == 0, "a warning must not fail --strict"

    settings.schema_path.write_text("types:\n  - {{{ broken\n", encoding="utf-8")
    code, _ = _doctor("--strict")
    assert code == 1


def test_every_error_kind_classifies_itself(settings: Settings) -> None:
    """Severity is derived from the kind, so a new finding cannot forget to
    classify itself — it either joins ERROR_KINDS or it is a warning."""
    assert doctor.severity_for("no-index") == doctor.ERROR
    assert doctor.severity_for("empty-index") == doctor.ERROR
    assert doctor.severity_for("index-behind-files") == doctor.WARNING
    assert doctor.severity_for("stale-index-build") == doctor.WARNING
    assert doctor.severity_for("a-kind-nobody-declared") == doctor.WARNING


def test_findings_lead_with_the_errors(settings: Settings) -> None:
    _add()
    settings.db_path.unlink()
    settings.schema_path.write_text("types:\n  - {{{ broken\n", encoding="utf-8")
    _, report = _doctor()
    severities = [finding["severity"] for finding in report["findings"]]
    assert severities == sorted(severities, key=lambda s: 0 if s == "error" else 1)


# -- helpers ----------------------------------------------------------------


def _message(report: dict, kind: str) -> str:
    for finding in report["findings"]:
        if finding["kind"] == kind:
            return str(finding["message"])
    raise AssertionError(f"no {kind} finding in {report['findings']}")


class _BrokenEmbedder:
    """An embedder whose model will not load, the way a truncated cache fails."""

    model_id = "broken-model"

    def embed(self, text: str):
        raise RuntimeError("model file is truncated")


def _never_embed() -> _BrokenEmbedder:
    return _BrokenEmbedder()


@pytest.fixture(autouse=True)
def _quiet_release_check(monkeypatch) -> None:
    """Nothing here may reach PyPI; the cache is empty, so `latest` is unknown."""
    monkeypatch.setenv("DOCIR_UPDATE_CHECK", "0")


# -- the conditions that cannot be staged in a temp store -------------------
#
# A published newer release, an absent fastembed, a daemon serving other code
# and a global-store fallback are properties of the machine, not of a fixture
# directory. `diagnose` is a pure mapping from facts to findings, so the facts
# are built directly — which is also the only way to assert the *wording*, and
# the wording is what these findings are for.


def _environment(**overrides) -> doctor.Environment:
    defaults: dict[str, object] = {
        "version": "1.2.3",
        "release": ReleaseStatus(
            installed="1.2.3",
            latest=None,
            checked_on=None,
            method="uv-tool",
            upgrade_command=("uv", "tool", "upgrade", "docir"),
            explanation="installed as a uv tool",
        ),
        "fastembed_installed": True,
        "home": Path("/store"),
        "home_origin": "project",
        "unintended_global": False,
        "shadowed_home": None,
        "schema_path": Path("/store/docs-schema.yaml"),
        "schema_present": True,
        "schema_error": "",
        "index_present": True,
        "embed_model": None,
        "embedder_env": "",
        "embedder_id": "fastembed:BAAI/bge-small-en-v1.5",
        "daemon": DaemonStatus(
            running=True, pid=7, socket_path="/tmp/s.sock", version="1.2.3", stale_code=False
        ),
        "daemon_env_disabled": False,
        "watch": True,
        "peers": (),
    }
    return doctor.Environment(**{**defaults, **overrides})


_HEALTHY_STORE = {
    "documents": 1,
    "documents_on_disk": 1,
    "version": "1.2.3",
    "stale_index_build": None,
    "schema_drift": [],
    "embedding_model": "fastembed:BAAI/bge-small-en-v1.5",
    "embeddings_pending": 0,
}


def _report(**overrides) -> doctor.DoctorReport:
    return doctor.diagnose(_environment(**overrides), dict(_HEALTHY_STORE))


def test_an_absent_fastembed_is_an_error() -> None:
    """It is a hard dependency, so its absence is a broken install rather than
    a configuration choice — every read silently degrades to shared vocabulary."""
    report = _report(fastembed_installed=False)
    assert "no-embedder" in {f.kind for f in report.findings}
    assert report.errors


def test_an_absent_fastembed_is_not_reported_when_the_fallback_was_asked_for() -> None:
    """DOCIR_EMBEDDER=deterministic is somebody saying they meant it. Reporting
    both would make the opt-out impossible to exercise without an error."""
    report = _report(fastembed_installed=False, embedder_env="deterministic")
    kinds = {f.kind for f in report.findings}
    assert "no-embedder" not in kinds
    assert "hashing-embedder" in kinds


def test_an_unknown_latest_release_is_not_reported_as_current() -> None:
    """Absent means nobody has checked, or the check failed — the reading every
    three-valued field in docir refuses."""
    assert "update-available" not in {f.kind for f in _report().findings}


def test_a_newer_release_is_reported_with_the_upgrade_command() -> None:
    status = ReleaseStatus(
        installed="1.2.3",
        latest="9.9.9",
        checked_on="2026-07-07",
        method="uv-tool",
        upgrade_command=("uv", "tool", "upgrade", "docir"),
        explanation="installed as a uv tool",
    )
    report = _report(release=status)
    finding = _find(report, "update-available")
    assert "9.9.9" in finding.message
    assert finding.fix == "docir self upgrade"
    assert finding.severity == doctor.WARNING, "an upgrade is not an outage"


def test_writes_landing_in_the_global_store_from_inside_a_repo_are_reported() -> None:
    """The documents land in the user's home directory, ungitted and invisible
    to everyone else, while the reported path reads as repo-relative."""
    finding = _find(_report(unintended_global=True), "global-fallback")
    assert "docir init" in finding.fix


def test_a_stale_daemon_names_the_version_gap_when_there_is_one() -> None:
    daemon = DaemonStatus(
        running=True, pid=7, socket_path="/tmp/s.sock", version="1.0.0", stale_code=True
    )
    assert (
        "serving docir 1.0.0 while this process is 1.2.3"
        in _find(_report(daemon=daemon), "stale-daemon").message
    )


def test_a_stale_daemon_on_the_same_version_says_what_actually_differs() -> None:
    """A code stamp is the version *and* the newest source mtime, so a reinstall
    or an edit under src/ makes a daemon stale with no version gap. Printing the
    pair anyway read as "serving 1.2.3 while this process is 1.2.3", which looks
    like a bug in the check rather than the finding it is."""
    daemon = DaemonStatus(
        running=True, pid=7, socket_path="/tmp/s.sock", version="1.2.3", stale_code=True
    )
    message = _find(_report(daemon=daemon), "stale-daemon").message
    assert "1.2.3 while this process is 1.2.3" not in message
    assert "different sources" in message


def test_a_daemon_from_before_the_version_check_reads_as_unknown() -> None:
    """A bare-integer pid file has no stamp; unknown never matches, which is
    correct — that daemon predates the check that would have replaced it."""
    daemon = DaemonStatus(
        running=True, pid=7, socket_path="/tmp/s.sock", version=None, stale_code=True
    )
    assert "unknown build" in _find(_report(daemon=daemon), "stale-daemon").message


def test_a_probe_that_works_reports_the_dimensions_and_the_time(monkeypatch) -> None:
    """ "It worked" and "it worked after fetching 67MB" are different answers to
    "why was my first command slow".

    Run against the hashing embedder, which is what keeps the assertion about
    the probe rather than about a model download: this test takes no `settings`
    fixture, so nothing else would stop it reaching the network.
    """
    monkeypatch.setenv("DOCIR_EMBEDDER", "deterministic")
    result = doctor.probe_embedder(None)
    assert result.ok and result.dimensions > 0 and result.seconds >= 0.0


def _find(report: doctor.DoctorReport, kind: str) -> doctor.DoctorFinding:
    for finding in report.findings:
        if finding.kind == kind:
            return finding
    raise AssertionError(f"no {kind} finding in {[f.kind for f in report.findings]}")
