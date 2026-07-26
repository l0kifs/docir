"""Concurrent id allocation across independent processes.

Guards GAP-009: ``docir --no-daemon add`` run in parallel used to hand every
caller the same id. ``next_number`` read the counter, incremented it in Python,
then wrote it back, so N processes could all read the same value before any of
them committed. Six simultaneous adds returned ``adr-0002`` six times; five of
those documents were written to disk and then shadowed in the index, which
dedupes by primary key.

The daemon hides this by serializing requests one connection at a time, so the
regression only reproduces with ``--no-daemon`` -- which is the mode this
project's own test suite and CI use, and the mode a parallel-agent script is
most likely to take.

These tests spawn real processes: nothing single-threaded can exercise a
cross-process read-modify-write race.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Enough writers to lose the race reliably on the old code (it failed at 6),
# while staying quick.
_WRITERS = 8

# Wall-clock barrier: every child sleeps until the same instant before calling
# docir, so the processes genuinely overlap instead of finishing in sequence
# behind staggered interpreter startup.
_BARRIER_DELAY_SECONDS = 2.0

_CHILD = """\
import sys, time
time.sleep(max(0.0, {start} - time.time()))
sys.argv = ['docir', '--no-daemon', '--home', {home!r},
            'add', '--type', 'decision', '--title', 'p{index}',
            '--description', 'concurrent write']
from docir.entry_points.cli.app import main
main()
"""


def _add_concurrently(home: Path, count: int) -> tuple[list[str], list[str]]:
    """Run ``count`` adds that all fire at once; return their ids and failures."""
    start = time.time() + _BARRIER_DELAY_SECONDS
    env = dict(os.environ, DOCIR_NO_DAEMON="1", DOCIR_HOME=str(home))
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", _CHILD.format(start=start, home=str(home), index=index)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        for index in range(count)
    ]
    ids: list[str] = []
    failures: list[str] = []
    for process in processes:
        output = (process.communicate()[0] or "").strip()
        try:
            ids.append(json.loads(output.splitlines()[-1])["id"])
        except (ValueError, IndexError, KeyError):
            failures.append(output)
    return ids, failures


@pytest.fixture
def seeded_store(settings, container):
    """A migrated store holding one document, so children race on allocation only."""
    container.dispatcher.dispatch(
        "add", {"type": "decision", "title": "seed", "description": "seed"}
    )
    return settings


@pytest.mark.slow
def test_parallel_adds_never_share_an_id(seeded_store) -> None:
    ids, failures = _add_concurrently(seeded_store.home, _WRITERS)

    assert not failures, f"some concurrent adds failed outright: {failures}"
    assert len(ids) == _WRITERS
    assert len(set(ids)) == _WRITERS, f"duplicate ids handed out: {sorted(ids)}"


@pytest.mark.slow
def test_parallel_adds_leave_every_document_on_disk(seeded_store) -> None:
    # The index dedupes by primary key, so a collision is invisible there; only
    # counting the canonical files proves no document was shadowed.
    ids, failures = _add_concurrently(seeded_store.home, _WRITERS)
    assert not failures

    files = sorted((seeded_store.docs_root / "decisions").glob("*.md"))
    assert len(files) == _WRITERS + 1  # the seed plus one file per writer
    assert sorted(ids) == sorted(set(ids))
