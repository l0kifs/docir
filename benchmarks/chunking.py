"""Measure whether the splitting rules actually make content reachable.

``run.py`` cannot answer this. Its corpus has no section over the ceiling, none
quoting a fenced heading and no continuation chunk anywhere, so the splitter
never runs and a broken one scores identically (issue-b1a6e57deeec). Two real
chunking defects were fixed on 2026-08-15 and that benchmark moved by nothing,
correctly and uselessly.

It runs a corpus built out of the shapes that fail::

    uv run python benchmarks/chunking.py

and reports two blocks that must be read differently.

**Structure** is the gate: how many real headings name a chunk, how much text no
heading points at, and whether any *phantom* heading appeared. All three are
pure functions of the splitting rules — no model involved — and both defects
fixed on 2026-08-15 moved them.

**Retrieval** is context, not a gate. Which section wins a query is the
embedder's judgement, and `matched expectation` is additionally one annotator's
view of which section answers a question. Tuning prose until those agree would
measure the tuning, so they are reported and not asserted.

A measurement, not a test: it prints numbers and exits 0. Run it before and
after a change to the splitting rules.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run import BENCH_DIR, K, build_store

from docir.modules.documents.domain.services.chunking import split_body


def _shape(
    dispatcher: object, ids: dict[str, str], truth: dict[str, list[str]]
) -> tuple[int, int, int, int]:
    """What the splitter produced. The deterministic half, and the headline.

    Returned rather than only printed, because these are the numbers a
    regression actually moves. Which section *wins* a query is the embedder's
    judgement and drifts with the model; whether a section is addressable at all
    is a pure function of the splitting rules, so that is what this benchmark
    asserts and what both 2026-08-15 defects broke.
    """
    header = f"{'document':<24} {'chunks':>7} {'headless':>9} {'headings addressable':>21}"
    print(header)
    print("-" * len(header))
    addressable = total = headless_total = phantom_total = 0
    for key, doc_id in ids.items():
        body = dispatcher.dispatch("get", {"doc_id": doc_id})["body"]
        chunks = split_body(body)
        named = {chunk.heading for chunk in chunks if chunk.heading}
        headings = truth[key]
        reachable = [h for h in headings if h in named]
        headless = sum(1 for c in chunks if not c.heading and c.ordinal > 0)
        addressable += len(reachable)
        total += len(headings)
        headless_total += headless
        invented = sorted(named - set(headings))
        phantom_total += len(invented)
        lost = [h for h in headings if h not in named]
        note = [f"unreachable: {', '.join(lost)}"] if lost else []
        note += [f"invented: {', '.join(invented)}"] if invented else []
        flag = f"   <- {'; '.join(note)}" if note else ""
        print(
            f"{key:<24} {len(chunks):>7} {headless:>9} "
            f"{f'{len(reachable)}/{len(headings)}':>21}{flag}"
        )
    return addressable, total, headless_total, phantom_total


def main() -> int:
    home = Path(tempfile.mkdtemp(prefix="docir-chunkbench-"))
    try:
        container, ids = build_store(home, "chunking_corpus.yaml")
        dispatcher = container.dispatcher
        tasks = yaml.safe_load((BENCH_DIR / "chunking_tasks.yaml").read_text(encoding="utf-8"))

        print(f"\ncorpus: {len(ids)} documents · tasks: {len(tasks)} · k={K}")
        print(f"embedder: {container.embedder.model_id}\n")
        corpus = yaml.safe_load((BENCH_DIR / "chunking_corpus.yaml").read_text(encoding="utf-8"))
        truth = {doc["key"]: doc["sections"] for doc in corpus}
        addressable, headings, headless, phantom = _shape(dispatcher, ids, truth)

        real_headings = {name for names in truth.values() for name in names}

        inverse = {doc_id: key for key, doc_id in ids.items()}
        header = f"\n{'task':<5} {'found':>6} {'rank':>5} {'section named':<22} {'expected':<22}"
        print(header)
        print("-" * (len(header) - 1))
        found = correct = named = routed_phantom = 0
        for task in tasks:
            rows = dispatcher.dispatch("context", {"task": task["task"], "limit": K})
            hits = [(inverse.get(row["id"]), row.get("matched_section")) for row in rows]
            rank = next(
                (i + 1 for i, (key, _) in enumerate(hits) if key == task["relevant"]),
                0,
            )
            section = next((s for key, s in hits if key == task["relevant"]), None)
            found += rank > 0
            named += section is not None
            correct += section == task["section"]
            routed_phantom += section is not None and section not in real_headings
            print(
                f"{task['id']:<5} {'yes' if rank else 'NO':>6} {rank or '-':>5} "
                f"{section or '—'!s:<22} {task['section']:<22}"
            )

        total = len(tasks)
        print("\nstructure — a pure function of the splitting rules:")
        print(
            f"  headings addressable  {addressable}/{headings}   name a chunk, "
            "so `--section` reaches them"
        )
        print(f"  unaddressable chunks  {headless}       text no heading points at")
        print(
            f"  phantom headings      {phantom + routed_phantom}       "
            "chunk or hit naming a heading no document has"
        )
        print("\nretrieval — the embedder's judgement, reported not asserted:")
        print(f"  recall                {found}/{total}     the document was retrieved at all")
        print(f"  section-routed        {named}/{total}     the hit came through a section vector")
        print(
            f"  matched expectation   {correct}/{total}     "
            "...and it was the heading the task names"
        )
        print(
            "\nRead the two blocks differently. The structural numbers are the gate: a\n"
            "heading that stops being addressable, or a phantom one appearing, means a\n"
            "splitting rule broke, and neither depends on the model. The retrieval\n"
            "numbers move with the embedder — `matched expectation` in particular is one\n"
            "annotator's view of which section answers a question, so a drop there is a\n"
            "prompt to look, not a failure."
        )
        container.close()
        return 0
    finally:
        shutil.rmtree(home, ignore_errors=True)
        os.environ.pop("DOCIR_HOME", None)


if __name__ == "__main__":
    raise SystemExit(main())
