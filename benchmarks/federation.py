"""What splitting a corpus across stores costs, and which merge to pay it with.

adr-fb938175f72a orders a federated read by ``similarity`` — the raw cosine,
the one number that means the same thing in every store — and records the
alternative it did not take: re-fusing every store's raw rankings with one RRF
pass. It also says that alternative may supersede it *on evidence*. This is the
evidence.

Run::

    uv run python benchmarks/federation.py

It builds three stores from ``corpus.yaml``: one holding everything (the
ceiling a single store reaches) and two holding half each, and then asks every
task in ``tasks.yaml`` of all three, merging the split pair two ways.

**Cross-store RRF is round-robin, and that is not a simplification.** RRF fuses
rankings by summing ``1/(k + rank)`` across the lists a document appears in.
Each document lives in exactly one store, so every document appears in exactly
one list and the sum has one term — the ordering it produces is by rank
position alone, which is interleaving. Any cross-store re-fusion of the lists
the stores *return* is this. (Re-fusing their raw lexical and vector rankings is
a different thing, and needs the fan-out to live inside ``indexing``; that is
the change this benchmark exists to justify or not.)

A second cost is measured because it is unavoidable rather than chosen: a
``related`` edge cannot cross stores (Tier 0 validates the target locally), so
splitting the corpus drops every edge whose ends land in different halves, and
graph expansion loses them. The single-store row is the ceiling that loss is
measured against.

This is a measurement, not a test: it prints numbers and always exits 0.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import yaml
from run import BENCH_DIR, K, _edge, score

from docir.config.settings import Settings
from docir.entry_points.composition import build_container
from docir.entry_points.federation import merge_ranked
from docir.modules.documents.api import render_schema_yaml


#: How the corpus is cut in two. Alternating by position rather than by type:
#: splitting on type would put every decision in one store and every issue in
#: the other, which is a tidier corpus than any real pair of repositories and
#: would flatter both merges by making the right store obvious.
def _halves(corpus: list[dict]) -> tuple[list[dict], list[dict]]:
    return corpus[0::2], corpus[1::2]


def _build(home: Path, docs: list[dict]) -> tuple[object, dict[str, str]]:
    """Load a subset into a fresh store, keeping only the edges it can hold."""
    settings = Settings.resolve(home=home, use_daemon=False)
    settings.ensure_directories()
    settings.schema_path.write_text(render_schema_yaml(id_style="random"), encoding="utf-8")
    container = build_container(settings, background_embeddings=False)
    dispatcher = container.dispatcher

    ids: dict[str, str] = {}
    for doc in docs:
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
    for doc in docs:
        # An edge whose target landed in the other half is dropped, not an
        # error: that is exactly what a split costs, and it is why the
        # single-store row is reported beside the federated ones.
        edges = [ref for ref in doc.get("related", []) if ref.partition(":")[0] in ids]
        if edges:
            dispatcher.dispatch(
                "update",
                {"doc_id": ids[doc["key"]], "set_related": [_edge(ids, ref) for ref in edges]},
            )
    for doc in docs:
        for status in doc.get("status_path", []):
            dispatcher.dispatch("update", {"doc_id": ids[doc["key"]], "status": status})
    dispatcher.dispatch("embed_flush", {})
    return container, ids


def _interleave_by_rank(ranked: list[list[dict]]) -> list[dict]:
    """What a cross-store RRF over the returned lists reduces to.

    One document, one list, one term in the sum — so the fused order is the
    order of ``1/(k + rank)``, which is round-robin across the lists.
    """
    merged: list[dict] = []
    for position in range(max((len(rows) for rows in ranked), default=0)):
        for rows in ranked:
            if position < len(rows):
                merged.append(rows[position])
    return merged


def _keys(rows: list[dict], inverse: dict[str, str]) -> list[str]:
    return [inverse[row["id"]] for row in rows if row["id"] in inverse]


def main() -> int:
    os.environ["DOCIR_NO_DAEMON"] = "1"
    root = Path(tempfile.mkdtemp(prefix="docir-fed-bench-"))
    corpus = yaml.safe_load((BENCH_DIR / "corpus.yaml").read_text(encoding="utf-8"))
    tasks = yaml.safe_load((BENCH_DIR / "tasks.yaml").read_text(encoding="utf-8"))
    left, right = _halves(corpus)

    containers = []
    try:
        whole, whole_ids = _build(root / "whole", corpus)
        a, a_ids = _build(root / "a", left)
        b, b_ids = _build(root / "b", right)
        containers = [whole, a, b]

        # Keys are the corpus's own, so the three stores are comparable even
        # though every store minted its own random ids.
        inverse_whole = {doc_id: key for key, doc_id in whole_ids.items()}
        inverse_split = {doc_id: key for key, doc_id in (*a_ids.items(), *b_ids.items())}

        kept = sum(
            1
            for doc in corpus
            for ref in doc.get("related", [])
            if (doc["key"] in a_ids) == (ref.partition(":")[0] in a_ids)
        )
        edges = sum(len(doc.get("related", [])) for doc in corpus)
        print(f"\ncorpus: {len(corpus)} documents · split {len(left)}/{len(right)} · k={K}")
        print(f"embedder: {whole.embedder.model_id}")
        print(f"edges: {kept}/{edges} survive the split ({edges - kept} cross it)\n")

        totals: dict[str, dict[str, list[float]]] = {}
        for task in tasks:
            payload = {"task": task["task"], "limit": K}
            one = whole.dispatcher.dispatch("context", payload)
            rows_a = a.dispatcher.dispatch("context", payload)
            rows_b = b.dispatcher.dispatch("context", payload)

            runs = {
                "single store (ceiling)": _keys(one, inverse_whole),
                "split · merge on similarity": _keys(
                    merge_ranked([rows_a, rows_b])[:K], inverse_split
                ),
                "split · merge on rank (RRF)": _keys(
                    _interleave_by_rank([rows_a, rows_b])[:K], inverse_split
                ),
            }
            for name, retrieved in runs.items():
                recall, _, rr = score(retrieved, task["relevant"])
                bucket = totals.setdefault(name, {"recall": [], "rr": []})
                bucket["recall"].append(recall)
                bucket["rr"].append(rr)

        width = max(len(name) for name in totals)
        print(f"{'strategy':<{width}}  {'recall@' + str(K):>9}  {'MRR':>6}")
        print("-" * (width + 19))
        for name, bucket in totals.items():
            recall = sum(bucket["recall"]) / len(bucket["recall"])
            mrr = sum(bucket["rr"]) / len(bucket["rr"])
            print(f"{name:<{width}}  {recall:>9.2f}  {mrr:>6.2f}")
        print(
            "\nrecall is over the whole corpus either way: a split that hides a "
            "relevant\ndocument in the store that was out-ranked shows up here as "
            "lost recall.\n"
        )
    finally:
        for container in containers:
            container.close()
        shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
