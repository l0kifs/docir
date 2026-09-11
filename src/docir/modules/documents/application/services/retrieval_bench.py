"""Scoring a store's own read path against judged tasks (``docir bench``).

Lives beside :class:`DocumentService` rather than inside it: a benchmark
*measures* the aggregate's read paths and owns none of them, so a change to how
retrieval quality is scored has no business editing the class that writes
documents. It takes the two read paths it compares as callables — that is the
whole of its dependency on the service, and naming them says which two.
"""

from __future__ import annotations

from collections.abc import Callable

from docir.modules.documents.application.dto import (
    BenchRequest,
    BenchResult,
    BenchTask,
    ContextRequest,
    DocumentSummary,
    SearchRequest,
    StrategyScore,
)
from docir.modules.documents.domain.services.retrieval_scoring import mean, score_task
from docir.platform.persistence.unit_of_work import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]
ReadPath = Callable[[ContextRequest], list[DocumentSummary]]
SearchPath = Callable[[SearchRequest], list[DocumentSummary]]


class RetrievalBench:
    """Scores the three retrieval strategies against a judged fixture."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        context: ReadPath,
        search: SearchPath,
    ) -> None:
        self._uow_factory = uow_factory
        self._context = context
        self._search = search

    def run(self, request: BenchRequest) -> BenchResult:
        """Score this store's read path against judged tasks.

        The instrument ``benchmarks/`` was, made portable: the numbers docir
        publishes are measured on docir's corpus, and an adopter had no way to
        find out whether their own behaves the same way (issue-c6d184704682).

        Three strategies, chosen because together they say *which part* of
        retrieval is working. ``context`` is the shipped default. ``context
        --expand 0`` removes graph expansion, which lifts every embedder and
        hides the difference between them (ref-e7534f1c812d) — the pair is what
        isolates the semantic signal. ``search`` is full-text alone, the floor
        anything semantic has to beat.

        Ids the corpus no longer carries are **reported, not dropped quietly**:
        removing one shrinks recall's denominator and raises the score for the
        wrong reason. A task left with no resolvable ids is dropped whole and
        named, because scoring it would count a certain miss against retrieval
        that never had anything to find.

        The caller validates ``limit`` before constructing this, where the other
        three read paths validate theirs.
        """
        with self._uow_factory() as uow:
            known = {
                doc_id
                for doc_id in {ref for task in request.tasks for ref in task.relevant}
                if uow.documents.exists(doc_id)
            }
        unresolved = sorted({ref for task in request.tasks for ref in task.relevant} - known)

        judged: list[tuple[BenchTask, tuple[str, ...]]] = []
        dropped: list[str] = []
        for task in request.tasks:
            keep = tuple(ref for ref in task.relevant if ref in known)
            if keep:
                judged.append((task, keep))
            else:
                dropped.append(task.id)

        runs: dict[str, Callable[[str], list[DocumentSummary]]] = {
            "context": lambda text: self._context(
                ContextRequest(task=text, limit=request.limit, expand=request.expand)
            ),
            "context --expand 0": lambda text: self._context(
                ContextRequest(task=text, limit=request.limit, expand=0)
            ),
            "search": lambda text: self._search(SearchRequest(text=text, limit=request.limit)),
        }

        strategies: list[StrategyScore] = []
        for name, run in runs.items():
            recalls: list[float] = []
            precisions: list[float] = []
            rrs: list[float] = []
            for task, relevant in judged:
                retrieved = [summary.id for summary in run(task.task)]
                scored = score_task(retrieved, relevant)
                recalls.append(scored.recall)
                precisions.append(scored.precision)
                rrs.append(scored.reciprocal_rank)
            strategies.append(
                StrategyScore(
                    name=name,
                    recall=mean(recalls),
                    precision=mean(precisions),
                    mrr=mean(rrs),
                    tasks=len(judged),
                )
            )

        return BenchResult(
            strategies=tuple(strategies),
            limit=request.limit,
            expand=request.expand,
            scored=len(judged),
            unresolved=tuple(unresolved),
            dropped=tuple(dropped),
        )
