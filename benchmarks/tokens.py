"""What an agent pays for context — by corpus size, and against what it would
otherwise have run.

``run.py`` prices one corpus (26 documents) and compares docir's read paths
against reading every body. Two things were missing, and this is them:

* **The curve.** ``context`` is bounded by ``--limit`` and the alternatives are
  not, so the ratio between them is a function of corpus size. Having measured a
  single point, the README could only say that the 13.7x "grows with corpus
  size ... the shape of the claim rather than a number to quote absolutely".
  Here it is as a line.
* **A baseline an agent would actually run.** Reading every body is an upper
  bound nobody pays. Without docir an agent greps and then opens the handful of
  files that matched, which is much cheaper — and it is the honest thing to be
  compared against, because a comparison against the worst possible alternative
  flatters the tool by construction.

Run::

    uv run python benchmarks/tokens.py
    uv run python benchmarks/tokens.py --sizes 25,100        # quicker

It reuses ``latency.py``'s seeded generator (docir's own store is one size, and
one point cannot draw a curve) and ``run.py``'s renderer, so every payload is
priced exactly as the CLI emits it: trimmed, compact JSON, at ``run.py``'s
~4 chars per token.

Two of the five strategies do not depend on the query — ``query`` returns the
whole store and "read every body" reads it — so they are priced once per size
rather than once per task. ``run.py`` recomputes them per task, which is
harmless at 26 documents and 2 000 ``get`` calls per task at this scale.

This is a measurement, not a test: it prints numbers and always exits 0.
"""

from __future__ import annotations

import argparse
import os
import random
import re
import shutil
import tempfile
from pathlib import Path

from latency import QUERIES, SEED, SIZES, extend_store
from run import CHARS_PER_TOKEN, _emit

from docir.config.settings import Settings
from docir.entry_points.composition import build_container
from docir.modules.documents.api import render_schema_yaml

#: Result-set size every strategy is measured at — `docir context`'s default,
#: and therefore the number of files the grep baseline is allowed to open.
K = 5

#: Words a grep would not be run with. Short tokens are already excluded by the
#: `{4,}` match; these are the long ones that carry no signal, and leaving them
#: in would make the baseline's file list every document in the store.
_STOPWORDS = frozenset(
    {
        "does",
        "from",
        "have",
        "keep",
        "keeps",
        "that",
        "them",
        "then",
        "this",
        "what",
        "when",
        "where",
        "which",
        "with",
        "would",
    }
)


def grep_then_read(docs_root: Path, task: str, limit: int = K) -> int:
    """Characters an agent pays without docir: ``rg -l``, then open what matched.

    Modelled rather than shelled out, and modelled as the *cheapest* sensible
    version of the alternative: ``rg -l`` prints paths and not matching lines,
    and the files opened are the ones with the most term hits — a ranking a real
    agent does not have. Anything it does beyond this (a second grep with other
    terms, a sixth file, re-reading after a compaction) costs more. So this is a
    floor for the without-docir path rather than an estimate of the average, and
    the multiple docir shows against it is a floor too.
    """
    terms = {word for word in re.findall(r"[a-z]{4,}", task.lower()) if word not in _STOPWORDS}
    hits: list[tuple[int, Path, str]] = []
    for path in sorted(docs_root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        score = sum(lowered.count(term) for term in terms)
        if score:
            hits.append((score, path, text))
    listing = "".join(f"{path.relative_to(docs_root)}\n" for _, path, _ in hits)
    opened = sorted(hits, key=lambda hit: -hit[0])[:limit]
    return len(listing) + sum(len(text) for _, _, text in opened)


def per_query_costs(dispatcher: object, docs_root: Path, task: str) -> dict[str, int]:
    """Payload characters for the strategies that depend on what was asked."""
    context = dispatcher.dispatch("context", {"task": task, "limit": K})
    search = dispatcher.dispatch("search", {"text": task, "limit": K})
    return {
        "context": len(_emit(context)),
        "search": len(_emit(search)),
        "grep -l + read 5": grep_then_read(docs_root, task),
    }


def whole_store_costs(dispatcher: object, ids: list[str]) -> dict[str, int]:
    """Payload characters for the strategies that ignore the query."""
    skeletons = dispatcher.dispatch("query", {"limit": len(ids)})
    bodies = [dispatcher.dispatch("get", {"doc_id": doc_id}) for doc_id in ids]
    return {
        "query (all skeletons)": len(_emit(skeletons)),
        "read every body": len(_emit(bodies)),
    }


#: Print order: docir's read paths, then the two ways of doing without it.
_ORDER = (
    "context",
    "search",
    "query (all skeletons)",
    "grep -l + read 5",
    "read every body",
)


def _tokens(chars: float) -> float:
    return chars / CHARS_PER_TOKEN


def _report_size(size: int, costs: dict[str, float]) -> None:
    print(f"\ncorpus: {size} documents")
    header = f"{'strategy':<24}{'~tokens':>10}{'vs context':>12}"
    print(header)
    print("-" * len(header))
    base = costs["context"] or 1.0
    for name in _ORDER:
        print(f"{name:<24}{_tokens(costs[name]):>10,.0f}{costs[name] / base:>11.1f}x")


def _report_curve(sizes: list[int], collected: dict[int, dict[str, float]]) -> None:
    print("\n~tokens by corpus size")
    header = f"{'strategy':<24}" + "".join(f"{size:>10}" for size in sizes)
    print(header)
    print("-" * len(header))
    for name in _ORDER:
        row = "".join(f"{_tokens(collected[size][name]):>10,.0f}" for size in sizes)
        print(f"{name:<24}{row}")
    print("\nthe same rows as a multiple of `context`")
    print(header)
    print("-" * len(header))
    for name in _ORDER:
        row = "".join(
            f"{collected[size][name] / (collected[size]['context'] or 1):>9.1f}x" for size in sizes
        )
        print(f"{name:<24}{row}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Token cost by corpus size and read method.")
    parser.add_argument(
        "--sizes",
        default=",".join(str(size) for size in SIZES),
        help="Comma-separated corpus sizes, smallest first (default: 25,100,500,2000).",
    )
    args = parser.parse_args()
    sizes = sorted({int(size) for size in args.sizes.split(",")})

    home = Path(tempfile.mkdtemp(prefix="docir-tokens-"))
    os.environ["DOCIR_HOME"] = str(home)
    os.environ["DOCIR_NO_DAEMON"] = "1"
    settings = Settings.resolve(home=home, use_daemon=False)
    settings.ensure_directories()
    # The shipped default: `docir init` writes random ids, and they are ~3x the
    # length of a sequential one in every skeleton and every edge (run.py §3b).
    settings.schema_path.write_text(render_schema_yaml(id_style="random"), encoding="utf-8")
    container = build_container(settings, background_embeddings=False)
    rng = random.Random(SEED)
    ids: list[str] = []
    collected: dict[int, dict[str, float]] = {}

    print(f"embedder: {container.embedder.model_id}")
    print(f"tasks: {len(QUERIES)} · k={K} · ~{CHARS_PER_TOKEN} chars/token")
    try:
        for size in sizes:
            seconds = extend_store(container.dispatcher, ids, size, rng)
            print(f"\nbuilt {size} documents (+{seconds:.1f}s)")
            fixed = whole_store_costs(container.dispatcher, ids)
            totals: dict[str, float] = dict.fromkeys(_ORDER, 0.0)
            for task in QUERIES:
                for name, chars in per_query_costs(
                    container.dispatcher, settings.docs_root, task
                ).items():
                    totals[name] += chars / len(QUERIES)
            totals.update(fixed)
            collected[size] = totals
            _report_size(size, totals)
        _report_curve(sizes, collected)
        print(
            "\n`context` is flat because `--limit` bounds it; everything else grows with\n"
            "the corpus. The grep baseline grows only in its file list — it still opens\n"
            f"{K} documents — which is why it is the number to quote, not `read every body`."
        )
    finally:
        container.close()
        shutil.rmtree(home, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
