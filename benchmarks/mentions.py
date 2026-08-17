"""Does following prose citations in ``docir context`` help, or dilute?

``run.py`` cannot answer this. It allocates ids at load time, so no body in its
corpus can name one and the mention graph is empty for the whole run — a broken
expansion and a working one score identically there. That is the same
wrong-instrument trap ``chunking.py`` was built for (issue-b1a6e57deeec).

So this builds a corpus whose documents cite each other the way real ones do:
bodies carry ``{key}`` placeholders, substituted with the real allocated id
after the first pass, because a real author writes the id they can see.

Run::

    uv run python benchmarks/mentions.py                   # the real model
    DOCIR_EMBEDDER=deterministic uv run python benchmarks/mentions.py

A measurement, not a test: it prints numbers and exits 0.

**Read the fixture before believing the numbers.** A benchmark written to decide
whether a feature helps can be rigged by choosing only the tasks it wins, so
``mentions_tasks.yaml`` records how each relevant document is reachable, and a
third of the tasks are ones where expansion has nothing to gain and precision to
lose. The mix is printed below the headline so it can be checked rather than
trusted.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml

from docir.config.settings import Settings
from docir.entry_points.composition import build_container
from docir.modules.documents.api import render_schema_yaml

BENCH_DIR = Path(__file__).resolve().parent

#: Result-set size every strategy is measured at — `docir context`'s default.
K = 5

#: Neighbour budgets to sweep. 2 is the shipped default, and it had never been
#: measured either — it was chosen before there was an instrument that could
#: see graph expansion at all.
EXPAND_VALUES = (0, 1, 2, 3)

_PLACEHOLDER = re.compile(r"\{([a-z0-9-]+)\}")

#: Merged on top of the profiles. Kept minimal — one live status, no cadence —
#: because nothing here measures the type system.
_INLINE_TYPES = """
types:
  reference:
    prefix: ref
    level: 1
    required: []
    default_status: active
    statuses:
      active: [retired]
      retired: []
"""


@dataclass
class Scores:
    recall: float
    precision: float
    mrr: float


def _load(name: str) -> list[dict]:
    return yaml.safe_load((BENCH_DIR / name).read_text(encoding="utf-8"))


def build_store(home: Path, *, expand_mentions: bool) -> tuple[object, dict[str, str]]:
    """Load the corpus into a fresh store, resolving prose citations.

    Three passes, and the third is the one this file exists for: bodies are
    rewritten with the real ids once every document has one. Writing them
    through ``update`` rather than poking the files is deliberate — the mention
    graph is derived on the write path, so a fixture that bypassed the CLI would
    measure a graph the product never builds.
    """
    os.environ["DOCIR_HOME"] = str(home)
    os.environ["DOCIR_NO_DAEMON"] = "1"
    settings = Settings.resolve(home=home, use_daemon=False)
    settings.ensure_directories()
    # `reference` is not in any bundled profile, and the corpus needs one: a
    # capability matrix cited by three other documents is exactly the shape of
    # thing people link to in passing. Declaring it inline on top of the
    # profiles is the supported way to add a type (adr-2a3f625bb2f8), so the
    # fixture also exercises the merge rather than avoiding it.
    # Sequential ids, unlike `run.py`, which mints random ones to price what
    # they cost to read. Nothing here measures tokens, and random ids made the
    # baseline move between runs: ranking ties break on id order, so the same
    # code scored 0.79 and 0.81 on consecutive runs. A benchmark whose baseline
    # wanders cannot settle a small difference.
    settings.schema_path.write_text(
        render_schema_yaml(profiles=["software", "ops"], id_style="sequential") + _INLINE_TYPES,
        encoding="utf-8",
    )
    container = build_container(
        settings, background_embeddings=False, expand_mentions=expand_mentions
    )
    dispatcher = container.dispatcher

    corpus = _load("mentions_corpus.yaml")
    ids: dict[str, str] = {}
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

    for doc in corpus:
        body = doc.get("body", "")
        if not _PLACEHOLDER.search(body):
            continue
        dispatcher.dispatch(
            "update",
            {
                "doc_id": ids[doc["key"]],
                "replace_body": _PLACEHOLDER.sub(lambda m: ids[m.group(1)], body),
                "force": True,
            },
        )

    dispatcher.dispatch("embed_flush", {})
    return container, ids


def _edge(ids: dict[str, str], ref: str) -> str:
    key, _, kind = ref.partition(":")
    return f"{ids[key]}:{kind}" if kind else ids[key]


def _edges(corpus: list[dict]) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """The fixture's two graphs, read out of the corpus file.

    Derived rather than declared. The first version of this benchmark grouped
    tasks by a hand-written ``reachable_by`` list, and the labels were wrong in
    the direction that flattered the feature: two documents marked "authored
    edge, no prose hop needed" cite each other in prose *as well*, and the win
    on them came from the mention graph. A fixture author cannot be trusted to
    label the fixture, so the grouping is computed from it.
    """
    authored = {
        (doc["key"], ref.partition(":")[0]) for doc in corpus for ref in doc.get("related") or []
    }
    prose = {
        (doc["key"], key) for doc in corpus for key in _PLACEHOLDER.findall(doc.get("body", ""))
    }
    return authored, prose


def _prose_only_tasks(corpus: list[dict], tasks: list[dict]) -> set[str]:
    """Tasks where two relevant documents are connected by prose and nothing else.

    ``related`` is directed and expansion follows successors backwards only, so
    an authored edge in the wrong direction does not make its target reachable.
    A prose citation makes it reachable both ways, which is most of what this
    measures.
    """
    authored, prose = _edges(corpus)
    chosen: set[str] = set()
    for task in tasks:
        relevant = set(task["relevant"])
        pairs = {(a, b) for a in relevant for b in relevant if a != b}
        if any(pair in prose and pair not in authored for pair in pairs):
            chosen.add(task["id"])
    return chosen


def score(retrieved: list[str], relevant: list[str]) -> Scores:
    if not relevant:
        return Scores(0.0, 0.0, 0.0)
    hits = [key for key in retrieved if key in relevant]
    rank = next((i + 1 for i, key in enumerate(retrieved) if key in relevant), 0)
    return Scores(
        recall=len(set(hits)) / len(set(relevant)),
        precision=len(hits) / len(retrieved) if retrieved else 0.0,
        mrr=1 / rank if rank else 0.0,
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _run(expand_mentions: bool, tasks: list[dict]) -> tuple[dict[int, dict[str, Scores]], int]:
    """Score every task at every neighbour budget, from one store.

    ``expand`` is a per-query argument, so the sweep costs two store builds
    rather than eight — worth doing deliberately, because each build embeds the
    whole corpus and the real model is most of the runtime.
    """
    home = Path(tempfile.mkdtemp(prefix="docir-bench-mentions-"))
    try:
        container, ids = build_store(home, expand_mentions=expand_mentions)
        try:
            dispatcher = container.dispatcher
            inverse = {doc_id: key for key, doc_id in ids.items()}
            edges = sum(
                len(dispatcher.dispatch("get", {"doc_id": doc_id}).get("mentions") or ())
                for doc_id in ids.values()
            )
            by_expand: dict[int, dict[str, Scores]] = {}
            for expand in EXPAND_VALUES:
                per_task: dict[str, Scores] = {}
                for task in tasks:
                    rows = dispatcher.dispatch(
                        "context", {"task": task["task"], "limit": K, "expand": expand}
                    )
                    keys = [inverse[row["id"]] for row in rows if row["id"] in inverse]
                    per_task[task["id"]] = score(keys, task["relevant"])
                by_expand[expand] = per_task
            return by_expand, edges
        finally:
            container.close()
    finally:
        shutil.rmtree(home, ignore_errors=True)


def _aggregate(per_task: dict[str, Scores], ids: list[str]) -> Scores:
    chosen = [per_task[i] for i in ids]
    return Scores(
        _mean([s.recall for s in chosen]),
        _mean([s.precision for s in chosen]),
        _mean([s.mrr for s in chosen]),
    )


def main() -> None:
    tasks = _load("mentions_tasks.yaml")
    by_id = {task["id"]: task for task in tasks}
    all_ids = [task["id"] for task in tasks]
    corpus = _load("mentions_corpus.yaml")
    # Tasks whose answer needs a document connected only by prose. Derived from
    # the corpus, never from a label: see `_edges`.
    prose_only = _prose_only_tasks(corpus, tasks)
    mention_ids = [i for i in all_ids if i in prose_only]
    other_ids = [i for i in all_ids if i not in prose_only]

    baseline, edges = _run(False, tasks)
    expanded, _ = _run(True, tasks)

    embedder = os.environ.get("DOCIR_EMBEDDER") or "fastembed (default)"
    print(f"\ncorpus: {len(corpus)} documents, {edges} resolved mentions")
    print(f"tasks:  {len(tasks)} ({len(mention_ids)} connected only by prose)")
    print(f"embedder: {embedder}   k={K}\n")

    header = f"{'expand':>6}  {'edges followed':<20} {'recall@5':>9} {'precision':>10} {'MRR':>6}"
    print(header)
    print("-" * len(header))
    for expand in EXPAND_VALUES:
        for name, table in (("authored only", baseline), ("+ mentions", expanded)):
            agg = _aggregate(table[expand], all_ids)
            if expand == 0 and name == "+ mentions":
                name += "  (no budget: identical)"
            print(
                f"{expand:>6}  {name:<20} {agg.recall:>9.2f} {agg.precision:>10.2f} {agg.mrr:>6.2f}"
            )
        print()

    print("split by whether the task needs a prose-only hop, at the shipped expand=2:")
    header2 = f"{'task group':<26} {'edges':<16} {'recall@5':>9} {'precision':>10} {'MRR':>6}"
    print(header2)
    print("-" * len(header2))
    for label, subset in (("connected only by prose", mention_ids), ("not", other_ids)):
        for name, table in (("authored only", baseline), ("+ mentions", expanded)):
            agg = _aggregate(table[2], subset)
            print(
                f"{label + f' ({len(subset)})':<26} {name:<16} {agg.recall:>9.2f} "
                f"{agg.precision:>10.2f} {agg.mrr:>6.2f}"
            )

    print("\nper-task movement at expand=2 (authored -> + mentions), changes only:")
    moved = 0
    for task_id in all_ids:
        before_s, after_s = baseline[2][task_id], expanded[2][task_id]
        deltas = [
            (name, getattr(before_s, name), getattr(after_s, name))
            for name in ("recall", "precision")
            if abs(getattr(before_s, name) - getattr(after_s, name)) > 1e-9
        ]
        if not deltas:
            continue
        moved += 1
        group = "prose-linked" if task_id in prose_only else "not prose-linked"
        shown = "  ".join(
            f"{'+' if after > before else '-'}{name} {before:.2f}->{after:.2f}"
            for name, before, after in deltas
        )
        print(f"  {task_id}  {shown:<44} ({group}) {by_id[task_id]['task']}")
    if not moved:
        print("  (none — expansion changed nothing)")

    authored, prose = _edges(corpus)
    print(
        f"\nfixture shape (derived): {len(authored)} authored edges, {len(prose)} prose "
        f"citations, {len(prose - authored)} of them with no authored edge"
    )
    kinds = Counter(doc["type"] for doc in corpus)
    print(f"types: {dict(kinds)}")
    print(
        "A gain in the not-prose-linked group is the fixture leaking or the grouping\n"
        "being too narrow — read the per-task lines before concluding either."
    )


if __name__ == "__main__":
    main()
