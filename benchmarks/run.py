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
import math
import os
import shutil
import tempfile
from collections.abc import Callable
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from docir.config.settings import Settings
from docir.entry_points.cli import rendering
from docir.entry_points.composition import build_container
from docir.modules.documents.api import render_schema_yaml
from docir.modules.documents.domain.entities.document import Document
from docir.modules.documents.domain.value_objects.identifiers import RANDOM_SUFFIX_LENGTH

#: Bits of entropy in a random id suffix, derived from the implementation rather
#: than restated, so the table cannot describe a size docir no longer mints.
_RANDOM_BITS = RANDOM_SUFFIX_LENGTH * 4

BENCH_DIR = Path(__file__).resolve().parent

#: Any fixed date. `Document` requires one; nothing here reads it.
_BENCH_DATE = date(2026, 1, 1)

#: Result-set size every strategy is measured at. 5 is `docir context`'s default.
K = 5

#: Characters per token. A stand-in for a real tokenizer, which would add a
#: dependency for a number that only needs to be comparable between strategies.
CHARS_PER_TOKEN = 4


#: Digits a sequential suffix uses (`adr-0007`) — the alternative a random id is
#: being priced against.
SEQUENTIAL_DIGITS = 4

#: Corpus sizes the collision table is computed at.
_CORPUS_SIZES = (100, 1_000, 10_000, 100_000)


@dataclass
class Outcome:
    """One strategy's result for one task."""

    retrieved: list[str]
    payload_chars: int
    #: Characters of that payload that are document ids — in the `id` field and
    #: in every `related` target. This is what the entropy choice actually buys
    #: and costs, and it was never measured (issue-7a271eb0f21a).
    id_chars: int
    #: What those same ids would have cost as `adr-0007`.
    sequential_id_chars: int


def _emit(data: object) -> str:
    """The JSON an agent would actually receive, via the real renderer."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rendering.emit_json(data, trim=True)
    return buffer.getvalue()


def _id_cost(payload: str, all_ids: list[str]) -> tuple[int, int]:
    """Characters spent on ids in ``payload``, actual and sequential-equivalent.

    Counts occurrences rather than parsing: an id is quoted the same way in the
    `id` field and in a `related` target, and both are paid for on every read.
    """
    actual = equivalent = 0
    for doc_id in all_ids:
        occurrences = payload.count(doc_id)
        if not occurrences:
            continue
        prefix = doc_id.split("-", 1)[0]
        actual += occurrences * len(doc_id)
        equivalent += occurrences * (len(prefix) + 1 + SEQUENTIAL_DIGITS)
    return actual, equivalent


def _outcome(retrieved: list[str], data: object, all_ids: list[str]) -> Outcome:
    payload = _emit(data)
    id_chars, sequential = _id_cost(payload, all_ids)
    return Outcome(retrieved, len(payload), id_chars, sequential)


def build_store(home: Path, corpus_file: str = "corpus.yaml") -> tuple[object, dict[str, str]]:
    """Load a corpus into a fresh store; return the container and key -> id map.

    ``corpus_file`` is parameterised so :mod:`chunking` can load its own corpus
    through this exact path rather than a second one — the store a benchmark
    measures has to be built the way the shipped default builds it, and two
    builders would eventually disagree about which that is.
    """
    os.environ["DOCIR_HOME"] = str(home)
    os.environ["DOCIR_NO_DAEMON"] = "1"
    settings = Settings.resolve(home=home, use_daemon=False)
    # Mint `random` ids, which is what `docir init` writes and therefore what a
    # real project store costs to read. Left to the bare schema default this
    # measured `adr-0007` and quietly understated every token figure by four
    # characters per id — the benchmark has to price the shipped default.
    settings.ensure_directories()
    settings.schema_path.write_text(render_schema_yaml(id_style="random"), encoding="utf-8")
    container = build_container(settings, background_embeddings=False)
    dispatcher = container.dispatcher

    corpus = yaml.safe_load((BENCH_DIR / corpus_file).read_text(encoding="utf-8"))
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

    all_ids = list(ids.values())
    return {
        "context": _outcome(keys(context), context, all_ids),
        "context --expand 0": _outcome(keys(context_flat), context_flat, all_ids),
        "search": _outcome(keys(search), search, all_ids),
        "query (all skeletons)": _outcome(keys(everything), everything, all_ids),
        "read every body": _outcome(keys(everything), bodies, all_ids),
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


def _collision_probability(bits: int, documents: int) -> float:
    """Birthday-problem odds that two of ``documents`` ids collide."""
    return 1.0 - math.exp(-(documents**2) / (2 * 2**bits))


def _report_id_cost(totals: dict, mean: Callable[[list[float]], float]) -> None:
    """What the random-id entropy costs to read, and what it buys.

    issue-7a271eb0f21a: a random id is ~3x a sequential one and appears in every skeleton
    and every edge of every result, but nothing measured the trade, so 48 bits
    was chosen by default rather than deliberately.
    """
    print(f"\nid cost per result set (random {_RANDOM_BITS}-bit vs sequential):")
    header = (
        f"{'strategy':<22} {'~tokens':>9} {'id chars':>9} "
        f"{'share':>7} {'as adr-0007':>12} {'saving':>8}"
    )
    print(header)
    print("-" * len(header))
    for name, bucket in totals.items():
        chars = mean(bucket["chars"])
        id_chars = mean(bucket["id_chars"])
        seq = mean(bucket["seq_id_chars"])
        share = id_chars / chars if chars else 0.0
        saving = (id_chars - seq) / chars if chars else 0.0
        print(
            f"{name:<22} {chars / CHARS_PER_TOKEN:>9.0f} {id_chars:>9.0f} "
            f"{share:>6.1%} {seq:>12.0f} {saving:>7.1%}"
        )

    print("\nwhat the entropy buys — odds that any two ids collide:")
    header = f"{'suffix':<18} {'bits':>5} " + " ".join(f"{n:>10,}" for n in _CORPUS_SIZES)
    print(header)
    print("-" * len(header))
    for hex_chars in (4, 6, 8, 12, 16):
        bits = hex_chars * 4
        row = " ".join(
            f"{_collision_probability(bits, n):>10.2%}"
            if n**2 / 2**bits > 1e-9
            else f"{'<0.01%':>10}"
            for n in _CORPUS_SIZES
        )
        marker = "  <- current" if hex_chars * 4 == _RANDOM_BITS else ""
        print(f"{f'{hex_chars} hex':<18} {bits:>5} {row}{marker}")
    print(
        "\nRead the two tables together: the collision row is a one-off risk at merge\n"
        "time, the id-cost row is paid on every read. Neither number decides on its\n"
        "own — that is the point of measuring both."
    )


#: A distinctive sentence appended to a prefix to see whether the model still
#: notices it. Nothing about it matters except that it is unlike the prefix.
_CANARY = " ZZQQ a distinctive canary sentence about certificate rotation."


def _embedding_window(embedder: object, sample: str) -> int | None:
    """The prefix length past which ``embedder`` stops reading ``sample``.

    Binary search on real corpus prose rather than repeated filler: the boundary
    is a *token* count, and a degenerate string like "x x x" tokenizes at a rate
    no document ever hits, which would put the answer hundreds of characters out.

    ``None`` means the embedder showed no window at all — the hashing fallback
    reads everything, so coverage is trivially complete and the table says so
    rather than printing a fabricated 100%.
    """

    def truncates(prefix: str) -> bool:
        with_canary = embedder.embed(prefix + _CANARY)
        return embedder.embed(prefix).cosine_similarity(with_canary) >= 0.999999

    if not truncates(sample):
        return None
    low, high = 0, len(sample)
    while low < high - 32:
        middle = (low + high) // 2
        if truncates(sample[:middle]):
            high = middle
        else:
            low = middle
    return high


def _report_coverage(container: object, corpus: list[dict]) -> None:
    """How much of the corpus is actually inside a vector.

    The headline number for chunking, and the one that measures the defect
    rather than a proxy for it: a document longer than the window was not ranked
    badly, it was absent from the semantic index past that point. Recall cannot
    show this on a corpus this size — full-text search covers the whole body and
    pulls the document to rank 1 regardless — so coverage is what is reported,
    and recall is the no-regression gate beside it.
    """
    embedder = container.embedder
    bodies = [f"{doc['title']}\n\n{doc['description']}\n\n{doc.get('body', '')}" for doc in corpus]
    window = _embedding_window(embedder, max(bodies, key=len))

    print("\nsemantic coverage — how much of each body is inside a vector:")
    if window is None:
        print(f"  {embedder.model_id} reads the whole body; coverage is 100% with or")
        print("  without chunking. Re-run with the real model to see the difference.")
        return

    total = sum(len(body) for body in bodies)
    whole_document = sum(min(window, len(body)) for body in bodies)
    chunked = sum(
        sum(min(window, len(text)) for _, _, text in _chunks_of(doc)) or min(window, len(body))
        for doc, body in zip(corpus, bodies, strict=True)
    )
    over = sum(1 for body in bodies if len(body) > window)
    print(f"  measured window: ~{window} chars · {over}/{len(bodies)} documents exceed it")
    print(f"  {'strategy':<26}{'chars embedded':>16}{'coverage':>10}")
    print(f"  {'one vector per document':<26}{whole_document:>16}{whole_document / total:>9.0%}")
    print(
        f"  {'+ one per section':<26}{min(chunked, total):>16}{min(chunked, total) / total:>9.0%}"
    )


def _chunks_of(doc: dict) -> list[tuple[int, str, str]]:
    """The chunks docir would build for a corpus entry, without a store."""
    document = Document(
        id="bench-0000",
        title=doc["title"],
        description=doc["description"],
        type=doc["type"],
        status="draft",
        created=_BENCH_DATE,
        updated=_BENCH_DATE,
        body=doc.get("body", ""),
    )
    return list(document.embedding_chunks())


def main() -> int:
    home = Path(tempfile.mkdtemp(prefix="docir-bench-"))
    try:
        container, ids = build_store(home)
        dispatcher = container.dispatcher
        tasks = yaml.safe_load((BENCH_DIR / "tasks.yaml").read_text(encoding="utf-8"))
        corpus = yaml.safe_load((BENCH_DIR / "corpus.yaml").read_text(encoding="utf-8"))

        # The resolved embedder, not the requested one: the default flipped to
        # fastembed (adr-ab9c454b760c) and this line still announced "deterministic",
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
                    {
                        "recall": [],
                        "precision": [],
                        "rr": [],
                        "chars": [],
                        "id_chars": [],
                        "seq_id_chars": [],
                        "lex": [],
                        "sem": [],
                    },
                )
                bucket["recall"].append(recall)
                bucket["precision"].append(precision)
                bucket["rr"].append(rr)
                bucket["chars"].append(outcome.payload_chars)
                bucket["id_chars"].append(outcome.id_chars)
                bucket["seq_id_chars"].append(outcome.sequential_id_chars)
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

        _report_coverage(container, corpus)
        _report_id_cost(totals, mean)

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
