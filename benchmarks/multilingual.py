"""Does a multilingual model actually help a non-English corpus?

``run.py`` answers what an embedder costs on docir's English fixture, and that
is how the multilingual entries in the catalogue were priced: they lose ranking
and buy nothing there, which is why the default did not move. It cannot answer
the question the setting exists for, because its corpus is in English —
the wrong-instrument trap issue-b1a6e57deeec named, one language over.

So this runs the same 20 tasks and the same 26 documents in Russian
(``multilingual_corpus.yaml``, a translation with identical keys, edges and
judgments — the English run is the control) against both models, and prints the
four cells together. Read the **paraphrased** column: a lexical task shares
vocabulary with the documents, so FTS5 carries it in either language and the
embedder is not what is being measured.

Run::

    uv run python benchmarks/multilingual.py

Each cell builds its own store and embeds 26 documents, so the first run
downloads ~220 MB for the multilingual model and takes a few minutes.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run import BENCH_DIR, K, build_store, score, strategies

from docir.entry_points import composition
from docir.platform.embedding.catalogue import DEFAULT_EMBED_MODEL
from docir.platform.embedding.fastembed import FastEmbedEmbedder

MULTILINGUAL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

#: ``(label, corpus file, tasks file)`` — the same fixture in two languages.
LANGUAGES = (
    ("English", "corpus.yaml", "tasks.yaml"),
    ("Russian", "multilingual_corpus.yaml", "multilingual_tasks.yaml"),
)

#: ``(label, model)``. The default is English-only by construction; the
#: alternative is the drop-in — same 384 width, ~220 MB instead of ~67 MB.
MODELS = (
    ("bge-small-en (default)", DEFAULT_EMBED_MODEL),
    ("multilingual-MiniLM", MULTILINGUAL),
)


def measure(corpus_file: str, tasks_file: str, model: str) -> dict[str, float]:
    """Run every task through ``context`` and report the means for one cell."""
    original = composition._build_embedder
    composition._build_embedder = lambda _name=None: FastEmbedEmbedder(model_name=model)
    home = Path(tempfile.mkdtemp(prefix="docir-multilingual-"))
    try:
        container, ids = build_store(home, corpus_file)
        tasks = yaml.safe_load((BENCH_DIR / tasks_file).read_text(encoding="utf-8"))
        recalls, precisions, rrs, lex, sem = [], [], [], [], []
        for task in tasks:
            outcome = strategies(container.dispatcher, task["task"], ids)["context"]
            recall, precision, rr = score(outcome.retrieved, task["relevant"])
            recalls.append(recall)
            precisions.append(precision)
            rrs.append(rr)
            (lex if task["lexical"] else sem).append(recall)
        container.close()
    finally:
        composition._build_embedder = original
        shutil.rmtree(home, ignore_errors=True)

    def mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    return {
        "recall": mean(recalls),
        "precision": mean(precisions),
        "mrr": mean(rrs),
        "lexical": mean(lex),
        "paraphrased": mean(sem),
    }


def main() -> int:
    header = (
        f"{'corpus':<9} {'model':<24} {'recall@' + str(K):>9} "
        f"{'prec':>6} {'MRR':>6} {'same words':>11} {'paraphrased':>12}"
    )
    print(f"\nsame 26 documents and 20 tasks in both languages · k={K}\n")
    print(header)
    print("-" * len(header))
    results: dict[tuple[str, str], dict[str, float]] = {}
    for language, corpus_file, tasks_file in LANGUAGES:
        for label, model in MODELS:
            row = measure(corpus_file, tasks_file, model)
            results[(language, label)] = row
            print(
                f"{language:<9} {label:<24} {row['recall']:>9.2f} {row['precision']:>6.2f} "
                f"{row['mrr']:>6.2f} {row['lexical']:>11.2f} {row['paraphrased']:>12.2f}"
            )

    print(
        "\nThe paraphrased column is the one that decides it: a lexical task shares\n"
        "vocabulary with the documents, so FTS5 carries it in either language and the\n"
        "embedder is not what is being measured."
    )
    for language, _corpus, _tasks in LANGUAGES:
        default = results[(language, MODELS[0][0])]["paraphrased"]
        other = results[(language, MODELS[1][0])]["paraphrased"]
        verdict = "helps" if other > default else "does not help" if other < default else "ties"
        print(f"  {language}: multilingual {verdict} ({default:.2f} -> {other:.2f} paraphrased)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
