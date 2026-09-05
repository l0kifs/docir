"""An index migrated past this build is refused by name, not by traceback.

`run_migrations` runs when the composition root opens the store, so an index
carrying a revision this docir does not ship took down every command — `get`,
`query`, `check`, `reindex` and `doctor` alike — with a raw
`alembic.util.exc.CommandError` naming a revision id and nothing else
(issue-38a4f13b1e61). `reindex` and `doctor` are the documented repair paths, so
the state that needed them was the one state they could not run in.

The condition was already detectable: `known_revisions()` and `index_revision()`
exist for the federation peer check, which asks this question of *someone else's*
store and never asked it of this one.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command

from docir.config.settings import Settings
from docir.entry_points.composition import build_container
from docir.entry_points.dispatch import Dispatcher
from docir.platform.errors import DocirError, UnknownIndexRevisionError
from docir.platform.persistence.engine import (
    _alembic_config,
    head_revision,
    known_revisions,
    run_migrations,
)

#: A revision no docir ships or will ship — the shape of a future migration.
FROM_THE_FUTURE = "9999"


def _stamp(db_path: Path, revision: str) -> None:
    """Rewrite the index's recorded alembic revision, as a newer build would."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE alembic_version SET version_num = ?", (revision,))


def _revision_of(db_path: Path) -> str:
    with sqlite3.connect(db_path) as conn:
        return str(conn.execute("SELECT version_num FROM alembic_version").fetchone()[0])


class TestItRefusesAnIndexFromANewerBuild:
    def test_a_revision_this_build_does_not_ship_is_refused_by_name(
        self, settings: Settings, dispatcher: Dispatcher
    ) -> None:
        _stamp(settings.db_path, FROM_THE_FUTURE)

        with pytest.raises(UnknownIndexRevisionError) as raised:
            run_migrations(settings.database_url)

        message = str(raised.value)
        # The three facts alembic's own error withholds: which store, which two
        # schemas, and what to do about it.
        assert str(settings.db_path) in message
        assert FROM_THE_FUTURE in message
        assert head_revision() in message
        assert "docir reindex" in message

    def test_it_is_a_docir_error_so_the_cli_maps_an_exit_code(
        self, settings: Settings, dispatcher: Dispatcher
    ) -> None:
        # The defect was that this escaped as an alembic exception: `runner.py`
        # maps `exit_code` off `DocirError` and nothing else.
        _stamp(settings.db_path, FROM_THE_FUTURE)

        with pytest.raises(DocirError) as raised:
            run_migrations(settings.database_url)

        assert raised.value.exit_code == 8

    def test_the_revision_it_refuses_is_genuinely_unknown_to_this_build(self) -> None:
        # Guards the guard: if `9999` ever ships, the two tests above would pass
        # while asserting nothing.
        assert FROM_THE_FUTURE not in known_revisions()
        assert head_revision() in known_revisions()


class TestItStillOpensEverythingElse:
    def test_an_index_at_this_build_s_head_upgrades_silently(
        self, settings: Settings, dispatcher: Dispatcher
    ) -> None:
        run_migrations(settings.database_url)  # the ordinary path, twice over

        assert _revision_of(settings.db_path) == head_revision()

    def test_an_index_behind_this_build_is_upgraded_not_refused(self, settings: Settings) -> None:
        # The ordinary upgrade path — an index a *previous* docir built — which
        # a guard aimed at the other direction must not catch. Migrated for real
        # rather than restamped: rewriting the version on a finished schema
        # replays migrations onto columns that already exist, which tests the
        # fixture rather than the product.
        settings.ensure_directories()
        command.upgrade(_alembic_config(settings.database_url), "0001")
        assert _revision_of(settings.db_path) == "0001"

        run_migrations(settings.database_url)

        assert _revision_of(settings.db_path) == head_revision()

    def test_a_store_with_no_index_yet_is_not_refused(self, settings: Settings) -> None:
        # Absent means "cannot say", the same rule `index_revision` follows for a
        # peer — and a fresh store must migrate from nothing, not fail.
        settings.ensure_directories()
        assert not settings.db_path.exists()

        run_migrations(settings.database_url)

        assert settings.db_path.exists()


class TestOpeningTheStoreIsWhereItFires:
    """Every command opens the store, so every command gets this error.

    Asserted against `build_container` rather than a dispatcher: the container
    the fixture already built ran its migration before the stamp, so dispatching
    through it would prove nothing. A CLI invocation builds a fresh one.
    """

    def test_building_a_container_on_a_future_index_raises(self, settings: Settings) -> None:
        settings.ensure_directories()
        run_migrations(settings.database_url)
        _stamp(settings.db_path, FROM_THE_FUTURE)

        with pytest.raises(UnknownIndexRevisionError):
            build_container(settings, background_embeddings=False).close()

    def test_it_fires_before_anything_reads_the_documents(self, settings: Settings) -> None:
        # `reindex` and `doctor` are the documented repair paths. They fail here
        # too, deliberately — but by name, which is the whole fix: the raw
        # `CommandError` said only "Can't locate revision identified by '9999'".
        settings.ensure_directories()
        run_migrations(settings.database_url)
        _stamp(settings.db_path, FROM_THE_FUTURE)

        with pytest.raises(UnknownIndexRevisionError) as raised:
            build_container(settings, background_embeddings=False).close()

        assert "CommandError" not in str(raised.value)
        assert "does not ship" in str(raised.value)
