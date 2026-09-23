"""Tests for ``initialize_store`` — the ``docir init`` bootstrap in composition."""

from __future__ import annotations

from pathlib import Path

import pytest

from docir.config.settings import Settings
from docir.entry_points.composition import (
    _STORE_GITIGNORE,
    _gitignore_entries,
    initialize_store,
    refresh_store_config,
    refresh_store_gitignore,
)
from docir.platform.errors import SchemaError


def _settings(tmp_path: Path) -> Settings:
    return Settings.resolve(home=tmp_path / ".docir", use_daemon=False)


def test_creates_schema_gitignore_and_index(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    result = initialize_store(settings)
    assert (settings.home / "docs-schema.yaml").exists()
    assert (settings.home / ".gitignore").exists()
    assert settings.db_path.exists()
    assert result.schema_written and result.gitignore_written
    assert result.profiles == ("software",)


def test_gitignore_excludes_the_derived_index(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    initialize_store(settings)
    text = (settings.home / ".gitignore").read_text(encoding="utf-8")
    assert "index.db" in text
    assert "daemon.pid" in text


def test_custom_profiles_are_written(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    result = initialize_store(settings, profiles=("research", "ops"))
    assert "profiles: [research, ops]" in settings.schema_path.read_text(encoding="utf-8")
    assert result.profiles == ("research", "ops")


def test_unknown_profile_raises(tmp_path: Path) -> None:
    with pytest.raises(SchemaError):
        initialize_store(_settings(tmp_path), profiles=("bogus",))


def test_idempotent_preserves_user_schema(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    initialize_store(settings)
    settings.schema_path.write_text("profiles: [research]\n", encoding="utf-8")
    result = initialize_store(settings)  # no force
    assert result.schema_written is False
    assert "research" in settings.schema_path.read_text(encoding="utf-8")


def test_force_rewrites_an_untouched_schema(tmp_path: Path) -> None:
    # Identical bytes: rewriting loses nothing, so --force alone is enough.
    settings = _settings(tmp_path)
    initialize_store(settings)
    result = initialize_store(settings, force=True)
    assert result.schema_written is True
    assert "profiles: [software]" in settings.schema_path.read_text(encoding="utf-8")


class TestForceProtectsACustomisedSchema:
    """`--force` no longer destroys a customised schema (guards issue-fde9a7151bd1).

    `--force` overwrote `docs-schema.yaml` and `.gitignore` under one flag, so
    re-running `init` to refresh the gitignore silently replaced every type,
    status and cadence a person had decided on — the one file in the store that
    cannot be rebuilt from the documents.

    The predecessor of this test was named `test_force_overwrites_schema` and
    asserted exactly that clobbering, so the suite could never have caught it.
    """

    @staticmethod
    def _customise(settings) -> str:
        settings.schema_path.write_text("profiles: [research]\n", encoding="utf-8")
        return "profiles: [research]"

    def test_force_alone_keeps_the_file_and_says_so(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path)
        initialize_store(settings)
        custom = self._customise(settings)
        result = initialize_store(settings, force=True)
        assert custom in settings.schema_path.read_text(encoding="utf-8")
        assert result.schema_written is False
        assert result.schema_preserved is True

    def test_force_schema_replaces_it_when_asked(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path)
        initialize_store(settings)
        self._customise(settings)
        result = initialize_store(settings, force=True, force_schema=True)
        assert result.schema_written is True
        assert "profiles: [software]" in settings.schema_path.read_text(encoding="utf-8")

    def test_the_gitignore_is_refreshed_even_when_the_schema_is_kept(self, tmp_path: Path) -> None:
        # The whole point, and why this skips rather than raises: refreshing the
        # gitignore is the thing the user came for, and an exception would abort
        # before it was written.
        settings = _settings(tmp_path)
        initialize_store(settings)
        self._customise(settings)
        gitignore = settings.home / ".gitignore"
        gitignore.write_text("stale contents\n", encoding="utf-8")

        result = initialize_store(settings, force=True)

        assert "index.db" in gitignore.read_text(encoding="utf-8")
        assert result.gitignore_written is True
        assert result.schema_preserved is True

    def test_an_unmodified_schema_is_not_reported_as_preserved(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path)
        initialize_store(settings)
        result = initialize_store(settings, force=True)
        assert result.schema_preserved is False


class TestAShadowedStoreIsReported:
    """issue-e10cde8c5085: `init` beneath an existing store captured every command run
    under it, and said nothing.

    Discovery walks *up*, so the nested store wins for the whole subtree and the
    outer store's `check` never sees documents added there — they are not
    orphaned or dangling, they are in a different corpus. adr-20eec6e2e2ca is right that
    `init` must not *reuse* a parent store; that is a different decision from
    not mentioning it.
    """

    def test_a_store_above_is_reported(self, tmp_path: Path) -> None:
        initialize_store(_settings(tmp_path))
        nested = tmp_path / "team"
        nested.mkdir()
        result = initialize_store(_settings(nested))
        assert result.enclosing_home == (tmp_path / ".docir").resolve()

    def test_a_store_with_nothing_above_reports_none(self, tmp_path: Path) -> None:
        # Distinguishes "nothing is above" from "the check did not run".
        assert initialize_store(_settings(tmp_path)).enclosing_home is None

    def test_re_initialising_does_not_report_itself(self, tmp_path: Path) -> None:
        initialize_store(_settings(tmp_path))
        assert initialize_store(_settings(tmp_path), force=True).enclosing_home is None

    def test_a_deeply_nested_store_finds_the_nearest_one(self, tmp_path: Path) -> None:
        initialize_store(_settings(tmp_path))
        middle = tmp_path / "a"
        middle.mkdir()
        initialize_store(_settings(middle))
        deep = middle / "b" / "c"
        deep.mkdir(parents=True)
        assert initialize_store(_settings(deep)).enclosing_home == (middle / ".docir").resolve()

    def test_an_explicitly_named_store_still_notices_a_sibling(self, tmp_path: Path) -> None:
        # `--home /srv/docs` does not end in `.docir`, so the walk has to start
        # at the store's own directory rather than its parent.
        initialize_store(_settings(tmp_path))
        named = Settings.resolve(home=tmp_path / "docs", use_daemon=False)
        assert initialize_store(named).enclosing_home == (tmp_path / ".docir").resolve()


class TestTheStoreIgnoresEverythingDocirWritesIntoIt:
    """The file's own promise: only `docs/` + `docs-schema.yaml` are committed.

    Guards issue-712f5bd17908, in the shape the defect asks for. `release-check.json`
    was missing from the generated list while docir wrote it into every store
    that ran `self status`, and the only test on the list read the list back —
    which passes on the constant being whatever the constant is.
    """

    #: The paths in the store that are meant to be committed, plus the ignore
    #: file itself. Everything else docir puts in `home` must be ignored.
    #:
    #: `store_config_path` is committed on purpose: it holds the answers a *team*
    #: gives once — today only whether this store's readers are told about a
    #: newer docir — so a teammate's clone inherits them. Per-machine choices are
    #: environment variables, and `release-check.json` below is where the
    #: per-machine *result* of this one lands, ignored like the rest.
    COMMITTED = ("docs_root", "schema_path", "tags_path", "store_config_path")

    def _store_paths(self, settings: Settings) -> list[Path]:
        """Every path ``Settings`` resolves inside the store, found by asking it.

        Introspection rather than a list, so the next path added to ``Settings``
        is covered by this test on the day it is added rather than on the day
        someone remembers. ``socket_path`` drops out on its own: it lives
        outside ``home`` precisely so a deep home cannot blow the ``AF_UNIX``
        limit.
        """
        committed = {getattr(settings, name) for name in self.COMMITTED}
        found = []
        for name in dir(type(settings)):
            if name.startswith("_") or not isinstance(getattr(type(settings), name), property):
                continue
            value = getattr(settings, name)
            if not isinstance(value, Path) or value in committed:
                continue
            if value != settings.home and settings.home in value.parents:
                found.append(value)
        return sorted(found)

    def test_every_path_settings_resolves_in_the_store_is_ignored(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path)
        initialize_store(settings)
        entries = set(_gitignore_entries((settings.home / ".gitignore").read_text("utf-8")))

        paths = self._store_paths(settings)

        # Which ones, not how many: a count cannot tell "all of them are
        # ignored" from "Settings stopped exposing any of them".
        assert {path.name for path in paths} == {
            "index.db",
            "daemon.log",
            "daemon.pid",
            "release-check.json",
        }
        for path in paths:
            assert path.name in entries, f"docir writes {path.name} and nothing ignores it"

    def test_nothing_meant_to_be_committed_is_ignored(self, tmp_path: Path) -> None:
        # The other direction, and it needs saying separately: the test above
        # walks what must be ignored and would stay green if a committed file
        # were added to the ignore list. `config.yaml` is the one that costs
        # something — it holds a decision a team took for everyone who clones
        # the repo, and ignoring it would make that decision this machine's.
        settings = _settings(tmp_path)
        initialize_store(settings)
        entries = set(_gitignore_entries((settings.home / ".gitignore").read_text("utf-8")))

        committed = {getattr(settings, name).name for name in self.COMMITTED}

        assert committed == {"docs", "docs-schema.yaml", "tags.yaml", "config.yaml"}
        for name in committed:
            assert name not in entries, f"{name} is meant to be committed and is ignored"

    def test_the_model_cache_is_ignored_where_the_store_is_the_global_home(
        self, tmp_path: Path
    ) -> None:
        # `~/.docir/models` sits inside the global store, and somebody keeping
        # personal notes there under git would otherwise commit 64 MB
        # (adr-78090be868ec). Not a `Settings` path, so the walk above cannot
        # see it.
        settings = _settings(tmp_path)
        initialize_store(settings)
        entries = _gitignore_entries((settings.home / ".gitignore").read_text("utf-8"))
        assert "models/" in entries

    def test_the_feedback_drafts_are_ignored_too(self, tmp_path: Path) -> None:
        # Not a `Settings` path — the skill names the directory — and the one
        # entry whose absence costs something: a draft nobody has reviewed for
        # redaction, showing up untracked (adr-7144cf291b1a).
        settings = _settings(tmp_path)
        initialize_store(settings)
        entries = _gitignore_entries((settings.home / ".gitignore").read_text("utf-8"))
        assert "feedback/" in entries


class TestAnExistingStoreIsBroughtUpToTheRunningBuild:
    """`refresh_store_gitignore` — the half `self upgrade` runs (issue-712f5bd17908).

    The file is written by the `init` that created the store and never again, so
    every entry docir has added since reached only the stores created after it.
    """

    def _aged(self, tmp_path: Path, keep: str) -> Settings:
        """A store whose ignore file predates an entry this build generates."""
        settings = _settings(tmp_path)
        initialize_store(settings)
        (settings.home / ".gitignore").write_text(keep, encoding="utf-8")
        return settings

    def test_it_adds_what_the_file_is_missing(self, tmp_path: Path) -> None:
        settings = self._aged(tmp_path, "index.db\ndaemon.pid\ndaemon.log\n")

        added = refresh_store_gitignore(settings.home, version="9.9.9")

        assert "feedback/" in added
        assert "release-check.json" in added
        text = (settings.home / ".gitignore").read_text("utf-8")
        assert "feedback/" in _gitignore_entries(text)
        assert "9.9.9" in text, "the block says which build added it"

    def test_it_keeps_the_lines_somebody_added(self, tmp_path: Path) -> None:
        # The reason this appends instead of regenerating. `init --force`
        # rewrites the file because the caller asked for exactly that; an
        # upgrade is routine, and deleting somebody's line without asking is the
        # defect `--force-schema` exists to avoid.
        settings = self._aged(tmp_path, "index.db\n*.local\n")

        refresh_store_gitignore(settings.home)

        entries = _gitignore_entries((settings.home / ".gitignore").read_text("utf-8"))
        assert "*.local" in entries
        assert "feedback/" in entries

    def test_one_version_announces_itself_once(self, tmp_path: Path) -> None:
        # Two releases that each add an entry each say so. One version saying it
        # twice is noise in a committed file, and it happens whenever a store is
        # upgraded again before the next release ships.
        settings = self._aged(tmp_path, "index.db\n")
        refresh_store_gitignore(settings.home, version="9.9.9")
        (settings.home / ".gitignore").write_text(
            (settings.home / ".gitignore").read_text("utf-8").replace("feedback/\n", ""),
            encoding="utf-8",
        )

        refresh_store_gitignore(settings.home, version="9.9.9")

        text = (settings.home / ".gitignore").read_text("utf-8")
        assert text.count("Added by docir 9.9.9") == 1
        assert "feedback/" in _gitignore_entries(text)

    def test_a_second_run_adds_nothing(self, tmp_path: Path) -> None:
        settings = self._aged(tmp_path, "index.db\n")
        refresh_store_gitignore(settings.home)
        before = (settings.home / ".gitignore").read_text("utf-8")

        assert refresh_store_gitignore(settings.home) == ()
        assert (settings.home / ".gitignore").read_text("utf-8") == before

    def test_a_store_this_build_created_needs_nothing(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path)
        initialize_store(settings)
        assert refresh_store_gitignore(settings.home) == ()

    def test_a_store_that_never_ran_init_gets_the_whole_file(self, tmp_path: Path) -> None:
        # A global `~/.docir` grown by first use rather than created by `init`.
        settings = _settings(tmp_path)
        initialize_store(settings)
        (settings.home / ".gitignore").unlink()

        added = refresh_store_gitignore(settings.home)

        assert "index.db" in added and "feedback/" in added
        assert (settings.home / ".gitignore").read_text("utf-8") == _STORE_GITIGNORE

    def test_a_file_with_no_trailing_newline_does_not_glue_two_entries(
        self, tmp_path: Path
    ) -> None:
        settings = self._aged(tmp_path, "index.db")

        refresh_store_gitignore(settings.home)

        assert "feedback/" in _gitignore_entries((settings.home / ".gitignore").read_text("utf-8"))


class TestTheStoreRecordsTheReleaseCheckDecision:
    """`config.yaml` — what a team answers once and commits (adr-a555ee6bc484).

    Creating a store is the act that opts into docir's only network call. The
    answer is recorded in the store rather than in each person's shell so that a
    clone inherits it, and `DOCIR_UPDATE_CHECK=0` is how one person opts back
    out. Everything here is about not overwriting an answer somebody gave.
    """

    def test_init_writes_the_opt_in(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path)
        result = initialize_store(settings)
        assert result.config_written
        assert settings.store_config_path.exists()
        from docir.config.settings import store_update_check

        assert store_update_check(settings.home) is True

    def test_a_store_that_said_no_keeps_saying_no(self, tmp_path: Path) -> None:
        # The one that matters: `self upgrade` runs the same top-up, so an
        # opt-out that a routine upgrade reversed would be an opt-out nobody
        # could hold. A key already present is a decision, whatever its value.
        settings = _settings(tmp_path)
        initialize_store(settings)
        settings.store_config_path.write_text("update_check: false\n", encoding="utf-8")

        added = refresh_store_config(settings.home)

        assert added == ()
        from docir.config.settings import store_update_check

        assert store_update_check(settings.home) is False

    def test_force_does_not_regenerate_it(self, tmp_path: Path) -> None:
        # Unlike the `.gitignore` beside it, which `--force` rewrites because it
        # is a constant this build generates.
        settings = _settings(tmp_path)
        initialize_store(settings)
        settings.store_config_path.write_text("update_check: false\n", encoding="utf-8")

        initialize_store(settings, force=True)

        assert settings.store_config_path.read_text("utf-8") == "update_check: false\n"

    def test_an_older_store_gains_it_on_upgrade(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path)
        initialize_store(settings)
        settings.store_config_path.unlink()

        added = refresh_store_config(settings.home)

        assert "update_check" in added
        assert settings.store_config_path.exists()

    def test_a_top_up_keeps_the_comments_somebody_wrote(self, tmp_path: Path) -> None:
        # Appended as text rather than dumped from parsed YAML: a parse-and-dump
        # round trip deletes every comment in a committed file, which is how a
        # command asked to add one line removes ten.
        settings = _settings(tmp_path)
        initialize_store(settings)
        settings.store_config_path.write_text(
            "# why we turned this off\nsomething_else: 1\n", encoding="utf-8"
        )

        added = refresh_store_config(settings.home)

        text = settings.store_config_path.read_text("utf-8")
        assert "update_check" in added
        assert "# why we turned this off" in text
        assert "something_else: 1" in text
