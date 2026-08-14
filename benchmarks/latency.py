"""What a read costs in wall-clock time, and what the daemon is worth.

``benchmarks/run.py`` answers whether docir finds the right documents. It says
nothing about how long the agent waits for them, and that is the other half of
the read contract: the daemon exists *only* to keep the embedding model warm
and serialize writes, and nothing in this repo measured whether it earns the
process it costs. This does.

Run::

    uv run python benchmarks/latency.py
    uv run python benchmarks/latency.py --sizes 25,100 --samples 8   # quicker

It grows one throwaway store through 25 -> 100 -> 500 -> 2000 generated
documents and, at each size, times whole ``python -m docir`` processes in three
modes:

``warm daemon``
    A daemon is already serving this store — the common case, and the one the
    architecture is designed around.
``cold daemon``
    The daemon is stopped before every sample, so each one pays a spawn, a
    model load and a socket handshake. That is the first command after an idle
    shutdown, a reboot, or an upgrade (a daemon serving different code is
    replaced rather than reused).
``no daemon``
    ``DOCIR_NO_DAEMON=1``: every command builds the container and loads the
    model in-process, sharing nothing with the invocation before it. This is
    what the daemon is measured against.

**Whole processes, not dispatcher calls.** The three modes differ only in what
a *process* has to do before it can answer, so timing ``dispatch()`` would
measure the one part of the question that is identical in all three. The price
is that every number here includes interpreter start and docir's imports, which
is why ``docir version`` is timed beside them as a floor row: it builds no
container and opens no store, so subtracting it separates "starting Python"
from "answering the question".

**The corpus is generated, not ``corpus.yaml``.** This measures time rather
than relevance, so a corpus needs a size and a shape instead of judgments — and
sizes past 26 do not exist in a hand-written fixture. Documents are templated
from a seeded RNG, so every run builds the same store. Each carries four ``##``
sections, because the semantic scan is linear in *chunks* rather than documents
(adr-927aa43d9635) — which is why the vector count is printed beside the
document count, and why 2 000 documents is really ~10 000 vectors.

Output is captured, so every timed command takes the JSON path a piped CLI
takes: the agent-facing one, not the rich renderer.

This is a measurement, not a test: it prints numbers and always exits 0.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from docir.config.settings import Settings
from docir.entry_points.composition import build_container
from docir.entry_points.daemon import lifecycle
from docir.modules.documents.api import render_schema_yaml

#: Corpus sizes the curve is drawn through. 2 000 is well past any hand-written
#: docs tree; it is here to show the shape, not to describe a real store.
SIZES = (25, 100, 500, 2000)

#: Samples per (command, mode). A cold sample costs a daemon spawn and a model
#: load, so it gets fewer of them — and at n=5 the p95 column *is* the slowest
#: run, which is why the count is printed in the table rather than assumed.
SAMPLES = {"warm daemon": 15, "cold daemon": 5, "no daemon": 5, "floor": 5}

#: Order is narrative: what you normally pay, what you pay after an idle
#: shutdown, and what you would pay with no daemon at all.
MODES = ("warm daemon", "cold daemon", "no daemon")

#: Read queries, rotated across samples so no single one is answered fifteen
#: times from a warm SQLite page cache. They deliberately paraphrase the corpus
#: rather than quote it: a query that hits nothing lexically still runs the
#: whole vector scan, which is the part that grows with the corpus.
QUERIES = (
    "how do we avoid charging a customer twice",
    "what happens when a downstream call keeps failing",
    "where is the audit trail for money movement",
    "who owns the rules for holding back a payout",
    "how is a partial reversal recorded",
    "what limits a noisy integration to its own share",
)

_SEED = 20260814

_TYPES = ("decision", "issue", "architecture")

_SUBJECTS = (
    "checkout",
    "the ledger",
    "webhook delivery",
    "refunds",
    "payout scheduling",
    "the reconciliation job",
    "card authorization",
    "dispute intake",
    "the fee engine",
    "settlement export",
)

_ASPECTS = (
    "idempotency",
    "retry policy",
    "rate limiting",
    "audit trail",
    "backpressure",
    "schema evolution",
    "failure isolation",
    "observability",
)

_UNITS = ("request", "batch", "merchant", "currency", "connector", "tenant")

_VERBS = ("validates", "records", "defers", "rejects", "replays", "coalesces")

_SECTIONS = ("Context", "Decision", "Consequences", "Alternatives considered")

_TEMPLATES = (
    "The {subject} path {verb} {aspect} on every {unit}, and the cost is paid once.",
    "Anything that skips {aspect} in {subject} shows up later as a mismatch per {unit}.",
    "We {verb} the {unit} before {subject} commits, so {aspect} has a single owner.",
    "Operators asked for {aspect} in {subject} after a bad week of duplicated work.",
    "A second writer to {subject} would break {aspect}, one {unit} at a time.",
    "{aspect} is cheap here and expensive downstream, so {subject} pays for it.",
    "The alternative was to let each {unit} carry its own {aspect}, which nobody could audit.",
    "Where {subject} {verb} a {unit} twice, {aspect} is what makes the second one free.",
)


def _sentence(rng: random.Random, subject: str, aspect: str) -> str:
    return rng.choice(_TEMPLATES).format(
        subject=subject,
        aspect=aspect,
        unit=rng.choice(_UNITS),
        verb=rng.choice(_VERBS),
    )


def _document(index: int, rng: random.Random, previous: list[str]) -> dict[str, object]:
    """One generated document: four sections, and edges to documents already in."""
    subject = _SUBJECTS[index % len(_SUBJECTS)]
    aspect = _ASPECTS[(index // len(_SUBJECTS)) % len(_ASPECTS)]
    body = "\n\n".join(
        f"## {heading}\n\n" + " ".join(_sentence(rng, subject, aspect) for _ in range(3))
        for heading in _SECTIONS
    )
    # Backwards only, so a target always exists and the corpus loads in one
    # pass — `run.py` needs two passes only because its edges point forwards.
    edges = rng.sample(previous, min(2, len(previous))) if previous else []
    return {
        "type": _TYPES[index % len(_TYPES)],
        "title": f"{aspect.capitalize()} for {subject} ({index:04d})",
        "description": f"How {subject} handles {aspect}.",
        "body": body,
        "related": edges,
    }


def extend_store(dispatcher: object, ids: list[str], target: int, rng: random.Random) -> float:
    """Grow the store to *target* documents in place; return seconds spent.

    Growing one store rather than building a fresh one per size halves the work
    (2 000 adds instead of 2 625) and costs nothing: a store that grew to 500 is
    the same store as one built at 500.
    """
    start = time.perf_counter()
    while len(ids) < target:
        doc = _document(len(ids), rng, ids)
        view = dispatcher.dispatch("add", doc)
        ids.append(view["id"])
    dispatcher.dispatch("embed_flush", {})
    return time.perf_counter() - start


def vector_count(settings: Settings) -> int:
    """Document vectors plus section vectors — what the semantic scan walks."""
    with sqlite3.connect(settings.db_path) as conn:
        documents = conn.execute(
            "SELECT COUNT(*) FROM embeddings WHERE vector IS NOT NULL"
        ).fetchone()[0]
        chunks = conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0]
    return int(documents) + int(chunks)


def timed(argv: list[str], *, no_daemon: bool) -> float:
    """Run one whole ``docir`` process and return its wall-clock seconds."""
    env = dict(os.environ)
    # Any non-empty value forces in-process execution, so daemon mode has to
    # *remove* the variable rather than set it to "0" (config/settings.py).
    env.pop("DOCIR_NO_DAEMON", None)
    if no_daemon:
        env["DOCIR_NO_DAEMON"] = "1"
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


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile: with n=5 the p95 is the slowest sample, not a fit."""
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def measure(
    settings: Settings,
    commands: dict[str, Callable[[int], list[str]]],
    warm_samples: int,
) -> dict[tuple[str, str], list[float]]:
    """Time every (command, mode) pair at the store's current size."""
    samples: dict[tuple[str, str], list[float]] = {}
    for mode in MODES:
        count = warm_samples if mode == "warm daemon" else SAMPLES[mode]
        if mode == "warm daemon":
            # One untimed run so the daemon is spawned and the model loaded;
            # timing that would be the cold row measured under the wrong name.
            timed(["version"], no_daemon=False)
            timed(next(iter(commands.values()))(0), no_daemon=False)
        for name, argv in commands.items():
            times: list[float] = []
            for index in range(count):
                if mode == "cold daemon":
                    lifecycle.stop(settings)
                times.append(timed(argv(index), no_daemon=(mode == "no daemon")))
            samples[name, mode] = times
            print(f"    {name:<9} {mode:<12} p50 {percentile(times, 50):>6.3f}s")
    floor = [timed(["version"], no_daemon=True) for _ in range(SAMPLES["floor"])]
    samples["version", "floor"] = floor
    print(f"    {'version':<9} {'floor':<12} p50 {percentile(floor, 50):>6.3f}s")
    return samples


def _report_size(size: int, vectors: int, samples: dict[tuple[str, str], list[float]]) -> None:
    print(f"\ncorpus: {size} documents · {vectors} vectors")
    header = f"{'command':<9} {'mode':<12} {'n':>3} {'p50 (s)':>9} {'p95 (s)':>9}"
    print(header)
    print("-" * len(header))
    for (name, mode), times in samples.items():
        print(
            f"{name:<9} {mode:<12} {len(times):>3} "
            f"{percentile(times, 50):>9.3f} {percentile(times, 95):>9.3f}"
        )


def _report_scaling(
    sizes: list[int], collected: dict[int, dict[tuple[str, str], list[float]]]
) -> None:
    """The curve: one p50 per (command, mode) per size, side by side."""
    pairs = list(collected[sizes[0]])
    print("\np50 seconds by corpus size")
    header = f"{'command':<9} {'mode':<12}" + "".join(f"{size:>9}" for size in sizes)
    print(header)
    print("-" * len(header))
    for name, mode in pairs:
        row = "".join(f"{percentile(collected[size][name, mode], 50):>9.3f}" for size in sizes)
        print(f"{name:<9} {mode:<12}{row}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read latency by corpus size and daemon mode.")
    parser.add_argument(
        "--sizes",
        default=",".join(str(size) for size in SIZES),
        help="Comma-separated corpus sizes, smallest first (default: 25,100,500,2000).",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=SAMPLES["warm daemon"],
        help="Warm-daemon samples per command (default: 15).",
    )
    args = parser.parse_args()
    sizes = sorted({int(size) for size in args.sizes.split(",")})

    home = Path(tempfile.mkdtemp(prefix="docir-latency-"))
    os.environ["DOCIR_HOME"] = str(home)
    settings = Settings.resolve(home=home, use_daemon=False)
    settings.ensure_directories()
    # The shipped default, as `docir init` writes it — a random id is three
    # times the length of a sequential one in every skeleton the read returns.
    settings.schema_path.write_text(render_schema_yaml(id_style="random"), encoding="utf-8")
    container = build_container(settings, background_embeddings=False)
    rng = random.Random(_SEED)
    ids: list[str] = []
    collected: dict[int, dict[tuple[str, str], list[float]]] = {}

    print(f"embedder: {container.embedder.model_id}")
    print(f"store: {home}")
    try:
        for size in sizes:
            # A daemon left over from the previous size is a second writer, and
            # SQLite has one — stop it before the store grows under it.
            lifecycle.stop(settings)
            seconds = extend_store(container.dispatcher, ids, size, rng)
            print(f"\nbuilt {size} documents (+{seconds:.1f}s)")
            # A document from the middle of the store, so `get` reads neither
            # the newest nor the oldest row.
            middle = ids[len(ids) // 2]
            commands: dict[str, Callable[[int], list[str]]] = {
                "context": lambda index: ["context", QUERIES[index % len(QUERIES)]],
                "search": lambda index: ["search", QUERIES[index % len(QUERIES)]],
                "get": lambda index, doc_id=middle: ["get", doc_id],
            }
            samples = measure(settings, commands, args.samples)
            collected[size] = samples
            _report_size(size, vector_count(settings), samples)
        _report_scaling(sizes, collected)
        print(
            "\nSubtract the `version` floor to separate starting Python from answering\n"
            "the question. What is left of a warm-daemon read is the daemon's whole\n"
            "cost: a socket round trip and the work itself."
        )
    finally:
        lifecycle.stop(settings)
        container.close()
        shutil.rmtree(home, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
