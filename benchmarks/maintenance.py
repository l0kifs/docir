"""What maintenance costs, and how much of it is the embedding model.

``benchmarks/latency.py`` measures the read path and concluded that interpreter
startup dominates it — true, and it stayed true while a *write*-path command
took a minute unmeasured. Nothing here timed ``reindex``, ``check --fix`` or
``build``, so ``docir self upgrade`` on a 315-document store cost ~65 s and the
only report of it was a user noticing (issue-cfeb6eaa31cc).

Run::

    uv run python benchmarks/maintenance.py
    uv run python benchmarks/maintenance.py --sizes 100        # quicker

**Its own file rather than rows in ``latency.py``.** That harness samples each
command 15 times in three daemon modes; at a minute a run this would be hours,
and it would answer a question that is already settled. The daemon's whole
read-path win is the warm model (~0.5 s), which against a 60 s rebuild cannot
change the answer — the 65 s observed through a warm daemon and the 58.5 s
measured in-process are the same number on different days. So: one mode, one
sample, and sizes that stop where a rebuild stops being worth waiting for.

**The corpus is ``latency.py``'s.** Same generator and same seed, because two
harnesses reporting different numbers for "500 documents" would be measuring two
corpora and saying one word — the rule ``tokens.py`` already follows. Vectors
are printed beside documents because the rebuild's cost is linear in *those*:
every ``##`` section is embedded (adr-927aa43d9635), so 300 documents is ~1,300
vectors.

**The embedding share is measured, not asserted.** The same rebuild is run
against ``DOCIR_EMBEDDER=deterministic``, the model-free hashing embedder. The
difference is what the model costs, and it is the only number here that says
*why* the command is slow rather than *that* it is.

This is a measurement, not a test: it prints numbers and always exits 0.
"""

from __future__ import annotations

import argparse
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from latency import SEED, extend_store, vector_count

from docir.config.settings import Settings
from docir.entry_points.composition import build_container
from docir.entry_points.daemon import lifecycle
from docir.modules.documents.api import render_schema_yaml

#: Corpus sizes. Smaller than ``latency.py``'s: a full rebuild is ~60 s at 300
#: documents and grows linearly, so 2 000 would be ~7 minutes for one row that
#: says what 300 already said.
SIZES = (100, 300)

#: A version no docir has shipped, written into the build stamp to force the
#: expensive path. The stamp is compared for equality rather than order, so any
#: value that is not the running one selects a full rebuild.
FOREIGN_VERSION = "0.0.1"


def timed(argv: list[str], *, home: Path, env_overrides: dict[str, str] | None = None) -> float:
    """Run one whole ``docir`` process against *home* and return its seconds."""
    env = dict(os.environ)
    env["DOCIR_HOME"] = str(home)
    # Every command here builds a container and does real work, so the daemon
    # would only add a spawn to the first one and a socket hop to the rest.
    env["DOCIR_NO_DAEMON"] = "1"
    env.update(env_overrides or {})
    start = time.perf_counter()
    process = subprocess.run(
        [sys.executable, "-m", "docir", *argv],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    elapsed = time.perf_counter() - start
    if process.returncode != 0:
        raise RuntimeError(
            f"`docir {' '.join(argv)}` exited {process.returncode}: {process.stderr.strip()[:400]}"
        )
    return elapsed


def stamp_build(settings: Settings, version: str) -> None:
    """Rewrite the index build stamp, to select the rebuild path deliberately.

    Reached directly rather than through a command because no command writes it
    except ``reindex``, which is the thing being timed — single-writer is the
    property under test, so the harness must not add a second one to the CLI.
    """
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute("UPDATE index_build SET docir_version = ?", (version,))


def measure(settings: Settings, home: Path, project: Path, out: Path) -> list[tuple[str, float]]:
    """Time each maintenance command once, in an order that is itself the setup.

    ``reindex`` runs first because it leaves the stamp equal to the running
    version, which is the state every later row needs to mean what it says.
    """
    rows: list[tuple[str, float]] = []

    rows.append(("reindex (full)", timed(["reindex"], home=home)))
    rows.append(("reindex --changed", timed(["reindex", "--changed"], home=home)))

    # The stamp now equals the running build, so this is the upgrade a user runs
    # when it turns out there was nothing to upgrade.
    rows.append(
        (
            "self upgrade (stamp equal)",
            timed(["self", "upgrade", str(project), "--no-package"], home=home),
        )
    )
    stamp_build(settings, FOREIGN_VERSION)
    rows.append(
        (
            "self upgrade (stamp moved)",
            timed(["self", "upgrade", str(project), "--no-package"], home=home),
        )
    )

    rows.append(("check", timed(["check"], home=home)))
    rows.append(("check --fix", timed(["check", "--fix"], home=home)))
    rows.append(("embed --flush", timed(["embed", "--flush"], home=home)))
    shutil.rmtree(out, ignore_errors=True)
    rows.append(("build", timed(["build", "--out", str(out)], home=home)))

    # The share probe. A foreign `model_id` counts as dirty, so this rebuild
    # really does recompute every vector — with a hashing embedder rather than
    # the model, which is the whole difference between the two rows.
    stamp_build(settings, FOREIGN_VERSION)
    rows.append(
        (
            "reindex (no model)",
            timed(["reindex"], home=home, env_overrides={"DOCIR_EMBEDDER": "deterministic"}),
        )
    )
    return rows


def report(size: int, vectors: int, rows: list[tuple[str, float]]) -> None:
    print(f"\ncorpus: {size} documents · {vectors} vectors")
    header = f"{'command':<28} {'seconds':>9}"
    print(header)
    print("-" * len(header))
    for name, seconds in rows:
        print(f"{name:<28} {seconds:>9.2f}")

    timings = dict(rows)
    full, hashed = timings.get("reindex (full)"), timings.get("reindex (no model)")
    if full and hashed and full > hashed:
        share = (full - hashed) / full * 100
        print(
            f"\nembedding is {share:.0f}% of a full rebuild ({full - hashed:.1f}s of {full:.1f}s)"
        )
    cheap = timings.get("self upgrade (stamp equal)")
    dear = timings.get("self upgrade (stamp moved)")
    if cheap and dear:
        print(f"an upgrade that changed nothing: {cheap:.1f}s against {dear:.1f}s for a real one")


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintenance-command cost by corpus size.")
    parser.add_argument(
        "--sizes",
        default=",".join(str(size) for size in SIZES),
        help="Comma-separated corpus sizes, smallest first (default: 100,300).",
    )
    args = parser.parse_args()
    sizes = sorted({int(size) for size in args.sizes.split(",")})

    home = Path(tempfile.mkdtemp(prefix="docir-maintenance-"))
    # `self upgrade` also refreshes agent instruction files, and it writes them
    # relative to the project root it is given. A throwaway directory, so a
    # benchmark run cannot rewrite this repository's own skill files.
    project = Path(tempfile.mkdtemp(prefix="docir-maintenance-project-"))
    out = Path(tempfile.mkdtemp(prefix="docir-maintenance-site-"))
    os.environ["DOCIR_HOME"] = str(home)
    settings = Settings.resolve(home=home, use_daemon=False)
    settings.ensure_directories()
    settings.schema_path.write_text(render_schema_yaml(id_style="random"), encoding="utf-8")
    container = build_container(settings, background_embeddings=False)
    rng = random.Random(SEED)
    ids: list[str] = []

    print(f"embedder: {container.embedder.model_id}")
    print(f"store: {home}")
    try:
        for size in sizes:
            lifecycle.stop(settings)
            seconds = extend_store(container.dispatcher, ids, size, rng)
            print(f"\nbuilt {size} documents (+{seconds:.1f}s)")
            rows = measure(settings, home, project, out)
            report(size, vector_count(settings), rows)
        print(
            "\nA rebuild is dominated by the model, so the only lever is not rebuilding:\n"
            "`self upgrade` resyncs, and rebuilds in full only when the build stamp moved."
        )
    finally:
        lifecycle.stop(settings)
        container.close()
        for path in (home, project, out):
            shutil.rmtree(path, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
