"""Recall, precision and reciprocal rank for one retrieval result.

Pure arithmetic over two lists of ids, so the numbers ``docir bench`` reports
can be unit-tested without a store, a model or a corpus. The same three
measures ``benchmarks/run.py`` prints, moved into the package so an adopter can
run them against their own documents rather than inherit docir's as a claim
(issue-c6d184704682).

Two conventions worth stating because they decide what a number means. Recall is
over the *distinct* relevant ids, so a task naming one document twice cannot
score 2.0. Reciprocal rank is of the first relevant hit and is 0.0 when none
appears — not undefined, because a task that retrieves nothing has to drag the
mean down rather than vanish from it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TaskScore:
    """How one task scored under one retrieval strategy."""

    #: Share of the distinct relevant ids that appeared, in ``[0.0, 1.0]``.
    recall: float
    #: Share of the returned ids that were relevant, in ``[0.0, 1.0]``.
    precision: float
    #: ``1 / rank`` of the first relevant hit, or ``0.0`` if none appeared.
    reciprocal_rank: float


def score_task(retrieved: Sequence[str], relevant: Sequence[str]) -> TaskScore:
    """Score one ranked list of ids against the ids a reader needed."""
    wanted = set(relevant)
    if not wanted:
        return TaskScore(0.0, 0.0, 0.0)
    hits = [doc_id for doc_id in retrieved if doc_id in wanted]
    recall = len(set(hits)) / len(wanted)
    precision = len(hits) / len(retrieved) if retrieved else 0.0
    rank = next((i + 1 for i, doc_id in enumerate(retrieved) if doc_id in wanted), 0)
    return TaskScore(recall, precision, 1 / rank if rank else 0.0)


def mean(values: Sequence[float]) -> float:
    """Arithmetic mean, ``0.0`` for an empty sequence.

    An empty mean is 0.0 rather than an error because a strategy can legitimately
    score nothing — every task dropped for naming only missing documents — and the
    report says how many tasks it covered beside every figure.
    """
    return sum(values) / len(values) if values else 0.0
