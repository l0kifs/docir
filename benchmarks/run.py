"""Measure what docir actually retrieves, and what it costs to read.

docir's two load-bearing claims are that it finds the right documents and that
it is cheap for an agent to read. Neither was measured anywhere in the repo, so
every retrieval constant (candidate pool, fusion k, similarity thresholds) and
every design trade was being chosen without evidence. This is the evidence.

Run::

    uv run python benchmarks/run.py                 # default embedder
    DOCIR_EMBEDDER=fastembed uv run python benchmarks/run.py

It builds a throwaway store from ``corpus.yaml``, runs every task in
``tasks.yaml`` through each retrieval strategy, and reports recall, precision
and the size of the payload an agent would have to read.

This is a measurement, not a test: it prints numbers and always exits 0. Wire a
threshold around it only once the numbers are understood.
"""

from __future__ import annotations

import io
import os
import shutil
import tempfile
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path

import yaml

from docir.config.settings import Settings
from docir.entry_points.cli import rendering
from docir.entry_points.composition import build_container

BENCH_DIR = Path(__file__).resolve().parent

#: Result-set size every strategy is measured at. 5 is `docir context`'s default.
K = 5

#: Characters per token. A stand-in for a real tokenizer, which would add a
#: dependency for a number that only needs to be comparable between strategies.
CHARS_PER_TOKEN = 4


@dataclass
class Outcome:
    """One strategy's result for one task."""

    retrieved: list[str]
    payload_chars: int


def _emit_chars(data: object) -> int:
    """Size of the JSON an agent would actually receive, via the real renderer."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rendering.emit_json(data, trim=True)
    return len(buffer.getvalue())


def build_store(home: Path) -> tuple[object, dict[str, str]]:
    """Load the corpus into a fresh store; return the container and key -> id map."""
    os.environ["DOCIR_HOME"] = str(home)
    os.environ["DOCIR_NO_DAEMON"] = "1"
    settings = Settings.resolve(home=home, use_daemon=False)
    container = build_container(settings, background_embeddings=False)
    dispatcher = container.dispatcher

    corpus = yaml.safe_load((BENCH_DIR / "corpus.yaml").read_text(encoding="utf-8"))
    ids: dict[str, str] = {}
    # Two passes: every `related` target must exist before it can be referenced.
    for doc in corpus:
        view = dispatcher.dispatch(
            "add",
            {
                "type": doc["type"],
                "title": doc["title"],
                "description": doc["description"],
                "body": doc.get("body", ""),
            },
        )
        ids[doc["key"]] = view["id"]
    for doc in corpus:
        if doc.get("related"):
            dispatcher.dispatch(
                "update",
                {
                    "doc_id": ids[doc["key"]],
                    "set_related": [_edge(ids, ref) for ref in doc["related"]],
                },
            )
    # Status last: an edge cannot be written to a document the schema has closed,
    # and `status_path` walks legal transitions rather than forcing with --override,
    # so the corpus stays a corpus the CLI would actually accept.
    for doc in corpus:
        for status in doc.get("status_path", []):
            dispatcher.dispatch("update", {"doc_id": ids[doc["key"]], "status": status})
    dispatcher.dispatch("embed_flush", {})
    return container, ids


def _edge(ids: dict[str, str], ref: str) -> str:
    """Resolve a corpus `related` entry — `key` or `key:kind` — to a real edge."""
    key, _, kind = ref.partition(":")
    return f"{ids[key]}:{kind}" if kind else ids[key]


def strategies(dispatcher: object, task: str, ids: dict[str, str]) -> dict[str, Outcome]:
    """Every way an agent could get context, including not using docir at all."""
    inverse = {doc_id: key for key, doc_id in ids.items()}

    def keys(rows: list[dict]) -> list[str]:
        return [inverse[row["id"]] for row in rows if row["id"] in inverse]

    context = dispatcher.dispatch("context", {"task": task, "limit": K})
    context_flat = dispatcher.dispatch("context", {"task": task, "limit": K, "expand": 0})
    search = dispatcher.dispatch("search", {"text": task, "limit": K})
    everything = dispatcher.dispatch("query", {"limit": 1000})
    bodies = [dispatcher.dispatch("get", {"doc_id": doc_id}) for doc_id in ids.values()]

    return {
        "context": Outcome(keys(context), _emit_chars(context)),
        "context --expand 0": Outcome(keys(context_flat), _emit_chars(context_flat)),
        "search": Outcome(keys(search), _emit_chars(search)),
        "query (all skeletons)": Outcome(keys(everything), _emit_chars(everything)),
        "read every body": Outcome(keys(everything), _emit_chars(bodies)),
    }


def score(retrieved: list[str], relevant: list[str]) -> tuple[float, float, float]:
    """Recall, precision and reciprocal rank of the first relevant hit."""
    if not relevant:
        return 0.0, 0.0, 0.0
    hits = [key for key in retrieved if key in relevant]
    recall = len(set(hits)) / len(set(relevant))
    precision = len(hits) / len(retrieved) if retrieved else 0.0
    rank = next((i + 1 for i, key in enumerate(retrieved) if key in relevant), 0)
    return recall, precision, (1 / rank if rank else 0.0)


def main() -> int:
    home = Path(tempfile.mkdtemp(prefix="docir-bench-"))
    try:
        container, ids = build_store(home)
        dispatcher = container.dispatcher
        tasks = yaml.safe_load((BENCH_DIR / "tasks.yaml").read_text(encoding="utf-8"))

        # The resolved embedder, not the requested one: the default flipped to
        # fastembed (ADR-0011) and this line still announced "deterministic",
        # so every run so far reported a configuration it had not measured.
        embedder = container.embedder.model_id
        print(f"\ncorpus: {len(ids)} documents · tasks: {len(tasks)} · k={K}")
        print(f"embedder: {embedder}\n")

        totals: dict[str, dict[str, list[float]]] = {}
        misses: list[str] = []
        for task in tasks:
            results = strategies(dispatcher, task["task"], ids)
            missed = set(task["relevant"]) - set(results["context"].retrieved)
            if missed:
                wording = "same words" if task["lexical"] else "paraphrased"
                misses.append(
                    f"  {task['id']} ({wording}) {task['task'][:52]!r}\n"
                    f"      missed: {', '.join(sorted(missed))}"
                )
            for name, outcome in results.items():
                recall, precision, rr = score(outcome.retrieved, task["relevant"])
                bucket = totals.setdefault(
                    name,
                    {"recall": [], "precision": [], "rr": [], "chars": [], "lex": [], "sem": []},
                )
                bucket["recall"].append(recall)
                bucket["precision"].append(precision)
                bucket["rr"].append(rr)
                bucket["chars"].append(outcome.payload_chars)
                bucket["lex" if task["lexical"] else "sem"].append(recall)

        def mean(values: list[float]) -> float:
            return sum(values) / len(values) if values else 0.0

        header = f"{'strategy':<22} {'recall@5':>9} {'prec@5':>8} {'MRR':>6} {'~tokens':>9}"
        print(header)
        print("-" * len(header))
        for name, bucket in totals.items():
            print(
                f"{name:<22} {mean(bucket['recall']):>9.2f} {mean(bucket['precision']):>8.2f} "
                f"{mean(bucket['rr']):>6.2f} {mean(bucket['chars']) / CHARS_PER_TOKEN:>9.0f}"
            )

        print(f"\nrecall@{K} split by how the task is worded:")
        print(f"{'strategy':<22} {'same words':>11} {'paraphrased':>12}")
        print("-" * 47)
        for name, bucket in totals.items():
            print(f"{name:<22} {mean(bucket['lex']):>11.2f} {mean(bucket['sem']):>12.2f}")

        print(
            "\nThe paraphrased column is the one that matters: those tasks share no\n"
            "vocabulary with the documents they need, so only retrieval that captures\n"
            "meaning can find them."
        )
        if misses:
            print(f"\nwhat `context` missed ({len(misses)}/{len(tasks)} tasks):")
            print("\n".join(misses))
        else:
            print(
                f"\n`context` retrieved every judged-relevant document in all {len(tasks)} tasks."
            )
        container.close()
        return 0
    finally:
        shutil.rmtree(home, ignore_errors=True)
        os.environ.pop("DOCIR_HOME", None)


if __name__ == "__main__":
    raise SystemExit(main())
